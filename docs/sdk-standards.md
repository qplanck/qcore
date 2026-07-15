# SDK Standards and Capability Contract

> Status: implemented experimental surface for `qplanck 0.2.0a1`  
> Evidence cut-off: 2026-07-14

QCore uses standards at explicit boundaries and reports when information cannot
cross a boundary intact. The package does not claim that one representation can
losslessly express every quantum program.

## Capability levels

| Level | Meaning |
|---|---|
| Supported alpha | Implemented, public, tested, and included in release checks; APIs may still change during `0.x`. |
| Experimental boundary | Implemented and validated for the documented subset, but not a complete implementation of the external ecosystem or hardware path. |
| Planned | Architecture or extension point only; must not be advertised as an available feature. |

## Current standards matrix

| Area | Status | Implemented contract | Explicit limit |
|---|---|---|---|
| Canonical circuit representation | Supported alpha | Immutable `CircuitIR`, deterministic JSON, finite numeric parameters, terminal measurement mapping | Static supported gate subset only |
| Dependency graph and compilation | Supported alpha | Derived immutable operation graph, deterministic exact rewrite pipeline, resource metrics, pass trace | Pure Python; no placement, routing, SWAP insertion, synthesis, or native accelerator |
| OpenQASM 3 | Supported alpha | Direct import/export for the documented OpenQASM 3 subset | Not the complete OpenQASM grammar; unsupported constructs fail |
| Qiskit | Supported alpha, optional | Direct conversion to and from the same semantic subset | Unsupported/custom instructions fail; no conversion through Cirq or QASM |
| Conversion fidelity | Supported alpha | `ConversionResult` and deterministic `LossReport` list preserved fields, warnings, and losses | Legacy convenience methods still return only the converted value |
| QIR | Experimental boundary | Deterministic textual LLVM/QIR lowering for the documented base-profile subset | Export only; no QIR import, adaptive profile, bitcode toolchain, runtime, or provider execution |
| Pulse and calibration | Experimental boundary | Hardware-neutral typed channels, waveforms, scheduled instructions, target validation, canonical JSON, and calibration library | QCore schema, not an OpenPulse conformance claim; no device driver or hardware execution |
| Native compiler acceleration | Planned and benchmark-gated | Public Python contracts are designed so an accelerator can preserve the same artifacts and trace semantics | No Rust/C++ accelerator and no comparative speed claim in this release |

## Interoperability and loss

QCore adapters convert directly between an external format and `CircuitIR`. A
Qiskit circuit is not routed through Cirq or OpenQASM, so QCore itself introduces
no intermediate conversion hop. The supported subset also performs no target
routing and therefore inserts no SWAP gates.

Direct conversion does not guarantee that every field survives. Prefer the
evidence-bearing methods when fidelity matters:

```python
from qplanck import Circuit

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
exported = circuit.to_qasm3_with_report()

print(exported.value)
print(exported.report.to_json(indent=2))
exported.report.require_lossless()
```

The current OpenQASM subset cannot preserve QCore metadata such as a circuit
name. That omission appears as a loss rather than being silently described as a
lossless round trip. Unsupported gates, control flow, reset, and custom gate
definitions fail closed; the exporter never decomposes or approximates them
without an explicit compiler contract.

## Graph compiler contract

The compiler derives a dependency graph from ordered operations and qubit
conflicts. The serialized `CircuitIR` remains the source of truth; the graph is an
analysis view and cannot fragment or silently replace the public representation.

The alpha optimizer performs only exact local transformations with deterministic
trace evidence. It does not map to hardware topology, choose a provider basis, or
insert SWAPs. Compilation must preserve terminal measurements and metadata.

A future Rust, C++, MLIR, or other native implementation must pass the same
canonical artifact, semantic-equivalence, and trace conformance tests. It also
requires a published benchmark that records pinned versions, workloads, machine
information, correctness checks, warm-up, sample count, median, and dispersion.
Until that evidence exists, QCore makes no claim that its compiler is faster than
Qiskit, Cirq, TKET, or another tool.

## QIR boundary

[QIR](https://github.com/qir-alliance/qir-spec) is an LLVM-based interchange and
runtime contract. QCore keeps its higher-level `CircuitIR` for source identity,
debugging, and compiler provenance, then lowers the supported static subset to
the [QIR base profile](https://github.com/qir-alliance/qir-spec/blob/main/specification/profiles/Base_Profile.md).

The exporter records the selected profile, required qubit/result counts, emitted
entry point, and source-operation mapping alongside the LLVM text. Unknown gates,
unbound parameters, non-terminal measurement semantics, and unsupported profiles
are rejected rather than guessed.

Text generation alone is not a complete QIR toolchain certification. Release
tests cover deterministic structure and declared profile rules; integration with
QIR Alliance validation tooling and an actual target runtime remains separate
work.

## Pulse and calibration boundary

Pulse control depends on hardware channels, clocks, frames, amplitude ranges,
acquisition rules, and calibration ownership. QCore therefore uses a program type
separate from `CircuitIR`. A pulse program can be validated, serialized, and
stored as a gate calibration without pretending that every provider exposes the
same hardware controls.

The schema is informed by the concepts in the
[OpenPulse grammar](https://openqasm.com/versions/3.0/language/openpulse.html), but
`qplanck 0.2.0a1` does not claim OpenPulse source compatibility. Provider adapters
must explicitly map QCore channel and timing contracts to a device, cite the
calibration snapshot, and reject unsupported instructions. The core package does
not connect to hardware, handle credentials, or submit pulse jobs.

## Release claim rules

Documentation, package metadata, announcements, and benchmark reports must keep
these distinctions:

- “graph-based deterministic compiler” is accurate;
- “native/high-performance compiler” is not accurate yet;
- “QIR base-profile exporter for the supported subset” is accurate;
- “complete QIR compiler/runtime” is not accurate;
- “hardware-neutral pulse and calibration model” is accurate;
- “seamless pulse control on quantum hardware” is not accurate without tested
  provider adapters;
- “faster” or “better” requires a public equivalent-semantics benchmark and a
  stated objective.

These rules are part of the release gate, not optional marketing guidance.
