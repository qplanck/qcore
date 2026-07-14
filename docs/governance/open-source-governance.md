# Open-Source Governance Recommendation

> Status: Proposed for Phase 0 review

## Recommendation

**Decision:** Retain Apache License 2.0, DCO 1.1 without a CLA, semantic versioning,
public RFCs, private security reporting, the existing code of conduct, and open
contribution guidelines. Add an explicit trademark policy before public promotion
or third-party distributions imply affiliation.

## License assessment

| Model | Patent grant | Permissive reuse | Enterprise familiarity | QCore assessment |
|---|---:|---:|---:|---|
| Apache-2.0 | Explicit | Yes, with notices | High | **Retain:** useful patent terms and compatible with broad adoption |
| MIT | No explicit patent clause | Very high | High | Simpler but weaker fit for compiler/hardware patent concerns |
| BSD-3-Clause | No explicit patent clause | High | High | Similar permissive option; no reason to churn existing project |
| Dual/community-commercial | Depends | Complex | Variable | Reject initially; risks trust and administration without a proven business need |

**Inference:** License churn would impose review and contributor-consent costs
without improving Phase 1 execution. Dependencies and optional integrations still
require license compatibility review; QCore's Apache license does not override
their terms. Mitiq's GPL-3.0 status, for example, requires explicit legal review
before distribution-level integration.

## Contribution agreement

- **Decision:** Continue DCO sign-off using `Signed-off-by` trailers.
- **Decision:** Do not require a CLA in the initial governance model.
- **Decision:** Document that contributors certify origin and licensing through
  DCO; maintainers do not promise future relicensing rights.
- **Open Question:** A CLA may be reconsidered only for a concrete legal need and
  would require a public RFC; enterprise optionality alone is insufficient.

## Governance model

Start with a transparent maintainer-led model appropriate to a small project:

| Role | Responsibilities | Appointment/removal |
|---|---|---|
| Contributor | Issues, docs, code, tests, RFC feedback under DCO | Any accepted contribution |
| Reviewer | Review in declared area; cannot release by role alone | Maintainer nomination based on sustained work |
| Maintainer | Merge, triage, releases, RFC decisions, security rotation | Existing maintainers by documented consensus |
| Release manager | Run one release checklist; no permanent extra authority | Assigned per release |
| Security contact | Receive and coordinate private reports | Named privately/public alias; least-access rotation |

- Maintainer names and ownership areas are published.
- Significant decisions include rationale and dissent; no private product roadmap
  silently changes public compatibility contracts.
- Conflicts of interest and employer/provider relationships relevant to a decision
  are disclosed.
- Governance changes use the RFC process.

**Open Question:** A technical steering committee is premature. Trigger review
when at least three independent maintainers regularly share release responsibility
or organizational conflicts can no longer be resolved by documented consensus.

## RFC process

1. Author opens a numbered RFC as `Proposed` with motivation, scope, alternatives,
   contracts, compatibility, security, testing, migration, and unresolved questions.
2. Maintainer assigns owners and a review window of at least 14 calendar days for
   breaking/public architecture decisions.
3. Implementable prototypes may accompany the RFC but cannot establish the public
   decision before acceptance.
4. Decision states are `Proposed`, `Accepted`, `Rejected`, `Withdrawn`, and
   `Superseded`.
5. Acceptance records approvers, date, dissent, required follow-ups, and target
   release.
6. Material changes after acceptance return the RFC to review or use a superseding
   RFC.

**Decision:** RFCs 0001-0004 remain `Proposed` until the Phase 0 milestone review
is explicitly accepted.

## Release policy

- Follow Semantic Versioning 2.0.0 for the distribution and independently version
  JSON schemas/contracts.
- During `0.x`, minor releases may evolve APIs, but deprecations still require
  release notes, coded warnings, migration guidance, and normally one minor-release
  overlap.
- Patch releases fix compatible defects and may reject previously accepted unsafe
  input when security/correctness requires it.
- Pre-releases use PEP 440 identifiers and do not imply stable compatibility.
- Every release publishes changelog, compatibility matrix, schema changes, wheel
  hashes, SBOM, build provenance when available, and known limitations.
- Release artifacts are built in CI from a protected tag by least-privilege trusted
  publishing; maintainers do not upload workstation-built wheels.

## API and deprecation policy

| Surface | Compatibility promise after stable release |
|---|---|
| Public Python imports | Semantic versioning; documented deprecation cycle |
| CLI command/exit code/JSON mode | Versioned contract; human prose may improve compatibly |
| CircuitIR/trace/manifest schema | Explicit reader/writer version matrix and migrations |
| Diagnostic code | Never reused for a different meaning; fields evolve additively within schema |
| Plugin/backend contract | Independent major version and conformance tests |
| Experimental namespace | May change in minor releases; visibly marked in docs/runtime |
| Private module/name | No compatibility promise |

**Decision:** Existing `Simulator` is a v0.x compatibility commitment. Any future
removal requires an accepted RFC, equivalent migration, and warning period.

## Security governance

- Keep the reporting path in `SECURITY.md` and acknowledge reports promptly.
- Avoid public issue disclosure before a fix/coordinated advisory when users are
  exposed.
- Define supported versions before the first public release.
- Publish advisories, severity rationale, affected versions, mitigation, and credit
  with reporter consent.
- Security fixes may bypass normal RFC timing but receive retrospective review.
- Provider credentials and hosted services require separate operational access and
  incident policies before launch.

## Trademark policy

**Decision:** Code license and trademark permission are separate. Before broader
ecosystem promotion, publish a policy that:

- permits truthful nominative use such as "compatible with QCore";
- permits unmodified community event/tutorial references;
- requires approval for names/logos implying an official distribution, provider,
  certification, partnership, or hosted service;
- prohibits confusing package names and altered logos that imply endorsement;
- provides a contact and fair correction process;
- preserves community forks' ability to describe origin while requiring distinct
  branding for modified products.

**Open Question:** Final policy wording and mark ownership require counsel review.
Until then, maintainers should not promise trademark licenses beyond nominative use.

## Documentation and decision transparency

- Architecture, schemas, test contracts, and roadmap gates remain public.
- Benchmark claims include workloads, pinned versions, machine details,
  correctness checks, statistics, and raw data.
- Provider sponsorship does not alter benchmark criteria or suppress limitations.
- AI-assisted contributions are reviewed under the same DCO, testing, security,
  and authorship expectations as other contributions.
- Course content pins supported QCore versions and publishes migration status.

## Long-term support

**Decision:** Do not promise LTS during alpha. Revisit after a stable 1.0, sustained
maintainer capacity, security response coverage, and real downstream demand. Until
then, publish a bounded supported-version window with every release.

## Phase 0 governance actions

1. Accept or reject RFCs 0001-0004 in a recorded milestone review.
2. Publish maintainer and ownership information before external contribution push.
3. Add a documented RFC template and state transitions in Phase 1.
4. Add release/SBOM/provenance workflow before publishing to PyPI.
5. Draft the trademark policy before official adapter naming guidance is promoted.
6. Keep DCO checks and code-of-conduct enforcement visible in contribution docs.
