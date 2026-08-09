import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import qplanck.routing as routing_module
from qplanck import Circuit, Simulator
from qplanck.errors import RoutingError
from qplanck.ir import CircuitIR, Operation
from qplanck.routing import route
from qplanck.targets import InstructionSupport, Layout, Target, Topology


def _target(
    topology: Topology,
    basis: frozenset[str] = frozenset({"h", "x", "rz", "cx"}),
) -> Target:
    return Target(
        "test-target",
        topology,
        tuple(
            InstructionSupport(name, 2 if name in {"cx", "cz", "swap"} else 1)
            for name in sorted(basis)
        ),
    )


@st.composite
def _small_routing_cases(
    draw: st.DrawFn,
) -> tuple[int, tuple[tuple[str, tuple[int, ...], float | None], ...], int]:
    qubits = draw(st.integers(min_value=2, max_value=8))
    operation_count = draw(st.integers(min_value=1, max_value=12))
    operations: list[tuple[str, tuple[int, ...], float | None]] = []
    for _ in range(operation_count):
        name = draw(st.sampled_from(("h", "x", "rz", "cx", "cz")))
        if name in {"cx", "cz"}:
            left = draw(st.integers(min_value=0, max_value=qubits - 1))
            right = draw(st.sampled_from(tuple(item for item in range(qubits) if item != left)))
            operations.append((name, (left, right), None))
        elif name == "rz":
            operations.append(
                (
                    name,
                    (draw(st.integers(min_value=0, max_value=qubits - 1)),),
                    draw(st.sampled_from((-1.25, -0.5, 0.125, 0.75, 1.5))),
                )
            )
        else:
            operations.append((name, (draw(st.integers(min_value=0, max_value=qubits - 1)),), None))
    basis_state = draw(st.integers(min_value=0, max_value=(1 << qubits) - 1))
    return qubits, tuple(operations), basis_state


def _case_ir(
    qubits: int,
    operations: tuple[tuple[str, tuple[int, ...], float | None], ...],
) -> CircuitIR:
    lowered = tuple(
        Operation(name, operands, () if parameter is None else (parameter,))
        for name, operands, parameter in operations
    )
    return CircuitIR(qubits, lowered)


def _initialized_ir(ir: CircuitIR, basis_state: int, layout: Layout) -> CircuitIR:
    initialization = tuple(
        Operation("x", (layout.logical_to_physical[logical],))
        for logical in range(ir.qubit_count)
        if basis_state & (1 << logical)
    )
    return CircuitIR(ir.qubit_count, (*initialization, *ir.operations))


def _permute_logical_state_to_physical(
    state: tuple[complex, ...],
    layout: Layout,
) -> np.ndarray:
    expected = np.zeros(len(state), dtype=np.complex128)
    for logical_index, amplitude in enumerate(state):
        physical_index = 0
        for logical, physical in enumerate(layout.logical_to_physical):
            physical_index |= ((logical_index >> logical) & 1) << physical
        expected[physical_index] = amplitude
    return expected


def test_already_conforming_circuit_inserts_no_swaps() -> None:
    circuit = Circuit(3).h(0).cx(0, 1).cx(1, 2).measure_all()
    result = route(
        circuit.ir,
        _target(Topology.line(3)),
        initial_layout=Layout.identity(3),
    )

    assert result.trace.steps == ()
    assert result.initial_layout == result.final_layout == Layout.identity(3)
    assert [item.name for item in result.final_ir.operations] == ["h", "cx", "cx"]
    assert result.final_ir.measurements == circuit.measurements


def test_line_route_inserts_distance_minus_one_swaps_and_remaps_measurements() -> None:
    circuit = Circuit(3).cx(0, 2).measure(0, 0).measure(2, 1)
    result = route(
        circuit.ir,
        _target(Topology.line(3)),
        initial_layout=Layout.identity(3),
        placement_trials=1,
    )

    assert len(result.trace.steps) == 1
    assert result.trace.steps[0].physical_edge == (0, 1)
    assert result.final_layout.logical_to_physical == (1, 0, 2)
    assert [(item.qubit, item.cbit) for item in result.final_ir.measurements] == [(1, 0), (2, 1)]
    assert result.trace.measurement_map == ((0, 1, 0), (2, 2, 1))
    assert all(
        result.final_ir.qubit_count == 3 and abs(item.qubits[0] - item.qubits[1]) == 1
        for item in result.final_ir.operations
        if len(item.qubits) == 2
    )


def test_inserted_swap_changes_layout_but_source_swap_does_not() -> None:
    circuit = Circuit(3).swap(0, 2).cx(0, 2)
    result = route(
        circuit.ir,
        _target(Topology.line(3)),
        initial_layout=Layout.identity(3),
        placement_trials=1,
    )

    assert result.trace.steps
    assert any(
        item.metadata.get("qplanck.inserted") == "routing" for item in result.routed_ir.operations
    )
    source_swap = next(
        item
        for item in result.routed_ir.operations
        if item.name == "swap" and "qplanck.inserted" not in item.metadata
    )
    assert source_swap.qubits in {(0, 1), (1, 2)}


def test_directed_cx_is_reoriented_with_h_conjugation() -> None:
    target = _target(
        Topology(2, ((0, 1),), directed=True),
        frozenset({"h", "cx"}),
    )
    result = route(
        Circuit(2).cx(1, 0).ir,
        target,
        initial_layout=Layout.identity(2),
        placement_trials=1,
    )

    assert [item.name for item in result.final_ir.operations] == ["h", "h", "cx", "h", "h"]
    assert result.final_ir.operations[2].qubits == (0, 1)


def test_routing_is_byte_deterministic_and_baseline_is_always_present() -> None:
    ir = Circuit(5).cx(0, 4).cx(1, 3).cx(4, 2).measure_all().ir
    target = _target(Topology.line(5))

    first = route(ir, target, routing_seed=9)
    second = route(ir, target, routing_seed=9)

    assert first.final_ir.to_json() == second.final_ir.to_json()
    assert first.trace.to_json() == second.trace.to_json()
    assert len(first.trace.trials) == 5
    assert sum(item.baseline for item in first.trace.trials) == 1
    assert sum(item.selected for item in first.trace.trials) == 1


def test_each_generated_trial_runs_two_forward_reverse_refinements(monkeypatch) -> None:
    ir = Circuit(5).cx(0, 4).cx(1, 3).cx(4, 2).ir
    target = _target(Topology.line(5))
    operation_orders: list[tuple[tuple[str, tuple[int, ...]], ...]] = []
    original_route_trial = routing_module._route_trial

    def recording_route_trial(*args, **kwargs):
        trial_ir = args[0]
        operation_orders.append(
            tuple((operation.name, operation.qubits) for operation in trial_ir.operations)
        )
        return original_route_trial(*args, **kwargs)

    monkeypatch.setattr(routing_module, "_route_trial", recording_route_trial)
    result = route(ir, target, routing_seed=9, placement_trials=1)

    forward = tuple((operation.name, operation.qubits) for operation in ir.operations)
    assert operation_orders[:4] == [
        forward,
        tuple(reversed(forward)),
        forward,
        tuple(reversed(forward)),
    ]
    assert result.trace.trials[0].inserted_swaps == 0
    assert result.trace.trials[-1].baseline
    assert result.trace.trials[-1].inserted_swaps == 3


def test_routed_measurement_distribution_preserves_logical_semantics() -> None:
    source = Circuit(3).h(0).cx(0, 2).measure(0, 0).measure(2, 1)
    routed = route(
        source.ir,
        _target(Topology.line(4)),
        initial_layout=Layout((0, 2, 3)),
        placement_trials=1,
    )

    source_result = Simulator().run(source, shots=2_000, seed=17)
    routed_result = Simulator().run(Circuit.from_ir(routed.final_ir), shots=2_000, seed=17)

    assert source_result.counts == routed_result.counts
    assert np.isclose(sum(routed_result.probabilities.values()), 1.0)


@given(_small_routing_cases())
@settings(max_examples=25, deadline=None)
def test_routing_preserves_basis_state_semantics_up_to_eight_qubits(
    case: tuple[int, tuple[tuple[str, tuple[int, ...], float | None], ...], int],
) -> None:
    qubits, operations, basis_state = case
    source = _case_ir(qubits, operations)
    initial_layout = Layout.identity(qubits)
    routed = route(
        source,
        _target(Topology.line(qubits)),
        initial_layout=initial_layout,
        placement_trials=1,
    )

    source_state = (
        Simulator()
        .statevector(Circuit.from_ir(_initialized_ir(source, basis_state, initial_layout)))
        .statevector
    )
    routed_state = (
        Simulator()
        .statevector(Circuit.from_ir(_initialized_ir(routed.final_ir, basis_state, initial_layout)))
        .statevector
    )

    assert np.allclose(
        np.asarray(routed_state),
        _permute_logical_state_to_physical(source_state, routed.final_layout),
        atol=1.0e-12,
    )


def test_routing_rejects_width_components_basis_and_budget() -> None:
    with pytest.raises(RoutingError, match="exceeds target width"):
        route(Circuit(3).cx(0, 2).ir, _target(Topology.line(2)))

    disconnected = _target(Topology(4, ((0, 1), (2, 3))))
    with pytest.raises(RoutingError, match="cannot fit"):
        route(Circuit(3).cx(0, 1).cx(1, 2).ir, disconnected)

    no_h = _target(Topology(2, ((0, 1),), directed=True), frozenset({"cx"}))
    with pytest.raises(RoutingError, match="SWAP"):
        route(CircuitIR(2, (Operation("cx", (1, 0)),)), no_h)

    with pytest.raises(RoutingError, match="0-SWAP budget"):
        route(
            Circuit(3).cx(0, 2).ir,
            _target(Topology.line(3)),
            initial_layout=Layout.identity(3),
            placement_trials=1,
            max_inserted_swaps=0,
        )


def test_disconnected_component_assignment_backtracks_past_greedy_dead_end() -> None:
    # Logical sizes (3, 2, 2, 2) fit physical capacities (5, 4), but best-fit
    # decreasing first places 3 in 4 and eventually reaches a false dead end.
    topology = Topology(
        9,
        ((0, 1), (1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8)),
    )
    circuit = Circuit(9).cx(0, 1).cx(1, 2).cx(3, 4).cx(5, 6).cx(7, 8).measure_all()

    result = route(circuit.ir, _target(topology), routing_seed=11)

    first_component = set(range(5))
    second_component = set(range(5, 9))
    assert set(result.initial_layout.logical_to_physical[:5]) == first_component
    assert set(result.initial_layout.logical_to_physical[5:]) == second_component
    assert all(
        topology.has_weak_edge(*operation.qubits)
        for operation in result.final_ir.operations
        if len(operation.qubits) == 2
    )
