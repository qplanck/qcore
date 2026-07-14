# qBraid Analysis and QCore Boundary

> Status: Phase 0 research baseline  
> Evidence cut-off: 2026-07-14

## Evidence reviewed

- [qBraid SDK overview](https://docs.qbraid.com/v2/sdk/user-guide/overview)
- [qBraid Lab overview](https://docs.qbraid.com/v2/lab/user-guide/overview)
- [qBraid environment CLI](https://docs.qbraid.com/cli/api-reference/qbraid_envs)
- two product screenshots supplied with the QCore brief

## Verified product observations

**Verified (official documentation):** qBraid SDK v2 presents a vendor-neutral
Python SDK. Program representations are nodes in a directed conversion graph, and
its runtime layer exposes providers, devices, jobs, and results.

**Verified (official documentation):** qBraid Lab is a managed browser development
environment with preconfigured quantum environments, notebooks/IDE tooling,
GitHub integration, and access to CPU, GPU, and quantum resources.

**Verified (supplied dashboard screenshot):** The visible account has selectable
Small, Medium, and Large environment profiles, including VS Code variants; a CPU
hours indicator; Quantum Jobs; and quick actions for credits, AI assistance,
documentation, account settings, and support.

**Verified (supplied Explore screenshot):** The Explore view presents searchable
project cards, notebook labels, readiness badges, tags, source organizations, star
counts, and a GitHub-project submission path.

**Open Question:** The screenshots do not establish environment isolation,
provider coverage, pricing, collaboration semantics, execution guarantees, or the
implementation architecture behind the visible controls. QCore will not infer
those details.

## Strategic assessment

| Dimension | qBraid evidence | QCore inference |
|---|---|---|
| Primary value | Broad SDK conversion/runtime plus hosted lab access. | Do not compete on breadth; win a narrower local workflow. |
| Integration burden | Directed conversion graph and multiple runtime providers. | A small team should maintain only selected adapters backed by contract tests. |
| Learning workflow | Lab and project discovery reduce setup friction. | Academy can distribute QCore through executable, version-pinned notebooks. |
| Developer environment | Managed profiles offer native toolchains and resource tiers. | Static JupyterLite is a credible first step with far lower operations burden. |
| Jobs and hardware | Runtime concepts and visible job workflow connect to remote resources. | Define generic contracts now, but implement local/mock only. |
| AI surface | Screenshot shows an AI entry point. | QCore agents should use typed, deterministic tools rather than making chat the architecture. |
| Project discovery | Explore catalog exposes community projects and metadata. | Defer marketplace/catalog work; first make experiments portable and reproducible. |

## What to learn from qBraid

- **Inference:** Environment setup is part of the product, not incidental
  documentation. QCore's `doctor`, examples, and Labs build must be treated as one
  first-run contract.
- **Inference:** Conversion and provider integrations are more sustainable when
  modeled as explicit registries with capability metadata.
- **Inference:** A project can connect education, tooling, and execution without
  forcing every learner into a provider-specific SDK.
- **Inference:** Visible jobs and resources make remote execution legible; QCore's
  future job model should expose state and cost-related metadata explicitly.

## What not to copy

- **Decision:** Do not clone the screenshots or reproduce qBraid's dashboard
  information architecture.
- **Decision:** Do not build a broad conversion graph before QCore has stable
  provenance and loss reporting.
- **Decision:** Do not launch managed containers, QPU credentials, credits,
  billing, scheduling, or a project marketplace in the initial phases.
- **Decision:** Do not normalize provider-specific capabilities away merely to
  present a single shallow interface.

## QCore's differentiated wedge

**Inference:** The opportunity adjacent to qBraid is a transparent development
loop:

```text
construct -> validate -> compile -> inspect diff -> simulate -> reproduce
```

For each arrow, QCore should expose stable inputs, outputs, diagnostics,
provenance, and metrics. A learner can understand a transformation, an SDK
developer can test it, and a researcher can replay it. Broad cloud access can be
integrated later without being the reason the core exists.

## Competitive boundary

**Decision:** QCore will treat qBraid as a potential future interoperability or
distribution partner, not a target to displace. Any future adapter must live
outside core, declare supported qBraid versions, preserve original payloads where
needed, and pass a provider-neutral contract suite.
