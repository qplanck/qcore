"""Optional, deterministic Qiskit compiler strategy for the QCore planner.

Qiskit is imported only when :meth:`QiskitCompilerStrategy.run` is invoked.
This adapter performs local transpilation only; it does not discover providers,
load credentials, or submit work to hardware.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

import numpy as np

from qplanck.circuit import Circuit
from qplanck.errors import InteropError
from qplanck.ir import CircuitIR, MeasurementSpec, Operation
from qplanck.planning import (
    Program,
    StrategyResult,
    StrategyUnavailableError,
    StrategyUnsupportedError,
)
from qplanck.targets import Target

QISKIT_STRATEGY_VERSION: Final = "qplanck.qiskit-strategy.v0.1"
_EQUIVALENCE_ATOL: Final = 1e-10
_MAX_EXACT_QUBITS: Final = 8


@dataclass(frozen=True)
class _QiskitModules:
    qiskit: Any
    coupling_map_type: Any
    statevector_type: Any
    version: str


@dataclass(frozen=True)
class _SemanticCheck:
    equivalent: bool
    maximum_probability_delta: float
    logical_qubits: int
    output_active_qubits: int
    classical_bits: tuple[int, ...]


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _load_qiskit() -> _QiskitModules:
    try:
        qiskit = importlib.import_module("qiskit")
        transpiler = importlib.import_module("qiskit.transpiler")
        quantum_info = importlib.import_module("qiskit.quantum_info")
    except (ImportError, ModuleNotFoundError) as error:
        raise StrategyUnavailableError(
            "Qiskit strategy requires the optional dependency: "
            'python -m pip install "qplanck[qiskit]".',
            reason_code="qiskit.dependency_unavailable",
        ) from error
    coupling_map_type = getattr(transpiler, "CouplingMap", None)
    statevector_type = getattr(quantum_info, "Statevector", None)
    transpile = getattr(qiskit, "transpile", None)
    if coupling_map_type is None or statevector_type is None or not callable(transpile):
        raise StrategyUnavailableError(
            "Installed Qiskit does not expose transpile, CouplingMap, and Statevector.",
            reason_code="qiskit.api_incompatible",
        )
    version: object
    try:
        version = importlib.metadata.version("qiskit")
    except importlib.metadata.PackageNotFoundError:
        version = getattr(qiskit, "__version__", None)
    if not isinstance(version, str) or not version.strip():
        raise StrategyUnavailableError(
            "Installed Qiskit does not expose a usable version.",
            reason_code="qiskit.version_unavailable",
        )
    return _QiskitModules(qiskit, coupling_map_type, statevector_type, version.strip())


def _coupling_edges(target: Target) -> tuple[tuple[int, int], ...]:
    edges = set(target.topology.edges)
    if not target.topology.directed:
        edges.update((right, left) for left, right in target.topology.edges)
    return tuple(sorted(edges))


def _coupling_map(target: Target, coupling_map_type: Any) -> Any:
    try:
        coupling = coupling_map_type()
        for qubit in range(target.qubit_count):
            coupling.add_physical_qubit(qubit)
        for left, right in _coupling_edges(target):
            coupling.add_edge(left, right)
    except Exception as error:
        raise StrategyUnsupportedError(
            f"Qiskit could not represent target topology: {type(error).__name__}: {error}",
            reason_code="qiskit.topology_unrepresentable",
        ) from error
    return coupling


def _artifact_ir(value: Any) -> CircuitIR:
    try:
        return Circuit.from_qiskit(value).ir
    except InteropError as error:
        raise StrategyUnsupportedError(
            f"Qiskit output is outside QCore's supported circuit subset: {error}",
            reason_code="qiskit.output_unsupported",
        ) from error


def _validate_target_conformance(ir: CircuitIR, target: Target) -> None:
    if ir.qubit_count > target.qubit_count:
        raise StrategyUnsupportedError(
            "Qiskit output width exceeds the immutable target snapshot.",
            reason_code="qiskit.output_width_exceeded",
        )
    for index, operation in enumerate(ir.operations):
        if not target.supports_operation(operation):
            raise StrategyUnsupportedError(
                f"Qiskit output operation {index} ({operation.name}{operation.qubits}) "
                "does not conform to the immutable target snapshot.",
                reason_code="qiskit.target_conformance_failed",
            )
    if any(measurement.qubit >= target.qubit_count for measurement in ir.measurements):
        raise StrategyUnsupportedError(
            "Qiskit output measurement references a qubit outside the target snapshot.",
            reason_code="qiskit.target_conformance_failed",
        )


def _compact_active_ir(ir: CircuitIR) -> CircuitIR:
    active = sorted(
        {qubit for operation in ir.operations for qubit in operation.qubits}
        | {measurement.qubit for measurement in ir.measurements}
    )
    if not active:
        raise StrategyUnsupportedError(
            "Exact semantic validation requires at least one active or measured qubit.",
            reason_code="qiskit.semantic_validation_no_active_qubits",
        )
    physical_to_compact = {physical: compact for compact, physical in enumerate(active)}
    return CircuitIR(
        qubit_count=len(active),
        operations=tuple(
            Operation(
                operation.name,
                tuple(physical_to_compact[qubit] for qubit in operation.qubits),
                operation.params,
                operation.metadata,
            )
            for operation in ir.operations
        ),
        measurements=tuple(
            MeasurementSpec(
                physical_to_compact[measurement.qubit],
                measurement.cbit,
                measurement.metadata,
            )
            for measurement in ir.measurements
        ),
    )


def _classical_marginal(
    ir: CircuitIR,
    statevector_type: Any,
) -> tuple[tuple[int, ...], dict[tuple[int, ...], float]]:
    measurements = tuple(sorted(ir.measurements, key=lambda item: item.cbit))
    if not measurements:
        raise StrategyUnsupportedError(
            "Exact Qiskit validation currently requires terminal measurements.",
            reason_code="qiskit.semantic_validation_measurements_required",
        )
    try:
        provider_circuit = Circuit.from_ir(ir).to_qiskit()
        unitary = provider_circuit.remove_final_measurements(inplace=False)
        state = np.asarray(statevector_type.from_instruction(unitary).data, dtype=np.complex128)
    except Exception as error:
        raise StrategyUnsupportedError(
            "Qiskit statevector validation could not be established: "
            f"{type(error).__name__}: {error}",
            reason_code="qiskit.semantic_validation_failed",
        ) from error
    expected_dimension = 1 << ir.qubit_count
    if state.ndim != 1 or state.size != expected_dimension:
        raise StrategyUnsupportedError(
            "Qiskit returned an unexpected statevector dimension.",
            reason_code="qiskit.semantic_validation_dimension_mismatch",
        )
    probabilities = np.abs(state) ** 2
    total_probability = float(np.sum(probabilities))
    if not math.isfinite(total_probability) or not math.isclose(
        total_probability, 1.0, abs_tol=_EQUIVALENCE_ATOL
    ):
        raise StrategyUnsupportedError(
            "Qiskit returned a non-normalized statevector.",
            reason_code="qiskit.semantic_validation_not_normalized",
        )

    marginal: dict[tuple[int, ...], float] = {}
    for basis_index, probability in enumerate(probabilities):
        outcome = tuple((basis_index >> measurement.qubit) & 1 for measurement in measurements)
        marginal[outcome] = marginal.get(outcome, 0.0) + float(probability)
    return tuple(measurement.cbit for measurement in measurements), marginal


def _semantic_check(
    source: CircuitIR,
    output: CircuitIR,
    statevector_type: Any,
) -> _SemanticCheck:
    if source.qubit_count > _MAX_EXACT_QUBITS:
        raise StrategyUnsupportedError(
            f"Exact Qiskit validation is limited to {_MAX_EXACT_QUBITS} logical qubits.",
            reason_code="qiskit.semantic_validation_logical_width_exceeded",
        )
    compact_output = _compact_active_ir(output)
    if compact_output.qubit_count > _MAX_EXACT_QUBITS:
        raise StrategyUnsupportedError(
            f"Exact Qiskit validation is limited to {_MAX_EXACT_QUBITS} active output qubits.",
            reason_code="qiskit.semantic_validation_output_width_exceeded",
        )
    source_bits, source_marginal = _classical_marginal(source, statevector_type)
    output_bits, output_marginal = _classical_marginal(compact_output, statevector_type)
    if source_bits != output_bits:
        return _SemanticCheck(
            False,
            1.0,
            source.qubit_count,
            compact_output.qubit_count,
            source_bits,
        )
    outcomes = set(source_marginal) | set(output_marginal)
    maximum_delta = max(
        (
            abs(source_marginal.get(outcome, 0.0) - output_marginal.get(outcome, 0.0))
            for outcome in outcomes
        ),
        default=0.0,
    )
    return _SemanticCheck(
        maximum_delta <= _EQUIVALENCE_ATOL,
        maximum_delta,
        source.qubit_count,
        compact_output.qubit_count,
        source_bits,
    )


def _swap_evidence(source: CircuitIR, output: CircuitIR) -> tuple[int | None, str | None]:
    source_swaps = sum(operation.name == "swap" for operation in source.operations)
    output_swaps = sum(operation.name == "swap" for operation in output.operations)
    if output_swaps > 0 and source_swaps == 0:
        return output_swaps, None
    if output_swaps > 0:
        return (
            None,
            "Qiskit output contains explicit SWAPs, but source-authored and inserted SWAPs "
            "cannot be distinguished without rewrite provenance.",
        )
    return (
        None,
        "Qiskit output contains no explicit SWAP instructions; routing SWAPs may have been "
        "lowered into target-basis gates.",
    )


@dataclass(frozen=True)
class QiskitCompilerStrategy:
    """Local Qiskit transpilation at one deterministic optimization level."""

    optimization_level: int = 1
    seed: int = 0
    strategy_id: str = field(default="qiskit.transpile", init=False)
    strategy_version: str = field(default=QISKIT_STRATEGY_VERSION, init=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.optimization_level, bool)
            or not isinstance(self.optimization_level, int)
            or self.optimization_level not in range(4)
        ):
            raise ValueError("Qiskit optimization_level must be one of 0, 1, 2, or 3.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Qiskit transpiler seed must be a non-negative integer.")

    @property
    def options(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "optimization_level": self.optimization_level,
                "seed_transpiler": self.seed,
                "layout_method": "sabre",
                "routing_method": "sabre",
                "num_processes": 1,
            }
        )

    def run(self, program: Program, target: Target) -> StrategyResult:
        if not isinstance(program, Program):
            raise TypeError("Qiskit strategy requires a qplanck.planning.Program.")
        if not isinstance(target, Target):
            raise TypeError("Qiskit strategy requires a qplanck.targets.Target.")
        if program.ir.qubit_count > target.qubit_count:
            raise StrategyUnsupportedError(
                "Program width exceeds the immutable target snapshot.",
                reason_code="qiskit.target_width_exceeded",
            )
        modules = _load_qiskit()
        coupling = _coupling_map(target, modules.coupling_map_type)
        try:
            provider_circuit = Circuit.from_ir(program.ir).to_qiskit()
        except InteropError as error:
            raise StrategyUnsupportedError(
                f"Normalized Program cannot be represented by Qiskit: {error}",
                reason_code="qiskit.input_unsupported",
            ) from error
        basis_gates = tuple(sorted(target.basis_gates))
        options = dict(self.options)

        started = time.perf_counter_ns()
        try:
            provider_output = modules.qiskit.transpile(
                provider_circuit,
                basis_gates=list(basis_gates),
                coupling_map=coupling,
                optimization_level=self.optimization_level,
                seed_transpiler=self.seed,
                layout_method="sabre",
                routing_method="sabre",
                num_processes=1,
            )
        except Exception as error:
            raise StrategyUnsupportedError(
                f"Qiskit transpilation failed: {type(error).__name__}: {error}",
                reason_code="qiskit.transpile_failed",
            ) from error
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

        artifact = _artifact_ir(provider_output)
        _validate_target_conformance(artifact, target)
        semantic = _semantic_check(program.ir, artifact, modules.statevector_type)
        swap_count, swap_unknown = _swap_evidence(program.ir, artifact)
        coupling_edges = _coupling_edges(target)
        semantic_evidence = (
            "Exact statevector-derived terminal classical marginal from the all-zero "
            "initial state.",
            f"Logical qubits: {semantic.logical_qubits}; active output qubits: "
            f"{semantic.output_active_qubits}.",
            f"Classical bits: {list(semantic.classical_bits)}; absolute tolerance: "
            f"{_EQUIVALENCE_ATOL}; maximum probability delta: "
            f"{semantic.maximum_probability_delta}.",
        )
        diagnostics: tuple[str, ...] = ()
        if not semantic.equivalent:
            diagnostics = (
                "Qiskit output classical marginal did not match the normalized Program.",
            )
        return StrategyResult(
            artifact=artifact,
            semantic_equivalent=semantic.equivalent,
            semantic_evidence=semantic_evidence,
            inserted_swap_count=swap_count,
            inserted_swap_unknown_reason=swap_unknown,
            compilation_latency_ms=elapsed_ms,
            assumptions=(
                "Execution starts in the all-zero computational basis state.",
                "Terminal measurement probabilities are the semantic validation boundary.",
                "Arbitrary QCore circuit and operation metadata are not compiler semantics.",
            ),
            diagnostics=diagnostics,
            provenance={
                "adapter": self.strategy_version,
                "compiler": "qiskit.transpile",
                "compiler_version": modules.version,
                "options": options,
                "effective_options": {
                    **options,
                    "basis_gates": list(basis_gates),
                    "coupling_edges": [list(edge) for edge in coupling_edges],
                },
                "program_hash": program.program_hash,
                "target_id": target.target_id,
                "target_hash": target.content_hash,
                "target_snapshot_id": target.snapshot_id,
                "artifact_hash": _canonical_hash(artifact.to_dict()),
                "semantic_validation": {
                    "method": "exact_statevector_terminal_classical_marginal",
                    "initial_state": "all_zero",
                    "maximum_qubits": _MAX_EXACT_QUBITS,
                    "absolute_tolerance": _EQUIVALENCE_ATOL,
                    "maximum_probability_delta": semantic.maximum_probability_delta,
                    "equivalent": semantic.equivalent,
                    "classical_bits": list(semantic.classical_bits),
                },
            },
        )


QiskitStrategy = QiskitCompilerStrategy


def qiskit_strategies(
    optimization_levels: Iterable[int] = (0, 1, 2, 3),
    *,
    seed: int = 0,
) -> tuple[QiskitCompilerStrategy, ...]:
    """Build a deterministic local Qiskit candidate portfolio.

    Levels are de-duplicated and sorted so the same requested set produces the
    same strategy descriptors regardless of caller ordering.  Constructing the
    portfolio does not import Qiskit; the optional dependency is loaded only
    when a strategy runs.
    """

    requested = tuple(
        QiskitCompilerStrategy(optimization_level=level, seed=seed) for level in optimization_levels
    )
    if not requested:
        raise ValueError("Qiskit strategy portfolio requires at least one optimization level.")
    by_level = {item.optimization_level: item for item in requested}
    return tuple(by_level[level] for level in sorted(by_level))


__all__ = [
    "QISKIT_STRATEGY_VERSION",
    "QiskitCompilerStrategy",
    "QiskitStrategy",
    "qiskit_strategies",
]
