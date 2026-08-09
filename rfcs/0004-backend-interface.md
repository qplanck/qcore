# RFC 0004: Backend and Runtime Interface

- Status: **Accepted and implemented for 0.3 alpha**
- Date: 2026-07-14
- Decision owner: QPlanck maintainer
- Supersedes: None

## Summary

Adopt typed `Backend`, `Target`, `LocalSimulator`, `MockBackend`, `Job`,
`RunResult`, `ExecutionOptions`, and `ExperimentManifest` contracts. Phase 1
implements local and mock backends in core and permits provider implementations
only in separate packages. Preserve the current `Simulator` API throughout v0.x
as a compatibility facade. RFC 0006 is the first adapter implementation.

## Motivation

**Verified:** Mature runtimes expose capability, job, result, and provider
boundaries, but provider-specific primitives and session models differ. Reducing
them to one shallow interface would hide important semantics.

**Inference:** QCore can stabilize lifecycle and reproducibility locally before
accepting provider credentials, API churn, and spend risk.

## Interface decision

```text
Circuit.compile(target, options) -> CompiledCircuit
Backend.run(compiled, options) -> RunResult
Backend.submit(compiled, options) -> Job
Job.status() -> JobStatus
Job.cancel() -> bool
Job.result(timeout) -> RunResult
```

These signatures describe the accepted behavior. The implemented Python
protocols use keyword-only execution options and immutable manifest contracts;
provider adapters may narrow the accepted program type (for example,
`CalibratedCircuit`) without pretending every backend accepts every program.

## Target

`Target` is an immutable capability snapshot with identity/hash, qubits,
topology, instruction availability, dynamic/reset/measurement features, timing,
pulse access, limits, parameter binding, result formats, calibration references,
runtime features, and authentication requirement identifiers.

- Unknown is distinct from unlimited or unsupported.
- Provider features remain typed or namespaced.
- Compilation and execution use the same target hash.
- Refresh is explicit; no silent target change after compile.
- Preflight reports all detectable incompatibilities in stable order.

## Backend

- `run` is synchronous and returns normalized `RunResult`.
- `submit` is asynchronous and returns QCore `Job`, never a raw provider job.
- Backends expose stable ID/version and current `Target`.
- Backend-specific options are validated JSON under a namespace and recorded with
  secret values redacted.
- Unsupported features are rejected, not silently approximated.

## Job

Stable states are `CREATED`, `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`,
`SUCCEEDED`, `FAILED`, and `CANCELLED`. States are monotonic; provider detail is
retained separately. Cancellation reports request acceptance rather than a false
guarantee. Result timeout does not imply cancellation.

## Result and manifest

- Retain current counts, probabilities, samples, metadata, and trace behavior.
- Add diagnostics, manifest, and optional raw artifact reference compatibly.
- Explicit measurements produce dense classical keys; implicit legacy all-qubit
  observation is marked in the manifest.
- `ExperimentManifest` records source, compilation, target, backend, execution
  options, environment, result identity, numeric tolerance profile, and
  diagnostics.
- Manifests exclude secrets, raw environment variables, and local absolute paths
  by default.

The full proposed data contract is in
[runtime and backends](../docs/architecture/runtime-and-backends.md).

## Core implementations

### LocalSimulator

- Existing static gate subset and terminal measurement contract.
- Exact NumPy `complex128` statevector.
- Deterministic seed handling and documented basis order.
- Preflight memory, shot, trace, and result limits.
- Existing `Simulator("statevector")` delegates without v0.x breaking change.

### MockBackend

- Declarative immutable target and scripted lifecycle under a fake clock.
- Deterministic success/failure/cancellation fixtures.
- No network, credentials, sleeping, or wall-clock dependence.
- Shared backend contract tests.

## Provider extension and deferred protocols

- `Session` is optional and provider-defined; not all backends emulate it.
- `Sampler` and `Estimator` are future optional capabilities.
- Streaming, partial results, queues, and remote cancellation await real adapter
  evidence.
- Provider backends ship in separate distributions. `qplanck-braket` implements
  the first pulse-specific adapter under RFC 0006.

## Security

- Core has no provider credentials, network calls, or billable submissions.
- Provider packages use their SDK's ambient credential chain; secrets never enter
  QCore options, manifests, diagnostics, or serialized artifacts.
- Resource budgets are validated before state allocation/execution.
- Plugin backends are trusted in-process code unless a future isolation protocol is
  explicitly used.
- Provider errors are normalized without exposing secrets or discarding provider
  identifiers.
- Remote retries require idempotency-aware policy and expose uncertain outcomes.

## Compatibility

- Existing `Simulator.run`, `.statevector`, and `.probabilities` remain.
- Existing `RunResult.trace` remains as an alias if a clearer
  `execution_trace` field is added.
- Provider-neutral contracts have independent versions and conformance tests.
- Raw provider payloads are optional references, not fields required of local code.

## Testing

One shared contract suite covers capability preflight, sync/async equivalence,
state transitions, cancellation, timeout, shot accounting, diagnostics,
manifests, and unsupported options. Local tests add matrix/differential and resource
tests; mock tests enumerate every transition.

## Alternatives considered

| Alternative | Reason not selected |
|---|---|
| Keep `Simulator` as the universal runtime | Cannot model targets, jobs, remote lifecycle, or manifests cleanly |
| Implement provider first | Introduces credentials/churn before contract proof |
| Force every backend into Sampler/Estimator | Not all program/result models fit primitives |
| Return raw provider jobs/results | Leaks dependencies and defeats stable SDK contracts |
| Hide provider differences | Produces unsafe lowest-common-denominator behavior |

## Consequences

- More data types and contract tests are required before first provider support.
- Local and mock behavior become meaningful specifications rather than demos.
- Provider-specific richness is preserved through capabilities and namespaces.
- Provider release and execution claims have independent protected evidence gates.

## Open questions

- Final measurement and zero-shot semantics.
- Whether local `submit` should return an already-completed job or use a deterministic
  executor abstraction.
- Artifact storage interface for large future state/results.

## Acceptance record

Accepted for the 0.3 alpha. The shared local/mock contract suite is the baseline
for providers; RFC 0006 adds snapshot, spend, retry, and credential constraints
for Amazon Braket.
