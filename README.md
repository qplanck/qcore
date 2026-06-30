# QCore

QCore by QPlanck Labs is the open-source framework and visual workspace for
quantum circuit development, debugging, and interoperability.

The product is called **QCore**. The Python package and command-line tool are
called **`qplanck`**.

## Why QCore?

QCore is built for one job first: helping you understand, inspect, and exchange
quantum circuits.

It combines:

- a clean Python circuit API
- a deterministic NumPy statevector simulator
- terminal measurement and seeded sampling
- ASCII circuit drawing
- portable execution traces for visual debuggers
- OpenQASM 3 subset import/export
- optional Qiskit subset import/export

## Install

```bash
pip install qplanck
qplanck doctor
```

For local development from this repository:

```bash
python -m pip install -e ".[dev]"
pytest
```

To run the optional Qiskit adapter tests:

```bash
python -m pip install -e ".[dev,qiskit]"
pytest
```

## Quick Start

```python
from qplanck import Circuit, Simulator

qc = Circuit(2, name="bell")
qc.h(0).cx(0, 1).measure_all()

result = Simulator("statevector").run(qc, shots=1000, seed=7, trace=True)

print(result.counts)
print(qc.draw())
print(result.trace.to_json(indent=2))
```

## CLI

```bash
qplanck doctor
qplanck draw examples/bell_state.qasm
qplanck trace examples/bell_state.qasm --output trace.json
```

`draw` and `trace` accept either QCore IR JSON or the supported OpenQASM 3
subset.

## Project Status

QCore is in active early alpha development. The v0.1 scope is intentionally
narrow:

- supported gates: `h`, `x`, `y`, `z`, `s`, `t`, `rx`, `ry`, `rz`, `cx`, `cz`
- numeric parameters only
- terminal measurements only
- trace snapshots default to circuits with at most 8 qubits
- Qiskit interop is optional and covers the same supported gate subset

PennyLane, browser visualisation, native acceleration, GPU backends, and plugin
entry points are planned after the first alpha slice.

## Documentation

- [Architecture](docs/architecture.md)
- [Interop](docs/interop.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

Apache-2.0.
