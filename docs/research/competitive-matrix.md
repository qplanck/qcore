# Competitive Matrix

> Status: Phase 0 research baseline  
> Evidence cut-off: 2026-07-14

## Scoring method

**Verified:** Scores describe documented product emphasis, not absolute quality or
feature completeness. Criteria are applied consistently:

- `3`: first-class, documented product capability;
- `2`: substantial capability, integration, or extension;
- `1`: limited, indirect, or specialized support;
- `0`: outside the documented core scope;
- `?`: evidence insufficient for a responsible score.

**Inference:** The matrix is useful for positioning, not procurement. Detailed
evidence and limitations are in the [ecosystem audit](ecosystem-audit.md).

## Capability comparison

| System | Approachable circuits | Compiler depth | Pass inspection/provenance | Local simulation | Provider runtime breadth | Browser lab | Education | Differentiable/hybrid | Pulse/analog | Agent-safe structured tools |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QCore audited alpha | 3 | 0 | 1 | 2 | 0 | 0 | 2 | 0 | 0 | 1 |
| QCore Phase 1 target | 3 | 2 | 3 | 2 | 0 | 1 | 3 | 0 | 0 | 2 |
| qBraid SDK + Lab | 2 | 1 | 1 | 2 | 3 | 3 | 3 | 1 | 1 | 1 |
| Qiskit + Runtime + Aer | 3 | 3 | 2 | 3 | 2 | 1 | 3 | 1 | 2 | 1 |
| Cirq + Cirq Google + qsim | 3 | 2 | 1 | 3 | 1 | 1 | 2 | 1 | 1 | 1 |
| TKET / pytket | 2 | 3 | 2 | 2 | 3 | 0 | 2 | 1 | 1 | 1 |
| PennyLane + Catalyst | 3 | 3 | 2 | 3 | 3 | 1 | 3 | 3 | 2 | 1 |
| CUDA-Q | 2 | 3 | 2 | 3 | 3 | 1 | 2 | 2 | 2 | 1 |
| Amazon Braket | 3 | 2 | 1 | 3 | 3 | 2 | 2 | 2 | 2 | 1 |
| Azure Quantum + QDK/Q# | 2 | 3 | 2 | 3 | 3 | 2 | 3 | 1 | 2 | 1 |
| Classiq | 2 | 3 | 1 | 2 | 3 | 2 | 2 | 2 | 1 | 1 |
| Pulser | 2 | 2 | 2 | 2 | 1 | 1 | 3 | 1 | 3 | 1 |
| Strawberry Fields | 2 | 1 | 1 | 3 | 0 | 1 | 3 | 3 | 3 | 0 |
| ProjectQ | 2 | 2 | 1 | 2 | 1 | 0 | 2 | 0 | 0 | 0 |
| PyZX | 1 | 3 | 3 | 1 | 0 | 2 | 3 | 0 | 0 | 0 |

## Positioning options

| Option | Evidence-based advantage | Cost and risk | Recommendation |
|---|---|---|---|
| Complete incumbent replacement | Full control of stack. | Requires compiler, simulators, providers, cloud operations, docs, and ecosystem compatibility at once. | **Reject.** Not credible for a small Phase 1 team. |
| Broad interoperability layer | Existing SDK demand and many formats. | qBraid and mature adapter ecosystems already cover this; round-trip fidelity is expensive. | **Defer.** Implement only OpenQASM 3 and narrow Qiskit adapters already proven. |
| Compiler/runtime layer | Proven demand for target-aware passes and backend contracts. | Compiler correctness, diagnostics, and compatibility are demanding but bounded locally. | **Select in a narrow form.** Focus on deterministic inspection and local/mock runtime. |
| Educational SDK | Direct Academy distribution and approachable surface. | Education-only positioning can weaken research credibility. | **Select as an audience mode, not a separate architecture.** |
| AI orchestration layer | Machine-readable tools are underserved. | Unsafe submission, prompt injection, and unstable APIs can destroy trust. | **Design now, package later.** Local read/compile/simulate tools first. |
| Research compiler | Explainable passes and provenance can differentiate. | Advanced synthesis and MLIR are expensive. | **Select pass-level inspection; integrate mature algorithms.** |
| Unified experiment platform | Reproducibility connects SDK, Labs, and Academy. | Hosted storage and collaboration expand scope rapidly. | **Select portable local manifests; defer cloud platform.** |

## Feature-priority matrix

Impact uses the first three audiences; effort is relative for a small Python team.

| Capability | User impact | Differentiation | Effort | Dependency risk | Phase decision |
|---|---:|---:|---:|---:|---|
| Stable diagnostics and schema validation | High | High | Medium | Low | Phase 1, must |
| Deterministic pass manager and compilation trace | High | High | Medium | Low | Phase 1, must |
| Experiment manifest and replay | High | High | Medium | Low | Phase 1, must |
| Local/mock backend contracts | High | Medium | Medium | Low | Phase 1, must |
| Hardened NumPy reference simulator | High | Medium | Low | Low | Phase 1, must |
| OpenQASM 3 exchange | High | Medium | Low | Medium | Retain and harden |
| Qiskit adapter | Medium | Low | Medium | High | Retain narrow subset |
| JupyterLite feasibility build | High | Medium | Medium | Medium | First 90 days |
| Topology placement/routing | Medium | High | High | Low | Phase 2 |
| External simulator adapters | Medium | Low | Medium | High | Phase 2, demand-led |
| Provider/QPU adapters | Medium | Low | High | Very high | Phase 4 |
| Dynamic control and multi-level IR | Medium | High | Very high | Medium | Phase 5, gated |
| Pulse/control model | Low initially | Medium | Very high | Very high | Defer |
| GPU/distributed simulator | Low initially | Low | Very high | Very high | Integrate, do not build |
| Hosted multi-tenant Lab | Medium | Low | Very high | Very high | Defer |
| Agent job submission | Low initially | Medium | High | Very high | Phase 6, guarded |

## Conclusion

**Inference:** QCore's credible white space is the intersection of approachable
learning, deterministic compiler inspection, and reproducible local experiments.
No matrix score establishes market superiority; the Phase 1 milestone must prove
that workflow with adoption and correctness evidence before the scope expands.
