# QCore

QCore by QPlanck is an open-source Python SDK for inspectable quantum circuits,
deterministic compilation, standards-oriented exchange, and reproducible local
experiments.

The product is called **QCore**. The PyPI distribution, Python package, and
command-line program are called **`qplanck`**.

## What is implemented

`qplanck 0.2.0a1` includes:

- a fluent Python circuit API and immutable, versioned `CircuitIR`;
- a deterministic graph-based reference compiler with exact local rewrites,
  resource metrics, and pass-by-pass provenance;
- a deterministic NumPy statevector simulator with seeded sampling, classical
  measurement mapping, allocation preflight, and portable execution traces;
- direct OpenQASM 3 subset and optional Qiskit subset conversion;
- machine-readable conversion `LossReport` evidence;
- an experimental QIR 2.0 Base Profile text exporter with capability checks and
  source/measurement maps;
- an experimental provider-neutral pulse schedule, target, and calibration
  schema;
- ASCII drawing and a small CLI.

The reference compiler is currently pure Python. It does not perform placement,
routing, SWAP insertion, native-gate synthesis, or pulse lowering, and QCore has
not published a speed comparison with other SDKs. The pulse API validates local
programs but does not connect to hardware. See the
[standards and capability contract](docs/sdk-standards.md) for precise claim
boundaries.

## Install

```bash
pip install qplanck
qplanck doctor
```

Qiskit interoperability is optional:

```bash
pip install "qplanck[qiskit]"
```

For development:

```bash
python -m pip install -e ".[dev,qiskit]"
pytest
```

## Build and simulate a circuit

```python
from qplanck import Circuit, Simulator

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
result = Simulator().run(circuit, shots=1_000, seed=7, trace=True)

print(result.counts)
print(circuit.draw())
print(result.trace.to_json(indent=2) if result.trace else "no trace")
```

## Compile with graph and pass evidence

```python
from qplanck import Circuit
from qplanck.compiler import CompileOptions, compile

circuit = Circuit(2).h(0).h(0).rx(0.25, 1).rx(0.5, 1).measure_all()
compiled = compile(circuit, CompileOptions(optimization_level=1))

print(compiled.before_metrics.operation_count)  # 4
print(compiled.after_metrics.operation_count)   # 1
print([event.pass_id for event in compiled.trace.events])
print(compiled.to_circuit().draw())
```

Compilation preserves circuit and measurement metadata. The alpha optimizer
performs conservative self-inverse cancellation and compatible numeric rotation
merging. Every pass records input/output identities and structural metrics.

## Inspect conversion loss

```python
from qplanck import Circuit

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
exported = circuit.to_qasm3_with_report()

print(exported.value)
print(exported.report.to_json(indent=2))
```

The supported semantic subset converts directly; QCore does not route a Qiskit
circuit through Cirq or OpenQASM. Metadata that the target representation does
not preserve is listed explicitly. Unsupported gates and custom definitions are
rejected instead of silently decomposed.

## Export the supported subset to QIR

```python
from qplanck import Circuit
from qplanck.qir import export_qir

circuit = Circuit(2).h(0).cx(0, 1).measure_all()
module = export_qir(circuit)

print(module.text)
print(module.manifest.to_dict())
```

The exporter emits deterministic opaque-pointer LLVM text for the QIR 2.0 Base
Profile and records required QIS calls and resource mappings. QIR import,
adaptive-profile lowering, bitcode production, provider execution, and a bundled
LLVM runtime are outside this release.

## Define a pulse calibration safely

```python
from qplanck.pulse import (
    CalibrationKey,
    CalibrationLibrary,
    DriveChannel,
    GaussianWaveform,
    PulseProgram,
)

program = PulseProgram(name="x_q0").play(
    start=0,
    channel=DriveChannel(0),
    waveform=GaussianWaveform(duration=160, sigma=40.0, amplitude=0.25),
)
calibrations = CalibrationLibrary().with_calibration(
    CalibrationKey("x", (0,)),
    program,
)

print(calibrations.to_json(indent=2))
```

This is QCore's hardware-neutral schema, not a claim of OpenPulse source
compatibility. A future provider adapter must map channels, clocks, constraints,
and calibration snapshots explicitly before execution.

## Current circuit subset

- gates: `h`, `x`, `y`, `z`, `s`, `t`, `rx`, `ry`, `rz`, `cx`, `cz`;
- finite numeric parameters only;
- terminal, uniquely mapped measurements only;
- little-endian internal state indexing;
- execution-trace snapshots default to at most eight qubits;
- the default exact statevector allocation budget is 256 MiB.

QCore remains an early alpha. The public APIs are tested but may evolve during
`0.x`; schemas carry independent version identifiers.

## CLI

```bash
qplanck doctor
qplanck draw examples/bell_state.qasm
qplanck trace examples/bell_state.qasm --output trace.json
```

`draw` and `trace` accept either QCore IR JSON or the supported OpenQASM 3
subset.

## Documentation

- [SDK standards and capability contract](docs/sdk-standards.md)
- [Architecture](docs/architecture.md)
- [Interoperability](docs/interop.md)
- [Compiler pipeline](docs/architecture/compiler-pipeline.md)
- [IR strategy](docs/architecture/ir-strategy.md)
- [PyPI publishing guide](docs/publishing.md)
- [Changelog](CHANGELOG.md)
- [Roadmap](docs/roadmap/qcore-roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

Apache-2.0.
