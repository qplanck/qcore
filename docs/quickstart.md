---
title: "Quickstart"
description: "Install the qplanck package, simulate a Bell state, and use the qplanck CLI to draw circuits and export portable traces."
icon: "rocket"
---

# Quickstart

This guide walks you through installing QCore, running your first circuit on the
built-in simulator, and using the `qplanck` command-line interface.

QCore is distributed on PyPI as the [`qplanck`](https://pypi.org/project/qplanck)
package. QCore v0.1 ships a small, deterministic surface: a Python circuit API,
a NumPy statevector simulator, ASCII drawing, portable execution traces, and an
[OpenQASM 3 and optional Qiskit interop](/docs/interop) layer.

## Prerequisites

- Python 3.10 or newer
- `pip` available on your `PATH`

## Install

Install the latest release from PyPI:

```bash
pip install qplanck
```

To also install the optional Qiskit interop dependency:

```bash
pip install "qplanck[qiskit]"
```

Verify the installation and run a built-in smoke test:

```bash
qplanck doctor
```

`qplanck doctor` prints the installed `qplanck` version, the Python and NumPy
versions in use, whether Qiskit is available, and the sampled counts and trace
status of a two-qubit Bell circuit. Use it whenever you need to confirm that
QCore is wired up correctly in a new environment.

## Simulate a Bell state

Build a two-qubit Bell circuit, sample it 1,000 times with a fixed seed, and
print the results:

```python
from qplanck import Circuit, Simulator

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()

result = Simulator("statevector").run(circuit, shots=1000, seed=7, trace=True)

print(circuit.draw())
print(result.counts)
```

Key points:

- `Circuit(n)` allocates `n` qubits. Gate methods return the circuit, so you can
  chain them.
- `Simulator("statevector")` is the deterministic NumPy backend. Passing a
  `seed` makes sampling reproducible.
- `shots` selects how many measurement samples to draw. `result.counts` is a
  mapping from bitstrings to sample counts.
- `trace=True` records a step-by-step execution trace on `result.trace`. Traces
  default to circuits with at most eight qubits.

The v0.1 gate set is `h`, `x`, `y`, `z`, `s`, `t`, `rx`, `ry`, `rz`, `cx`, and
`cz`. Only terminal measurements are supported, one qubit to one classical bit.

## Draw and export from the CLI

The `qplanck` CLI accepts either QCore IR JSON or the supported OpenQASM 3
subset.

Draw a circuit as ASCII art:

```bash
qplanck draw examples/bell_state.qasm
```

Export a portable execution trace as JSON:

```bash
qplanck trace examples/bell_state.qasm --output bell_trace.json
```

Omit `--output` to print the trace to stdout. Trace JSON is designed to be
consumed by visual debuggers and other downstream tools without requiring them
to re-run the simulator.

## Round-trip through OpenQASM 3

Circuits can be exported to and imported from the supported OpenQASM 3 subset:

```python
from qplanck import Circuit

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
qasm = circuit.to_qasm3()
restored = Circuit.from_qasm3(qasm)
```

Unsupported operations, multiple registers, non-numeric parameters, and
non-terminal measurements raise an error at import time. See
[Interop](/docs/interop) for the full supported shape and the optional Qiskit
adapter.

## Next steps

- [Interop](/docs/interop) — supported OpenQASM 3 and Qiskit subsets.
- [QCore system overview](/docs/architecture/qcore-overview) — how the circuit,
  IR, simulator, and trace layers fit together.
- [MVP definition](/docs/roadmap/mvp-definition) — what is in and out of scope
  for the v0.1 audited alpha.
