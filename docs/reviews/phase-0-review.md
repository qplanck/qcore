# Phase 0 Milestone Review

> Milestone: Research and Architecture Gate  
> Review status: **Ready for human review; not accepted**  
> Evidence cut-off: 2026-07-14  
> Implementation baseline: commit `2f2ed07`

## Gate recommendation

**Inference:** Proceed to Phase 1 only after a human reviewer accepts RFCs
0001-0004, assigns maintainers, and resolves the measurement and zero-shot open
questions. The research supports the proposed product wedge and architecture, but
this report does not self-approve production refactoring.

**Decision:** Phase 0 stops here. No compiler/runtime refactor, `qcore` alias,
provider adapter, or Labs implementation is included in this milestone.

## Conclusions

1. **Inference:** QCore should exist as an explainable, reproducible
   compile-inspect-run environment, not as a broad SDK/provider replacement.
2. **Verified:** The current alpha is a coherent prototype: circuit builder,
   versioned IR, reference simulator, sampling, traces, ASCII, and narrow
   OpenQASM/Qiskit interop all pass their baseline tests.
3. **Inference:** The alpha should be evolved behind compatible interfaces rather
   than rewritten. Its highest-priority gaps are measurement semantics, resource
   limits, structured diagnostics, compiler provenance, backend contracts, and
   manifests.
4. **Decision:** Keep a Python-first monorepo and `qplanck` namespace. Native code
   requires published benchmark evidence.
5. **Decision:** Keep custom CircuitIR for source/trace/provenance, OpenQASM 3 for
   exchange, QIR for future lowering, and defer MLIR.
6. **Decision:** Implement local and mock backends only in Phase 1 while retaining
   the current `Simulator` API throughout v0.x.
7. **Decision:** Build the first Labs proof as static JupyterLite/Pyodide; do not
   operate hosted untrusted kernels.
8. **Decision:** Keep plugins explicitly trusted and agents in a separate optional
   package with policy-enforced typed tools.

## Deliverable review

| Requirement | Canonical artifact | Status |
|---|---|---|
| Ten strategic questions | [Executive summary](../executive-summary.md) | Complete |
| Ecosystem audit | [Ecosystem audit](../research/ecosystem-audit.md) | Complete |
| qBraid analysis | [qBraid analysis](../research/qbraid-analysis.md) | Complete |
| Competitive matrix | [Competitive matrix](../research/competitive-matrix.md) | Complete |
| Source register | [Source register](../research/source-register.md) | Complete |
| Current-alpha audit | [Current alpha audit](../research/current-alpha-audit.md) | Complete |
| Positioning/design principles/build matrix | [QCore positioning](../strategy/qcore-positioning.md) | Complete |
| System architecture/package/API/dependencies | [System overview](../architecture/qcore-overview.md) | Complete |
| IR analysis and example | [IR strategy](../architecture/ir-strategy.md) | Complete |
| Compiler design | [Compiler pipeline](../architecture/compiler-pipeline.md) | Complete |
| Runtime/backends/API examples | [Runtime and backends](../architecture/runtime-and-backends.md) | Complete |
| Plugins and agents | [Plugin system](../architecture/plugin-system.md), [agent architecture](../architecture/ai-agent-architecture.md) | Complete |
| Labs and Academy direction | [QPlanck Labs](../architecture/qplanck-labs.md) | Complete |
| Threat/risk register | [Threat model](../security/threat-model.md) | Complete |
| Governance | [Open-source governance](../governance/open-source-governance.md) | Complete |
| Three-year and 30/60/90 roadmap | [Roadmap](../roadmap/qcore-roadmap.md) | Complete |
| MVP and exact backlog | [MVP](../roadmap/mvp-definition.md), [backlog](../roadmap/implementation-backlog.md) | Complete |
| RFCs 0001-0004 | [`rfcs/`](../../rfcs) | Proposed, as required |

## Baseline evidence

An isolated `/tmp/qcore-phase0-venv` environment used Python 3.13.12 with
`.[dev,qiskit]` installed.

| Check | Result |
|---|---|
| Ruff lint | Passed |
| Ruff format check | Passed on the implementation baseline |
| mypy `src/qplanck` | Passed; 11 files |
| pytest with coverage | Passed; 25 tests; 80% total line coverage |
| Optional Qiskit tests | Passed; Qiskit 2.5.0 |
| Current examples/CLI | Passed as part of the suite |

**Verified:** The baseline exposed no failing behavior before audit. Passing tests
do not resolve the measurement-mapping semantic gap documented below.

## Documentation validation

| Validation | Result |
|---|---|
| Mandatory document/source coverage | Passed; all required research, architecture, roadmap, review, and RFC artifacts present |
| Markdown lint | Passed across 32 repository Markdown files with markdownlint-cli2 0.23.0 |
| Relative links and anchors | Passed across 32 files with `tools/check_docs.py` |
| External links | Passed across all Markdown with markdown-link-check 3.14.2; expected-404 `qplanck` PyPI evidence is explicitly excluded |
| Mermaid rendering | Passed; all 11 diagrams rendered with Mermaid CLI 11.16.0 |
| Current code examples | Passed within the 25-test suite; dedicated docs CI configured |
| Production source unchanged | Passed; diff from `2f2ed07` under `src/qplanck` is empty |

## Evidence gaps

- **Open Question:** No common benchmark supports comparative compiler or simulator
  performance claims. Phase 1 backlog P1-054 creates the first honest baseline.
- **Open Question:** Provider pricing, quotas, service availability, and live job
  behavior were excluded as volatile and irrelevant to local Phase 1.
- **Open Question:** Commercial platform/code licensing needs legal review before
  integration, especially where service terms and source licenses differ.
- **Open Question:** External documentation can change after the evidence cut-off;
  source links and product versions must be rechecked at implementation gates.
- **Open Question:** User interviews/adoption evidence are not part of this
  codebase audit. The wedge remains an evidence-backed strategy hypothesis.
- **Open Question:** Final trademark wording needs counsel review.

## Correctness and security blockers

| Blocker | Evidence | Required resolution |
|---|---|---|
| Measurement mapping | Current sampling formats all qubits and ignores `MeasurementSpec.cbit` | Accept P1-002 semantics and executable fixtures before runtime extraction |
| Exponential allocation | Statevector allocates `2**qubits` complex128 with no ordinary-run limit | Accept P1-003 budgets and implement P1-015/P1-033 preflight |
| Shallow metadata immutability | Frozen dataclasses can contain mutable nested metadata | Implement recursive JSON validation/deep-freeze P1-011 |
| Parser resource bounds | QASM/JSON have no complete byte/depth/token policy | Implement P1-012/P1-040 and fuzz task P1-051 |
| Facade collision | Unrelated PyPI `qcore` can own the same import/CLI name | Do not ship facade; implement ownership check P1-042 first |

## Accepted Phase 1 risks

- In-process explicitly loaded Python plugins retain full host authority; auto-load
  remains disabled.
- The NumPy simulator is a small local oracle, not hardened multi-tenant compute.
- Content hashes identify artifacts but are not signatures or remote-execution
  attestations.
- Static Labs inherits browser/Wasm constraints and is limited to pinned workloads.
- No provider credentials or remote submissions exist, removing rather than
  deferring their immediate operational risk.

## Exact Phase 1 backlog

The canonical acceptance criteria, dependencies, sizes, and day bands are in the
[implementation backlog](../roadmap/implementation-backlog.md). The exact task set
approved for review is:

| Group | Task IDs and deliverables |
|---|---|
| Gate/semantics | P1-001 RFC ownership; P1-002 measurement; P1-003 budgets; P1-004 zero-shot/numerics |
| Contracts | P1-010 diagnostics; P1-011 JSON/deep-freeze; P1-012 IR validation/canonical JSON; P1-013 identity; P1-014 source/provenance; P1-015 estimates/policy |
| Compiler | P1-020 contracts; P1-021 pass manager; P1-022 validation; P1-023 canonicalization; P1-024 analyses; P1-025 inverse cancellation; P1-026 rotation merge; P1-027 compilation trace; P1-028 `Circuit.compile`/compiled artifact |
| Runtime | P1-030 target; P1-031 execution options; P1-032 backend/job protocols; P1-033 local extraction; P1-034 measurement application; P1-035 mock/job; P1-036 result/manifest; P1-037 replay |
| Interop/CLI | P1-040 QASM hardening; P1-041 Qiskit range; P1-042 doctor/collision; P1-043 compile/manifest/replay CLI |
| Verification | P1-050 correctness; P1-051 fuzzing; P1-052 backend conformance; P1-053 cross-platform goldens; P1-054 benchmark; P1-055 docs validation |
| Delivery | P1-060 API/migration docs; P1-061 JupyterLite; P1-062 Academy lesson; P1-063 release supply chain; P1-064 Phase 1 review |

No provider, native, dynamic-circuit, pulse, hosted-kernel, or remote-agent task is
part of this backlog.

## Required human decisions

1. Accept, reject, or revise RFCs 0001-0004 and record owners.
2. Accept exact measurement and zero-shot semantics.
3. Approve the Phase 1 resource-policy process and default-setting evidence.
4. Assign security/release responsibility and the first benchmark reviewer.
5. Confirm that static Labs feasibility, not hosted infrastructure, is the first
   product experiment.

## Final gate state

**Decision:** Ready for review does not mean accepted. Until the decisions above
are recorded, the repository should remain at the Phase 0 boundary and production
modules under `src/qplanck` should not be refactored for the proposed architecture.
