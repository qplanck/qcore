# QCore Positioning and Product Strategy

**Implementation update (`0.2.0a1`):** the deterministic compiler foundation,
loss reports, experimental QIR base-profile exporter, and experimental
hardware-neutral pulse/calibration schema now exist. The native accelerator and
provider pulse execution remain gated. The
[SDK standards contract](../sdk-standards.md) is authoritative for current
capability claims.

> Status: Proposed for Phase 0 review  
> Evidence cut-off: 2026-07-14

## Position

**Decision:** QCore is an explainable, reproducible quantum
compile-inspect-run environment. It will initially serve learners, SDK developers,
and compiler researchers through the same local workflow, with different levels
of detail rather than separate products.

**Inference:** This is narrower and more credible than competing with broad
provider platforms. The [ecosystem audit](../research/ecosystem-audit.md) shows
that qBraid, IBM, AWS, Azure, Quantinuum, NVIDIA, and others already maintain
substantial integration and runtime surfaces.

## Product wedge

```text
Readable source
  -> validated, versioned CircuitIR
  -> deterministic compiler pipeline
  -> pass-by-pass diffs and provenance
  -> capability-aware local execution
  -> portable result + experiment manifest
```

**Decision:** The first promise is not "run everywhere." It is "understand and
reproduce what happened here." Hardware neutrality is achieved through explicit
targets and adapters, not by hiding target differences.

## Audience model

| Audience | First need | Default experience | Advanced affordance | Acceptance signal |
|---|---|---|---|---|
| Learner | Build intuition without environment friction | Fluent circuits, ASCII/visual traces, deterministic local runs | Reveal basis order, amplitudes, and transformation explanations on demand | Completes a version-pinned lesson and reproduces its result |
| SDK developer | Dependable contracts and errors | Typed APIs, schemas, compatibility policy, mock backend | Adapter contracts, manifests, machine-readable diagnostics | Integrates without provider credentials and survives patch/minor updates |
| Compiler researcher | Inspect and compare transformations | Explicit pipeline and before/after metrics | Custom passes, analysis cache, replay, circuit diffs | Reproduces a pass experiment from a manifest |

**Inference:** These groups can share one architecture because transparency is
useful at different depths. Defaults should be approachable; data contracts must
remain rigorous; instrumentation should be optional but complete.

## Design principles

1. **Explicit transformations.** Every semantic change has a pass identity,
   reason, input/output reference, diagnostics, and metrics.
2. **Reproducibility by construction.** Seeds, versions, options, target snapshot,
   inputs, and outputs belong in an `ExperimentManifest`.
3. **Deterministic local core.** Equivalent local inputs and options produce
   canonical artifacts across supported platforms, subject to documented numeric
   tolerances.
4. **Stable typed boundaries.** Public objects and JSON schemas evolve under an
   explicit compatibility policy.
5. **Capabilities, not lowest common denominator.** Targets declare features and
   extensions; unsupported programs fail before submission.
6. **Standards at the edges.** OpenQASM 3 is exchange, QIR is future lowering, and
   external SDKs are adapters. QCore owns only the metadata they cannot preserve.
7. **Local first, cloud ready.** The first useful workflow needs no account,
   network, credentials, or platform service.
8. **Integrate specialized engines.** QCore owns a small reference simulator and
   contracts; it does not recreate mature GPU, tensor, pulse, chemistry, or error
   mitigation stacks.
9. **Safe extensibility.** Plugins are ordinary trusted Python code unless an
   explicit isolation boundary says otherwise. Discovery never means execution.
10. **Education without a toy fork.** Academy and Labs use the same schemas,
    diagnostics, compiler, and runtime contracts as SDK users.
11. **Agent-readable, human-auditable.** Machine tools have bounded JSON schemas,
    stable error codes, dry runs, budgets, and audit records.
12. **Benchmark before native code.** Rust, C++, GPU, Wasm, or distributed paths
    require measured bottlenecks and a published correctness-preserving benchmark.

## Resolving principle conflicts

| Conflict | Resolution rule |
|---|---|
| Approachability vs explicit behavior | Use concise defaults, but never omit the artifact or diagnostic that explains a decision. |
| Stable API vs research experimentation | Stable namespaces reject silent change; experimental APIs are visibly versioned and excluded from compatibility promises. |
| Vendor neutrality vs provider features | Standardize lifecycle and capability discovery while preserving namespaced provider options and raw payload references. |
| Determinism vs compiler quality | Deterministic tie-breaking is mandatory by default; explicitly seeded exploratory passes may opt out and record the seed. |
| Local-first vs cloud-ready | Keep execution contracts transport-neutral, but implement no remote transport until local/mock conformance is complete. |
| Custom IR vs standards-first | Custom fields exist only for source maps, diagnostics, provenance, and stable in-memory behavior; publish loss reports at every exchange boundary. |
| Performance vs transparency | Tracing is optional and budgeted; disabling it may reduce observability but must not change semantics. |
| Extensibility vs security | In-process plugins require explicit trust; untrusted code runs only in a future sandbox service, never by entry-point discovery alone. |

## Build-versus-integrate matrix

| Capability | Build | Integrate/wrap | Defer | Reject initially | Rationale |
|---|:---:|:---:|:---:|:---:|---|
| Circuit builder and validation | Yes |  |  |  | Core user and diagnostic contract already proven. |
| Versioned CircuitIR and provenance | Yes | Standards at boundaries |  |  | Primary differentiation and reproducibility foundation. |
| Deterministic pass manager | Yes | Optional algorithm plugins |  |  | Needed for explainable compilation. |
| Basic canonicalization/cancellation passes | Yes |  |  |  | Small, testable compiler spine. |
| Advanced synthesis and ZX optimization |  | PyZX/TKET/Qiskit adapters | Yes |  | Mature algorithms exist; preserve provenance around calls. |
| NumPy reference statevector | Harden | Differential oracles |  |  | Small correctness oracle, not performance product. |
| GPU/tensor/distributed simulation |  | Aer, qsim, Qulacs, QuEST, CUDA-Q | Yes | Yes | Native performance ecosystem is mature and expensive. |
| OpenQASM 3 | Subset contract | Official parser when justified |  |  | Required exchange format; report unsupported/lossy constructs. |
| QIR |  | QIR Alliance tooling | Yes |  | Useful only when lower-level runtime demand exists. |
| MLIR dialect |  | Study Catalyst/CUDA-Q | Yes | Yes | No Phase 1 structured-control/multi-level need. |
| Local and mock backends | Yes |  |  |  | Proves runtime contract without provider instability. |
| Provider/QPU adapters |  | Separate distributions | Yes | Yes | Credentials and provider churn do not belong in core. |
| Pulse/control |  | Pulser, Dynamics, LabOne Q, QUA adapters | Yes | Yes | Distinct semantics and hardware ownership. |
| Error mitigation |  | Mitiq/provider services | Yes | Yes | Technique and license complexity; not the wedge. |
| Differentiable programming |  | PennyLane | Yes | Yes | Valuable but orthogonal to initial users. |
| Static browser Labs | Thin integration | JupyterLite/Pyodide |  |  | Strong early experience at low operations cost. |
| Hosted kernels/containers |  | Jupyter/Kubernetes/sandbox platforms | Yes | Yes | Security and operations burden is premature. |
| Agent tools | Schemas and local tools | MCP transport later | Yes |  | Core should be machine-safe without agent dependencies. |
| Academy content runtime | Version contract | JupyterLite/notebook tooling |  |  | Distribution channel and real compatibility consumer. |

## Academy integration

**Decision:** Academy lessons reference an explicit QCore compatibility range and
an immutable experiment fixture. Every executable lesson declares:

- QCore and notebook environment versions;
- allowed gates/features and execution budget;
- initial circuit or template hash;
- expected invariants rather than a single random sample;
- deterministic seed where sampling is graded;
- hint and rubric identifiers outside the quantum IR;
- migration status when the SDK changes.

**Inference:** This makes Academy a continuous compatibility test and distribution
channel while keeping pedagogy out of compiler/runtime modules.

## Measures and non-goals

| Objective | Phase 1 measure |
|---|---|
| Clearer compilation | 100% of passes emit coded diagnostics and before/after metrics |
| Reproducibility | Manifest replay reproduces canonical artifacts in CI |
| Stable integration | Public schema fixtures and compatibility tests cover every released version |
| Simulator trust | Randomized differential and invariant tests pass within declared tolerance |
| Educational fit | Bell/GHZ and one compiler lesson run in Python and JupyterLite feasibility build |
| Agent accessibility | Local tools validate against JSON Schema and support dry-run/budget errors |

**Decision:** Download counts, provider count, gate count, and unsupported speedup
claims are not Phase 1 success measures.

## Naming

- **Decision:** `qplanck` remains the distribution and implementation namespace.
- **Decision:** `qcore` is a future exact import and CLI facade only.
- **Verified:** An unrelated `qcore` distribution occupies that name on PyPI as of
  the evidence cut-off.
- **Decision:** No facade ships until `doctor` can identify distribution ownership
  and fail clearly on collision. See [RFC 0002](../../rfcs/0002-language-and-repository-strategy.md).
