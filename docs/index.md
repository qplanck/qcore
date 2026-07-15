# QCore Documentation

> Status: `qplanck 0.2.0a1` implementation and release preparation
> Evidence cut-off: 2026-07-14

QCore is the product brand. The SDK is distributed and imported as `qplanck`.
Any future `qcore` import or CLI is **Proposed**, not implemented because that
name is owned by an unrelated distribution.

The current alpha includes a deterministic graph-based compiler foundation,
loss-aware OpenQASM/Qiskit exchange, an experimental QIR base-profile export
boundary, and an experimental hardware-neutral pulse/calibration model. Read the
[SDK standards and capability contract](sdk-standards.md) before making feature
or performance claims.

## Evidence labels

- **Verified**: directly supported by source code, a test run, supplied product
  evidence, or a cited primary source.
- **Inference**: analysis or a recommendation derived from verified evidence.
- **Open Question**: unresolved evidence, ownership, scope, or validation work.
- **Decision**: a Phase 0 architectural choice proposed for milestone review.

The evidence cut-off applies to external versions and product capabilities.
Re-check time-sensitive facts before implementation or publication.

## Start here

1. [SDK standards and capability contract](sdk-standards.md)
2. [Current interoperability contract](interop.md)
3. [Prototype architecture](architecture.md)
4. [Publishing guide](publishing.md)
5. [Executive summary](executive-summary.md)
6. [Phase 0 milestone review](reviews/phase-0-review.md)

## Research

- [Source register](research/source-register.md)
- [Ecosystem audit](research/ecosystem-audit.md)
- [qBraid analysis](research/qbraid-analysis.md)
- [Competitive matrix](research/competitive-matrix.md)
- [Current alpha audit](research/current-alpha-audit.md)

## Architecture and strategy

- [QCore positioning](strategy/qcore-positioning.md)
- [System overview](architecture/qcore-overview.md)
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

- [Roadmap](roadmap/qcore-roadmap.md)
- [MVP definition](roadmap/mvp-definition.md)
- [Implementation backlog](roadmap/implementation-backlog.md)
- [Phase 0 milestone review](reviews/phase-0-review.md)
- [PyPI publishing guide](publishing.md)

## Proposed RFCs

- [RFC 0001: QCore charter](../rfcs/0001-qcore-charter.md)
- [RFC 0002: language and repository strategy](../rfcs/0002-language-and-repository-strategy.md)
- [RFC 0003: intermediate representation](../rfcs/0003-intermediate-representation.md)
- [RFC 0004: backend interface](../rfcs/0004-backend-interface.md)

## Existing alpha references

- [Prototype architecture](architecture.md)
- [Current interoperability contract](interop.md)
