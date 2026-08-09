"""Amazon Braket backend and one-task job wrappers."""

from __future__ import annotations

import hashlib
import json
import queue
import threading
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from typing import Any

from qplanck.ir import Operation
from qplanck.pulse import CalibrationKey
from qplanck.results import RunResult
from qplanck.runtime import (
    BackendError,
    CalibratedCircuit,
    Diagnostic,
    ExecutionOptions,
    ExperimentManifest,
    ExternalArtifactRef,
    JobCancelledError,
    JobFailedError,
    JobStatus,
    JobTimeoutError,
)
from qplanck.targets import LimitKind, Target

from .artifacts import redacted_arn_identity
from .channel_map import BraketChannelMap
from .device import BraketPulseDevice
from .errors import BraketCapabilityError, BraketSubmissionError
from .lowering import lower_pulse_program
from .snapshot import BraketPulseSnapshot


@dataclass(frozen=True)
class _BraketCircuitSDK:
    circuit: type[Any]
    gate: Any
    qubit_set: type[Any]


def _load_circuit_sdk() -> _BraketCircuitSDK:
    try:
        from braket.circuits import Circuit, Gate, QubitSet
    except ImportError as exc:  # pragma: no cover - packaging dependency provides it
        raise BraketCapabilityError(
            "amazon-braket-sdk is required for Braket circuit execution."
        ) from exc
    return _BraketCircuitSDK(Circuit, Gate, QubitSet)


def _adapter_version() -> str:
    try:
        return importlib_metadata.version("qplanck-braket")
    except importlib_metadata.PackageNotFoundError:
        return "development"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _hash_json(value: object) -> str:
    payload = json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


_GATE_TYPES = {
    "h": "H",
    "x": "X",
    "y": "Y",
    "z": "Z",
    "s": "S",
    "t": "T",
    "rx": "Rx",
    "ry": "Ry",
    "rz": "Rz",
    "cx": "CNot",
    "cz": "CZ",
    "swap": "Swap",
}


def _gate_for_calibration(key: CalibrationKey, sdk: _BraketCircuitSDK) -> Any:
    class_name = _GATE_TYPES.get(key.gate)
    if class_name is None:
        raise BraketCapabilityError(
            f"QPlanck calibration gate {key.gate!r} has no Braket gate mapping."
        )
    constructor = getattr(sdk.gate, class_name, None)
    if not callable(constructor):
        raise BraketCapabilityError(f"Pinned Braket SDK does not expose Gate.{class_name}.")
    expected_parameters = 1 if key.gate in {"rx", "ry", "rz"} else 0
    if len(key.parameters) != expected_parameters:
        raise BraketCapabilityError(
            f"Calibration {key.gate!r} requires {expected_parameters} parameter(s)."
        )
    return constructor(*key.parameters)


def _append_operation(circuit: Any, operation: Any) -> None:
    method_name = "cnot" if operation.name == "cx" else operation.name
    method = getattr(circuit, method_name, None)
    if not callable(method):
        raise BraketCapabilityError(
            f"Pinned Braket SDK circuit has no mapping for {operation.name!r}."
        )
    method(*operation.qubits, *operation.params)


def _build_provider_payload(
    program: CalibratedCircuit,
    *,
    channel_map: BraketChannelMap,
    snapshot: BraketPulseSnapshot,
    frames: Mapping[str, Any],
    sdk: _BraketCircuitSDK,
) -> tuple[Any, dict[tuple[Any, Any], Any]]:
    circuit = sdk.circuit()
    compiled_ir = program.compiled_circuit.ir
    for operation in compiled_ir.operations:
        _append_operation(circuit, operation)
    if compiled_ir.measurements:
        measured_qubits = [
            measurement.qubit
            for measurement in sorted(compiled_ir.measurements, key=lambda item: item.cbit)
        ]
        measure = getattr(circuit, "measure", None)
        if not callable(measure):
            raise BraketCapabilityError("Pinned Braket SDK does not support circuit measurement.")
        measure(measured_qubits)

    gate_definitions: dict[tuple[Any, Any], Any] = {}
    for key, pulse_program in program.calibrations.entries:
        gate = _gate_for_calibration(key, sdk)
        qubits = sdk.qubit_set(key.qubits)
        sequence = lower_pulse_program(
            pulse_program,
            channel_map=channel_map,
            snapshot=snapshot,
            frames=frames,
        )
        gate_definitions[(gate, qubits)] = sequence
    if not gate_definitions:
        raise BraketCapabilityError(
            "BraketPulseBackend requires at least one explicit gate calibration."
        )
    return circuit, gate_definitions


def _provider_options(options: ExecutionOptions) -> dict[str, Any]:
    supported = {
        "aws.braket.poll_interval_seconds",
        "aws.braket.reservation_arn",
        "aws.braket.s3_bucket",
        "aws.braket.s3_prefix",
    }
    unknown = sorted(set(options.backend_options).difference(supported))
    if unknown:
        raise BackendError("Unsupported Braket backend options: " + ", ".join(unknown) + ".")
    if options.seed is not None:
        raise BackendError("Amazon Braket QPU execution does not promise a client seed.")
    if options.trace != "off":
        raise BackendError("Amazon Braket QPU execution does not expose QPlanck execution traces.")
    if options.max_memory_bytes is not None:
        raise BackendError("Amazon Braket does not expose an enforceable client memory budget.")

    raw = options.backend_options
    kwargs: dict[str, Any] = {}
    if options.timeout_seconds is not None:
        kwargs["poll_timeout_seconds"] = options.timeout_seconds
    if "aws.braket.poll_interval_seconds" in raw:
        interval = raw["aws.braket.poll_interval_seconds"]
        if isinstance(interval, bool) or not isinstance(interval, int | float) or interval <= 0:
            raise BackendError("aws.braket.poll_interval_seconds must be positive.")
        kwargs["poll_interval_seconds"] = float(interval)
    if "aws.braket.reservation_arn" in raw:
        reservation = raw["aws.braket.reservation_arn"]
        if not isinstance(reservation, str) or not reservation.startswith("arn:aws:braket:"):
            raise BackendError("aws.braket.reservation_arn must be a Braket ARN.")
        kwargs["reservation_arn"] = reservation
    bucket = raw.get("aws.braket.s3_bucket")
    prefix = raw.get("aws.braket.s3_prefix")
    if (bucket is None) != (prefix is None):
        raise BackendError(
            "aws.braket.s3_bucket and aws.braket.s3_prefix must be provided together."
        )
    if bucket is not None:
        if not isinstance(bucket, str) or not bucket or not isinstance(prefix, str) or not prefix:
            raise BackendError("Braket S3 bucket and prefix options must be non-empty strings.")
        kwargs["s3_destination_folder"] = (bucket, prefix)
    return kwargs


def _effective_options(options: ExecutionOptions, *, shots: int) -> ExecutionOptions:
    if options.shots == shots:
        return options
    return ExecutionOptions(
        shots=shots,
        seed=options.seed,
        trace=options.trace,
        timeout_seconds=options.timeout_seconds,
        max_memory_bytes=options.max_memory_bytes,
        max_result_bytes=options.max_result_bytes,
        backend_options=options.backend_options,
    )


def _artifact_options(options: ExecutionOptions) -> dict[str, Any]:
    """Serialize execution semantics without provider storage/reservation values."""

    payload = options.to_dict()
    raw_backend_options = payload.get("backend_options", {})
    payload["backend_options"] = {
        key: (
            value
            if key == "aws.braket.poll_interval_seconds"
            else "[REDACTED]"
        )
        for key, value in sorted(raw_backend_options.items())
    }
    return payload


def _provider_error_code(error: BaseException) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, Mapping):
        details = response.get("Error")
        if isinstance(details, Mapping):
            code = details.get("Code")
            if isinstance(code, str) and code.replace("_", "").replace("-", "").isalnum():
                return code
    return type(error).__name__


def _raw_rows(provider_result: Any) -> list[list[int]] | None:
    raw = getattr(provider_result, "measurements", None)
    if raw is None:
        return None
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if not isinstance(raw, Sequence):
        return None
    rows: list[list[int]] = []
    for raw_row in raw:
        if isinstance(raw_row, Sequence):
            row = [int(bit) for bit in raw_row]
        else:
            return None
        if any(bit not in {0, 1} for bit in row):
            return None
        rows.append(row)
    return rows


def _measurement_strings(provider_result: Any, calibrated: CalibratedCircuit) -> list[str] | None:
    rows = _raw_rows(provider_result)
    if rows is None:
        return None
    raw_qubits = getattr(provider_result, "measured_qubits", None)
    if raw_qubits is None:
        raw_qubits = list(range(len(rows[0]))) if rows else []
    measured_qubits = [int(qubit) for qubit in raw_qubits]
    if any(len(row) != len(measured_qubits) for row in rows):
        raise JobFailedError("Braket result rows do not match measured-qubit metadata.")

    specs = calibrated.compiled_circuit.ir.measurements
    if not specs:
        return ["".join(str(bit) for bit in reversed(row)) for row in rows]
    qubit_to_column = {qubit: index for index, qubit in enumerate(measured_qubits)}
    classical_width = max(spec.cbit for spec in specs) + 1
    strings: list[str] = []
    for row in rows:
        classical = [0] * classical_width
        for spec in specs:
            if spec.qubit not in qubit_to_column:
                raise JobFailedError(f"Braket result omitted measured physical qubit {spec.qubit}.")
            classical[spec.cbit] = row[qubit_to_column[spec.qubit]]
        strings.append("".join(str(bit) for bit in reversed(classical)))
    return strings


def _normalize_result(
    provider_result: Any,
    *,
    calibrated: CalibratedCircuit,
    task_id: str,
    device_arn: str,
    options: ExecutionOptions,
    submitted_at: str,
) -> RunResult:
    strings = _measurement_strings(provider_result, calibrated)
    diagnostics: tuple[Diagnostic, ...] = ()
    if strings is not None:
        counts = dict(Counter(strings))
        measurements = strings
        total = len(strings)
        probabilities = {key: value / total for key, value in counts.items()} if total else {}
    else:
        raw_counts = getattr(provider_result, "measurement_counts", {}) or {}
        raw_probabilities = getattr(provider_result, "measurement_probabilities", {}) or {}
        if not isinstance(raw_counts, Mapping) or not isinstance(raw_probabilities, Mapping):
            raise JobFailedError("Braket result does not expose normalizable measurements.")
        counts = {str(key): int(value) for key, value in raw_counts.items()}
        probabilities = {str(key): float(value) for key, value in raw_probabilities.items()}
        measurements = []
        diagnostics = (
            Diagnostic(
                code="BRAKET_SHOT_MEMORY_UNAVAILABLE",
                message="Braket result did not expose shot rows; aggregate keys are provider ordered.",
                severity="warning",
            ),
        )

    completed_at = _utc_now()
    accepted_shots = sum(counts.values())
    if options.shots is not None and accepted_shots != options.shots:
        raise JobFailedError(
            f"Braket returned {accepted_shots} accepted shots; {options.shots} were requested."
        )
    task_identity = redacted_arn_identity(task_id)
    device_identity = redacted_arn_identity(device_arn)
    metadata = {
        "provider": "aws.braket",
        "device_identity": device_identity,
        "task_identity": task_identity,
        "target_hash": calibrated.target_hash,
        "pulse_snapshot_hash": calibrated.pulse_snapshot_hash,
        "submitted_at": submitted_at,
        "completed_at": completed_at,
        "accepted_shots": accepted_shots,
    }
    artifact = ExternalArtifactRef(
        reference=task_identity,
        media_type="application/vnd.amazon.braket.quantum-task",
        metadata={"provider": "aws.braket", "device_identity": device_identity},
    )
    preliminary = RunResult(
        counts=counts,
        probabilities=probabilities,
        measurements=measurements,
        metadata=metadata,
        diagnostics=diagnostics,
        raw_result=artifact,
    )
    compiled = calibrated.compiled_circuit
    source_ir = compiled.source_ir
    manifest = ExperimentManifest(
        source={
            "schema_version": source_ir.schema_version,
            "semantic_hash": _hash_json(source_ir.to_dict()),
        },
        compilation={
            "compiled_hash": _hash_json(compiled.to_dict()),
            "trace_hash": _hash_json(compiled.trace.to_dict()),
            "calibrated_circuit_hash": calibrated.content_hash,
        },
        target={
            "target_hash": calibrated.target_hash,
            "pulse_snapshot_hash": calibrated.pulse_snapshot_hash,
            "device_identity": device_identity,
        },
        execution={
            "backend_id": "aws.braket.pulse",
            "backend_version": _adapter_version(),
            "job_id": task_identity,
            "options": _artifact_options(options),
            "seed_handling": "unsupported",
            "submitted_at": submitted_at,
            "completed_at": completed_at,
        },
        result={
            "result_hash": preliminary.content_hash,
            "accepted_shots": accepted_shots,
            "requested_shots": options.shots,
        },
        diagnostics=diagnostics,
    )
    normalized = RunResult(
        counts=counts,
        probabilities=probabilities,
        measurements=measurements,
        metadata=metadata,
        diagnostics=diagnostics,
        manifest=manifest,
        raw_result=artifact,
    )
    if options.max_result_bytes is not None:
        result_size = len(normalized.to_json().encode())
        if result_size > options.max_result_bytes:
            raise BackendError(
                f"Normalized Braket result is {result_size} bytes, exceeding max_result_bytes."
            )
    return normalized


def _call_with_timeout(function: Any, timeout: float | None) -> Any:
    if timeout is None:
        return function()
    outcomes: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcomes.put((True, function()))
        except BaseException as exc:  # propagated on the waiting thread
            outcomes.put((False, exc))

    thread = threading.Thread(target=invoke, daemon=True, name="qplanck-braket-result")
    thread.start()
    try:
        succeeded, value = outcomes.get(timeout=timeout)
    except queue.Empty as exc:
        raise JobTimeoutError(f"Braket task did not complete within {timeout} seconds.") from exc
    if succeeded:
        return value
    raise value


_STATUS_MAP = {
    "CREATED": JobStatus.CREATED,
    "QUEUED": JobStatus.QUEUED,
    "RUNNING": JobStatus.RUNNING,
    "CANCELLING": JobStatus.CANCEL_REQUESTED,
    "COMPLETED": JobStatus.SUCCEEDED,
    "FAILED": JobStatus.FAILED,
    "CANCELLED": JobStatus.CANCELLED,
}


@dataclass(frozen=True)
class BraketSubmissionPreflight:
    """Secret-free evidence produced before a Braket task can be submitted."""

    device_identity: str
    shots: int
    payload_bytes: int
    target_hash: str
    pulse_snapshot_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_identity": self.device_identity,
            "shots": self.shots,
            "payload_bytes": self.payload_bytes,
            "target_hash": self.target_hash,
            "pulse_snapshot_hash": self.pulse_snapshot_hash,
        }


@dataclass
class BraketJob:
    """One QPlanck job mapped to exactly one Amazon Braket quantum task."""

    provider_task: Any = field(repr=False)
    calibrated: CalibratedCircuit = field(repr=False)
    options: ExecutionOptions = field(repr=False)
    device_arn: str = field(repr=False)
    submitted_at: str
    _last_status: JobStatus = field(default=JobStatus.CREATED, init=False, repr=False)
    _result: RunResult | None = field(default=None, init=False, repr=False)

    @property
    def id(self) -> str:
        task_id = getattr(self.provider_task, "id", None)
        if not isinstance(task_id, str) or not task_id:
            raise BraketSubmissionError("Braket task does not expose a stable task ARN.")
        return task_id

    @property
    def artifact_id(self) -> str:
        """Redacted task identity safe to persist in logs and manifests."""

        return redacted_arn_identity(self.id)

    def status(self) -> JobStatus:
        if self._last_status.terminal:
            return self._last_status
        state = getattr(self.provider_task, "state", None)
        if not callable(state):
            raise BraketSubmissionError("Braket task does not expose state().")
        raw = str(state()).upper()
        if raw not in _STATUS_MAP:
            raise BraketSubmissionError(f"Unsupported Amazon Braket task state {raw!r}.")
        candidate = _STATUS_MAP[raw]
        rank = {
            JobStatus.CREATED: 0,
            JobStatus.QUEUED: 1,
            JobStatus.RUNNING: 2,
            JobStatus.CANCEL_REQUESTED: 3,
            JobStatus.SUCCEEDED: 4,
            JobStatus.FAILED: 4,
            JobStatus.CANCELLED: 4,
        }
        if rank[candidate] >= rank[self._last_status]:
            self._last_status = candidate
        return self._last_status

    def cancel(self) -> bool:
        current = self.status()
        if current.terminal:
            return False
        cancel = getattr(self.provider_task, "cancel", None)
        if not callable(cancel):
            raise BraketSubmissionError("Braket task does not expose cancel().")
        try:
            cancel()
        except Exception as exc:
            raise BraketSubmissionError(
                f"Amazon Braket cancellation failed ({_provider_error_code(exc)})."
            ) from None
        if current in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            self._last_status = JobStatus.CANCEL_REQUESTED
        return True

    def result(self, *, timeout: float | None = None) -> RunResult:
        if self._result is not None:
            return self._result
        result_method = getattr(self.provider_task, "result", None)
        if not callable(result_method):
            raise BraketSubmissionError("Braket task does not expose result().")
        try:
            provider_result = _call_with_timeout(result_method, timeout)
        except (JobTimeoutError, JobCancelledError, JobFailedError):
            raise
        except Exception as exc:
            raise JobFailedError(
                f"Amazon Braket result retrieval failed ({_provider_error_code(exc)})."
            ) from None
        status = self.status()
        if status is JobStatus.CANCELLED:
            raise JobCancelledError(f"Amazon Braket task {self.artifact_id} was cancelled.")
        if status is JobStatus.FAILED:
            raise JobFailedError(f"Amazon Braket task {self.artifact_id} failed.")
        if provider_result is None:
            raise JobTimeoutError(f"Amazon Braket task {self.artifact_id} returned no result.")
        self._result = _normalize_result(
            provider_result,
            calibrated=self.calibrated,
            task_id=self.id,
            device_arn=self.device_arn,
            options=self.options,
            submitted_at=self.submitted_at,
        )
        self._last_status = JobStatus.SUCCEEDED
        return self._result


@dataclass
class BraketPulseBackend:
    """Submit calibrated physical circuits to one capability-pinned Braket QPU."""

    device: BraketPulseDevice
    channel_map: BraketChannelMap
    default_shots: int = 1_000
    _sdk: _BraketCircuitSDK | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.default_shots, bool) or not isinstance(self.default_shots, int):
            raise BraketCapabilityError("default_shots must be a positive integer.")
        if self.default_shots <= 0:
            raise BraketCapabilityError("default_shots must be a positive integer.")
        if self.device.snapshot.calibration_digest is None:
            raise BraketCapabilityError(
                "BraketPulseBackend requires a content-hashed native calibration snapshot; "
                "construct BraketPulseDevice with refresh_calibrations=True."
            )
        self.channel_map.validate_snapshot(self.device.snapshot)

    @property
    def backend_id(self) -> str:
        return "aws.braket.pulse"

    @property
    def backend_version(self) -> str:
        return _adapter_version()

    @property
    def target(self) -> Target:
        return self.device.target

    def run(
        self,
        program: CalibratedCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> RunResult:
        selected = options or ExecutionOptions(shots=self.default_shots)
        return self.submit(program, options=selected).result(timeout=selected.timeout_seconds)

    def _prepare_submission(
        self,
        program: CalibratedCircuit,
        options: ExecutionOptions,
    ) -> tuple[BraketSubmissionPreflight, Any, dict[tuple[Any, Any], Any], dict[str, Any]]:
        if not isinstance(program, CalibratedCircuit):
            raise BackendError("BraketPulseBackend requires a CalibratedCircuit.")
        shots = self.default_shots if options.shots is None else options.shots
        if shots <= 0:
            raise BackendError("Amazon Braket QPU shots must be positive.")
        shot_limit = self.target.limits.max_shots
        if (
            shot_limit.kind is LimitKind.VALUE
            and shot_limit.value is not None
            and shots > shot_limit.value
        ):
            raise BackendError(
                f"Requested shots {shots} exceed Braket target maximum {shot_limit.value}."
            )
        kwargs = _provider_options(options)
        refreshed = self.device.assert_submission_snapshot(
            expected_target_hash=program.target_hash,
            expected_pulse_snapshot_hash=program.pulse_snapshot_hash,
        )
        self.channel_map.validate_snapshot(refreshed)
        for key in program.calibrations:
            calibrated_operation = Operation(key.gate, key.qubits, key.parameters)
            if not self.target.supports_operation(calibrated_operation):
                raise BackendError(
                    f"Calibration {key.gate!r} on {key.qubits} is not native to the target."
                )
        circuit, gate_definitions = _build_provider_payload(
            program,
            channel_map=self.channel_map,
            snapshot=refreshed,
            frames=self.device.frames,
            sdk=self._sdk or _load_circuit_sdk(),
        )
        to_ir = getattr(circuit, "to_ir", None)
        if not callable(to_ir):
            raise BraketCapabilityError("Pinned Braket SDK circuit cannot produce OpenQASM IR.")
        provider_ir = to_ir(gate_definitions=gate_definitions)
        source = getattr(provider_ir, "source", None)
        if not isinstance(source, str):
            raise BraketCapabilityError("Pinned Braket SDK did not produce OpenQASM source.")
        payload_bytes = len(source.encode())
        hard_limit = 5_000_000
        target_limit = self.target.limits.max_payload_bytes
        if target_limit.kind is LimitKind.VALUE and target_limit.value is not None:
            hard_limit = min(hard_limit, target_limit.value)
        if payload_bytes > hard_limit:
            raise BackendError(
                f"Braket OpenQASM payload is {payload_bytes} bytes, exceeding {hard_limit}."
            )
        preflight = BraketSubmissionPreflight(
            device_identity=redacted_arn_identity(self.device.arn),
            shots=shots,
            payload_bytes=payload_bytes,
            target_hash=program.target_hash,
            pulse_snapshot_hash=program.pulse_snapshot_hash,
        )
        return preflight, circuit, gate_definitions, kwargs

    def preflight(
        self,
        program: CalibratedCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> BraketSubmissionPreflight:
        """Refresh capabilities and validate a submission without creating a task."""

        selected = options or ExecutionOptions(shots=self.default_shots)
        preflight, _, _, _ = self._prepare_submission(program, selected)
        return preflight

    def submit(
        self,
        program: CalibratedCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> BraketJob:
        selected = options or ExecutionOptions(shots=self.default_shots)
        preflight, circuit, gate_definitions, kwargs = self._prepare_submission(program, selected)
        selected = _effective_options(selected, shots=preflight.shots)
        run = getattr(self.device.provider_device, "run", None)
        if not callable(run):
            raise BraketSubmissionError("Initialized Braket device does not expose run().")
        submitted_at = _utc_now()
        try:
            task = run(
                task_specification=circuit,
                shots=preflight.shots,
                gate_definitions=gate_definitions,
                disable_qubit_rewiring=True,
                **kwargs,
            )
        except Exception as exc:
            raise BraketSubmissionError(
                f"Amazon Braket submission failed ({_provider_error_code(exc)}); "
                "no retry was attempted."
            ) from None
        return BraketJob(task, program, selected, self.device.arn, submitted_at)


__all__ = ["BraketJob", "BraketPulseBackend", "BraketSubmissionPreflight"]
