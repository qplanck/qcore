# SDK Standards and Capability Contract

> Status: `qplanck 0.3.0a1` release-candidate contract
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
| Dependency graph and compilation | Supported alpha | Required Rust kernel; immutable operation graph; deterministic O0/O1 rewrites; O2 placement, routing, SWAP insertion, exact basis lowering; metrics and trace | Static circuits only; no arbitrary synthesis or scheduling |
| OpenQASM 3 | Supported alpha | Direct import/export for the documented OpenQASM 3 subset | Not the complete OpenQASM grammar; unsupported constructs fail |
| Qiskit | Supported alpha, optional | Direct conversion to and from the same semantic subset | Unsupported/custom instructions fail; no conversion through Cirq or QASM |
| Conversion fidelity | Supported alpha | `ConversionResult` and deterministic `LossReport` list preserved fields, warnings, and losses | Legacy convenience methods still return only the converted value |
| QIR | Experimental boundary | Native deterministic LLVM/QIR 2.0 Base Profile lowering, including SWAP expansion and compiled provenance | Export only; no import, adaptive profile, arbitrary target QIS, or bundled runtime |
| Pulse and calibration | Experimental boundary | Hardware-neutral typed channels, waveforms, schedules, target validation, canonical snapshots, and calibration library | QCore schema, not universal OpenPulse conformance |
| Runtime and jobs | Supported alpha | Provider-neutral backend/job/status/options/manifest contracts, local simulator, and deterministic mock backend | Provider capabilities remain adapter-specific |
| Braket pulse adapter | Experimental boundary | Separate package, immutable capabilities/calibrations, explicit channel maps, offline-tested pulse subset, one task per submission | No `Acquire`; live execution claim gated by the protected paid smoke |
| Native compiler acceleration | Implemented; performance claim gated | Rust is required for production compile/routing/QIR; Python O0/O1 is a frozen oracle | No named speed-superiority claim until the benchmark release gates pass |
| WebAssembly/browser runtime | Unsupported in 0.3 | The Python-independent core is target-build checked; use a remote supported CPython kernel or pin static lessons to the final pure-Python 0.2 artifact | No JavaScript binding, npm package, or Pyodide support |

## Interoperability and loss

QCore adapters convert directly between an external format and `CircuitIR`. A
Qiskit circuit is not routed through Cirq or OpenQASM, so QCore introduces no
intermediate conversion hop. O2 may then deliberately insert SWAPs as documented
routing transformations; those insertions and their layout changes are recorded
in the compilation artifact.

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

The production kernel is Rust. O0 validates and measures; O1 adds conservative
exact local rewrites; O2 requires a `Target`, chooses a deterministic initial
layout, routes the dependency DAG, records inserted abstract SWAPs, lowers those
SWAPs and other operations exactly to the target basis, and remaps terminal
measurements through the final layout. Stable tie-breaking, bounded lookahead,
release-valve routing, and a finite SWAP budget make artifacts reproducible and
fail closed when a target cannot express the circuit.

The frozen Python O0/O1 compiler remains a non-production differential oracle.
Native artifacts must match it at O0/O1, and routing must satisfy semantic,
layout, measurement, budget, and determinism invariants. Performance reports
record pinned versions, workloads, machine information, correctness checks,
warm-up, sample count, median, MAD/p95, RSS, SWAPs, added two-qubit gates, and
depth. Until the thresholds in the benchmark policy pass, QCore makes no claim
that it is faster than Qiskit, Cirq, TKET, or another tool.

## QIR boundary

[QIR](https://github.com/qir-alliance/qir-spec) is an LLVM-based interchange and
runtime contract. QCore keeps its higher-level `CircuitIR` for source identity,
debugging, and compiler provenance, then lowers the supported static subset to
the [QIR base profile](https://github.com/qir-alliance/qir-spec/blob/main/specification/profiles/Base_Profile.md).

The exporter records the selected profile, required qubit/result counts, emitted
entry point, source-operation mapping, compiled artifact hash, target identity,
and compiler-trace identity alongside the LLVM text. SWAP lowers to three QIR
CNOT calls. Unknown gates, unbound parameters, non-terminal measurement
semantics, and unsupported profiles are rejected rather than guessed.

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
QCore does not claim universal OpenPulse source compatibility. Provider adapters
must explicitly map QCore channel and timing contracts to a device, cite the
calibration snapshot, and reject unsupported instructions.

`qplanck-braket` is the first adapter. It derives frame mappings from captured
capability metadata, never frame-name heuristics; requires predefined frames,
matching `dt`, and one QCore channel per provider port; supports the documented
play/delay/phase/frequency and waveform subset; and rejects `Acquire` because
Braket capture semantics cannot preserve QCore's duration and memory-slot model.
Credentials come only from the ambient AWS SDK chain and are excluded from
artifacts. Snapshot drift blocks submission, and one submit maps to one task with
no blind retry.

## Release claim rules

Documentation, package metadata, announcements, and benchmark reports must keep
these distinctions:

- “required Rust graph compiler and QIR kernel” is accurate only after the
  native conformance/release checks are green;
- “target-aware deterministic routing” is accurate only after the routing and
  native parity checks are green;
- “QIR base-profile exporter for the supported subset” is accurate;
- “complete QIR compiler/runtime” is not accurate;
- “hardware-neutral pulse and calibration model” is accurate;
- “offline-tested Braket pulse lowering subset” is accurate;
- “executed on Braket hardware” is not accurate until the paid smoke is recorded;
- “faster” or “better” requires a public equivalent-semantics benchmark and a
  stated objective.

These rules are machine checked against [`claims.json`](claims.json) and are part
of the release gate, not optional marketing guidance.
