"""Optional Qiskit round-trip example."""

from qplanck import Circuit, InteropError


def main() -> None:
    circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
    try:
        qiskit_circuit = circuit.to_qiskit()
        restored = Circuit.from_qiskit(qiskit_circuit)
    except InteropError as exc:
        print(f"Qiskit optional dependency unavailable or unsupported: {exc}")
        return

    print(restored.draw())
    print(restored.to_qasm3())


if __name__ == "__main__":
    main()
