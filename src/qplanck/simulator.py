"""Thin Python facade over QCore's required Rust statevector kernel."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from qplanck._native import simulate_ir
from qplanck.circuit import Circuit
from qplanck.errors import ResourceLimitError
from qplanck.ir import CircuitIR
from qplanck.results import (
    ExecutionTrace,
    ProbabilityResult,
    RunResult,
    StatevectorResult,
)
from qplanck.runtime import BackendError, ExecutionOptions, ExperimentManifest
from qplanck.targets import Target

if TYPE_CHECKING:
    from qplanck.compiler import CompiledCircuit


DEFAULT_MAX_STATEVECTOR_BYTES = 256 * 1024 * 1024


class LocalSimulator:
    """Bounded deterministic Rust statevector backend.

    The Python layer validates the public call shape and constructs the stable
    runtime objects. Gate evolution, measurement mapping, seeded sampling, and
    allocation/result preflight all execute in the required Rust kernel. There
    is intentionally no Python numerical fallback.
    """

    def __init__(
        self,
        backend: str = "statevector",
        *,
        max_statevector_bytes: int = DEFAULT_MAX_STATEVECTOR_BYTES,
    ) -> None:
        if backend != "statevector":
            raise ValueError("QCore currently provides only the 'statevector' backend.")
        if (
            isinstance(max_statevector_bytes, bool)
            or not isinstance(max_statevector_bytes, int)
            or max_statevector_bytes <= 0
        ):
            raise ValueError("max_statevector_bytes must be positive.")
        self.backend = backend
        self.max_statevector_bytes = max_statevector_bytes
        complex_slots = max(1, max_statevector_bytes // 16)
        max_qubits = max(1, complex_slots.bit_length() - 1)
        self._target = Target.testing(
            qubits=max_qubits,
            target_id="qplanck.local-statevector",
        )
        self._submission_count = 0

    @property
    def backend_id(self) -> str:
        return "qplanck.local-statevector"

    @property
    def backend_version(self) -> str:
        return "1"

    @property
    def target(self) -> Target:
        return self._target

    def run(
        self,
        program: Circuit | CircuitIR | CompiledCircuit,
        *,
        options: ExecutionOptions | None = None,
        shots: int | None = None,
        seed: int | None = None,
        trace: bool | None = None,
        max_trace_qubits: int = 8,
    ) -> RunResult:
        resolved = _resolve_options(options, shots=shots, seed=seed, trace=trace)
        if resolved.backend_options:
            names = ", ".join(sorted(resolved.backend_options))
            raise BackendError(f"LocalSimulator does not support backend options: {names}.")
        circuit = _coerce_circuit(program)
        started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        response = self._invoke(
            circuit,
            mode="run",
            options=resolved,
            max_trace_qubits=max_trace_qubits,
        )
        completed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        execution_trace = (
            None if response.get("trace") is None else ExecutionTrace.from_dict(response["trace"])
        )
        metadata = {
            **dict(response.get("metadata", {})),
            "backend": self.backend,
            "backend_id": self.backend_id,
            "shots": resolved.shots,
            "seed": resolved.seed,
            "basis_key_order": ("c[n-1]...c[0]" if circuit.measurements else "q[n-1]...q[0]"),
            "measurement_mode": ("explicit" if circuit.measurements else "implicit-all-qubits"),
            "native_ir_hash": response["ir_hash"],
            "statevector_bytes": response["statevector_bytes"],
            "peak_execution_bytes": response["peak_execution_bytes"],
            "estimated_result_bytes": response["estimated_result_bytes"],
        }
        preliminary = RunResult(
            counts=response["counts"],
            probabilities=response["probabilities"],
            measurements=response["measurements"],
            metadata=metadata,
            execution_trace=execution_trace,
        )
        self._submission_count += 1
        job_id = f"local-{self._submission_count:08d}"
        manifest = _build_local_manifest(
            program=program,
            circuit=circuit,
            target=_execution_target(program, self.target),
            options=resolved,
            result=preliminary,
            native_ir_hash=str(response["ir_hash"]),
            native_implementation=response["implementation"],
            backend_id=self.backend_id,
            backend_version=self.backend_version,
            job_id=job_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        return RunResult(
            counts=preliminary.counts,
            probabilities=preliminary.probabilities,
            measurements=preliminary.measurements,
            metadata=preliminary.metadata,
            diagnostics=preliminary.diagnostics,
            execution_trace=preliminary.execution_trace,
            manifest=manifest,
            raw_result=preliminary.raw_result,
        )

    def submit(
        self,
        program: Circuit | CircuitIR | CompiledCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> Any:
        """Execute immediately and return an already-succeeded local job."""

        from qplanck.backends import CompletedJob

        result = self.run(program, options=options)
        job_id = str(result.manifest.execution["job_id"]) if result.manifest else "local-unknown"
        return CompletedJob(job_id, result)

    def statevector(
        self,
        program: Circuit | CircuitIR | CompiledCircuit,
    ) -> StatevectorResult:
        circuit = _coerce_circuit(program)
        response = self._invoke(
            circuit,
            mode="statevector",
            options=ExecutionOptions(),
            max_trace_qubits=8,
        )
        raw_state = response.get("statevector")
        if not isinstance(raw_state, list):
            raise RuntimeError("The QCore native kernel omitted its statevector result.")
        statevector = tuple(complex(float(item["real"]), float(item["imag"])) for item in raw_state)
        return StatevectorResult(
            statevector=statevector,
            metadata={
                "backend": self.backend,
                "endianness": "little",
                "native_ir_hash": response["ir_hash"],
            },
        )

    def probabilities(
        self,
        program: Circuit | CircuitIR | CompiledCircuit,
    ) -> ProbabilityResult:
        circuit = _coerce_circuit(program)
        response = self._invoke(
            circuit,
            mode="probabilities",
            options=ExecutionOptions(),
            max_trace_qubits=8,
        )
        return ProbabilityResult(
            probabilities={
                str(key): float(value) for key, value in response["probabilities"].items()
            },
            metadata={
                "backend": self.backend,
                "basis_key_order": "q[n-1]...q[0]",
                "native_ir_hash": response["ir_hash"],
            },
        )

    def _invoke(
        self,
        circuit: Circuit,
        *,
        mode: Literal["run", "statevector", "probabilities"],
        options: ExecutionOptions,
        max_trace_qubits: int,
    ) -> dict[str, Any]:
        if (
            isinstance(max_trace_qubits, bool)
            or not isinstance(max_trace_qubits, int)
            or max_trace_qubits < 0
        ):
            raise ValueError("max_trace_qubits must be a non-negative integer.")
        memory_limit = self.max_statevector_bytes
        if options.max_memory_bytes is not None:
            memory_limit = min(memory_limit, options.max_memory_bytes)
        if circuit.qubit_count > self.target.qubit_count:
            required = (1 << circuit.qubit_count) * 16
            raise ResourceLimitError(
                f"Statevector requires {required} bytes, exceeding the configured "
                f"{memory_limit}-byte limit."
            )
        return simulate_ir(
            circuit.to_json(),
            mode=mode,
            shots=options.shots,
            seed=options.seed,
            trace=options.trace == "full",
            max_statevector_bytes=memory_limit,
            max_result_bytes=options.max_result_bytes,
            max_trace_qubits=max_trace_qubits,
        )


class Simulator(LocalSimulator):
    """Backward-compatible v0.x facade over :class:`LocalSimulator`."""


def _coerce_circuit(program: Circuit | CircuitIR | CompiledCircuit) -> Circuit:
    if isinstance(program, Circuit):
        return program
    if isinstance(program, CircuitIR):
        return Circuit.from_ir(program)
    to_circuit = getattr(program, "to_circuit", None)
    if callable(to_circuit):
        circuit = to_circuit()
        if isinstance(circuit, Circuit):
            return circuit
    raise TypeError("LocalSimulator expects Circuit, CircuitIR, or CompiledCircuit.")


def _resolve_options(
    options: ExecutionOptions | None,
    *,
    shots: int | None,
    seed: int | None,
    trace: bool | None,
) -> ExecutionOptions:
    if options is not None and any(value is not None for value in (shots, seed, trace)):
        raise ValueError("Pass either options or direct shots/seed/trace keywords, not both.")
    if options is not None:
        if not isinstance(options, ExecutionOptions):
            raise TypeError("options must be an ExecutionOptions instance or None.")
        return options
    return ExecutionOptions(
        shots=shots,
        seed=seed,
        trace="full" if trace else "off",
    )


def _hash_dict(value: object) -> str:
    payload = json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _execution_target(
    program: Circuit | CircuitIR | CompiledCircuit,
    local_target: Target,
) -> Target:
    compiled_target = getattr(program, "target", None)
    return compiled_target if isinstance(compiled_target, Target) else local_target


def _build_local_manifest(
    *,
    program: Circuit | CircuitIR | CompiledCircuit,
    circuit: Circuit,
    target: Target,
    options: ExecutionOptions,
    result: RunResult,
    native_ir_hash: str,
    native_implementation: dict[str, Any],
    backend_id: str,
    backend_version: str,
    job_id: str,
    started_at: str,
    completed_at: str,
) -> ExperimentManifest:
    source_ir = getattr(program, "source_ir", circuit.ir)
    source_dict = source_ir.to_dict() if isinstance(source_ir, CircuitIR) else circuit.ir.to_dict()
    compiled_to_dict = getattr(program, "to_dict", None)
    is_compiled = callable(compiled_to_dict) and not isinstance(program, Circuit | CircuitIR)
    compiled_dict = compiled_to_dict() if is_compiled and callable(compiled_to_dict) else None
    return ExperimentManifest(
        source={
            "circuit_hash": _hash_dict(source_dict),
            "native_ir_hash": native_ir_hash,
            "schema_version": source_dict.get("schema_version"),
        },
        compilation={
            "compiled": is_compiled,
            "compiled_hash": _hash_dict(compiled_dict) if compiled_dict is not None else None,
            "target_hash": target.content_hash,
        },
        target={
            "target_id": target.target_id,
            "target_hash": target.content_hash,
        },
        execution={
            "backend_id": backend_id,
            "backend_version": backend_version,
            "job_id": job_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "options": options.to_dict(),
            "seed_handling": "honored" if options.seed is not None else "stable-default-zero",
            "implicit_measure_all": not bool(circuit.measurements),
        },
        result={
            "result_hash": result.content_hash,
            "accepted_shots": options.shots,
            "returned_shots": sum(result.counts.values()),
            "numeric_tolerance_profile": "rust-f64",
        },
        environment={
            "native_implementation": native_implementation,
            "python_adapter": "qplanck",
        },
        diagnostics=result.diagnostics,
    )


__all__ = ["DEFAULT_MAX_STATEVECTOR_BYTES", "LocalSimulator", "Simulator"]
