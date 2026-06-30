"""Bell-state quick start for QCore."""

from qplanck import Circuit, Simulator


def main() -> None:
    circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
    result = Simulator("statevector").run(circuit, shots=1000, seed=7, trace=True)
    print(circuit.draw())
    print(result.counts)
    if result.trace is not None:
        print(result.trace.to_json(indent=2))


if __name__ == "__main__":
    main()
