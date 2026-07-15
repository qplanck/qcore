# QCore Roadmap

**Implementation update (`0.2.0a1`):** a bounded QIR base-profile exporter and
provider-neutral pulse/calibration model were pulled forward as experimental
representation boundaries. This does not pull forward a QIR runtime, provider
execution, OpenPulse conformance, or native compiler. See the
[current standards contract](../sdk-standards.md).

> Status: Proposed  
> Planning horizon: Phase 0 through three years

## Roadmap rule

**Decision:** Phases are evidence gates, not calendar promises. A phase begins only
after the previous milestone review records accepted contracts, remaining risks,
owners, and a funded maintenance path. Features may be removed to meet a gate;
they may not be smuggled forward as undocumented experimental behavior.

## First 90 days

The 90-day program assumes Phase 0 is accepted and a small Python team is assigned.
Exact tasks and dependencies are in the
[implementation backlog](implementation-backlog.md).

### Days 1-30: contract and correctness foundation

**Objective:** Resolve semantic blockers and make current artifacts safe to evolve.

- Accept RFCs 0001-0004 and assign maintainers.
- Decide measurement, partial measurement, implicit measurement, and zero-shot
  semantics.
- Implement stable diagnostic envelope/codes.
- Add bounded schema validation, canonical JSON rules, and deep metadata
  immutability.
- Add simulator/trace/result resource preflight.
- Create canonical v0.1 fixtures and randomized/differential correctness harness.
- Establish benchmark format and baseline current alpha.

**Acceptance:** Existing APIs remain compatible; malicious/oversized input corpus
fails with coded diagnostics; current examples and adapters still pass; measurement
contract has executable fixtures.

**Excluded:** Compiler optimizations, runtime extraction, Labs UI, providers.

### Days 31-60: technical spine

**Objective:** Prove deterministic compilation and runtime contracts beneath the
existing API.

- Implement `Diagnostic`, `CompileOptions`, `CompiledCircuit`, pass manager, and
  `CompilationTrace` summary/full modes.
- Implement structural/semantic validation, canonicalization, resource analysis,
  and target validation passes.
- Implement `Target`, `ExecutionOptions`, `Backend`, and backend contract tests.
- Extract `LocalSimulator` while retaining `Simulator` behavior.
- Implement deterministic `MockBackend` and `Job` state machine.
- Implement `ExperimentManifest` and local replay.

**Acceptance:** The end-to-end path builder -> IR -> compile -> local/mock run ->
manifest works; compile-twice fixtures are stable across CI; sync/async backend
contract tests pass.

**Excluded:** Provider adapters, advanced routing/synthesis, dynamic circuits.

### Days 61-90: useful alpha and distribution proof

**Objective:** Demonstrate real inspectability, reproducibility, and Academy/Labs
reuse.

- Add exact inverse cancellation and numeric rotation merging with provenance.
- Harden QASM/Qiskit boundaries with loss/compatibility diagnostics.
- Add CLI JSON mode, package-origin checks, compile/manifest workflows.
- Publish benchmark baseline and correctness data.
- Build JupyterLite/Pyodide feasibility site with Bell/compiler lesson.
- Run browser/local artifact parity, notebook, Markdown, link, Mermaid, and release
  artifact checks.
- Produce Phase 1 milestone review with measured evidence.

**Acceptance:** A fresh user can construct, compile, inspect, run, export, and
replay a Bell experiment locally and in the static feasibility environment. Every
artifact is versioned and the benchmark is reproducible.

**Excluded:** Hosted kernels, remote jobs, accounts, collaboration, agent network
tools.

## Three-year direction

### Year 1: trusted local foundation and learning distribution

**Inference:** Focus should remain on Phase 1, a useful SDK alpha, and a static Labs
alpha. Success means downstream lessons and integrations depend on stable schemas,
not that QCore lists many providers.

- Complete compiler/runtime spine and harden compatibility.
- Add selected topology-aware compilation, parameters, observables, noise
  interchange, plugin contracts, and benchmark corpus only as accepted Phase 2
  items.
- Publish QPlanck Academy lessons and static Labs releases pinned to QCore.
- Consider one external simulator adapter based on demand and contract quality.

### Year 2: selective execution and advanced compiler evidence

**Inference:** Add one or two provider adapters only where users and maintainers can
support credentials, targets, job lifecycles, and live contract tests.

- Implement selected provider adapters as separate distributions.
- Add capability-aware mapping/routing and richer resource estimation.
- Evaluate remote Labs only if Pyodide limitations block validated workloads.
- Prototype dynamic/control-flow or QIR lowering only behind accepted RFCs.
- Establish a community maintainer and extension certification process.

### Year 3: guarded agents and research/enterprise capabilities

**Inference:** Agent and enterprise work becomes credible only after stable tools,
runtime governance, and operational security exist.

- Release local MCP-compatible tools; enable provider reads before writes.
- Gate remote submission behind permissions, idempotency, spend controls, and audit.
- Evaluate organization workspaces, private registries, scheduling, and compliance
  only from concrete partners/users.
- Pursue advanced simulation/native compiler work only from benchmark evidence.
- Reassess governance, stable 1.0, and LTS based on maintainer capacity.

## Phase catalogue

Complexity is relative: `M` is a bounded subsystem, `L` crosses several contracts,
and `XL` requires sustained multi-disciplinary ownership.

### Phase 0: research and architecture gate

- **Objective:** Establish evidence, position, architecture, risks, and accepted
  decision records before production refactoring.
- **User value:** Trustworthy scope and a coherent path rather than disconnected
  implementation.
- **Deliverables:** Research set, architecture set, threat model, governance,
  RFCs 0001-0004, MVP, backlog, validation, review report.
- **Dependencies:** Audited commit `2f2ed07`, primary-source access.
- **Acceptance/tests:** Mandatory-source coverage; Markdown/link/Mermaid validation;
  current examples tested; terminology/API/roadmap cross-check.
- **Risk/debt limit:** Time-sensitive evidence is dated; no unowned production
  code; documentation contradictions are gate failures.
- **Complexity:** M.
- **Excluded:** Any `src/qplanck` change, compiler/runtime refactor, facade, Labs
  implementation.

### Phase 1: technical spine

- **Objective:** Prove deterministic compile-inspect-run-reproduce locally.
- **User value:** Stable diagnostics, compiler evidence, local/mock runtime, and
  portable experiments.
- **Deliverables:** Hardened IR, pass manager, core passes, traces, targets,
  local/mock backends, manifests, CLI, benchmark baseline, Labs feasibility.
- **Dependencies:** Accepted RFCs and measurement contract.
- **Acceptance/tests:** [MVP definition](mvp-definition.md), backend contracts,
  cross-platform canonical fixtures, randomized/differential correctness, browser
  parity.
- **Risk/debt limit:** No unresolved high-risk measurement/resource semantics; no
  provider SDK required by core; no unversioned JSON contract.
- **Complexity:** L.
- **Excluded:** Providers, credentials, hosted kernels, dynamic circuits, MLIR,
  native/GPU core.

### Phase 2: useful SDK alpha

- **Objective:** Add the most demanded circuit/compiler features without weakening
  Phase 1 contracts.
- **User value:** Real target-aware experimentation and richer algorithms.
- **Candidate deliverables:** Parameter binding, observables, noise primitives,
  topology placement/routing, native-gate lowering, richer OpenQASM, selected
  external simulator, plugin API, notebook/Academy corpus.
- **Dependencies:** Phase 1 adoption/correctness data and accepted feature RFCs.
- **Acceptance/tests:** Cross-framework differential tests, routing invariants,
  plugin conformance, published benchmark deltas, course migrations.
- **Risk/debt limit:** No feature encoded only in metadata; approximation error is
  explicit; external algorithms retain license/provenance.
- **Complexity:** L.
- **Excluded:** Broad provider runtime, pulse, GPU implementation, multi-tenancy.

### Phase 3: QPlanck Labs alpha

- **Objective:** Deliver a polished static browser learning and compiler-inspection
  environment.
- **User value:** No-install lessons and shareable local artifacts.
- **Deliverables:** JupyterLite distribution, circuit/trace/pass views, exercises,
  static sharing/export, execution history in local workspace.
- **Dependencies:** Stable wheel/schemas and browser feasibility evidence.
- **Acceptance/tests:** Browser performance/accessibility/security, notebook
  reproducibility, local/browser parity, course completion study.
- **Risk/debt limit:** No server-side arbitrary code or account data; immutable
  course assets; bounded browser resources.
- **Complexity:** L.
- **Excluded:** Remote terminals, cloud workspaces, QPU jobs, collaboration.

### Phase 4: selected hardware/runtime integrations

- **Objective:** Run on a small set of demanded providers without polluting core.
- **User value:** Carry the same compiled/manifests workflow to real hardware.
- **Deliverables:** Separate adapters, capability snapshots, credential broker
  pattern, job lifecycle, retries/idempotency, raw/normalized results, mocks/live
  smoke tests.
- **Dependencies:** Stable backend contract, maintainers, provider agreements/budget,
  security review.
- **Acceptance/tests:** Contract suite, provider mock corpus, budgeted live tests,
  secret-canary and incident exercises.
- **Risk/debt limit:** Every adapter has an owner/support matrix; no credentials in
  core; uncertain outcomes represented.
- **Complexity:** XL.
- **Excluded:** "All providers," billing marketplace, lowest-common-denominator
  capability claims.

### Phase 5: advanced compiler and simulation

- **Objective:** Address validated research/performance needs.
- **User value:** Dynamic programs, stronger target lowering, and larger/specialized
  simulation through appropriate engines.
- **Candidate deliverables:** Structured control IR, QIR lowering, advanced
  synthesis, noise-aware mapping, tensor/GPU adapters, pulse program boundary.
- **Dependencies:** Accepted RFCs, public benchmarks, external engine contracts,
  maintainer/toolchain capacity.
- **Acceptance/tests:** Formalized invariants, profile conformance, numerical error
  budgets, benchmark correctness and regression gates.
- **Risk/debt limit:** No native rewrite without benchmark gate; no universal IR
  claim; calibration ownership explicit.
- **Complexity:** XL.
- **Excluded:** Unmeasured "faster" work and unsupported provider generalization.

### Phase 6: AI-native quantum engineering

- **Objective:** Expose stable QCore operations to agents under policy.
- **User value:** Reliable experiment construction, inspection, diagnosis, and
  reproduction without opaque direct access.
- **Deliverables:** `qcore-agent`, MCP transport, docs retrieval, local tools,
  guarded provider reads then writes, audit and permission policy.
- **Dependencies:** Stable schemas/diagnostics/manifests, provider security controls.
- **Acceptance/tests:** Adversarial prompt/policy corpus, deterministic schema
  conformance, dry-run/budget behavior, spend/idempotency incident tests.
- **Risk/debt limit:** Model output never authorizes action; no secrets in context;
  remote writes opt-in and auditable.
- **Complexity:** XL.
- **Excluded:** Unbounded autonomous job submission or self-installed plugins.

### Phase 7: research and enterprise platform

- **Objective:** Add organizational/operational capabilities only for evidenced
  users and sustainable support.
- **User value:** Governed collaborative experiments and managed execution.
- **Candidate deliverables:** Private registries, workspaces, quotas, scheduling,
  observability, compliance controls, distributed execution, support model.
- **Dependencies:** Product demand, operating budget, privacy/security/compliance
  program, mature governance.
- **Acceptance/tests:** SLOs, isolation/abuse testing, audit/compliance evidence,
  disaster recovery, cost and capacity models.
- **Risk/debt limit:** No hosted platform without dedicated operations/security
  ownership; open core remains useful independently.
- **Complexity:** XL+.
- **Excluded:** Enterprise features that make open local QCore intentionally
  incomplete or untrustworthy.

## Roadmap decision gates

| Gate | Required evidence |
|---|---|
| Phase 1 start | Human acceptance of RFCs 0001-0004 and measurement semantics |
| Phase 2 feature | User demand, schema design, compatibility/security/test owner |
| Labs remote compute | Browser limitation evidence plus hosted threat/operations review |
| First provider | Named maintainer, support range, credentials/job security, live-test budget |
| Native core | Published profile/benchmark and cross-platform packaging ownership |
| Dynamic/MLIR | Accepted language/IR use case that static CircuitIR cannot preserve |
| Agent remote write | Permissions, confirmation, idempotency, spend limits, audit, incident runbook |
| LTS/1.0 | Stable contracts, downstream adoption, security rotation, sustained maintainers |
