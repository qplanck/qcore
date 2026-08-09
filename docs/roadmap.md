# QCore Strategic Roadmap

> Status: canonical repository product-stage overview, subordinate to the
> governing [QCore Master Specification](QCORE_MASTER_SPECIFICATION.md). Scope:
> product direction and evidence gates, not a release calendar. Package context:
> the repository is preparing the unreleased `qplanck 0.3.0a1` alpha.

QCore is the adaptive execution layer for quantum computing. It takes a quantum
program, a target or target set, and a user objective, then produces the strongest
evidence-backed execution plan it can justify. The product promise is **adaptive
performance portability**: one program should obtain strong, explainable plans as
compilers, providers, devices, calibrations, and objectives change, without making
the user adopt a vendor-specific control plane.

The execution planner is QCore's strategic control point. Circuit construction,
compiler integrations, provider adapters, and runtime services support that
planner; they are not the product thesis by themselves.

## How to read this roadmap

The stage numbers below are **product stages**, not Python package semantic
versions. In particular, the normative planner milestone in
[`spec-v0.1.md`](spec-v0.1.md) may be delivered by a package whose version is not
`0.1`. The product is QCore; its current Python distribution, import package, and
CLI are named `qplanck` because the `qcore` package name is occupied by an unrelated
project.

This file is the canonical overview for stage order, outcomes, and gates. Existing
detailed planning material is retained rather than rewritten:

- [`roadmap/qcore-roadmap.md`](roadmap/qcore-roadmap.md) records the earlier phase
  catalogue, the 90-day plan, and the native `0.3.0a1` acceleration;
- [`roadmap/mvp-definition.md`](roadmap/mvp-definition.md) records the earlier
  compile-inspect-run MVP and its acceptance criteria;
- [`roadmap/implementation-backlog.md`](roadmap/implementation-backlog.md) contains
  the detailed technical-spine backlog.

Those documents remain useful implementation history and supporting detail. Where
their older phase numbering or Pyodide/provider/native assumptions conflict with
this product roadmap, the master specification prevails, followed by this
overview, accepted RFCs, and the current [`claim matrix`](claims.md). The [product thesis](thesis.md) explains why
the planner matters; the [architecture](architecture.md) defines its system
boundaries.

## Current baseline, without roadmap inflation

The current tree contains substantial alpha foundations: a versioned circuit IR,
Qiskit and OpenQASM subset interoperability, a required Rust/PyO3 compiler and QIR
kernel, deterministic target-aware routing, local simulation, generic runtime/job
contracts, pulse/calibration models, and an offline-tested Braket adapter subset.
These are implementation foundations for the roadmap, not evidence that the QCore
planner product is complete.

In particular, the current alpha does not yet establish the complete
`Program -> Target -> Objective -> Plan -> Execution -> Result` lifecycle; an
orchestrated Qiskit/TKET/BQSKit/QCore-native strategy portfolio; IBM target
snapshot ingestion and execution; or a published `qcore-bench` evidence set that
supports comparative performance claims. Native compilation and routing claims
remain subject to their release gates, and Braket hardware execution remains
gated. Before changing any status or claim, verify code, tests, benchmark artifacts,
provider evidence, and [`claims.json`](claims.json).

## Roadmap rules

1. **Stages close on evidence, not dates or demos.** A stage may overlap in research,
   but its public capability claim waits for its exit gate.
2. **Correctness precedes optimization.** A faster or lower-scoring candidate is
   invalid if semantic equivalence or target compatibility is unproved.
3. **Planning is deterministic and reproducible by default.** Seeds, versions,
   options, snapshots, unknowns, assumptions, and tie-breaks belong in artifacts.
4. **Unknown capability data stays unknown.** QCore must not convert missing target
   or calibration evidence into an optimistic estimate.
5. **Semantic and capability mismatches fail closed.** Adapters and strategies do
   not silently approximate unsupported behavior.
6. **Claims are objective-specific and evidence-gated.** Estimated metrics are not
   hardware guarantees, and no named superiority claim is allowed without an
   equivalent-semantics `qcore-bench` result.
7. **Core contracts remain vendor-neutral.** Provider SDK objects, credentials, and
   secrets do not enter core abstractions or reproducibility manifests.
8. **Integrations stay modular.** Compiler and provider implementations are optional
   plugins behind normalized, versioned boundaries.

## Stage summary

| Stage | Strategic outcome | Status boundary |
|---|---|---|
| 0 | Research kernel, evidence baseline, and stable planner schemas | Foundations exist; the product gate is not formally closed |
| 1 | v0.1 multi-strategy planner across IBM target snapshots | Next product milestone; not implemented end to end |
| 2 | IBM-first execution lifecycle with closed-loop evidence | Planned after the offline planner gate |
| 3 | Broader QCore-native compiler portfolio and deeper lowering | Planned; current native compiler is a foundation, not completion |
| 4 | Hybrid CPU/GPU/QPU planning and orchestration | Later research and product stage |
| 5 | Fault-tolerant and QEC-aware planning and execution | Long-horizon research and product stage |

## Stage 0 — research kernel, evidence, and schema stabilization

### Outcome

Establish the smallest trustworthy kernel from which adaptive planning can evolve:
clear product abstractions, normalized artifacts, repeatable evidence, and honest
implementation status. Stage 0 turns experimental compiler/runtime capabilities
into stable inputs to planning without claiming an execution advantage.

### Major deliverables

- Versioned contracts and stable identifiers for `Program`, `Target`, `Objective`,
  `Plan`, `Execution`, and `Result`, including migration policy.
- Canonical program/IR serialization, hashing, provenance, diagnostics, resource
  bounds, and explicit treatment of partial or unknown data.
- A provider-neutral `Target` snapshot schema covering topology, native
  instructions, instruction/qubit properties, timing, errors/calibrations,
  constraints, capabilities, provenance, immutable snapshot identity, and capture
  time.
- A normalized compiler-strategy and plugin boundary that can wrap external
  compilers without leaking their private objects into core artifacts.
- The first `qcore-bench` schemas: versioned workloads, target snapshots,
  objectives, strategy options, correctness evidence, environment manifests, raw
  measurements, and comparable reports.
- Accepted product, IR, runtime, plugin, security, and evidence decisions with
  contradictions recorded rather than hidden.

### Exit and evidence gate

Stage 0 closes only when the six core abstractions round-trip through versioned
schemas; canonical artifacts and hashes are deterministic across supported
platforms; unknown/invalid capability fixtures fail as specified; at least one
representative workload can be evaluated through the benchmark schema; and a
milestone review maps every implemented claim to tests or artifacts. Existing
alpha compiler features alone do not close this gate.

### Dependencies and risks

- Depends on reconciled RFC ownership, compatibility decisions for existing
  `qplanck` artifacts, and maintainers for schema evolution.
- Risks include freezing abstractions before real provider/compiler evidence,
  confusing declared capability with observed calibration, and allowing legacy
  package milestones to masquerade as product acceptance.

### Deliberately deferred

Production hardware submission, broad provider coverage, automatic optimizer
selection, AI-directed optimization, a giant IDE, a full Academy, and comparative
performance wording.

## Stage 1 — v0.1 multi-strategy planner for IBM targets

### Outcome

Deliver the first complete adaptive-planning workflow: accept one program, compare
several valid ways to compile it for accessible immutable IBM target snapshots,
rank the candidates against an explicit objective, explain the selection, and
retain enough evidence to reproduce the decision. The normative requirements are
in [`spec-v0.1.md`](spec-v0.1.md).

### Major deliverables

- Qiskit input and a first-class OpenQASM frontend contract, both normalized to a
  versioned QCore `Program`/IR without unnecessary conversion hops.
- IBM target discovery and immutable snapshot ingestion for offline planning,
  preserving provenance, timestamps, partial fields, and the distinction between
  provider declarations and observed/calibrated evidence.
- Optional compiler-strategy plugins for Qiskit, TKET, BQSKit, and QCore-native
  passes. QCore orchestrates and compares these strategies rather than attempting
  to replace each compiler.
- Deterministic candidate generation across Program × compiler strategy × options ×
  Target, with explicit seeds, bounded search, validation, and stable tie-breaking.
- An `Objective` model with hard constraints and documented weights. Candidate
  reports include at minimum two-qubit gate count, circuit depth, SWAP count, and
  estimated error, with the error model, missing inputs, and limitations named.
- Candidate validation, scoring, ranking, selection rationale, rejection reasons,
  and retained Pareto alternatives. Estimated quality remains an estimate, not a
  promise of hardware fidelity.
- Reproducibility manifests containing program and artifact hashes, parser and IR
  versions, exact strategy/plugin/provider versions and options, seeds, target
  snapshot identity, objective, candidate set, metrics, scores, rationale,
  selected-plan hash, toolchain/environment data, and artifact timestamps.
- A first-class `qcore-bench` suite separating compile-time performance from
  output-quality metrics, with correctness checks before timing and published raw
  artifacts.

### Exit and evidence gate

Stage 1 closes when a clean environment can take the normative example from
Qiskit/OpenQASM input through at least two materially distinct compiler strategies
on versioned IBM snapshots; reject invalid candidates; reproduce the complete
candidate set, metrics, ranking, plan hash, and explanation; and pass semantic,
determinism, plugin-conformance, manifest-redaction, and benchmark checks. The
report must identify tradeoffs and rejected or Pareto alternatives, not merely
emit one circuit. Hardware submission is not required to prove the offline planner.

Any statement that QCore is faster or produces better circuits must separately
pass the objective-specific claim gates with equivalent semantics, uncertainty,
and no correctness or timeout deficit.

### Dependencies and risks

- Depends on Stage 0 schemas, stable optional-plugin boundaries, legal and
  maintainable Qiskit/TKET/BQSKit integrations, and repeatable IBM snapshot
  fixtures.
- Risks include incomparable compiler semantics, moving provider schemas,
  incomplete calibration evidence, objective weights that hide tradeoffs, plugin
  version churn, and benchmark gaming.

### Deliberately deferred

Automatic hardware submission, broad multi-provider execution, replacing all
external compilers, proprietary universal languages, pulse optimization, dynamic
circuits unless separately specified, unverified AI optimization, a giant IDE,
and a full learning platform.

## Stage 2 — IBM-first runtime lifecycle and closed-loop feedback

### Outcome

Turn a frozen, selected `Plan` into a controlled `Execution`, normalize its
`Result`, and feed observed evidence back into later planning without rewriting
the original plan or overstating causality. IBM is the first lifecycle adapter;
the core remains provider-neutral.

### Major deliverables

- A separate IBM provider plugin for discovery, authenticated submission, status
  polling, timeout, cancellation where supported, and result normalization.
- Immutable plan-to-execution binding: the submitted artifact, target snapshot,
  objective, options, and plan hash cannot drift after submission.
- Explicit job state transitions, idempotency policy, provider references,
  uncertainty/failure representation, spend and payload preflight, and audit-safe
  operational diagnostics.
- Reproducibility manifests extended with execution reference, submission and
  completion timestamps, runtime/plugin versions, normalized result and raw
  artifact hashes, and links back to the selected plan. Secrets and provider SDK
  objects are never recorded.
- A closed-loop evidence path that records observed outcomes alongside—never in
  place of—declared capabilities, calibration snapshots, and planning estimates.
- Offline provider fixtures, contract tests, and a protected, explicitly budgeted
  live-smoke workflow with no blind retry.

### Exit and evidence gate

Stage 2 closes only after offline lifecycle suites cover success, cancellation,
timeout, provider rejection, snapshot drift, result normalization, idempotency,
and redaction; a protected live IBM smoke proves the documented path; and replay
can connect `Program -> Plan -> Execution -> Result` without exposing credentials
or mutating the frozen plan. Closed-loop data must preserve its source, timestamp,
sample size, and uncertainty.

### Dependencies and risks

- Depends on the Stage 1 plan/manifest contracts, an owned IBM compatibility
  range, credentials and test budget, provider terms, security review, and a
  sustainable live-test policy.
- Risks include API and device churn, queue and cancellation ambiguity, cost,
  stale calibration data, credential leakage, retry duplication, and treating a
  small hardware sample as universal optimizer evidence.

### Deliberately deferred

An all-provider runtime, hidden automatic resubmission, provider credentials in
core, guaranteed fidelity, autonomous spending, marketplace/billing features, and
provider-specific primitives forced into the common model.

## Stage 3 — native compiler portfolio and deeper lowering

### Outcome

Expand QCore's own evidence-backed strategy portfolio where native implementation
creates measurable planning value, while retaining external compilers as peers.
Evolve toward progressive, multi-level lowering with MLIR/LLVM/QIR-compatible
boundaries where use cases justify them.

The existing Rust graph compiler, O2 routing, and QIR Base Profile exporter are
foundations for this stage. They do not mean that QCore already supplies an MLIR
stack, arbitrary QIR, or a complete native replacement for mature compilers.

### Major deliverables

- Additional QCore-native placement, routing, rebasing, scheduling, synthesis, or
  error-aware strategies admitted one at a time behind the same portfolio
  boundary as external compilers.
- Versioned source/high-, middle-, and target-level IR contracts introduced only
  when a transformation requires them, with explicit lowering legality,
  provenance, diagnostics, and migration.
- MLIR-compatible dialect or pass integration experiments where they improve
  multi-level composition; LLVM/QIR lowering profiles with external validation and
  runtime contracts. Compatibility is an architectural boundary, not a claim that
  all of MLIR or QIR is implemented.
- Cross-strategy equivalence, property, differential, fuzz, determinism, memory,
  and performance suites in `qcore-bench`.
- Planner policies that can select native or external strategies from evidence,
  retain Pareto options, and explain why a strategy was admitted or selected.

### Exit and evidence gate

Each native strategy must independently pass semantic and target-validity checks,
resource limits, cross-platform determinism, packaging/supply-chain gates, and a
published benchmark showing material value for a named workload/objective without
regressing correctness. Multi-level IRs must have versioned schemas, verifier
rules, round-trip/golden fixtures, and provenance-preserving lowering. No strategy
is accepted merely because it is written in Rust.

### Dependencies and risks

- Depends on the Stage 1 portfolio and benchmark system, representative user
  workloads, compiler expertise, sustained Rust/LLVM toolchain ownership, and
  stable profile/tooling dependencies.
- Risks include compiler-scope explosion, opaque rewrites, IR fragmentation,
  compile-time and memory regressions, native packaging burden, upstream ABI
  churn, and benchmarks that reward only one topology or objective.

### Deliberately deferred

A universal proprietary language, wholesale replacement of Qiskit/TKET/BQSKit,
unsupported arbitrary QIR or MLIR conformance claims, approximation without an
error contract, and “native therefore faster” marketing.

## Stage 4 — hybrid CPU/GPU/QPU orchestration

### Outcome

Plan and execute workflows whose classical and quantum components belong on
different resources, optimizing the end-to-end objective rather than an isolated
quantum circuit. QCore becomes a reproducible orchestration layer while retaining
clear ownership boundaries with workflow engines, providers, and accelerators.

### Major deliverables

- Versioned hybrid program graphs describing classical kernels, quantum tasks,
  data dependencies, control boundaries, placement constraints, and artifacts.
- Capability snapshots for CPU, GPU, simulator, and QPU resources, including data
  movement, queue, locality, cost, timing, and trust-boundary evidence where known.
- Candidate partitioning, placement, batching, scheduling, and fallback plans
  scored against multi-resource objectives.
- Plugin adapters for selected classical/GPU workflow systems and provider
  runtimes, without embedding vendor objects in core plans.
- End-to-end manifests, replay boundaries, checkpoint/recovery semantics, and
  benchmark workloads that separate orchestration overhead from kernel and QPU
  performance.

### Exit and evidence gate

Stage 4 closes when at least one representative hybrid workload can be planned,
executed, interrupted, and reproduced across an explicitly supported resource
combination; data/control semantics survive partitioning; cost and latency
estimates expose uncertainty; failures are attributable; and `qcore-bench` shows
an end-to-end advantage for a stated objective over a defined baseline. A faster
individual kernel is insufficient.

### Dependencies and risks

- Depends on the Stage 2 execution lifecycle, Stage 3 compiler/IR boundaries,
  owned scheduler and accelerator integrations, representative workloads, and
  operational security/cost controls.
- Risks include combinatorial search, nondeterministic queues, data-transfer
  dominance, distributed failure, vendor-specific scheduling, secret spread,
  resource overspend, and irreproducible accelerator behavior.

### Deliberately deferred

Universal workflow-engine replacement, transparent execution on every accelerator,
unbounded autonomous scheduling/spend, unsupported real-time guarantees, and
fault-tolerant logical-qubit orchestration.

## Stage 5 — fault-tolerant and QEC-aware planning and execution

### Outcome

Extend adaptive performance portability from physical circuits to logical
programs: compare fault-tolerant compilation, code, decoder, architecture, and
resource choices against explicit correctness, reliability, latency, and cost
objectives, then preserve the assumptions behind every estimate and run.

### Major deliverables

- Versioned logical-program, fault-tolerant target, noise/evidence, QEC code,
  decoder, resource-estimate, and execution-plan contracts.
- Strategy plugins for selected logical lowering, synthesis, magic-state/resource
  estimation, code/layout selection, syndrome processing, and decoder workflows.
- Models that connect physical error assumptions and calibration evidence to
  logical failure estimates while retaining uncertainty, correlations, and model
  provenance.
- Planner comparison of space, time, logical error, classical decoding load,
  architecture constraints, and monetary/energy cost, with Pareto alternatives.
- Simulation/emulation and, when available, hardware adapter boundaries for
  syndrome data and logical results; reproducibility manifests spanning the full
  stack.
- Public `qcore-bench` QEC workloads, reference models, correctness checks, raw
  evidence, and claim gates developed with domain experts.

### Exit and evidence gate

Each supported QEC path must state its code/noise/decoder/architecture assumptions,
validate transformations and resource formulas against independent references,
quantify uncertainty, preserve syndrome/result provenance, and reproduce published
benchmarks. Any hardware execution claim requires a protected supported-device
workflow; any logical-advantage claim requires predefined statistical and
correctness gates and must name its baseline and domain of validity.

### Dependencies and risks

- Depends on stable multi-level IR and execution provenance, credible physical and
  logical noise evidence, QEC and decoder expertise, reference implementations,
  large-scale simulation resources, and evolving hardware interfaces.
- Risks include immature or incompatible architectures, unrealistic independent-
  error assumptions, extreme compute requirements, correlated-noise uncertainty,
  rapidly changing terminology, and turning research estimates into misleading
  product guarantees.

### Deliberately deferred

A universal fault-tolerant ISA, support for every code/decoder/architecture,
guaranteed logical advantage, black-box AI code selection, and claims extrapolated
beyond the benchmarked noise and hardware regimes.

## Product North Star beyond individual stages

The roadmap succeeds when users can keep a program and objective stable while
QCore adapts the evidence-backed plan as the available compilers, providers,
devices, calibrations, and compute resources change. Success is not the number of
integrations or native passes. It is a measurable, reproducible execution advantage
with an explanation strong enough for a user to audit, reject, or reproduce.
