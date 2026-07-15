import json
from dataclasses import FrozenInstanceError
from math import pi

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from qplanck import Circuit, CircuitIR, MeasurementSpec, Operation, Parameter, Simulator
from qplanck.compiler import (
    CompileOptions,
    DependencyGraph,
    ResourceMetrics,
    compile,
)
from qplanck.errors import CircuitError


def test_dependency_graph_tracks_only_direct_qubit_conflicts() -> None:
    ir = CircuitIR(
        3,
        operations=(
            Operation("h", (0,)),
            Operation("x", (1,)),
            Operation("cx", (0, 1)),
            Operation("z", (2,)),
            Operation("cz", (1, 2)),
        ),
    )

    graph = DependencyGraph.from_ir(ir)

    assert graph.nodes == (0, 1, 2, 3, 4)
    assert graph.edges == ((0, 2), (1, 2), (2, 4), (3, 4))
    assert graph.predecessors_of(2) == (0, 1)
    assert graph.successors_of(2) == (4,)
    assert graph.depth == 3


def test_dependency_graph_is_canonical_and_immutable() -> None:
    graph = DependencyGraph(operation_count=3, edges=((1, 2), (0, 2), (0, 2)))

    assert graph.edges == ((0, 2), (1, 2))
    with pytest.raises(FrozenInstanceError):
        graph.operation_count = 4  # type: ignore[misc]
    with pytest.raises(ValueError, match="source operation order"):
        DependencyGraph(operation_count=2, edges=((1, 0),))


@pytest.mark.parametrize("gate", ["h", "x", "y", "z", "cx", "cz"])
def test_compile_cancels_adjacent_self_inverse_gates(gate: str) -> None:
    qubits = (0,) if gate in {"h", "x", "y", "z"} else (0, 1)
    ir = CircuitIR(2, operations=(Operation(gate, qubits), Operation(gate, qubits)))

    compiled = compile(ir)

    assert compiled.operations == ()
    rewrite = compiled.trace.events[1].rewrites[0]
    assert rewrite.rule == "self-inverse-adjacent"
    assert rewrite.source_indices == (0, 1)
    assert rewrite.after == ()


def test_graph_local_cancellation_can_cross_disjoint_operations() -> None:
    circuit = Circuit(2).h(0).x(1).h(0)

    compiled = compile(circuit)

    assert compiled.operations == (Operation("x", (1,)),)
    assert compiled.trace.events[1].rewrites[0].source_indices == (0, 2)


def test_conflicting_gate_blocks_cancellation() -> None:
    circuit = Circuit(1).h(0).x(0).h(0)

    compiled = compile(circuit)

    assert compiled.operations == circuit.operations
    assert compiled.trace.events[1].rewrites == ()


def test_local_optimizer_reaches_cascading_rewrites_in_one_pass() -> None:
    circuit = Circuit(1).h(0).rx(0.25, 0).x(0).x(0).rx(-0.25, 0).h(0)

    compiled = compile(circuit)

    assert compiled.operations == ()
    assert [item.rule for item in compiled.trace.events[1].rewrites] == [
        "self-inverse-adjacent",
        "remove-near-zero-rotation",
        "self-inverse-adjacent",
    ]


def test_compile_merges_rotations_and_preserves_equal_metadata() -> None:
    metadata = {"calibration": "logical-only"}
    ir = CircuitIR(
        1,
        operations=(
            Operation("rz", (0,), (pi / 4,), metadata=metadata),
            Operation("rz", (0,), (pi / 2,), metadata=metadata),
        ),
    )

    compiled = compile(ir)

    assert len(compiled.operations) == 1
    assert compiled.operations[0].name == "rz"
    assert compiled.operations[0].params == pytest.approx((3 * pi / 4,))
    assert compiled.operations[0].metadata == metadata
    assert compiled.trace.events[1].rewrites[0].rule == "merge-adjacent-rotation"


def test_rotation_elision_has_an_explicit_tolerance() -> None:
    ir = CircuitIR(
        1,
        operations=(Operation("rx", (0,), (1.0,)), Operation("rx", (0,), (-1.0 + 1e-13,))),
    )

    strict = compile(ir)
    assert len(strict.operations) == 1
    assert strict.operations[0].params[0] != 0.0

    tolerant = compile(ir, CompileOptions(angle_tolerance=1e-12))
    assert tolerant.operations == ()


def test_rotation_metadata_mismatch_is_a_rewrite_boundary() -> None:
    ir = CircuitIR(
        1,
        operations=(
            Operation("ry", (0,), (0.1,), metadata={"source": "a"}),
            Operation("ry", (0,), (0.2,), metadata={"source": "b"}),
        ),
    )

    compiled = compile(ir)

    assert compiled.operations == ir.operations
    assert compiled.trace.events[1].rewrites == ()


def test_level_zero_validates_and_analyzes_without_rewrites() -> None:
    circuit = Circuit(1).x(0).x(0)

    compiled = compile(circuit, CompileOptions(optimization_level=0))

    assert compiled.ir is circuit.ir
    assert compiled.operations == circuit.operations
    assert [item.id for item in compiled.trace.passes] == [
        "validate.static",
        "analyze.resources",
    ]
    assert not compiled.trace.changed


def test_compile_preserves_circuit_and_measurement_metadata() -> None:
    ir = CircuitIR(
        2,
        operations=(Operation("h", (0,), metadata={"tag": "keep"}),),
        measurements=(
            MeasurementSpec(0, 3, metadata={"basis": "z"}),
            MeasurementSpec(1, 4, metadata={"basis": "z"}),
        ),
        metadata={"name": "metadata-demo", "owner": "test"},
    )

    compiled = compile(ir)

    assert compiled.ir.metadata == ir.metadata
    assert compiled.measurements == ir.measurements
    assert compiled.operations[0].metadata == ir.operations[0].metadata
    assert compiled.to_circuit().to_dict() == compiled.ir.to_dict()


def test_metrics_report_before_and_after_counts_and_dependency_depth() -> None:
    circuit = Circuit(2).h(0).h(0).x(1).cx(0, 1).measure_all()

    compiled = compile(circuit)

    assert compiled.before_metrics == ResourceMetrics.from_ir(circuit.ir)
    assert compiled.before_metrics.operation_count == 4
    assert compiled.before_metrics.measurement_count == 2
    assert compiled.before_metrics.gate_counts == {"cx": 1, "h": 2, "x": 1}
    assert compiled.after_metrics.operation_count == 2
    assert compiled.after_metrics.single_qubit_gate_count == 1
    assert compiled.after_metrics.two_qubit_gate_count == 1
    assert compiled.after_metrics.depth == 2
    assert compiled.after_metrics.gate_count("H") == 0
    assert compiled.after_metrics.gate_count("cx") == 1


def test_trace_is_stable_and_each_pass_has_hashes_and_metrics() -> None:
    circuit = Circuit(2, name="stable").h(0).h(0).cx(0, 1)

    first = compile(circuit)
    second = compile(circuit)

    assert first.trace == second.trace
    assert first.trace.pipeline_id == "qplanck.default-o1.v1"
    assert first.trace.input_ir_hash.startswith("sha256:")
    assert first.trace.output_ir_hash.startswith("sha256:")
    assert first.trace.changed
    assert [event.index for event in first.trace.events] == [0, 1, 2]
    assert [event.pass_id for event in first.trace.events] == [
        "validate.static",
        "opt.local-exact",
        "analyze.resources",
    ]
    assert first.trace.events[1].metrics_before.operation_count == 3
    assert first.trace.events[1].metrics_after.operation_count == 1


def test_compilation_artifacts_have_deterministic_json() -> None:
    compiled = compile(Circuit(2, name="artifact").h(0).h(0).cx(0, 1).measure_all())

    trace_payload = json.loads(compiled.trace.to_json())
    artifact_payload = json.loads(compiled.to_json())

    assert trace_payload["schema_version"] == "qplanck.compilation.trace.v0.1"
    assert trace_payload["events"][1]["rewrites"][0]["rule"] == "self-inverse-adjacent"
    assert artifact_payload["schema_version"] == "qplanck.compiled.v0.1"
    assert artifact_payload["source_graph"]["operation_count"] == 3
    assert artifact_payload["compiled_graph"]["operation_count"] == 1
    assert compiled.to_json() == compiled.to_json()


def test_compilation_is_idempotent() -> None:
    circuit = Circuit(1).h(0).rx(0.1, 0).rx(0.2, 0).h(0)

    once = compile(circuit)
    twice = compile(once.ir)

    assert twice.ir.to_dict() == once.ir.to_dict()
    assert not twice.trace.events[1].changed


@given(
    st.floats(min_value=-4 * pi, max_value=4 * pi, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-4 * pi, max_value=4 * pi, allow_nan=False, allow_infinity=False),
)
def test_rotation_merge_preserves_reference_statevector(theta: float, phi: float) -> None:
    circuit = Circuit(1).rx(theta, 0).rx(phi, 0)
    compiled = compile(circuit).to_circuit()

    before = Simulator().statevector(circuit).statevector
    after = Simulator().statevector(compiled).statevector

    assert np.allclose(before, after, rtol=1e-12, atol=1e-12)


def test_disjoint_graph_rewrites_preserve_reference_statevector() -> None:
    circuit = Circuit(3).h(0).x(2).h(0).rz(0.25, 1).rz(0.5, 1).cx(1, 2)
    compiled = compile(circuit).to_circuit()

    before = Simulator().statevector(circuit).statevector
    after = Simulator().statevector(compiled).statevector

    assert np.allclose(before, after, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize(
    "options",
    [
        CompileOptions(optimization_level=0),
        CompileOptions(optimization_level=1),
    ],
)
def test_compile_accepts_circuit_and_ir(options: CompileOptions) -> None:
    circuit = Circuit(1).h(0)

    assert compile(circuit, options).ir.to_dict() == compile(circuit.ir, options).ir.to_dict()


def test_compile_rejects_non_finite_and_symbolic_parameters() -> None:
    with pytest.raises(CircuitError, match="finite"):
        compile(CircuitIR(1, operations=(Operation("rx", (0,), (float("nan"),)),)))
    with pytest.raises(CircuitError, match="numeric gate parameters"):
        compile(CircuitIR(1, operations=(Operation("rx", (0,), (Parameter("theta"),)),)))


def test_compile_options_and_input_types_are_checked() -> None:
    with pytest.raises(ValueError, match="optimization_level"):
        CompileOptions(optimization_level=2)
    with pytest.raises(ValueError, match="angle_tolerance"):
        CompileOptions(angle_tolerance=float("inf"))
    with pytest.raises(TypeError, match="CircuitIR"):
        compile(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CompileOptions"):
        compile(Circuit(1), object())  # type: ignore[arg-type]
