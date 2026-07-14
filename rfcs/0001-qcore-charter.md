# RFC 0001: QCore Charter

- Status: **Proposed**
- Date: 2026-07-14
- Decision owners: Unassigned pending Phase 0 review
- Supersedes: None

## Summary

QCore will be an open, vendor-neutral, explainable, reproducible quantum
compile-inspect-run environment. Its first shared workflow serves learners, SDK
developers, and compiler researchers. The project will earn scope through small,
tested milestones and will not initially operate a provider marketplace or hosted
multi-tenant compute platform.

## Motivation

**Verified:** The current `qplanck` alpha proves a coherent path from circuit
construction through versioned IR, local statevector simulation, sampling, trace
JSON, ASCII rendering, and narrow OpenQASM/Qiskit interchange.

**Verified:** The Phase 0 [ecosystem audit](../docs/research/ecosystem-audit.md)
shows mature products already provide broad provider runtimes, high-performance
simulators, differentiable programming, pulse control, and hosted environments.

**Inference:** QCore can create distinct value by making validation, compilation,
target assumptions, execution, and reproducibility unusually inspectable rather
than duplicating those broad surfaces.

## Mission

QCore enables a user to express a quantum circuit, validate it, transform it
through a deterministic compiler, inspect every transformation, execute it under
explicit capabilities and budgets, and reproduce the resulting experiment.

## Initial users

1. Learners who need approachable builders and visible state/transformation
   explanations.
2. SDK developers who need typed APIs, stable schemas, diagnostics, and mocks.
3. Compiler researchers who need pass-level metrics, diffs, provenance, and replay.

Hardware engineers, provider operators, and enterprise platform teams are
long-term users, not Phase 1 product requirements.

## Design principles

This RFC adopts the principles in
[QCore positioning](../docs/strategy/qcore-positioning.md): explicit
transformations, reproducibility, deterministic local behavior, typed contracts,
capability fidelity, standards at edges, local-first operation, integration of
specialized engines, safe extensibility, one technical core for education,
agent-readable tools, and benchmark-gated native code.

## Phase 1 scope

- Preserve the current circuit API and `Simulator` compatibility.
- Harden and version CircuitIR, diagnostics, canonical serialization, and input
  limits.
- Add deterministic compiler/pass/analysis contracts and `CompilationTrace`.
- Add `CompiledCircuit`, `Target`, `Backend`, `ExecutionOptions`, `Job`, and
  `ExperimentManifest` contracts.
- Implement local statevector and mock backends only.
- Retain narrow OpenQASM 3 and Qiskit interoperability.
- Establish reproducible benchmarks and static JupyterLite feasibility.

## Non-goals

- Direct QPU submission or provider credentials.
- Broad conversion graph or provider catalogue.
- Sessions, billing, quotas, cloud scheduling, or multi-tenancy.
- Pulse control, calibrations, GPU/distributed simulation, or error mitigation.
- Native autodiff, hybrid kernels, dynamic circuits, or an MLIR dialect.
- General AI autonomy or remote job submission by an agent.
- Claims of compiler or simulator superiority without public benchmarks.

## Public promise

For a supported local circuit, QCore will answer:

1. Is the program valid, and if not, where and why?
2. Which target and capabilities were assumed?
3. Which passes ran and what did each change?
4. What resources were estimated and consumed?
5. How were counts, probabilities, and bit order interpreted?
6. Which versions, options, seeds, and artifacts reproduce the experiment?

## Success criteria

- Canonical artifacts and diagnostics are deterministic across supported CI
  platforms, within documented numeric tolerance boundaries.
- Every pass has declared dependencies/effects and replayable provenance.
- Local and mock implementations pass one backend contract suite.
- Manifest replay reproduces the Phase 1 reference experiments.
- Existing `Simulator` use remains compatible throughout v0.x.
- No provider credential or remote execution dependency enters core.
- Browser feasibility runs the same released wheel and canonical fixtures.

## Alternatives considered

| Alternative | Reason not selected |
|---|---|
| Full Qiskit/qBraid replacement | Breadth and maintenance exceed credible early capacity |
| Education-only circuit library | Would split teaching from stable research/SDK contracts |
| Provider-first runtime | Credentials and API churn arrive before core differentiation |
| MLIR-first compiler | Static circuit slice does not justify the infrastructure |
| AI-first orchestration product | Agents need stable tools, errors, permissions, and provenance first |

## Security and reliability

This charter adopts the [threat model](../docs/security/threat-model.md). Phase 1
must bound all untrusted input and exponential work, avoid code-executing
serialization, keep plugins explicitly trusted, and remove provider/spend risks by
not implementing them.

## Governance

Apache-2.0, DCO without CLA, semantic versioning, public RFCs, private security
reporting, and an explicit trademark policy govern the project, subject to
[governance review](../docs/governance/open-source-governance.md).

## Consequences

- The project may appear narrower than platforms advertising many providers.
- Compiler trace/schema quality becomes core product work, not optional debugging.
- Specialized capabilities arrive through adapters and explicit program types.
- Academy and Labs become real compatibility consumers of the same SDK.
- Scope expansion requires evidence and milestone review.

## Open questions

- Who accepts and owns this charter?
- Which Phase 1 adoption metric best complements correctness and compatibility?
- What public trademark wording is approved?

## Acceptance record

Pending. This RFC remains **Proposed** until the Phase 0 milestone review records
approvers, date, dissent, and assigned follow-up owners.
