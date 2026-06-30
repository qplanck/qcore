import pytest

from qplanck import Circuit, Operation, UnsupportedOperationError, gates
from qplanck.errors import CircuitError


def test_fluent_api_and_gate_builders() -> None:
    circuit = Circuit(2, name="bell").add(gates.H(0)).cx(0, 1).measure_all()

    assert circuit.name == "bell"
    assert [operation.name for operation in circuit.operations] == ["h", "cx"]
    assert [(measurement.qubit, measurement.cbit) for measurement in circuit.measurements] == [
        (0, 0),
        (1, 1),
    ]
    assert "q0" in circuit.draw()
    assert "*" in circuit.draw()


def test_gates_after_measurement_are_rejected() -> None:
    circuit = Circuit(1).measure_all()

    with pytest.raises(UnsupportedOperationError, match="terminal measurements"):
        circuit.h(0)


def test_validation_rejects_bad_operations() -> None:
    with pytest.raises(UnsupportedOperationError):
        Circuit(1).add(Operation("swap", (0, 1)))

    with pytest.raises(CircuitError):
        Circuit(1).cx(0, 0)

    with pytest.raises(CircuitError):
        Circuit(1).h(2)


def test_measurement_validation() -> None:
    circuit = Circuit(2).measure(0, 0)

    with pytest.raises(CircuitError, match="already been measured"):
        circuit.measure(0, 1)
    with pytest.raises(CircuitError, match="already assigned"):
        circuit.measure(1, 0)


def test_circuit_json_round_trip() -> None:
    circuit = Circuit(2, name="json").h(0).cx(0, 1).measure_all()
    restored = Circuit.from_json(circuit.to_json())

    assert restored.to_dict() == circuit.to_dict()
