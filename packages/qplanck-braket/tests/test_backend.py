from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from qplanck.ir import CircuitIR, MeasurementSpec, Operation
from qplanck.pulse import CalibrationKey, CalibrationLibrary, DriveChannel, PulseProgram
from qplanck.runtime import (
    BackendError,
    CalibratedCircuit,
    ExecutionOptions,
    JobStatus,
)
from qplanck.targets import Target

from qplanck_braket import (
    BraketChannelMap,
    BraketPulseBackend,
    BraketPulseDevice,
    BraketPulseSnapshot,
    BraketSnapshotMismatchError,
    BraketSubmissionError,
    redacted_arn_identity,
)
from qplanck_braket.backend import _BraketCircuitSDK

from .fakes import FakeFrame, FakePort


@dataclass(frozen=True)
class DummyTrace:
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": "test.trace.v1", "events": []}


@dataclass(frozen=True)
class DummyCompiled:
    source_ir: CircuitIR
    ir: CircuitIR
    target: Target
    trace: DummyTrace = DummyTrace()

    def to_dict(self) -> dict[str, object]:
        return {
            "source_ir": self.source_ir.to_dict(),
            "compiled_ir": self.ir.to_dict(),
            "target": self.target.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class FakeGateToken:
    name: str
    parameters: tuple[float, ...] = ()


class FakeGate:
    @staticmethod
    def X() -> FakeGateToken:
        return FakeGateToken("x")


class FakeCircuit:
    def __init__(self) -> None:
        self.operations: list[tuple[str, tuple[Any, ...]]] = []
        self.measured: list[int] = []

    def x(self, *args: Any) -> FakeCircuit:
        self.operations.append(("x", args))
        return self

    def measure(self, qubits: list[int]) -> FakeCircuit:
        self.measured.extend(qubits)
        return self

    def to_ir(self, *, gate_definitions: dict[tuple[Any, Any], Any]) -> Any:
        assert gate_definitions
        return type("FakeIR", (), {"source": "OPENQASM 3.0;\n// synthetic"})()


class FakeResult:
    measurements = [[0], [1], [1]]
    measured_qubits = [0]
    measurement_counts = {"0": 1, "1": 2}
    measurement_probabilities = {"0": 1 / 3, "1": 2 / 3}


class FakeTask:
    id = "arn:aws:braket:us-west-1:123456789012:quantum-task/test-task"

    def __init__(self, *, result: object = FakeResult(), task_id: str | None = None) -> None:
        if task_id is not None:
            self.id = task_id
        self._states = ["QUEUED", "RUNNING", "COMPLETED"]
        self._last = "QUEUED"
        self._result = result
        self.cancelled = False

    def state(self) -> str:
        if self._states:
            self._last = self._states.pop(0)
        return self._last

    def cancel(self) -> None:
        self.cancelled = True
        self._states = ["CANCELLED"]

    def result(self) -> object:
        self._last = "COMPLETED"
        self._states = []
        return self._result


class FakeAwsDevice:
    def __init__(
        self,
        snapshot: BraketPulseSnapshot,
        frames: dict[str, FakeFrame],
        *,
        task: FakeTask | None = None,
    ) -> None:
        self.arn = snapshot.device_arn
        self.frames = frames
        self.task = task or FakeTask()
        self.run_calls: list[dict[str, Any]] = []
        self.refreshed = 0

    def refresh_metadata(self) -> None:
        self.refreshed += 1

    def run(self, **kwargs: Any) -> FakeTask:
        self.run_calls.append(kwargs)
        return self.task


@pytest.fixture
def target() -> Target:
    return Target.testing(1, basis_gates=frozenset({"x"}), target_id="aws.braket.test")


@pytest.fixture
def compiled(target: Target) -> DummyCompiled:
    ir = CircuitIR(
        1,
        operations=(Operation("x", (0,)),),
        measurements=(MeasurementSpec(0, 0),),
    )
    return DummyCompiled(ir, ir, target)


@pytest.fixture
def calibrated(
    compiled: DummyCompiled,
    snapshot: BraketPulseSnapshot,
) -> CalibratedCircuit:
    calibrations = CalibrationLibrary.from_mapping(
        {CalibrationKey("x", (0,)): PulseProgram().delay(0, DriveChannel(0), 4)}
    )
    return CalibratedCircuit(
        compiled,  # type: ignore[arg-type]
        calibrations,
        compiled.target.content_hash,
        snapshot.snapshot_hash,
    )


@pytest.fixture
def backend(
    snapshot: BraketPulseSnapshot,
    target: Target,
    frames: dict[str, FakeFrame],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[BraketPulseBackend, FakeAwsDevice]:
    aws_device = FakeAwsDevice(snapshot, frames)
    device = BraketPulseDevice(
        aws_device,
        target,
        snapshot,
        snapshot_loader=lambda _device: snapshot,
    )
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    sdk = _BraketCircuitSDK(FakeCircuit, FakeGate, tuple)
    monkeypatch.setattr(
        "qplanck_braket.backend.lower_pulse_program",
        lambda *args, **kwargs: "fake-pulse-sequence",
    )
    return BraketPulseBackend(device, channel_map, _sdk=sdk), aws_device


def test_submit_maps_one_task_and_normalizes_result(
    backend: tuple[BraketPulseBackend, FakeAwsDevice],
    calibrated: CalibratedCircuit,
) -> None:
    adapter, aws_device = backend
    options = ExecutionOptions(shots=3, timeout_seconds=2.0)
    job = adapter.submit(calibrated, options=options)

    assert len(aws_device.run_calls) == 1
    call = aws_device.run_calls[0]
    assert call["shots"] == 3
    assert call["disable_qubit_rewiring"] is True
    assert call["poll_timeout_seconds"] == 2.0
    assert len(call["gate_definitions"]) == 1
    assert job.status() is JobStatus.QUEUED
    assert job.status() is JobStatus.RUNNING

    result = job.result(timeout=1.0)
    assert dict(result.counts) == {"0": 1, "1": 2}
    assert result.measurements == ["0", "1", "1"]
    assert result.raw_result is not None
    assert result.raw_result.reference == job.artifact_id
    assert result.manifest is not None
    assert result.manifest.execution["job_id"] == job.artifact_id
    assert result.metadata["pulse_snapshot_hash"] == calibrated.pulse_snapshot_hash
    assert job.status() is JobStatus.SUCCEEDED


def test_preflight_is_non_submitting_and_reports_payload(
    backend: tuple[BraketPulseBackend, FakeAwsDevice],
    calibrated: CalibratedCircuit,
) -> None:
    adapter, aws_device = backend
    evidence = adapter.preflight(calibrated, options=ExecutionOptions(shots=3))
    assert evidence.shots == 3
    assert evidence.payload_bytes == len(b"OPENQASM 3.0;\n// synthetic")
    assert evidence.pulse_snapshot_hash == calibrated.pulse_snapshot_hash
    assert aws_device.refreshed == 1
    assert aws_device.run_calls == []


def test_result_artifacts_redact_provider_and_storage_identifiers(
    backend: tuple[BraketPulseBackend, FakeAwsDevice],
    calibrated: CalibratedCircuit,
) -> None:
    adapter, aws_device = backend
    account_canary = "998877665544"
    task_arn = (
        f"arn:aws:braket:us-west-1:{account_canary}:"
        "quantum-task/provider-task-canary"
    )
    reservation_arn = (
        f"arn:aws:braket:us-west-1:{account_canary}:"
        "reservation/reservation-canary"
    )
    bucket_canary = "qplanck-private-bucket-canary"
    prefix_canary = "accounts/private-prefix-canary"
    aws_device.task = FakeTask(task_id=task_arn)
    options = ExecutionOptions(
        shots=3,
        backend_options={
            "aws.braket.reservation_arn": reservation_arn,
            "aws.braket.s3_bucket": bucket_canary,
            "aws.braket.s3_prefix": prefix_canary,
        },
    )

    preflight = adapter.preflight(calibrated, options=options)
    assert preflight.device_identity == redacted_arn_identity(aws_device.arn)
    assert aws_device.arn not in str(preflight.to_dict())

    job = adapter.submit(calibrated, options=options)
    result = job.result(timeout=1.0)
    artifact_json = result.to_json()
    assert job.id == task_arn
    assert job.artifact_id == redacted_arn_identity(task_arn)
    assert result.raw_result is not None
    assert result.raw_result.reference == job.artifact_id
    for canary in (
        account_canary,
        task_arn,
        aws_device.arn,
        reservation_arn,
        bucket_canary,
        prefix_canary,
    ):
        assert canary not in artifact_json
    assert result.manifest is not None
    artifact_options = result.manifest.execution["options"]
    assert artifact_options["backend_options"] == {
        "aws.braket.reservation_arn": "[REDACTED]",
        "aws.braket.s3_bucket": "[REDACTED]",
        "aws.braket.s3_prefix": "[REDACTED]",
    }
    assert aws_device.run_calls[-1]["reservation_arn"] == reservation_arn
    assert aws_device.run_calls[-1]["s3_destination_folder"] == (
        bucket_canary,
        prefix_canary,
    )


def test_backend_rejects_unsupported_semantics_before_submission(
    backend: tuple[BraketPulseBackend, FakeAwsDevice],
    calibrated: CalibratedCircuit,
) -> None:
    adapter, aws_device = backend
    with pytest.raises(BackendError, match="client seed"):
        adapter.submit(calibrated, options=ExecutionOptions(shots=1, seed=7))
    assert aws_device.run_calls == []

    with pytest.raises(BackendError, match="Unsupported Braket backend options"):
        adapter.submit(
            calibrated,
            options=ExecutionOptions(shots=1, backend_options={"aws.braket.unknown": True}),
        )
    assert aws_device.run_calls == []


def test_snapshot_race_prevents_submission(
    snapshot: BraketPulseSnapshot,
    capabilities: dict[str, object],
    target: Target,
    calibrated: CalibratedCircuit,
    frames: dict[str, FakeFrame],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed_capabilities = {**capabilities, "pulse": dict(capabilities["pulse"])}  # type: ignore[arg-type]
    changed_capabilities["pulse"]["validationParameters"] = {"MAX_AMPLITUDE": 0.5}  # type: ignore[index]
    changed = BraketPulseSnapshot.from_capabilities(snapshot.device_arn, changed_capabilities)
    aws_device = FakeAwsDevice(snapshot, frames)
    device = BraketPulseDevice(
        aws_device,
        target,
        snapshot,
        snapshot_loader=lambda _device: changed,
    )
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    monkeypatch.setattr(
        "qplanck_braket.backend.lower_pulse_program",
        lambda *args, **kwargs: "fake-pulse-sequence",
    )
    adapter = BraketPulseBackend(
        device,
        channel_map,
        _sdk=_BraketCircuitSDK(FakeCircuit, FakeGate, tuple),
    )
    with pytest.raises(BraketSnapshotMismatchError, match="changed before submission"):
        adapter.submit(calibrated, options=ExecutionOptions(shots=1))
    assert aws_device.run_calls == []


def test_submission_failure_is_not_retried_or_leaked(
    backend: tuple[BraketPulseBackend, FakeAwsDevice],
    calibrated: CalibratedCircuit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, aws_device = backend
    calls = 0

    def fail(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("secret credential /Users/alice/.aws/credentials")

    monkeypatch.setattr(aws_device, "run", fail)
    with pytest.raises(BraketSubmissionError) as error:
        adapter.submit(calibrated, options=ExecutionOptions(shots=1))
    assert calls == 1
    assert "secret credential" not in str(error.value)
    assert "/Users/alice" not in str(error.value)
    assert "no retry" in str(error.value)


@pytest.fixture
def frames() -> dict[str, FakeFrame]:
    return {
        "q0_drive": FakeFrame("q0_drive", FakePort("q0_rf", 1e-9)),
        "q1_drive": FakeFrame("q1_drive", FakePort("q1_rf", 1e-9)),
        "q0_readout": FakeFrame("q0_readout", FakePort("q0_rx", 1e-9)),
    }
