# Phase 1 Implementation Backlog

> Status: Proposed and implementation-ready after RFC acceptance  
> Scope: Exact backlog for the first 90-day programme  
> Owners: Unassigned pending Phase 0 review

## Conventions

- Priority `P0` blocks the MVP; `P1` is required before Phase 1 review but may run
  off the critical path.
- Size is relative: `S` (small), `M` (bounded multi-file), `L` (cross-contract).
- A task is complete only with implementation, tests, documentation, and stable
  diagnostics/fixtures where relevant.
- Dependencies list task IDs; `Gate` means human acceptance is required.
- No task authorizes changes before RFCs 0001-0004 and measurement semantics are
  accepted.

## Gate and semantic decisions

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-001 | P0 | 1-5 | S | Record acceptance/rejection and owners for RFCs 0001-0004 | RFC status/acceptance records updated; dissent and follow-ups recorded; no production refactor before acceptance | Gate |
| P1-002 | P0 | 1-10 | M | Measurement and bit-order specification | Fixtures cover full/partial/implicit measurement, dense classical mapping, duplicates, repeated sources, no measurements, key order; current behavior impact documented | P1-001 |
| P1-003 | P0 | 1-10 | M | Execution and parser resource-budget specification | Limits and estimate formulas defined for bytes, nodes, operations, qubits, state/temporary arrays, shots, trace/result; boundary fixtures and override policy accepted | P1-001 |
| P1-004 | P0 | 1-10 | S | Zero-shot and numeric-value decision | `shots=0`, negative shots, NaN, infinity, negative zero, and numeric tolerance behavior documented with fixtures | P1-001, P1-002 |

## Contract foundation

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-010 | P0 | 5-20 | M | Immutable `Diagnostic` and `DiagnosticError` envelope | Stable code/severity/message/path/span/context/remediation; deterministic ordering/JSON; old exception classes retained; golden/error-chain tests | P1-001 |
| P1-011 | P0 | 5-20 | M | Validated recursive `JsonValue` and deep-freeze utilities | Reject non-JSON, over-depth/size, non-finite values; nested structures immutable; canonical map order; property and mutation tests | P1-003, P1-004 |
| P1-012 | P0 | 10-25 | L | Bounded CircuitIR schema validation and canonical JSON profile | Validate before construction/expensive work; exact v0.1 canonical fixtures; byte/depth/node limits; unknown versions fail coded; cross-platform fixture tests | P1-010, P1-011 |
| P1-013 | P0 | 15-30 | M | Deterministic artifact/node identity and v0.1 reader fixtures | Deterministic operation/measurement IDs and semantic hash profile; v0.1 remains readable; repeated serialization stable; path privacy tests | P1-012 |
| P1-014 | P1 | 20-35 | M | Source reference and provenance data contracts | Source URI/span validation; provenance links input/output node IDs; no URI fetch; canonical JSON/golden tests | P1-013 |
| P1-015 | P0 | 10-25 | M | Resource estimate and policy primitives | Typed limits/estimates, overflow-safe arithmetic, stable over-budget diagnostics; property/boundary tests | P1-003, P1-010 |

## Compiler spine

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-020 | P0 | 25-40 | M | `CompileOptions`, `PassInfo`, `PassContext`, `PassResult`, analysis contracts | Frozen typed contracts; canonical pipeline identity; invalid/cyclic/missing dependencies diagnosed; API/type tests | P1-010, P1-013 |
| P1-021 | P0 | 30-45 | L | Deterministic pass manager and analysis cache | Stable order/tie-breaks; declared require/provide/preserve/invalidate enforced; cache keys include IR/target/options; compile-twice and invalidation tests | P1-020 |
| P1-022 | P0 | 35-48 | M | Structural and semantic validation passes | Aggregate stable diagnostics for bounds, arity, values, features, measurement rules; generated invalid-circuit tests | P1-002, P1-004, P1-021 |
| P1-023 | P0 | 38-50 | M | Static canonicalization pass | Normalizes names/params/metadata without semantic change; idempotent; matrix/differential and fixture tests | P1-011, P1-021, P1-022 |
| P1-024 | P0 | 38-52 | M | Resource analyses | Operation/gate/two-qubit counts, depth, interaction graph, simulator/trace estimates; known-circuit and property tests | P1-015, P1-021 |
| P1-025 | P0 | 50-70 | M | Adjacent exact inverse-cancellation pass | Handles only proved gate pairs and compatible rotations; emits node provenance/metrics; negative-boundary, random differential, idempotence tests | P1-014, P1-023, P1-024 |
| P1-026 | P0 | 52-72 | M | Adjacent numeric rotation-merge pass | Finite angle rules and normalization documented; no unsafe commute; provenance/error budget; matrix/differential/metamorphic tests | P1-004, P1-014, P1-023 |
| P1-027 | P0 | 40-58 | L | `CompilationTrace` off/summary/full with budgets | Event schema includes pass/version, hashes, changed, provenance, metrics, diagnostics; timing excluded from semantic hash; truncation tests | P1-014, P1-015, P1-021 |
| P1-028 | P0 | 50-60 | M | `CompiledCircuit` and additive `Circuit.compile` | Carries source/compiled/target/pipeline identities and trace; existing Circuit API unchanged; API, serialization, compile-twice tests | P1-022, P1-023, P1-024, P1-027, P1-030 |

## Runtime and backends

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-030 | P0 | 25-42 | L | Immutable `Target` static-circuit capability snapshot | Gates/arity/qubits/topology/measurement/result/limits/unknown states; canonical hash; complete deterministic preflight diagnostics | P1-010, P1-011, P1-013 |
| P1-031 | P0 | 30-45 | M | Immutable `ExecutionOptions` and execution budget resolution | Shots/seed/trace/time/memory/result/backend options; policy tightens requests; secret-like fields prohibited; boundary tests | P1-004, P1-015 |
| P1-032 | P0 | 35-48 | M | `Backend`, `Job`, `JobStatus` public protocols | Sync/async signatures, monotonic state rules, cancellation/timeout semantics, no provider dependency; typing and contract skeleton tests | P1-030, P1-031 |
| P1-033 | P0 | 40-60 | L | Extract `LocalSimulator` behind `Simulator` compatibility facade | Existing tests/API pass unchanged; target preflight and resource rejection before allocation; state/probability/seed/trace parity fixtures | P1-002, P1-015, P1-030, P1-031, P1-032 |
| P1-034 | P0 | 45-62 | L | Apply accepted measurement/result semantics | Explicit classical keys, partial mappings, implicit legacy behavior/manifest flag, shot accounting; exact and randomized fixtures | P1-002, P1-033 |
| P1-035 | P0 | 42-62 | L | Deterministic `MockBackend` and job state machine | Declarative scenarios, fake clock, every transition/failure/cancel/timeout, repeated-result stability; no sleeps/network | P1-032 |
| P1-036 | P0 | 45-65 | L | Evolve `RunResult` and implement `ExperimentManifest` | Existing fields/trace alias retained; canonical source/compile/target/execution/environment/result refs; secret/path redaction tests | P1-013, P1-027, P1-031, P1-034 |
| P1-037 | P0 | 55-70 | M | Local manifest replay and comparison | Validate schemas/hashes/versions, rerun only approved local backend, compare canonical artifacts and numeric profile; tamper/missing-version tests | P1-028, P1-033, P1-036 |

## Interoperability and CLI

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-040 | P0 | 60-78 | M | Harden OpenQASM 3 subset and add `LossReport` | Published grammar subset; byte/token/nesting limits; source-located diagnostics; supported round trip; unsupported/loss cases and fuzz corpus | P1-010, P1-012, P1-015 |
| P1-041 | P1 | 62-78 | M | Bound Qiskit adapter compatibility | Tested provider-version range, wrapped numeric/API errors, loss/unsupported diagnostics, optional-only import; matrix in docs/CI | P1-010, P1-012 |
| P1-042 | P0 | 60-75 | M | `doctor --json`, installation origins, facade collision detection | Reports qplanck origin/versions/capabilities; inspects distributions/spec/entry points without importing suspect qcore; synthetic collision tests | P1-010, RFC 0002 accepted |
| P1-043 | P0 | 68-82 | M | CLI compile, manifest, and replay workflows | Machine JSON and human output; stable exit codes; atomic writes; no unsafe overwrite/path leakage; subprocess smoke tests | P1-028, P1-037, P1-042 |

## Verification and benchmarks

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-050 | P0 | 10-85 | L | Independent simulator/compiler correctness harness | Matrix oracle plus at least one optional external reference; seeded random circuits; Bell/GHZ/rotation/control/bit-order invariants; tolerances published | P1-002, P1-004; expands with P1-025/026/034 |
| P1-051 | P0 | 15-85 | M | Parser/schema/pipeline fuzz-smoke suites | Malformed JSON/QASM/pipeline corpus, depth/size/numeric edge cases, no uncaught crash or over-budget work; deterministic minimized fixtures | P1-003, P1-012, P1-021, P1-040 |
| P1-052 | P0 | 35-75 | L | Shared backend conformance suite | Preflight, run/submit equivalence, lifecycle, cancel, timeout, options, result/manifest, unsupported capabilities; Local and Mock pass | P1-032; implementations P1-033/035/036 |
| P1-053 | P0 | 20-85 | M | Golden and cross-platform artifact suite | IR, pipeline, diagnostics, compilation trace, execution trace, target, result, manifest fixtures stable on Python 3.11-3.13/Linux/macOS/Windows | P1-012, P1-027, P1-030, P1-036 |
| P1-054 | P0 | 10-88 | L | Honest reproducible benchmark framework and baseline | Pinned workloads/env, correctness-before-timing, raw JSON, median/dispersion, parsing/IR/pass/compile/sim/memory/serialization metrics; no unsupported superiority claim | Baseline early; final uses P1-028, P1-033, P1-037 |
| P1-055 | P1 | 65-88 | M | Documentation validation suite | Markdown lint, internal/external links, Mermaid render, code examples, CLI docs, notebooks; deterministic CI job | Documentation set and P1-043 |

## Documentation, Labs, and release readiness

| ID | Pri | Days | Size | Deliverable | Acceptance and required tests | Depends |
|---|---|---:|:---:|---|---|---|
| P1-060 | P0 | 55-85 | M | API/schema/compatibility/migration documentation | Current vs Proposed labels removed only for implemented APIs; every public type documented; v0.1 compatibility and limitations explicit; doctests/examples pass | P1-028, P1-032, P1-036, P1-043 |
| P1-061 | P0 | 65-88 | L | JupyterLite/Pyodide feasibility build | Released wheel installs in pinned browser stack; Bell + compiler notebook runs; local/browser canonical artifacts match; resource/XSS/mobile Playwright tests | P1-028, P1-033, P1-036, P1-055 |
| P1-062 | P1 | 70-88 | M | One version-pinned Academy compiler lesson | Lesson manifest, budgets, invariant grading, progressive hint references, immutable assets; clean browser and local notebook tests | P1-061 |
| P1-063 | P0 | 70-88 | M | Release supply-chain and governance readiness | CI wheel/sdist, hashes, SBOM, build provenance where available, DCO/RFC/release checklist, supported-version statement; dry-run release test | P1-001, P1-055, P1-060 |
| P1-064 | P0 | 86-90 | M | Phase 1 milestone review | Evidence against MVP-01..12, benchmark report, residual risks/debt, adoption feedback, exact next backlog; no automatic Phase 2 start | All P0 tasks |

## Critical path

```text
P1-001 -> P1-002/P1-003/P1-004
  -> P1-010/P1-011/P1-012/P1-015
  -> P1-013 -> P1-020/P1-030/P1-031
  -> P1-021/P1-032
  -> P1-022/P1-027/P1-033/P1-035
  -> P1-028/P1-034/P1-036
  -> P1-037/P1-043/P1-052/P1-053
  -> P1-061/P1-063
  -> P1-064
```

P1-050, P1-051, and P1-054 begin early and expand with each contract; treating
verification as an end-of-program task is explicitly outside this plan.

## Backlog controls

- A new P0 task requires milestone owner approval and an equal scope removal or
  revised gate; the 90-day plan is not an unbounded queue.
- Provider, native, dynamic-circuit, pulse, hosted-kernel, and remote-agent tasks
  belong to later phase backlogs and cannot be relabeled as Phase 1 "spikes" unless
  they replace an accepted deliverable.
- Any task discovering a security/correctness ambiguity may block release without
  being marked complete by documentation alone.
- The canonical acceptance criteria are
  [MVP-01 through MVP-12](mvp-definition.md#functional-acceptance-criteria).
