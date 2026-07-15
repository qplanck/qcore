# RFC 0002: Language, Repository, and Naming Strategy

> Implementation note (`0.2.0a1`): the compiler now derives an immutable
> dependency graph and executes deterministic exact Python passes. No native
> module has been added; the benchmark and packaging gate below still applies.

- Status: **Proposed**
- Date: 2026-07-14
- Decision owners: Unassigned pending Phase 0 review
- Supersedes: None

## Summary

Retain a Python-first monorepo and the `qplanck` distribution/implementation
namespace. Introduce Rust or another native core only after published benchmarks
identify a material bottleneck that cannot be addressed within the Python design.
Reserve `qcore` as a future exact import and CLI facade with mandatory ownership
collision detection.

## Evidence

- **Verified:** The audited alpha is a Python `src/qplanck` package with NumPy as
  its only required runtime dependency and a passing Python 3.11-3.13 CI design.
- **Verified:** The local Python 3.13 audit passed Ruff, mypy, 25 tests, and the
  optional Qiskit adapter.
- **Verified:** The unrelated [`qcore` PyPI project](https://pypi.org/project/qcore/)
  occupied the distribution name on 2026-07-14.
- **Verified:** [`qplanck` on PyPI](https://pypi.org/project/qplanck/) exposed no
  project page on that date; this does not reserve the name.

## Repository decision

Use one repository for core, official adapters under active development, schemas,
Labs assets, agent tools, tests, benchmarks, documentation, and RFCs. Package and
dependency boundaries remain real even inside the monorepo.

The canonical staged package map is in the
[system overview](../docs/architecture/qcore-overview.md). Phase 0 creates no
native crates and moves no production modules.

## Language allocation

| Area | Default | Rationale |
|---|---|---|
| Public SDK, IR, compiler, runtime | Python 3.11+ | Existing code, accessibility, typing, iteration, education |
| Reference simulator | Python + NumPy `complex128` | Small auditable oracle and Pyodide path |
| CLI and schemas | Python/JSON | One behavior across platforms and agent tools |
| Labs kernel | Same Python wheel in Pyodide | Avoid second implementation |
| Provider adapters | Python packages around provider SDKs | Ecosystem compatibility and separate release cadence |
| Native/compiler acceleration | Undecided | Requires measured need and ownership plan |

## Native-code gate

Rust, C++, GPU, Wasm-native modules, or another language may enter core only when
an accepted follow-up RFC includes:

1. A public benchmark with pinned versions, representative workloads, machine
   specifications, statistical treatment, and correctness checks.
2. A profile identifying the actual bottleneck and attempted Python/data-structure
   improvements.
3. A measured user-facing objective and minimum material improvement.
4. Packaging support for all supported operating systems/Python versions and the
   browser impact.
5. Maintainers able to review, release, debug, and secure the new toolchain.
6. Fallback/compatibility behavior and migration cost.

No fixed speedup threshold is encoded before a benchmark exists.

## Namespace decision

- `qplanck` remains the authoritative distribution and implementation namespace.
- Public object identities, serialization schemas, and compatibility imports use
  `qplanck` during v0.x.
- `QCore` remains the product brand.
- A future exact `qcore` import re-exports approved `qplanck` public objects; it does
  not fork implementations or change class `__module__` identities.
- A future `qcore` console script delegates to the same CLI implementation.

## Collision problem

**Inference:** A QPlanck distribution that installs a top-level `qcore` package can
collide on disk/import resolution with the unrelated PyPI distribution, even if
the QPlanck wheel itself has another distribution name. Console script names can
also collide. The two facades cannot be advertised as safely co-installable.

**Decision:** Do not ship the facade until its packaging design and doctor checks
pass isolated collision tests on pip-supported platforms.

## Required `doctor` ownership detection

Before enabling or recommending the facade, `qplanck doctor` and future
`qcore doctor` must:

1. Use `importlib.metadata.packages_distributions()` to list every distribution
   claiming the top-level `qcore` package.
2. Resolve `importlib.util.find_spec("qcore")` and report its exact origin.
3. Match the origin to files owned by the expected QPlanck facade distribution.
4. Inspect `console_scripts` entry points named `qcore` and report every provider
   distribution and target.
5. Fail closed when ownership is absent, ambiguous, unrelated, or the resolved
   module/entry point is outside the expected installation.
6. Emit a stable machine-readable diagnostic and human remediation without
   importing the questionable `qcore` module.
7. Report canonical `qplanck` installation origin independently so core remains
   diagnosable.

Example future diagnostic:

```json
{
  "code": "QCORE-INSTALL-NAMESPACE-COLLISION",
  "severity": "error",
  "package": "qcore",
  "providers": ["qcore==1.11.1", "qplanck-qcore-facade==0.3.0"],
  "origin": "/environment/site-packages/qcore/__init__.py"
}
```

This JSON is **Proposed**. Doctor must not uninstall or mutate the environment.

## Adapter placement

- Core retains current Qiskit compatibility until extraction can preserve imports.
- New providers are separate distributions from their first implementation.
- Official adapters may live in the monorepo while they share CI/governance, but
  their dependency metadata, tests, release notes, and version cadence are
  independent.
- Provider SDKs never become required dependencies of `qplanck` core.

## Alternatives considered

| Alternative | Reason not selected |
|---|---|
| Rust-first rewrite | No benchmarked bottleneck; would disrupt proven Python/browser path |
| Polyrepo immediately | Coordination and release overhead before ownership boundaries are proven |
| Rename distribution to `qcore` | Name is occupied by unrelated project |
| Quietly install top-level `qcore` from `qplanck` | Unsafe collision and confusing package ownership |
| Keep brand and package names unrelated forever | Harms first-run clarity; facade remains a useful gated goal |

## Consequences

- Python remains the performance ceiling of core algorithms until evidence opens a
  native gate; specialized external backends provide scale.
- The repo may contain several packages but cannot rely on undeclared internal
  imports.
- Documentation must consistently distinguish QCore brand, `qplanck` current
  package/CLI, and **Proposed** `qcore` facade.
- Every publication re-checks both PyPI names.

## Open questions

- Should the facade be an opt-in distribution, a bundled alias, or postponed until
  name ownership changes? Packaging experiments must inform the decision.
- Which benchmark objective would justify native compiler work first?

## Acceptance record

Pending Phase 0 milestone review.
