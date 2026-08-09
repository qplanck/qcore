# QCore v0.1 Research-Kernel Implementation Report

> Evidence date: 2026-08-09
> Worktree package: `qplanck 0.3.0a1`
> Scope: offline planner vertical slice; no provider submission or hardware claim
> Governing specification: [QCore Master Specification](QCORE_MASTER_SPECIFICATION.md)
> Repository companion: [QCore Planner Product Specification v0.1](spec-v0.1.md)

## Outcome

The worktree now contains the smallest coherent QCore adaptive-planning vertical
slice. It can normalize a supported program, evaluate declared compiler
strategies against immutable provider-neutral target snapshots, reject invalid
candidates, measure and rank the remaining candidates under an explicit
objective, explain the selected plan, and emit a secret-free reproducibility
manifest.

The first executable offline smoke fixture returned **`vertical-slice-go` under
its own narrow criterion**: the two-candidate portfolio selected adaptive
placement, reduced every declared structural/output-quality estimate relative
to the canonical-layout baseline, and reproduced the same frozen-seed
terminal-measurement counts and exact statevector-derived terminal probability
marginal. Its artifact records the master-specification v0.1 gate separately as
**`not_evaluated`**.

This is evidence for offline compiler-selection behavior on one synthetic target.
It is not acceptance of every normative v0.1 requirement, evidence of improved
hardware outcomes, a general performance result, or a claim that QCore beats
another compiler.

The full master-specification v0.1 go/no-go gate remains **open**. It requires,
among other things, fair strong/equal-budget baselines, a preregistered held-out
benchmark, the complete correctness floor, offline replay, statistical reporting,
and independent human review. The current evidence therefore supports
**research continue**, not the master specification's product-level **Go**
decision. See the
[implementation conformance matrix](implementation-conformance-v0.1.md).

## Implemented behavior

### Planning contracts and decision engine

- `Program` normalizes the existing QCore `Circuit`/`CircuitIR`, the current safe
  OpenQASM 3 subset, and the current direct Qiskit subset. It records frontend and
  parser provenance while deriving a frontend-independent semantic hash from the
  normalized IR.
- `Objective` supports versioned deterministic weighted minimization, inclusive
  hard constraints, scales, explicit unknown-metric policy, and stable tie-break
  terms.
- `CandidatePlan`, `PlanMetrics`, `Plan`, and `PlanningManifest` are immutable,
  schema-versioned, canonically serialized, and hash-checked on restoration.
  Candidate evidence retains valid, rejected, unavailable, unsupported, failed,
  and timed-out dispositions rather than silently dropping integrations.
- The provider-neutral `CompilerStrategy` contract normalizes artifacts and
  evidence. `QCoreNativeStrategy` reuses the existing native O2 compiler, and the
  default offline portfolio compares adaptive placement with an identity-layout
  baseline.
- Planning validates semantic evidence and final target instruction/location
  support before scoring, then applies constraints, ranks with deterministic
  tie-breaking, marks Pareto candidates, and fails with retained evidence if no
  valid candidate remains.
- `Plan.explain()` reports the winning target and strategy, metrics, score terms,
  assumptions, validation evidence, alternatives, rejection groups, and the
  offline/hardware caveat.
- `PlanningManifest` binds the program, objective, target snapshots, complete
  candidate set, selected plan, tool versions, and observations. Secret-shaped
  fields and provider SDK objects fail closed. Wall-clock and latency observations
  are excluded from semantic plan and manifest identities.

The public researcher entry point is available from the current package name:

```python
import qplanck

decision = qplanck.plan(
    circuit,
    targets=[target_snapshot],
    objective="minimize_error",
)
print(decision.explain())
decision.manifest.write("planning-manifest.json")
```

### Metrics and approximation boundary

Each transformed artifact records:

- final operation depth, excluding terminal measurements;
- two-qubit operation count and operation families;
- compiler-inserted SWAP count when the strategy preserves recoverable evidence,
  otherwise `unknown` with a reason;
- user-authored SWAP count separately;
- compilation latency as an observation, not a semantic identity or a benchmark
  claim; and
- estimated error under `independent_instruction_error_v1` when every included
  instruction has an error value in the exact target snapshot.

The estimated-error model is:

```text
estimated_error = 1 - product(1 - instruction_error_i)
```

It assumes independent stochastic instruction failures and excludes readout,
coherent error, crosstalk, correlated noise, state dependence, scheduling,
calibration drift, queues, and cost. Missing evidence remains unknown; it is not
converted to zero. The value is a ranking heuristic, not predicted hardware
fidelity.

### Optional Qiskit strategy

`QiskitCompilerStrategy` lazy-loads the optional Qiskit dependency and exposes
fixed-seed transpilation at optimization levels 0 through 3. It derives the
coupling map and basis from the immutable QCore target, fixes SABRE layout and
routing plus single-process execution, validates the returned artifact against
the target, and records the Qiskit version and effective options.
`qiskit_strategies()` builds a deterministic, de-duplicated portfolio across the
requested levels without importing Qiskit until a candidate runs.

For the supported validation profile it compares exact statevector-derived
terminal classical marginals from the all-zero initial state. Validation is
currently limited to eight logical/active qubits and terminal measurements.
Unsupported output or unavailable Qiskit becomes explicit candidate evidence.
An inserted-SWAP value is reported only when an explicit added `swap` survives in
the returned artifact; otherwise the metric remains unknown.

### Offline IBM target normalization

`target_from_ibm_backend()` converts an already-obtained IBM BackendV2-like
object into the provider-neutral `Target` contract without importing
`qiskit-ibm-runtime`, discovering devices, reading credentials, or submitting a
job. It records backend identity, topology, normalized supported instructions,
instruction/qubit calibration fields, timing, limits, source versions, snapshot
time, and explicit unknown/excluded fields. The resulting snapshot is composed
only of JSON values and has deterministic snapshot/content hashes when the
capture time and source capabilities are fixed.

The adapter deliberately excludes provider/session objects and credentials.
Operations outside the current QCore instruction model, including common IBM
operations such as `ecr` and measurement-as-an-instruction, are retained as
excluded capability evidence rather than claimed as executable support.

### `qcore-bench` smoke gate

`benchmarks.planner` defines a versioned five-qubit non-local circuit, a fixed
five-qubit line target, a minimize-estimated-error objective, one canonical
baseline, and a two-candidate adaptive portfolio. It writes a complete JSON
report and five JSONL records containing baseline, adaptive, manifest,
correctness, environment, and gate evidence. Correctness combines an exact
statevector-derived terminal classical marginal with a frozen-seed sampled-count
check.

## Recorded vertical-slice benchmark result

Artifacts:

- [Complete JSON report](../benchmarks/results/planner-gate.json)
  (`SHA-256 a2e7c270cf51971ab63f7b36d76b5be8ff9a7762f36141d8623be2fc4ca38d28`)
- [Raw JSONL records](../benchmarks/results/planner-gate.jsonl)
  (`SHA-256 d025268fbc889f2c34b93a1002bbe6fdc5bbab09011460170123326c3ebf394b`)

Recorded environment: CPython 3.14.5, Darwin 25.5.0, arm64. Workload seed was 9.
Every checked artifact reproduced the exact terminal marginal `00000:
0.5000000000000001`, `10101: 0.5000000000000001` with maximum probability
delta 0 under tolerance `1e-12`. The additional 4,096-shot frozen-seed check
reproduced counts `00000: 2034` and `10101: 2062`.

| Metric | Canonical-layout baseline | Selected adaptive placement | Baseline minus adaptive |
|---|---:|---:|---:|
| Circuit depth | 12 | 3 | 9 |
| Two-qubit gates | 15 | 3 | 12 |
| Inserted SWAPs | 4 | 0 | 4 |
| `independent_instruction_error_v1` | 0.14080170371335277 | 0.030671299000000003 | 0.11013040471335277 |

The selected strategy was `qcore-native.adaptive-placement`. The target hash was
`sha256:e780d26b0081817e0ac7d1b8c3811b7613786c3ee0ba829bafb0d06ab200616c`.
Correctness was preserved under the declared check, at least one metric improved,
and the adaptive candidate won, so the fixture's internal smoke decision is
**`vertical-slice-go`**. The artifact records the full v0.1 gate as
**`not_evaluated`**; this is not the go/no-go decision defined by the master
specification.

Compilation latency appears in the raw artifact as observational provenance, but
this single warm run is not a timing study and is intentionally omitted from the
comparison table and claim decision.

## Exact-small multi-target development evidence

The next increment adds `benchmarks.planner_acceptance`, a draft development
protocol spanning five measured workload families and three immutable synthetic
IBM-style target snapshots. For each of 15 workload/target pairs it compares an
ordinary Qiskit level-1 recipe, eight Qiskit level/seed attempts, and an
eight-attempt mixed Qiskit/QCore-native portfolio under the same Objective.

All 255 valid candidate occurrences passed the declared exact terminal-marginal
check (180 unique candidate IDs and 67 unique compiled artifact hashes), and all
45 generated manifests passed hash-integrity round trips plus
offline compiler-reexecution replay with exact strategy descriptors in the
current environment. Against the ordinary Qiskit recipe the mixed portfolio
recorded 6 material wins, 9 ties, and no material losses. Against the stronger
same-attempt Qiskit baseline it recorded 2 material wins, 12 ties, and 1 material
loss. Median improvement among the two strong-baseline material wins was 25.07%;
median improvement across all pairs was 0%.

The unfavorable row is retained: decomposed QFT on the ring target was 16.26%
worse than the strong Qiskit baseline because that baseline's winning Qiskit
level-2/seed-17 attempt was not allocated to the mixed portfolio. This exposes a
real recipe-budget trade-off rather than a ranking error.

This evidence is classified **research continue**. The protocol is still draft,
wall time is not equalized, semantic validation covers one exact-small initial
state boundary, the compact committed report is not a locked complete replay
bundle, and no TKET, BQSKit, held-out, or independent-review evidence exists.
Read the complete [planner development report](planner-development-report-v0.1.md)
and its [JSON](../benchmarks/results/planner-development.json) and
[JSONL](../benchmarks/results/planner-development.jsonl) artifacts. The master
v0.1 gate remains `not_evaluated`.

## Reproduce and validate

Install the editable worktree and optional test integrations, then build the
native extension as described in the [publishing guide](publishing.md). Run the
planner gate from the repository root:

```bash
python -m benchmarks.planner \
  --output benchmarks/results/planner-gate.json \
  --jsonl benchmarks/results/planner-gate.jsonl
```

The evidence above was generated in the current development environment with:

```bash
PYTHONPATH=src ./.venv/bin/python3.14 -m benchmarks.planner \
  --output benchmarks/results/planner-gate.json \
  --jsonl benchmarks/results/planner-gate.jsonl
```

Final local validation completed after artifact generation:

| Check | Result |
|---|---|
| Focused planner/replay/IBM/Qiskit/public API/benchmark tests | 95 passed |
| Full root Python suite | 274 passed in 7.74 seconds |
| Ruff lint, repository-wide | Passed |
| Ruff format, Python files added or revised by this increment | Passed |
| MyPy over `src/qplanck` | Passed, 24 source files |
| Documentation links and Mermaid extraction | 53 Markdown files and 16 diagrams passed |
| Rust format / no-default-features check / Clippy | Passed |
| Rust tests | 12 passed |
| Rust advisories, bans, licenses, and sources | Passed with `cargo deny` |
| Python runtime dependency/license policy and `pip check` | Passed |
| Maturin release wheel and source distribution | Built successfully |
| Strict Twine metadata check | Wheel and source distribution passed |
| Isolated CPython 3.14 wheel execution | `qplanck doctor` and public planning API passed |

After adding strict replay, the mixed Rust/Python wheel was rebuilt and its
extracted payload imported both `qplanck.replay` and the compiled native
extension successfully.

The repository-wide Ruff format check still identifies six style-only files
from pre-existing, unrelated dirty-worktree work. They were deliberately not
rewritten by this slice; every file changed for the planner/master-spec work
passes its scoped formatting check. The separate `qplanck-braket` test suite was
also exercised as an extra compatibility check in the available CPython 3.14
environment: 23 offline tests passed and the SDK integration test skipped because
`amazon-braket-sdk` was absent. Python 3.14 remains outside that package's
declared 3.11-3.13 support range; its supported-version matrix remains a CI gate.
These local checks do not substitute for the master specification's held-out
experiment, platform matrix, or independent review.

## Intentional stubs and non-goals

- No IBM discovery, authentication, snapshot refresh service, job submission,
  polling, cancellation, or result normalization is implemented by this slice.
- No remote provider call occurs during planning, and no fake backend is labeled
  as hardware execution.
- TKET and BQSKit remain future implementations behind the strategy boundary;
  they are not installed dependencies or placeholder success paths.
- The built-in scorer is deterministic weighted minimization. General metric
  direction/maximization policy from the normative specification remains future
  work.
- The Qiskit semantic check is a deliberately bounded terminal-measurement
  profile, not universal circuit/process equivalence.
- The first smoke remains one synthetic target/workload and one QCore-native
  placement comparison. The newer exact-small development cohort tests Qiskit,
  but it is not a ratified held-out corpus, a real IBM snapshot corpus, or the
  complete master-specification experiment.
- Exact inserted-SWAP attribution across arbitrary external compiler
  decompositions remains unknown unless the adapter can preserve explicit
  evidence.
- No claims are made here about hardware fidelity, hardware advantage, queue or
  cost outcomes, cross-provider portability, or superiority over Qiskit, Cirq,
  TKET, BQSKit, or another tool.
- IDE, Academy, managed cloud, proprietary language, AI optimization, hybrid
  CPU/GPU/QPU orchestration, QEC, and fault-tolerant execution remain outside
  this milestone.

## Smoke decision, full gate status, and next milestone

The fixture's `vertical-slice-go` passes its narrow smoke criterion: on the
recorded offline example, adaptive candidate selection materially improved
structural and model-based quality metrics while preserving the declared
correctness observation. The appropriate project-level decision is **research
continue**. The full v0.1 gate remains `not_evaluated` and cannot be called go
until the fair-baseline, held-out, correctness, replay, statistical, and
independent-review requirements are satisfied.

The highest-leverage next milestone is to turn the successful development-run
machinery into a ratifiable acceptance protocol. It should:

1. materialize complete replay bundles and enforce replay on locked reference
   and second supported environments;
2. add the curated mapping/transformation corruption floor and broader semantic
   verification tiers;
3. enforce wall-time/candidate budgets and report core-versus-compiler resource
   use;
4. add source-faithful IBM-style snapshot fixtures plus validation and held-out
   corpus commitments;
5. introduce TKET and BQSKit through optional isolated adapters only after the
   shared evaluator is ready;
6. map every master-specification §27 criterion `C01`-`C12` to a test and durable
   artifact; and
7. obtain independent review before running or unblinding the held-out cohort.

After that gate closes, the next product stage is an optional IBM execution
lifecycle derived from a frozen Plan, with snapshot revalidation, normalized
results, monotonic job semantics, secret redaction, and separately protected live
evidence.
