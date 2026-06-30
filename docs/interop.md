# Interop

QCore v0.1 treats `CircuitIR` as the source of truth. Exchange formats are
supported only for the documented alpha subset.

## Supported Operations

Single-qubit gates:

- `h`
- `x`
- `y`
- `z`
- `s`
- `t`
- `rx(theta)`
- `ry(theta)`
- `rz(theta)`

Two-qubit gates:

- `cx(control, target)`
- `cz(control, target)`

Measurements:

- terminal only
- one qubit to one classical bit

## OpenQASM 3

Supported import/export shape:

```qasm
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
```

The importer rejects unsupported operations, multiple registers, non-numeric
parameters, and non-terminal measurements.

## Qiskit

Qiskit support is optional:

```bash
python -m pip install "qplanck[qiskit]"
```

Supported Qiskit circuits must use the same v0.1 gate subset. Unsupported
instructions such as barriers, resets, conditions, custom gates, and parameter
expressions raise `InteropError`.

## PennyLane

PennyLane support is deferred until after the first alpha.
