import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from qplanck import (
    Circuit,
    ExecutionTrace,
    ResourceLimitError,
    Simulator,
    UnsupportedOperationError,
)


def test_single_qubit_h_probabilities() -> None:
    probabilities = Simulator().probabilities(Circuit(1).h(0)).probabilities

    assert probabilities["0"] == pytest.approx(0.5)
    assert probabilities["1"] == pytest.approx(0.5)


def test_bell_state_statevector_and_counts_are_seeded() -> None:
    circuit = Circuit(2).h(0).cx(0, 1).measure_all()
    simulator = Simulator()

    state = simulator.statevector(circuit).statevector
    assert state[0] == pytest.approx(1 / math.sqrt(2))
    assert state[3] == pytest.approx(1 / math.sqrt(2))
    assert state[1] == pytest.approx(0)
    assert state[2] == pytest.approx(0)

    result_a = simulator.run(circuit, shots=32, seed=123)
    result_b = simulator.run(circuit, shots=32, seed=123)
    assert result_a.measurements == result_b.measurements
    assert set(result_a.counts) <= {"00", "11"}


def test_ghz_state_probabilities() -> None:
    circuit = Circuit(3).h(0).cx(0, 1).cx(1, 2)
    probabilities = Simulator().probabilities(circuit).probabilities

    assert probabilities["000"] == pytest.approx(0.5)
    assert probabilities["111"] == pytest.approx(0.5)
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_rotations() -> None:
    circuit = Circuit(1).rx(math.pi, 0)
    probabilities = Simulator().probabilities(circuit).probabilities

    assert probabilities["0"] == pytest.approx(0.0, abs=1e-12)
    assert probabilities["1"] == pytest.approx(1.0)


def test_trace_json_round_trip() -> None:
    circuit = Circuit(2, name="trace").h(0).cx(0, 1).measure_all()
    trace = Simulator().run(circuit, trace=True).trace

    assert trace is not None
    assert trace.metadata["endianness"] == "little"
    assert len(trace.steps) == 3
    assert trace.steps[0].operation is None
    assert trace.steps[-1].probabilities["11"] == pytest.approx(0.5)

    restored = ExecutionTrace.from_json(trace.to_json())
    assert restored.to_dict() == trace.to_dict()


def test_trace_qubit_limit() -> None:
    with pytest.raises(UnsupportedOperationError, match="at most 8 qubits"):
        Simulator().run(Circuit(9), trace=True)


def test_explicit_measurements_map_qubits_to_classical_bits() -> None:
    circuit = Circuit(3).x(0).x(2).measure(0, 2).measure(1, 0)

    result = Simulator().run(circuit, shots=4, seed=7)

    assert result.counts == {"100": 4}
    assert result.measurements == ["100"] * 4
    assert result.metadata["basis_key_order"] == "c[n-1]...c[0]"
    assert result.metadata["measurement_mode"] == "explicit"


def test_unmeasured_circuit_retains_implicit_all_qubits_sampling() -> None:
    result = Simulator().run(Circuit(2).x(1), shots=2, seed=7)

    assert result.counts == {"10": 2}
    assert result.metadata["measurement_mode"] == "implicit-all-qubits"


def test_statevector_allocation_is_rejected_before_budget_is_exceeded() -> None:
    simulator = Simulator(max_statevector_bytes=16)

    with pytest.raises(ResourceLimitError, match="32 bytes"):
        simulator.run(Circuit(1).h(0))


@given(st.floats(min_value=-2 * math.pi, max_value=2 * math.pi, allow_nan=False))
def test_probability_normalization(theta: float) -> None:
    circuit = Circuit(1).rx(theta, 0).ry(theta / 2, 0).rz(theta / 3, 0)
    probabilities = Simulator().probabilities(circuit).probabilities

    assert np.isfinite(list(probabilities.values())).all()
    assert sum(probabilities.values()) == pytest.approx(1.0)
