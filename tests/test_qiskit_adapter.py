import pytest

from qplanck import Circuit
from qplanck.errors import InteropError

qiskit = pytest.importorskip("qiskit")


def test_qiskit_round_trip_supported_subset() -> None:
    circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()

    qiskit_circuit = circuit.to_qiskit()
    restored = Circuit.from_qiskit(qiskit_circuit)

    assert restored.to_dict() == circuit.to_dict()


def test_qiskit_rejects_unsupported_instruction() -> None:
    quantum_circuit = qiskit.QuantumCircuit(1)
    quantum_circuit.reset(0)

    with pytest.raises(InteropError, match="Unsupported Qiskit operation"):
        Circuit.from_qiskit(quantum_circuit)
