# QCore Documentation

> Product direction: adaptive execution layer and adaptive performance portability
>
> Implementation status: `qplanck 0.3.0a1` alpha plus an offline v0.1
> research-kernel planner vertical slice
> Evidence cut-off: 2026-08-09

QCore is the open-source, vendor-neutral adaptive execution layer for quantum
computing. Its execution planner is intended to turn a `Program`, candidate
`Target` snapshots, and an `Objective` into a validated, ranked, explainable
`Plan`, then preserve the relationship from `Execution` to `Result`. The core
promise is **adaptive performance portability** across changing compiler,
provider, device, calibration, and objective conditions.

QCore is the product brand. The SDK is currently distributed and imported as
`qplanck`. Any future `qcore` import or CLI is **Proposed**, not implemented
because that name is owned by an unrelated distribution.

The exact [QCore Master Specification](QCORE_MASTER_SPECIFICATION.md) governs
product and build decisions. Repository-specific RFCs and status/conformance
documents describe adaptations and implementation gaps; they do not silently
amend or weaken the master report.

The current worktree adds a tested offline planner vertical slice and a 15-pair
exact-small development cohort to its native compiler, routing, runtime, and
provider-adapter foundations. This is not yet full acceptance of every normative
v0.1 criterion, provider execution evidence, or a competitive-performance
result. Read the
[implementation report](implementation-report-v0.1.md) for the exact boundary.
The [planner development report](planner-development-report-v0.1.md) records the
fairer Qiskit comparison, including its unfavorable row.
The [implementation conformance matrix](implementation-conformance-v0.1.md)
maps the full master specification to implemented, partial, and open work.
Read the [machine-checked claim matrix](claims.md) and
[SDK standards contract](sdk-standards.md) before making feature, provider, or
performance claims.

## Evidence labels

- **Verified**: directly supported by source code, a test run, supplied product
  evidence, or a cited primary source.
- **Inference**: analysis or a recommendation derived from verified evidence.
- **Open Question**: unresolved evidence, ownership, scope, or validation work.
- **Decision**: a Phase 0 architectural choice proposed for milestone review.

The evidence cut-off applies to external versions and product capabilities.
Re-check time-sensitive facts before implementation or publication.

## Start here

1. [QCore master specification](QCORE_MASTER_SPECIFICATION.md)
2. [Product thesis](thesis.md)
3. [Normative v0.1 planner specification](spec-v0.1.md)
4. [v0.1 research-kernel implementation report](implementation-report-v0.1.md)
5. [Exact-small planner development report](planner-development-report-v0.1.md)
6. [v0.1 implementation conformance matrix](implementation-conformance-v0.1.md)
7. [Architecture](architecture.md)
8. [Canonical strategic roadmap](roadmap.md)
9. [Claim matrix](claims.md)
10. [SDK standards and capability contract](sdk-standards.md)
11. [Current interoperability contract](interop.md)
12. [Publishing guide](publishing.md)

## Research

- [Source register](research/source-register.md)
- [Ecosystem audit](research/ecosystem-audit.md)
- [qBraid analysis](research/qbraid-analysis.md)
- [Competitive matrix](research/competitive-matrix.md)
- [Current alpha audit](research/current-alpha-audit.md)

## Architecture and strategy

- [QCore master specification](QCORE_MASTER_SPECIFICATION.md)
- [Product thesis](thesis.md)
- [Normative v0.1 planner specification](spec-v0.1.md)
- [v0.1 research-kernel implementation report](implementation-report-v0.1.md)
- [Exact-small planner development report](planner-development-report-v0.1.md)
- [v0.1 implementation conformance matrix](implementation-conformance-v0.1.md)
- [Canonical strategic roadmap](roadmap.md)
- [QCore positioning](strategy/qcore-positioning.md)
- [System overview](architecture/qcore-overview.md)
- [Native core contract](architecture/native-contract.md)
- [IR strategy](architecture/ir-strategy.md)
- [Compiler pipeline](architecture/compiler-pipeline.md)
- [Runtime and backends](architecture/runtime-and-backends.md)
- [Plugin system](architecture/plugin-system.md)
- [AI-agent architecture](architecture/ai-agent-architecture.md)
- [QPlanck Labs](architecture/qplanck-labs.md)
- [Open-source governance](governance/open-source-governance.md)
- [Threat model](security/threat-model.md)
- [SDK standards and capability contract](sdk-standards.md)

## Delivery

- [v0.1 research-kernel implementation report](implementation-report-v0.1.md)
- [Exact-small planner development report](planner-development-report-v0.1.md)
- [v0.1 implementation conformance matrix](implementation-conformance-v0.1.md)
- [Canonical strategic roadmap](roadmap.md)
- [Detailed historical roadmap](roadmap/qcore-roadmap.md)
- [MVP definition](roadmap/mvp-definition.md)
- [Implementation backlog](roadmap/implementation-backlog.md)
- [Phase 0 milestone review](reviews/phase-0-review.md)
- [PyPI publishing guide](publishing.md)

## RFCs

- [RFC 0001: QCore charter](../rfcs/0001-qcore-charter.md)
- [RFC 0002: language and repository strategy](../rfcs/0002-language-and-repository-strategy.md)
- [RFC 0003: intermediate representation](../rfcs/0003-intermediate-representation.md)
- [RFC 0004: backend interface](../rfcs/0004-backend-interface.md)
- [RFC 0005: native target compiler](../rfcs/0005-native-target-compiler.md)
- [RFC 0006: Amazon Braket pulse adapter](../rfcs/0006-amazon-braket-pulse-adapter.md)

## Existing alpha references

- [Current adaptive architecture and alpha boundary](architecture.md)
- [Current interoperability contract](interop.md)
