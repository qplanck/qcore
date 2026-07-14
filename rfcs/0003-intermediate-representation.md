# RFC 0003: Intermediate Representation Strategy

- Status: **Proposed**
- Date: 2026-07-14
- Decision owners: Unassigned pending Phase 0 review
- Supersedes: None

## Summary

Retain and evolve QCore's immutable custom `CircuitIR` as the canonical Phase 1
representation. Use OpenQASM 3 for exchange, derived dependency graphs for
analyses, and QIR as a future lowering target. Defer structured/multi-level IR and
an MLIR dialect until accepted feature triggers require them.

## Motivation

**Verified:** `qplanck.ir.v0.1` currently provides deterministic JSON and is shared
by the builder, simulator, traces, QASM, and Qiskit adapters.

**Verified:** OpenQASM 3 provides a rich source/exchange language, QIR provides an
LLVM-based lowering/runtime contract, and MLIR provides multi-level dialect and
pass infrastructure. None directly supplies QCore's operation identity, source
mapping, diagnostics, visual trace, or transformation provenance contract.

**Inference:** A narrow custom layer is justified for those contracts, not as a
new universal quantum standard.

## Decision details

1. `CircuitIR` is immutable, schema-versioned, canonical JSON data.
2. It represents static gate circuits and terminal measurements in Phase 1.
3. Numeric parameters must be finite at compile/execution time.
4. Stable deterministic node IDs connect source maps, diagnostics, compiler
   provenance, visual diffs, and execution traces.
5. Metadata is validated JSON with namespaces and hard size/depth limits.
6. Graphs, depth, liveness, commutation, and topology are derived analyses keyed by
   IR and target hashes.
7. Import/export returns diagnostics and an explicit loss report.
8. No deserializer imports plugins, evaluates code, or contacts a backend.

The complete proposed schema example and option matrix live in
[IR strategy](../docs/architecture/ir-strategy.md).

## Schema compatibility

- Readers support released schema versions according to a published matrix.
- Unknown versions fail closed with a coded diagnostic.
- Writers emit one explicit version; no output changes based on installed plugins.
- `qplanck.ir.v0.1` remains readable through v0.x.
- A `v0.2` writer requires canonical fixtures and a deterministic v0.1 migrator.
- Stable major schema changes require a new RFC and migration/loss policy.

## Interchange

### OpenQASM 3

- Preferred human-readable exchange language.
- Current subset remains supported and explicitly documented.
- Full language control flow is not pretended to fit the static CircuitIR.
- Unsupported syntax receives source-located diagnostics.
- Lossy export requires opt-in and itemized `LossReport`.

### QIR

- Future target when an accepted runtime/provider use case requires it.
- Lowering declares QIR profile, runtime calls, target capability assumptions, and
  source/provenance mapping.
- QIR import is deferred; unknown runtime semantics are never guessed.

### MLIR

- No QCore dialect in Phase 1.
- Reconsider only for structured control flow, multiple lowering levels, or two
  independent target paths whose maintenance clearly benefits from dialect
  infrastructure.
- Any reconsideration needs a prototype, benchmark, packaging plan, and maintainer
  commitment.

## Future feature triggers

| Accepted feature | Required response |
|---|---|
| Mid-circuit measurement/conditionals | Typed classical values and structured order/control semantics |
| Loops/functions | High-level structured IR or preserved OpenQASM AST analysis |
| QIR provider/runtime | Profile-aware lowering and conformance tests |
| Pulse/calibration | Separate timed/pulse program representation |
| Variational/observable workflows | Typed parameter binding and observable schemas |
| Photonic/continuous-variable programs | Separate program kind preserving non-qubit semantics |

## Measurement blocker

**Verified:** The current simulator does not apply `MeasurementSpec` mappings to
sampled count keys.

**Decision:** Before schema evolution, Phase 1 must accept exact semantics for
dense unique classical mappings, partial measurements, implicit measurement,
duplicate sources/destinations, and bit-string order. The current recommendation
is in [runtime architecture](../docs/architecture/runtime-and-backends.md).

## Security

- Bound input bytes, object depth/count, operation count, qubits, metadata, and
  numeric representations before expensive work.
- JSON-only stable serialization; no pickle, object hooks, or executable YAML.
- Source URIs are data and never fetched automatically.
- Hashes identify canonical content but are not signatures.
- Validate plugin-produced IR exactly like external untrusted input.

## Testing

- Golden canonical bytes and hashes per schema version.
- Property/fuzz tests for shape, semantics, limits, and decoder failures.
- Migration idempotence and semantic-hash preservation.
- OpenQASM/Qiskit semantic round trips with explicit loss cases.
- Cross-platform deterministic fixtures.
- Compiler pass invariants over generated circuits.

## Alternatives considered

| Alternative | Reason not selected |
|---|---|
| OpenQASM AST only | Does not own QCore provenance/runtime contracts and couples internal evolution to language syntax |
| QIR/LLVM only | Too low-level for source circuit editing and visual traces |
| Graph only | Loses straightforward source order/serialization; best as analysis view |
| MLIR dialect now | Infrastructure exceeds static-circuit Phase 1 needs |
| Unversioned Python objects | Cannot support reproducibility, adapters, browser artifacts, or agents safely |

## Consequences

- QCore must maintain schema readers, migrations, fixtures, and loss reports.
- The custom IR remains intentionally limited; unsupported program kinds are
  rejected rather than encoded in metadata.
- Future lowerings can evolve without replacing the public builder or provenance
  model.

## Open questions

- Canonical JSON/float/Unicode profile before stable content hashes.
- Final measurement semantics and classical-bit representation.
- Source-path hash profile and privacy defaults.

## Acceptance record

Pending Phase 0 milestone review.
