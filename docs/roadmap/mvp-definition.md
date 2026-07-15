# QCore Phase 1 MVP Definition

**Implementation update:** `0.2.0a1` now implements the initial deterministic
compiler plus experimental QIR export and pulse/calibration representation
boundaries. The exclusions below remain the original Phase 1 planning record;
current capability claims are defined in the
[SDK standards contract](../sdk-standards.md).

> Status: Proposed  
> Candidate release: `qplanck 0.2.0a1` (not committed)

## MVP statement

**Decision:** The smallest technically meaningful MVP preserves the existing
Circuit experience and proves one complete, deterministic path:

```text
Python Circuit
  -> validated/canonical CircuitIR
  -> explicit compiler pipeline + CompilationTrace
  -> CompiledCircuit for an immutable Target
  -> LocalSimulator or MockBackend
  -> RunResult + ExecutionTrace
  -> ExperimentManifest
  -> replay and artifact comparison
```

A user can inspect what changed and reproduce the local experiment without a
network account, provider SDK, hosted service, or native build toolchain.

## Primary user story

As a learner, SDK developer, or compiler researcher, I can create a Bell circuit,
compile it for a local target, inspect every pass and metric, run deterministic
sampling, export the complete experiment record, and replay it in a clean supported
environment with equivalent canonical artifacts and results.

## Included scope

### Programming model and compatibility

- Existing `Circuit`, gates, terminal measurement, ASCII draw, QASM/Qiskit subset,
  IR JSON, traces, results, errors, CLI, and `Simulator` behavior remain available.
- **Proposed** `Circuit.compile(...) -> CompiledCircuit` is additive.
- Existing `Simulator` delegates to the new local backend without requiring user
  migration during v0.x.

### Contracts

- Bounded, canonical, immutable CircuitIR with v0.1 compatibility fixtures.
- Structured `Diagnostic` with stable code, severity, message, source/path, context,
  and remediation fields.
- `CompileOptions`, `CompiledCircuit`, `CompilationTrace`.
- `Target`, `ExecutionOptions`, `Backend`, `Job`, `JobStatus`.
- Evolved `RunResult` and new `ExperimentManifest`.

### Compiler

- Stage skeleton with explicit versioned pipeline identity.
- Structural validation, semantic validation, canonicalization, exact adjacent
  inverse cancellation, compatible numeric rotation merge, resource analysis, and
  target validation.
- Declared dependencies and preserved/invalidated analyses.
- `off`, `summary`, and budgeted `full` compilation traces.
- Deterministic operation IDs, diffs, metrics, and provenance.

### Backends

- `LocalSimulator`: existing NumPy `complex128` exact static statevector semantics,
  explicit resource preflight, seeded sampling, execution traces.
- `MockBackend`: deterministic target, job transitions, failures, cancellation, and
  result fixtures under a fake clock.
- One shared backend conformance suite.

### Developer experience

- `qplanck doctor` human and machine-readable checks, including package origin and
  future facade collision readiness.
- CLI compile/trace/manifest/replay workflow using safe output behavior.
- Bell and compiler-inspection examples.
- Published schemas, compatibility matrix, benchmark baseline, and migration notes.
- JupyterLite/Pyodide feasibility site running the released wheel and one Academy
  lesson.

## Explicitly excluded

- `qcore` import/CLI facade release.
- Mid-circuit measurement, reset, conditions, loops, dynamic circuits.
- Symbolic execution, variational primitives, observables, channels, or noise.
- Placement, routing, scheduling, synthesis, pulse, calibration.
- Provider adapters, sessions, credentials, remote jobs, retries, spend.
- GPU, tensor-network, density-matrix, stabilizer, distributed, or native simulator
  implementations.
- Automatic plugin loading or untrusted plugin isolation.
- Hosted kernels, terminals, accounts, collaboration, or persistence service.
- Agent/MCP package or remote-effect tools.

## Proposed API acceptance example

This example is **Proposed**:

```python
from qplanck import Circuit
from qplanck.backends import LocalSimulator

circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()
backend = LocalSimulator()

compiled = circuit.compile(
    target=backend.target,
    optimization_level=1,
    trace="full",
)
result = backend.run(compiled, shots=1_000, seed=7, trace="summary")

assert set(result.counts) <= {"00", "11"}
result.manifest.write("bell.manifest.json")
```

Equivalent current code using `Simulator("statevector")` must continue to pass.

## Functional acceptance criteria

| ID | Criterion |
|---|---|
| MVP-01 | Every existing test/example passes unchanged unless an accepted measurement decision adds a documented fixture. |
| MVP-02 | Invalid IR/QASM/options return stable diagnostics without uncaught implementation errors. |
| MVP-03 | Resource preflight rejects over-budget simulation/trace/result before state allocation. |
| MVP-04 | Compile of identical IR/target/options yields identical canonical compiled artifact, diagnostics, and semantic trace data. |
| MVP-05 | Every pass event records pass/version, input/output hash, changed flag, provenance, before/after metrics, and diagnostics. |
| MVP-06 | Optimization passes preserve reference state/probabilities within declared tolerance on generated valid circuits. |
| MVP-07 | Local and mock backends pass the shared sync/async/lifecycle/result/manifest suite. |
| MVP-08 | Measurement mappings and bit-string order match accepted fixtures for full, partial, explicit, and implicit measurement cases. |
| MVP-09 | Manifest replay validates versions/hashes and reproduces Bell canonical artifacts and seeded counts. |
| MVP-10 | QASM/Qiskit boundaries enumerate unsupported/lossy features and preserve the supported subset. |
| MVP-11 | JupyterLite clean build installs the wheel and produces artifacts matching local canonical fixtures. |
| MVP-12 | `doctor --json` reports core origin/versions/capabilities and detects synthetic `qcore` package/entry-point collisions without importing them. |

## Quality acceptance criteria

- Ruff formatting/lint and strict mypy pass.
- Python 3.11-3.13 tests pass on Linux, macOS, and Windows.
- Branch coverage target is agreed from measured baseline; critical parsers,
  validators, passes, backend lifecycle, and manifest code meet explicit per-module
  thresholds rather than chasing one aggregate number.
- Property, differential, metamorphic, golden, fuzz-smoke, docs, example, notebook,
  and CLI tests are present.
- Markdown lint, relative/external link checks, and Mermaid rendering pass.
- No required provider SDK, Rust/C++ compiler, network, or secret is needed for core
  tests.
- Release produces wheel/sdist, hashes, SBOM, and build provenance where supported.

## Benchmark acceptance

The baseline records parsing, IR construction, each pass, total compile, output
operation/depth/two-qubit counts, simulation runtime, peak memory, serialization,
and replay. It includes:

- pinned QCore/dependency versions and source commit;
- CPU, memory, OS, Python, and relevant NumPy details;
- fixed Bell/GHZ, structured workload, and seeded random-circuit corpora;
- correctness checks before timing;
- warm-up policy, sample count, median and dispersion;
- raw machine-readable results;
- no cross-framework superiority claim unless equivalent semantics and public
  workloads are established.

## Resource defaults to decide

**Open Question:** Exact defaults require measured implementation data. Phase 1
must set and document conservative values for maximum input bytes, operations,
qubits, statevector bytes, shots, compile events/time, trace bytes, result bytes,
and browser lesson limits. Defaults are policy, not schema maxima, and are
overridable only through explicit options.

## Definition of done

The MVP is done only when code, schemas, tests, docs, examples, benchmark data,
security controls, migration notes, and a milestone review are complete. A demo or
passing happy-path unit test is not acceptance. Provider or advanced compiler work
does not begin to compensate for an unmet MVP criterion.
