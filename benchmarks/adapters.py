"""Compiler adapters with exact dependency-pin and evidence contracts."""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from typing import Any, cast

import numpy as np

from benchmarks.models import (
    BenchmarkCase,
    CompilerOutcome,
    QualityMetrics,
    canonical_hash,
)
from qplanck.compiler import CompileOptions, DependencyGraph, ResourceMetrics
from qplanck.ir import CircuitIR, Operation

QPLANCK_ENGINE = "qplanck-native"
ORACLE_ENGINE = "python-oracle"
QISKIT_ENGINE = "qiskit-2.5.1"
CIRQ_ENGINE = "cirq-1.7.0"
ENGINE_NAMES = (QPLANCK_ENGINE, ORACLE_ENGINE, QISKIT_ENGINE, CIRQ_ENGINE)

PINNED_DEPENDENCIES: dict[str, dict[str, str]] = {
    QISKIT_ENGINE: {
        "distribution": "qiskit",
        "module": "qiskit",
        "version": "2.5.1",
    },
    CIRQ_ENGINE: {
        "distribution": "cirq-core",
        "module": "cirq",
        "version": "1.7.0",
    },
}


class EngineUnavailableError(RuntimeError):
    """Raised when an optional engine is absent or differs from its public pin."""


@dataclass(frozen=True)
class EngineStatus:
    engine: str
    available: bool
    requested_version: str | None
    installed_version: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "engine": self.engine,
            "available": self.available,
            "requested_version": self.requested_version,
            "installed_version": self.installed_version,
            "reason": self.reason,
        }


def engine_status(engine: str) -> EngineStatus:
    if engine not in ENGINE_NAMES:
        raise ValueError(f"Unknown benchmark engine {engine!r}.")
    if engine == ORACLE_ENGINE:
        compiler = importlib.import_module("qplanck.compiler")
        available = callable(getattr(compiler, "_compile_reference", None))
        return EngineStatus(
            engine,
            available,
            None,
            None,
            None if available else "Frozen Python oracle is not available in this checkout.",
        )
    if engine == QPLANCK_ENGINE:
        try:
            native = importlib.import_module("qplanck._native")
            info = native.implementation_info()
        except Exception as error:
            return EngineStatus(engine, False, None, None, f"{type(error).__name__}: {error}")
        return EngineStatus(engine, True, None, str(info.get("version", "unknown")))

    pin = PINNED_DEPENDENCIES[engine]
    try:
        installed = importlib_metadata.version(pin["distribution"])
    except importlib_metadata.PackageNotFoundError:
        return EngineStatus(
            engine,
            False,
            pin["version"],
            None,
            f"Install {pin['distribution']}=={pin['version']}.",
        )
    if installed != pin["version"]:
        return EngineStatus(
            engine,
            False,
            pin["version"],
            installed,
            "Installed version differs from the benchmark pin.",
        )
    return EngineStatus(engine, True, pin["version"], installed)


def _require_engine(engine: str) -> None:
    status = engine_status(engine)
    if not status.available:
        raise EngineUnavailableError(status.reason or f"Engine {engine} is unavailable.")


def _source_metrics(ir: CircuitIR) -> ResourceMetrics:
    return ResourceMetrics.from_ir(ir, DependencyGraph.from_ir(ir))


def _qplanck_quality(case: BenchmarkCase, compiled: Any) -> QualityMetrics:
    before = compiled.before_metrics
    after = compiled.after_metrics
    swaps = None
    if compiled.routing_trace is not None:
        swaps = len(compiled.routing_trace.steps)
    return QualityMetrics(
        source_operations=before.operation_count,
        output_operations=after.operation_count,
        source_two_qubit_gates=before.two_qubit_gate_count,
        output_two_qubit_gates=after.two_qubit_gate_count,
        added_two_qubit_gates=max(
            0,
            after.two_qubit_gate_count - before.two_qubit_gate_count,
        ),
        depth=after.depth,
        conceptual_swaps=swaps,
    )


def _encoded_index(index: int, layout: Any) -> int:
    encoded = 0
    for logical, physical in enumerate(layout.logical_to_physical):
        if (index >> logical) & 1:
            encoded |= 1 << physical
    return encoded


def _apply_ir(ir: CircuitIR, state: Any) -> Any:
    evolved = state
    for operation in ir.operations:
        name = operation.name
        if name == "h":
            matrix = np.array([[1, 1], [1, -1]], dtype=np.complex128) / math.sqrt(2)
        elif name == "x":
            matrix = np.array([[0, 1], [1, 0]], dtype=np.complex128)
        elif name == "y":
            matrix = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
        elif name == "z":
            matrix = np.array([[1, 0], [0, -1]], dtype=np.complex128)
        elif name == "s":
            matrix = np.array([[1, 0], [0, 1j]], dtype=np.complex128)
        elif name == "t":
            matrix = np.array(
                [[1, 0], [0, np.exp(1j * math.pi / 4)]],
                dtype=np.complex128,
            )
        elif name == "rx":
            theta = float(cast(float, operation.params[0]))
            matrix = np.array(
                [
                    [math.cos(theta / 2), -1j * math.sin(theta / 2)],
                    [-1j * math.sin(theta / 2), math.cos(theta / 2)],
                ],
                dtype=np.complex128,
            )
        elif name == "ry":
            theta = float(cast(float, operation.params[0]))
            matrix = np.array(
                [
                    [math.cos(theta / 2), -math.sin(theta / 2)],
                    [math.sin(theta / 2), math.cos(theta / 2)],
                ],
                dtype=np.complex128,
            )
        elif name == "rz":
            theta = float(cast(float, operation.params[0]))
            matrix = np.array(
                [[np.exp(-0.5j * theta), 0], [0, np.exp(0.5j * theta)]],
                dtype=np.complex128,
            )
        else:
            matrix = None

        if matrix is not None:
            evolved = _apply_single(evolved, ir.qubit_count, operation.qubits[0], matrix)
        elif name == "cx":
            evolved = _apply_controlled_x(evolved, operation.qubits[0], operation.qubits[1])
        elif name == "cz":
            evolved = _apply_controlled_z(evolved, operation.qubits[0], operation.qubits[1])
        elif name == "swap":
            evolved = _apply_swap(evolved, operation.qubits[0], operation.qubits[1])
        else:  # pragma: no cover - the benchmark corpus has a frozen gate inventory
            raise ValueError(f"Unsupported exact-equivalence gate {name!r}.")
    return evolved


def _apply_single(state: Any, qubit_count: int, qubit: int, matrix: Any) -> Any:
    out = state.copy()
    step = 1 << qubit
    for base in range(0, 1 << qubit_count, step * 2):
        for offset in range(step):
            zero = base + offset
            one = zero + step
            out[zero] = matrix[0, 0] * state[zero] + matrix[0, 1] * state[one]
            out[one] = matrix[1, 0] * state[zero] + matrix[1, 1] * state[one]
    return out


def _apply_controlled_x(state: Any, control: int, target: int) -> Any:
    out = state.copy()
    control_mask = 1 << control
    target_mask = 1 << target
    for index in range(state.size):
        if index & control_mask and not index & target_mask:
            partner = index | target_mask
            out[index], out[partner] = state[partner], state[index]
    return out


def _apply_controlled_z(state: Any, control: int, target: int) -> Any:
    out = state.copy()
    mask = (1 << control) | (1 << target)
    for index in range(state.size):
        if index & mask == mask:
            out[index] = -state[index]
    return out


def _apply_swap(state: Any, left: int, right: int) -> Any:
    out = state.copy()
    left_mask = 1 << left
    right_mask = 1 << right
    for index in range(state.size):
        if bool(index & left_mask) == bool(index & right_mask):
            continue
        partner = index ^ left_mask ^ right_mask
        if index < partner:
            out[index], out[partner] = state[partner], state[index]
    return out


def _qplanck_exact_equivalence(case: BenchmarkCase, compiled: Any) -> bool:
    logical_qubits = case.workload.qubit_count
    physical_qubits = compiled.ir.qubit_count
    logical_dimension = 1 << logical_qubits
    physical_dimension = 1 << physical_qubits
    expected = np.zeros((physical_dimension, logical_dimension), dtype=np.complex128)
    actual = np.zeros((physical_dimension, logical_dimension), dtype=np.complex128)
    for basis in range(logical_dimension):
        logical_state = np.zeros(logical_dimension, dtype=np.complex128)
        logical_state[basis] = 1.0
        logical_output = _apply_ir(case.workload.ir, logical_state)
        for logical_index, amplitude in enumerate(logical_output):
            expected[_encoded_index(logical_index, compiled.final_layout), basis] = amplitude

        physical_state = np.zeros(physical_dimension, dtype=np.complex128)
        physical_state[_encoded_index(basis, compiled.initial_layout)] = 1.0
        actual[:, basis] = _apply_ir(compiled.ir, physical_state)

    overlap = np.vdot(expected.ravel(), actual.ravel())
    phase = 1.0 + 0.0j if abs(overlap) < 1e-15 else overlap / abs(overlap)
    return bool(np.allclose(actual, phase * expected, rtol=1e-9, atol=1e-9))


def _ir_operator(ir: CircuitIR) -> Any:
    dimension = 1 << ir.qubit_count
    operator = np.zeros((dimension, dimension), dtype=np.complex128)
    for basis in range(dimension):
        state = np.zeros(dimension, dtype=np.complex128)
        state[basis] = 1.0
        operator[:, basis] = _apply_ir(ir, state)
    return operator


def _operators_equivalent(left: CircuitIR, right: CircuitIR) -> bool:
    if left.qubit_count != right.qubit_count:
        return False
    expected = _ir_operator(left)
    actual = _ir_operator(right)
    overlap = np.vdot(expected.ravel(), actual.ravel())
    phase = 1.0 + 0.0j if abs(overlap) < 1e-15 else overlap / abs(overlap)
    return bool(np.allclose(actual, phase * expected, rtol=1e-9, atol=1e-9))


def _operation_matches(source: Any, routed: Any, layout: Any) -> bool:
    parameters_match = len(source.params) == len(routed.params) and all(
        math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
        for left, right in zip(source.params, routed.params, strict=True)
    )
    return (
        source.name == routed.name
        and tuple(layout.logical_to_physical[item] for item in source.qubits) == routed.qubits
        and parameters_match
        and dict(source.metadata) == dict(routed.metadata)
    )


def _qplanck_routing_invariant(
    case: BenchmarkCase,
    compiled: Any,
    routed_source_ir: CircuitIR,
) -> dict[str, bool]:
    if case.target is None:
        raise ValueError("Routing invariant validation requires a benchmark target.")
    target = case.target.target
    trace = compiled.routing_trace
    routed_ir = compiled.routed_ir
    source_ir = routed_source_ir
    if trace is None or routed_ir is None:
        return {
            "mapping_bijective": False,
            "routing_symbolic_consistent": False,
            "basis_lowering_exact": False,
            "measurement_remap_consistent": False,
            "topology_conformant": False,
        }

    def layout_valid(layout: Any) -> bool:
        values = tuple(layout.logical_to_physical)
        return (
            len(values) == source_ir.qubit_count
            and len(set(values)) == source_ir.qubit_count
            and all(0 <= item < target.qubit_count for item in values)
        )

    mapping_bijective = layout_valid(compiled.initial_layout) and layout_valid(
        compiled.final_layout
    )
    source_mapping = trace.source_to_routed_indices
    mapped_indices = [indices[0] for indices in source_mapping if len(indices) == 1]
    source_by_routed = {
        routed_index: source_index
        for source_index, indices in enumerate(source_mapping)
        for routed_index in indices
    }
    symbolic = (
        mapping_bijective
        and trace.initial_layout == compiled.initial_layout
        and trace.final_layout == compiled.final_layout
        and len(source_mapping) == len(source_ir.operations)
        and len(mapped_indices) == len(source_ir.operations)
        and len(set(mapped_indices)) == len(source_ir.operations)
        and all(0 <= index < len(routed_ir.operations) for index in mapped_indices)
    )
    current = compiled.initial_layout
    step_cursor = 0
    if symbolic:
        for routed_index, operation in enumerate(routed_ir.operations):
            source_index = source_by_routed.get(routed_index)
            if source_index is not None:
                symbolic = _operation_matches(
                    source_ir.operations[source_index],
                    operation,
                    current,
                )
            elif step_cursor < len(trace.steps):
                step = trace.steps[step_cursor]
                expected_after = current.swap_physical(*step.physical_edge)
                symbolic = (
                    step.index == step_cursor
                    and step.layout_before == current
                    and step.layout_after == expected_after
                    and target.topology.has_weak_edge(*step.physical_edge)
                    and operation.name == "swap"
                    and operation.qubits == step.physical_edge
                    and operation.metadata.get("qplanck.inserted") == "routing"
                    and operation.metadata.get("routing_step") == step.index
                )
                current = expected_after
                step_cursor += 1
            else:
                symbolic = False
            if not symbolic:
                break
    symbolic = bool(
        symbolic and step_cursor == len(trace.steps) and current == compiled.final_layout
    )

    lowering_exact = len(trace.routed_to_final_indices) == len(routed_ir.operations)
    flattened = [index for indices in trace.routed_to_final_indices for index in indices]
    lowering_exact = lowering_exact and sorted(flattened) == list(
        range(len(compiled.ir.operations))
    )
    if lowering_exact:
        for routed_operation, final_indices in zip(
            routed_ir.operations,
            trace.routed_to_final_indices,
            strict=True,
        ):
            if not final_indices or tuple(final_indices) != tuple(
                range(final_indices[0], final_indices[-1] + 1)
            ):
                lowering_exact = False
                break
            physical_qubits = tuple(sorted(routed_operation.qubits))
            physical_to_local = {physical: local for local, physical in enumerate(physical_qubits)}
            final_operations = tuple(compiled.ir.operations[index] for index in final_indices)
            if any(
                any(qubit not in physical_to_local for qubit in operation.qubits)
                for operation in final_operations
            ):
                lowering_exact = False
                break
            source_local = CircuitIR(
                len(physical_qubits),
                (
                    Operation(
                        routed_operation.name,
                        tuple(physical_to_local[item] for item in routed_operation.qubits),
                        routed_operation.params,
                    ),
                ),
            )
            final_local = CircuitIR(
                len(physical_qubits),
                tuple(
                    Operation(
                        operation.name,
                        tuple(physical_to_local[item] for item in operation.qubits),
                        operation.params,
                    )
                    for operation in final_operations
                ),
            )
            if not _operators_equivalent(source_local, final_local):
                lowering_exact = False
                break

    expected_measurements = tuple(
        (
            measurement.qubit,
            compiled.final_layout.logical_to_physical[measurement.qubit],
            measurement.cbit,
        )
        for measurement in source_ir.measurements
    )
    final_measurements = tuple(
        (measurement.qubit, measurement.cbit) for measurement in compiled.ir.measurements
    )
    measurement_consistent = (
        trace.measurement_map == expected_measurements
        and final_measurements
        == tuple((physical, cbit) for _logical, physical, cbit in expected_measurements)
        and compiled.ir.measurements == routed_ir.measurements
    )
    topology_conformant = all(
        target.supports_operation(operation) for operation in compiled.ir.operations
    )
    return {
        "mapping_bijective": mapping_bijective,
        "routing_symbolic_consistent": symbolic,
        "basis_lowering_exact": bool(lowering_exact),
        "measurement_remap_consistent": measurement_consistent,
        "topology_conformant": topology_conformant,
    }


def _qplanck_correctness(
    case: BenchmarkCase,
    compiled: Any,
    routed_source_ir: CircuitIR | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    if case.target is None:
        passed = compiled.ir.qubit_count == case.workload.qubit_count
        return (
            passed,
            "O1 IR contract",
            {
                "kind": "o1-semantic-hash",
                "verified": passed,
                "source_semantic_hash": case.workload.semantic_hash,
                "output_semantic_hash": compiled.trace.output_ir_hash,
            },
        )
    target = case.target.target
    if compiled.target_hash != target.content_hash:
        return False, "compiled target hash differs from the case target", {}
    unsupported = [
        operation
        for operation in compiled.ir.operations
        if not target.supports_operation(operation)
    ]
    if unsupported:
        return False, f"{len(unsupported)} final operations violate target constraints", {}
    if (
        compiled.routing_trace is None
        or compiled.initial_layout is None
        or compiled.final_layout is None
    ):
        return False, "O2 routing evidence is incomplete", {}
    if routed_source_ir is None:
        return False, "optimized pre-routing oracle evidence is missing", {}
    invariant = _qplanck_routing_invariant(case, compiled, routed_source_ir)
    invariant_passed = all(invariant.values())
    if case.workload.qubit_count <= 5:
        exact = invariant_passed and _qplanck_exact_equivalence(case, compiled)
        return (
            exact,
            "exact encoded statevector-matrix equivalence",
            {
                "kind": "exact-statevector-matrix-equivalence",
                "verified": exact,
                "atol": 1e-9,
                "rtol": 1e-9,
                "logical_dimension": 1 << case.workload.qubit_count,
                "source_semantic_hash": case.workload.semantic_hash,
                **invariant,
            },
        )
    evidence = {
        "kind": "qplanck-routing-permutation-invariant",
        "verified": invariant_passed,
        "source_semantic_hash": case.workload.semantic_hash,
        "initial_layout_hash": canonical_hash(compiled.initial_layout.to_dict()),
        "final_layout_hash": canonical_hash(compiled.final_layout.to_dict()),
        "routing_trace_hash": canonical_hash(compiled.routing_trace.to_dict()),
        **invariant,
    }
    return invariant_passed, "symbolic routing and exact basis-lowering invariants", evidence


def _run_qplanck(
    case: BenchmarkCase,
    *,
    oracle: bool,
    validate: bool = True,
) -> CompilerOutcome:
    compiler = importlib.import_module("qplanck.compiler")
    options = CompileOptions(optimization_level=case.optimization_level)
    if oracle:
        reference = getattr(compiler, "_compile_reference", None)
        if not callable(reference):
            raise EngineUnavailableError("Frozen Python oracle is unavailable.")
        if case.target is not None:
            raise EngineUnavailableError("The frozen Python oracle supports O0/O1 only.")
        compiled = reference(case.workload.ir, options)
    else:
        compile_program = compiler.compile
        compiled = compile_program(
            case.workload.ir,
            options,
            target=None if case.target is None else case.target.target,
        )
    if validate:
        routed_source_ir = None
        if case.target is not None:
            reference = getattr(compiler, "_compile_reference", None)
            if not callable(reference):
                raise EngineUnavailableError("Frozen Python oracle is unavailable.")
            routed_source_ir = reference(
                case.workload.ir,
                CompileOptions(optimization_level=1),
            ).ir
        correctness, detail, semantic_evidence = _qplanck_correctness(
            case,
            compiled,
            routed_source_ir,
        )
    else:
        correctness = True
        detail = "semantic validation intentionally excluded from timed compilation"
        semantic_evidence = {}
    return CompilerOutcome(
        artifact_hash=compiled.content_hash,
        semantic_hash=compiled.trace.output_ir_hash,
        quality=_qplanck_quality(case, compiled),
        correctness_passed=correctness,
        correctness_method="qplanck-contract",
        correctness_detail=detail,
        semantic_evidence=semantic_evidence,
    )


def _qiskit_payload(circuit: Any) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for instruction in circuit.data:
        operation = instruction.operation
        payload.append(
            {
                "name": str(operation.name),
                "qubits": [circuit.find_bit(qubit).index for qubit in instruction.qubits],
                "params": [str(parameter) for parameter in operation.params],
            }
        )
    return payload


def _run_qiskit(case: BenchmarkCase, *, validate: bool = True) -> CompilerOutcome:
    if case.target is None:
        raise EngineUnavailableError("Qiskit comparison is defined for routing cases only.")
    qiskit = importlib.import_module("qiskit")
    source = case.workload.ir
    from qplanck.circuit import Circuit

    provider_circuit = Circuit.from_ir(source).to_qiskit()
    topology = case.target.target.topology
    coupling_edges = list(topology.edges)
    if not topology.directed:
        coupling_edges.extend((right, left) for left, right in topology.edges)
    transpile: Callable[..., Any] = qiskit.transpile
    compiled = transpile(
        provider_circuit,
        basis_gates=sorted(case.target.target.basis_gates),
        coupling_map=coupling_edges,
        optimization_level=1,
        seed_transpiler=0,
        layout_method="sabre",
        routing_method="sabre",
        num_processes=1,
    )
    payload = _qiskit_payload(compiled)
    source_metrics = _source_metrics(source)
    output_two_qubit = sum(len(item["qubits"]) == 2 for item in payload)
    bad_edges = [
        item
        for item in payload
        if len(item["qubits"]) == 2
        and not topology.has_weak_edge(item["qubits"][0], item["qubits"][1])
    ]
    semantic_payload = {
        "operations": payload,
        "final_layout": str(getattr(compiled, "layout", None)),
    }
    layout = getattr(compiled, "layout", None)
    final_index_layout = getattr(layout, "final_index_layout", None)
    try:
        physical_layout = (
            tuple(int(item) for item in final_index_layout(filter_ancillas=True))
            if callable(final_index_layout)
            else ()
        )
    except Exception:
        physical_layout = ()
    mapping_bijective = (
        len(physical_layout) == case.workload.qubit_count
        and len(set(physical_layout)) == case.workload.qubit_count
        and all(0 <= item < case.target.target.qubit_count for item in physical_layout)
    )
    topology_conformant = not bad_edges
    if not validate:
        semantic_detail = "semantic validation intentionally excluded from timed compilation"
        semantic_evidence = {}
        correctness = True
    elif case.workload.qubit_count <= 5:
        try:
            quantum_info = importlib.import_module("qiskit.quantum_info")
            operator_type = quantum_info.Operator
            source_operator = operator_type(provider_circuit)
            output_operator = operator_type.from_circuit(compiled)
            exact = bool(source_operator.equiv(output_operator, rtol=1e-9, atol=1e-9))
            semantic_detail = "exact Operator equivalence with transpiler layout applied"
        except Exception as error:
            exact = False
            semantic_detail = f"operator equivalence failed: {type(error).__name__}: {error}"
        semantic_evidence = {
            "kind": "exact-operator-equivalence",
            "verified": exact and mapping_bijective and topology_conformant,
            "source_semantic_hash": case.workload.semantic_hash,
            "atol": 1e-9,
            "rtol": 1e-9,
            "logical_dimension": 1 << case.workload.qubit_count,
            "layout_hash": canonical_hash(list(physical_layout)),
            "mapping_bijective": mapping_bijective,
            "topology_conformant": topology_conformant,
        }
    else:
        semantic_detail = "layout permutation and coupling-map invariants"
        semantic_evidence = {
            "kind": "qiskit-layout-permutation-invariant",
            "verified": mapping_bijective and topology_conformant,
            "source_semantic_hash": case.workload.semantic_hash,
            "layout_hash": canonical_hash(list(physical_layout)),
            "mapping_bijective": mapping_bijective,
            "topology_conformant": topology_conformant,
        }
    if validate:
        correctness = bool(semantic_evidence["verified"])
    return CompilerOutcome(
        artifact_hash=canonical_hash(semantic_payload),
        semantic_hash=canonical_hash(semantic_payload),
        quality=QualityMetrics(
            source_operations=source_metrics.operation_count,
            output_operations=len(payload),
            source_two_qubit_gates=source_metrics.two_qubit_gate_count,
            output_two_qubit_gates=output_two_qubit,
            added_two_qubit_gates=max(
                0,
                output_two_qubit - source_metrics.two_qubit_gate_count,
            ),
            depth=int(compiled.depth() or 0),
            conceptual_swaps=sum(item["name"] == "swap" for item in payload),
        ),
        correctness_passed=correctness,
        correctness_method="qiskit-semantic-and-topology",
        correctness_detail=(
            semantic_detail
            if correctness
            else (
                f"{semantic_detail}; mapping_bijective={mapping_bijective}; "
                f"topology_violations={len(bad_edges)}"
            )
        ),
        semantic_evidence=semantic_evidence,
    )


def _cirq_source(ir: CircuitIR, cirq: Any) -> tuple[Any, tuple[Any, ...]]:
    qubits = tuple(cirq.LineQubit(index) for index in range(ir.qubit_count))
    operations: list[Any] = []
    for operation in ir.operations:
        selected = tuple(qubits[index] for index in operation.qubits)
        if operation.name == "h":
            gate = cirq.H
        elif operation.name == "x":
            gate = cirq.X
        elif operation.name == "y":
            gate = cirq.Y
        elif operation.name == "z":
            gate = cirq.Z
        elif operation.name == "s":
            gate = cirq.S
        elif operation.name == "t":
            gate = cirq.T
        elif operation.name == "rx":
            gate = cirq.rx(float(cast(float, operation.params[0])))
        elif operation.name == "ry":
            gate = cirq.ry(float(cast(float, operation.params[0])))
        elif operation.name == "rz":
            gate = cirq.rz(float(cast(float, operation.params[0])))
        elif operation.name == "cx":
            gate = cirq.CNOT
        elif operation.name == "cz":
            gate = cirq.CZ
        elif operation.name == "swap":
            gate = cirq.SWAP
        else:  # pragma: no cover - corpus is constrained to QCore gates
            raise ValueError(f"Unsupported Cirq benchmark gate {operation.name!r}.")
        operations.append(gate.on(*selected))
    return cirq.Circuit(operations), qubits


def _cirq_decompose_swaps(circuit: Any, cirq: Any) -> tuple[Any, int]:
    operations: list[Any] = []
    swaps = 0
    for operation in circuit.all_operations():
        gate = operation.gate
        if isinstance(gate, cirq.SwapPowGate) and float(gate.exponent) % 2 == 1:
            left, right = operation.qubits
            operations.extend(
                (cirq.CNOT(left, right), cirq.CNOT(right, left), cirq.CNOT(left, right))
            )
            swaps += 1
        else:
            operations.append(operation)
    return cirq.Circuit(operations), swaps


def _run_cirq(case: BenchmarkCase, *, validate: bool = True) -> CompilerOutcome:
    if case.target is None:
        raise EngineUnavailableError("Cirq comparison is defined for routing cases only.")
    cirq = importlib.import_module("cirq")
    nx = importlib.import_module("networkx")
    provider_circuit, qubits = _cirq_source(case.workload.ir, cirq)
    graph = nx.Graph()
    graph.add_nodes_from(qubits)
    graph.add_edges_from(
        (qubits[left], qubits[right]) for left, right in case.target.target.topology.edges
    )
    routed, initial_mapping, swap_mapping = cirq.RouteCQC(graph).route_circuit(provider_circuit)
    compiled, conceptual_swaps = _cirq_decompose_swaps(routed, cirq)
    payload: list[dict[str, Any]] = []
    bad_edges = 0
    topology = case.target.target.topology
    for operation in compiled.all_operations():
        physical = [int(qubit.x) for qubit in operation.qubits]
        if len(physical) == 2 and not topology.has_weak_edge(physical[0], physical[1]):
            bad_edges += 1
        payload.append(
            {
                "gate": str(operation.gate),
                "qubits": physical,
            }
        )
    source_metrics = _source_metrics(case.workload.ir)
    output_two_qubit = sum(len(item["qubits"]) == 2 for item in payload)
    semantic_payload = {
        "operations": payload,
        "initial_mapping": sorted((str(key), str(value)) for key, value in initial_mapping.items()),
        "swap_mapping": sorted((str(key), str(value)) for key, value in swap_mapping.items()),
    }
    initial_values = tuple(initial_mapping.values())
    mapping_bijective = (
        len(initial_mapping) == case.workload.qubit_count
        and set(initial_mapping) == set(qubits)
        and len(set(initial_values)) == case.workload.qubit_count
        and set(initial_values) == set(qubits)
        and len(swap_mapping) == case.workload.qubit_count
        and set(swap_mapping) == set(qubits)
        and set(swap_mapping.values()) == set(qubits)
    )
    topology_conformant = bad_edges == 0
    if not validate:
        semantic_detail = "semantic validation intentionally excluded from timed compilation"
        semantic_evidence = {}
        correctness = True
    elif case.workload.qubit_count <= 5:
        exact = False
        try:
            corrected = routed.copy()
            initial_qubits, sorted_qubits = zip(
                *sorted(swap_mapping.items(), key=lambda item: item[1]),
                strict=True,
            )
            inverse_permutation = [sorted_qubits.index(qubit) for qubit in initial_qubits]
            corrected.append(cirq.QubitPermutationGate(inverse_permutation).on(*sorted_qubits))
            _logical, qubit_order = zip(
                *sorted(initial_mapping.items(), key=lambda item: item[0]),
                strict=True,
            )
            cirq.testing.assert_allclose_up_to_global_phase(
                provider_circuit.unitary(),
                corrected.unitary(qubit_order=qubit_order),
                atol=1e-9,
            )
            exact = True
            semantic_detail = "exact unitary equivalence with router permutations applied"
        except Exception as error:
            semantic_detail = f"unitary equivalence failed: {type(error).__name__}: {error}"
        semantic_evidence = {
            "kind": "exact-operator-equivalence",
            "verified": exact and mapping_bijective and topology_conformant,
            "source_semantic_hash": case.workload.semantic_hash,
            "atol": 1e-9,
            "logical_dimension": 1 << case.workload.qubit_count,
            "initial_mapping_hash": canonical_hash(semantic_payload["initial_mapping"]),
            "swap_mapping_hash": canonical_hash(semantic_payload["swap_mapping"]),
            "mapping_bijective": mapping_bijective,
            "topology_conformant": topology_conformant,
        }
    else:
        semantic_detail = "router initial/final permutation and device-graph invariants"
        semantic_evidence = {
            "kind": "cirq-router-permutation-invariant",
            "verified": mapping_bijective and topology_conformant,
            "source_semantic_hash": case.workload.semantic_hash,
            "initial_mapping_hash": canonical_hash(semantic_payload["initial_mapping"]),
            "swap_mapping_hash": canonical_hash(semantic_payload["swap_mapping"]),
            "mapping_bijective": mapping_bijective,
            "topology_conformant": topology_conformant,
        }
    if validate:
        correctness = bool(semantic_evidence["verified"])
    return CompilerOutcome(
        artifact_hash=canonical_hash(semantic_payload),
        semantic_hash=canonical_hash(semantic_payload),
        quality=QualityMetrics(
            source_operations=source_metrics.operation_count,
            output_operations=len(payload),
            source_two_qubit_gates=source_metrics.two_qubit_gate_count,
            output_two_qubit_gates=output_two_qubit,
            added_two_qubit_gates=max(
                0,
                output_two_qubit - source_metrics.two_qubit_gate_count,
            ),
            depth=len(compiled),
            conceptual_swaps=conceptual_swaps,
        ),
        correctness_passed=correctness,
        correctness_method="cirq-semantic-and-topology",
        correctness_detail=(
            semantic_detail
            if correctness
            else (
                f"{semantic_detail}; mapping_bijective={mapping_bijective}; "
                f"topology_violations={bad_edges}"
            )
        ),
        semantic_evidence=semantic_evidence,
    )


def run_engine(
    engine: str,
    case: BenchmarkCase,
    *,
    validate: bool = True,
) -> CompilerOutcome:
    """Compile one case with a verified engine pin and return normalized evidence."""

    _require_engine(engine)
    if engine == QPLANCK_ENGINE:
        return _run_qplanck(case, oracle=False, validate=validate)
    if engine == ORACLE_ENGINE:
        return _run_qplanck(case, oracle=True, validate=validate)
    if engine == QISKIT_ENGINE:
        return _run_qiskit(case, validate=validate)
    if engine == CIRQ_ENGINE:
        return _run_cirq(case, validate=validate)
    raise ValueError(f"Unknown benchmark engine {engine!r}.")


def pinned_environment() -> dict[str, dict[str, str | bool | None]]:
    return {engine: engine_status(engine).to_dict() for engine in ENGINE_NAMES}


__all__ = [
    "CIRQ_ENGINE",
    "ENGINE_NAMES",
    "EngineStatus",
    "EngineUnavailableError",
    "ORACLE_ENGINE",
    "PINNED_DEPENDENCIES",
    "QISKIT_ENGINE",
    "QPLANCK_ENGINE",
    "engine_status",
    "pinned_environment",
    "run_engine",
]
