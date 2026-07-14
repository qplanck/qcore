# QCore Phase 0 Executive Summary

> Status: Proposed for milestone review  
> Evidence cut-off: 2026-07-14

## Recommendation

**Inference:** QCore should enter as an explainable, reproducible
compile-inspect-run environment, not as another universal provider marketplace.
Its first users are learners who need to see what a circuit does, SDK developers
who need stable contracts, and compiler researchers who need deterministic pass
inspection. One workflow should serve all three without hiding transformations.

**Verified:** Established products already cover broad conversion, provider, and
hosted-environment surfaces. qBraid SDK exposes a directed conversion graph and
runtime abstractions, while qBraid Lab provides managed browser development
environments. Qiskit, pytket, Braket, Azure Quantum, and CUDA-Q each have mature
compiler or execution surfaces. See the [ecosystem audit](research/ecosystem-audit.md).

**Decision:** Phase 1 is local-only: typed circuit construction, a versioned IR,
deterministic compilation with provenance, a reference simulator, stable
diagnostics, execution manifests, and mock/local backends. Providers, hosted
containers, GPU simulation, pulse control, billing, and multi-tenancy remain out
of scope.

## The ten strategic questions

### 1. Why should QCore exist?

**Inference:** Quantum tools often optimize for one primary concern: provider
access, differentiable programming, compilation throughput, pulse control, or
education. QCore can make the whole local path observable and reproducible:
source intent, validated IR, every transformation, target assumptions, execution
options, and results. The differentiator is the inspectable contract, not a larger
gate catalogue.

### 2. Who should use its first version?

**Decision:** The first version serves three adjacent groups:

- learners using approachable circuit builders and visual traces;
- SDK developers depending on typed, versioned serialization and diagnostics;
- compiler researchers inspecting pass inputs, outputs, metrics, and provenance.

**Inference:** Hardware engineers, enterprise platform teams, and production QPU
users are later audiences because their needs require provider operations,
calibration, scheduling, credentials, and reliability infrastructure.

### 3. What specific problem should it solve first?

**Decision:** Given a small circuit, QCore must deterministically validate,
compile, explain, simulate, and reproduce it. A user must be able to answer:
"What changed, why did it change, what target was assumed, and can I rerun the
same experiment?"

### 4. What should QCore not attempt initially?

**Decision:** QCore will not initially provide a broad conversion graph, direct
QPU submission, credentials, sessions, pulse authoring, GPU or distributed
simulation, a hosted multi-tenant lab, billing, cloud scheduling, error-mitigation
suites, differentiable programming, or an MLIR dialect.

### 5. What architecture gives it the strongest long-term foundation?

**Decision:** Use a Python-first monorepo with strict layers: public programming
model, versioned custom circuit IR, deterministic compiler, runtime contracts,
local/mock backends, adapters, and separate UI/agent packages. OpenQASM 3 is an
exchange language; QIR is a future lowering target. Rust requires published
benchmark evidence before introduction. See the [system overview](architecture/qcore-overview.md).

### 6. What can QPlanck build credibly without large funding?

**Inference:** A high-quality local SDK, deterministic pass manager, trace schema,
reference simulator, static browser lab, documentation, and selected external
adapters are credible. Maintaining many provider APIs, operating kernels for
untrusted users, or competing on simulator scale is not.

### 7. How can QCore become useful before hardware integrations?

**Inference:** Compilation provenance, circuit diffs, resource metrics, deterministic
simulation, OpenQASM exchange, reproducible manifests, mock targets, and notebook
labs all provide standalone value. Provider-neutral target descriptions also let
users teach and test hardware constraints without credentials.

### 8. How can Academy and Labs create distribution?

**Decision:** Academy content will pin supported QCore versions and ship executable
exercise contracts. QPlanck Labs will first be a static JupyterLite/Pyodide site
with bundled notebooks and trace visualization. Every lesson should produce a
portable circuit, compilation trace, and experiment manifest that also works in
the desktop Python SDK.

### 9. What technical advantages could become defensible?

**Inference:** Defensibility can accumulate in stable provenance schemas,
cross-version experiment reproduction, excellent transformation explanations,
target-aware diagnostics, a corpus of validated educational experiments, and
machine-safe agent tools. These depend on sustained contract quality and data,
not on unsupported speed claims.

### 10. What should Codex implement in 30, 60, and 90 days?

**Decision:** Days 1-30 complete this gate and resolve measurement semantics,
schema ownership, and compatibility policy. Days 31-60 implement the compiler and
runtime spine behind the existing `Simulator` API. Days 61-90 add useful passes,
manifests, contract tests, benchmark baselines, and a JupyterLite feasibility
slice. Exact acceptance criteria live in the [implementation backlog](roadmap/implementation-backlog.md).

## Success measures

**Decision:** Phase 1 is accepted only when:

- identical inputs and options produce byte-stable IR, traces, diagnostics, and
  manifests on supported Python versions;
- every compiler pass declares dependencies and preserved/invalidated analyses;
- local and mock backends pass one shared backend contract suite;
- current `Simulator` behavior remains compatible across v0.x unless an RFC
  explicitly approves a deprecation;
- reference examples run locally and in the browser feasibility environment;
- benchmark results include pinned dependencies, hardware, workloads, correctness
  checks, and statistical treatment.

## Gate outcome

**Inference:** The audited alpha is a useful prototype and should be evolved, not
rewritten. It already proves circuit-to-IR-to-simulation-to-trace plus OpenQASM and
Qiskit round trips. Its key gaps are compiler provenance, runtime contracts,
measurement semantics, resource guards, and durable reproducibility metadata.

**Open Question:** The Phase 1 gate must explicitly accept RFCs 0001-0004 and
assign maintainers before production refactoring begins.
