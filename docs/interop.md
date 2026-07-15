# Interoperability

QCore `0.2.0a1` treats immutable `CircuitIR` as the source of truth and uses
external standards at explicit conversion or lowering boundaries. Each adapter
supports a documented semantic subset; unsupported features fail instead of
being guessed or silently decomposed.

## Supported circuit subset

Single-qubit gates are `h`, `x`, `y`, `z`, `s`, `t`, `rx(theta)`, `ry(theta)`,
and `rz(theta)`. Two-qubit gates are `cx(control, target)` and
`cz(control, target)`. Parameters must be finite numeric values. Measurements
are terminal with unique qubit-to-classical-bit mappings.

## Fidelity reports

Formats preserve different information. `ConversionResult[T]` pairs a converted
value with a deterministic `LossReport` containing:

- source and target format identities;
- fields whose semantics were preserved;
- machine-readable warnings;
- machine-readable losses and their source paths;
- `is_lossless` and `require_lossless()` checks.

```python
from qplanck import Circuit

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
exported = circuit.to_qasm3_with_report()

print(exported.value)
print(exported.report.to_json(indent=2))
```

The existing `to_qasm3()` and `to_qiskit()` convenience methods remain
compatible, but workflows that depend on round-trip fidelity should use their
`*_with_report()` forms.

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

The parser rejects unsupported operations, multiple registers, symbolic
parameters, custom definitions, dynamic control, resets, and non-terminal
measurements. The exporter preserves supported gate order, numeric parameters,
qubit count, and terminal measurement mapping. QCore metadata is reported as a
loss because the alpha subset does not encode it.

This is a tested OpenQASM 3 subset, not complete language conformance.

## Qiskit

Install the optional dependency:

```bash
python -m pip install "qplanck[qiskit]"
```

The adapter converts directly between a Qiskit `QuantumCircuit` and `CircuitIR`;
it does not route through Cirq or OpenQASM. Supported gates and measurement
mappings are retained. Barriers, resets, conditions, custom gates, symbolic
parameter expressions, and other unsupported instructions raise `InteropError`.
The `0.2.0a1` package declares Qiskit `>=1.0,<3`; release CI currently exercises
the latest available compatible Qiskit in that range.

`to_qiskit_with_report()` records any QCore metadata that cannot be mapped. A
normal circuit name is preserved.

## QIR

`qplanck.qir` lowers the static supported subset to deterministic textual LLVM IR
for the [QIR 2.0 Base Profile](https://github.com/qir-alliance/qir-spec/blob/2.1/specification/profiles/Base_Profile.md):

```python
from qplanck import Circuit

circuit = Circuit(2).h(0).cx(0, 1).measure_all()
module = circuit.to_qir()

print(module.text)
print(module.manifest.to_dict())
```

The manifest records the declared profile/version, entry point, required qubit
and result counts, required QIS calls, dense QIR result allocation, classical-bit
mapping, and source operation mapping. `QIRCapabilities` can restrict QIS and
resource limits before generation.

`to_qir_with_report()` additionally reports QCore metadata not encoded in the
QIR module. The generated all-gate fixture has been parsed by LLVM, verified by
official PyQIR, and executed by the official QIR runner. That evidence covers the
supported Base Profile artifact; it is not a claim of QIR import, adaptive
programs, bundled bitcode tooling, or hardware execution.

CI installs the optional `qir-validation` extra and verifies a generated module
with official PyQIR:

```bash
python -m pip install ".[dev,qir-validation]"
pytest tests/test_qir.py
```

QIR profiles constrain classical program structure, while target QIS vocabulary
is a separate capability contract. QCore uses common official PyQIR Basic QIS
spellings and validates them explicitly.

## Pulse and calibration

The `qplanck.pulse` module is a separate provider-neutral program schema. It does
not convert a gate circuit implicitly and does not claim OpenPulse source
compatibility. See the [standards contract](sdk-standards.md) and
[architecture](architecture.md) for the exact boundary.

## Deferred adapters

PennyLane, Cirq, provider runtimes, OpenPulse source, QIR import, and other
conversion paths remain deferred. New adapters must define a supported feature
matrix, loss policy, version range, conformance fixtures, and security/resource
limits before entering the package.
