# QCore Exact-Small Planner Development Report v0.1

> Evidence date: 2026-08-09
> Protocol: `qcore-bench.planner-development-small.v0.1`
> Protocol status: **draft development protocol**
> Decision: **research continue**
> Master-specification v0.1 gate: **not evaluated**

## Why this experiment exists

The first QCore planner smoke showed that adaptive native placement could beat a
fixed native layout on one synthetic circuit. That proved the vertical slice
worked, but it did not test QCore's actual product thesis against a credible
external compiler workflow.

This development run is the next controlled step. It asks whether the current
offline planner can compare an ordinary Qiskit recipe, a stronger multi-seed
Qiskit baseline, and a same-attempt mixed Qiskit/QCore portfolio while preserving
small-circuit semantics and durable evidence.

It is intentionally **not** called a held-out result. The protocol is still a
draft, no independent reviewer ratified it before execution, candidate attempts
are equal but wall time is not, and TKET/BQSKit are absent. The governing
[QCore Master Specification](QCORE_MASTER_SPECIFICATION.md) therefore remains
the claim boundary.

## Frozen development protocol

| Field | Value |
|---|---|
| Cohort | Development |
| Workloads | GHZ, Bernstein–Vazirani, decomposed QFT, two-layer QAOA, seeded random |
| Width | 5 qubits |
| Targets | Line, ring, sparse degree-three |
| Workload/target pairs | 15 |
| Ordinary baseline | Qiskit optimization level 1, seed 0 |
| Strong single-family baseline | Qiskit levels 0–3 at seeds 0 and 17; 8 attempts |
| Mixed portfolio | Qiskit levels 0–3 at seed 0 plus four QCore-native routing seeds; 8 attempts |
| Objective | Minimize `independent_instruction_error_v1`, then two-qubit gates and depth |
| Material threshold | 5% relative improvement/regression |
| Semantic check | Exact terminal classical marginal from the all-zero input |
| Tolerance | `1e-10` absolute probability delta |
| Target evidence | Immutable synthetic IBM-style snapshots with asymmetric instruction errors and explicit unknowns |

The protocol hash is
`sha256:d033953678c92540a9f98d685ed66cc887ef757cde46c55ec4bb2e9b5719d268`.
It records `protocol_status=draft`, no ratification, no review attestation, and no
held-out commitment. Those null fields prevent this run from being presented as
the final experiment.

## Results

All 255 valid candidate occurrences across the three workflows passed the
declared exact terminal-marginal check. They represent 180 unique candidate IDs
and 67 unique compiled artifact hashes because recipes overlap across workflows.
All 45 generated planning manifests passed their
hash-verified serialization round trip and offline compiler-reexecution replay
with exact caller-supplied strategy descriptors in the current environment.
Strong-Qiskit and mixed portfolios both used eight candidate attempts for every
pair.

| Comparator | Material wins | Ties | Material losses | Win rate | Median improvement on material wins |
|---|---:|---:|---:|---:|---:|
| Ordinary Qiskit recipe | 6 | 9 | 0 | 40.0% | 19.02% |
| Strong same-attempt Qiskit | 2 | 12 | 1 | 13.33% | 25.07% |

The median relative improvement over the strong Qiskit baseline was 0%. The two
material mixed-portfolio wins came from QCore-native candidates:

- Bernstein–Vazirani on the sparse target: 40.57% lower estimated-error proxy;
- QAOA on the line target: 9.58% lower estimated-error proxy.

The material loss is equally important:

- decomposed QFT on the ring target: the mixed portfolio was 16.26% worse than
  the strong Qiskit baseline.

The strong baseline found its better QFT result with Qiskit optimization level 2,
seed 17. The mixed portfolio allocated that attempt to the QCore-native family,
so its Qiskit seed-0 candidate won the local portfolio but lost the external
comparison. This is not a ranking bug—the stronger candidate was not in the
mixed candidate set. It demonstrates the real search-budget trade-off the
planner must solve and is a reason to tune portfolio recipes only on development
data before freezing validation and held-out cohorts.

## What passed

- every evaluated pair produced valid ordinary, strong, and mixed Plans;
- exact-small terminal-marginal checks passed for all 255 valid candidate
  occurrences under the declared all-zero-input boundary;
- no target-invalid selected candidate escaped the existing planner checks;
- all saved Plan/Manifest identities survived serialization integrity checks and
  actual offline re-execution with exact strategy IDs, versions, and options;
- candidate-attempt parity was enforced at 8 versus 8;
- the result contains every pair, including the material regression; and
- no provider credentials, network discovery, remote submission, or hardware
  result entered the run.

## What did not pass—or was not tested

- The protocol was not human-preregistered or independently reviewed.
- The cohort is development data, not untouched held-out data.
- Candidate counts are equal, but wall time, internal search effort, CPU, and
  memory are not yet resource-equalized.
- Exact terminal marginals from one initial state are weaker than exact unitary
  equivalence up to global phase and do not cover parameterized input families.
- Medium randomized verification, structural-large verification, and the
  curated corruption/mapping fault floor are absent.
- Replay reran saved compiler recipes in the current environment, but the
  committed development JSON is compact evidence rather than a complete
  manifest/artifact bundle; no locked second-environment replay floor exists.
- The environment record identifies the checked-out commit but not the dirty
  worktree's diff identity, so it is not a locked source-state attestation.
- TKET and BQSKit are not included.
- The error model is an independent-instruction approximation using synthetic
  rates. It omits readout, coherent error, crosstalk, drift, timing, scheduling,
  queue, cost, and real hardware outcomes.
- The run used one machine and one pass, so the observed compiler latencies are
  not a publication-quality performance study.
- There is no design-partner or independent quantum/compiler review.

## Decision

The development infrastructure gate passes: QCore can run the paired protocol,
preserve the declared small-circuit check, compare a mixed portfolio against a
stronger same-attempt single-family baseline, and retain an unfavorable row.
The appropriate decision is **research continue**.

The result is promising but mixed. Two QCore-native wins support continued
portfolio research; the QFT regression shows that a fixed family allocation can
discard a valuable incumbent seed. No blanket superiority or hardware-fidelity
claim is allowed from this evidence.

## Next evidence-gated milestone

1. Materialize complete replay bundles, lock the reference environment, and run
   the replay floor again on a second supported environment.
2. Add a curated exact-small corruption suite covering wrong gates, mappings,
   measurement bits, unsupported edges, and snapshot/hash tampering.
3. Use development results to propose—but not silently post-select—the next
   portfolio recipe and record its change history.
4. Add enforceable wall-time/candidate budgets and resource accounting.
5. Freeze separate validation and held-out corpus hashes plus the proposed
   thresholds before examining their results.
6. Add TKET and BQSKit only through optional, isolated adapters with the same
   evaluator and saved targets.
7. Obtain independent quantum/compiler methodology review before the held-out
   run or any headline claim.

## Reproduce this development run

Install the source worktree and its optional Qiskit dependency, build the native
extension, then run:

```bash
python -m benchmarks.planner_acceptance \
  --output benchmarks/results/planner-development.json \
  --jsonl benchmarks/results/planner-development.jsonl \
  --quiet
```

Recorded environment: CPython 3.14.5, Qiskit 2.5.1, `qplanck 0.3.0a1`, Darwin
arm64. The committed artifacts are the
[JSON](../benchmarks/results/planner-development.json) and
[JSONL](../benchmarks/results/planner-development.jsonl). Their current SHA-256
digests are:

- JSON: `476fd991a90e76459e39dd9e9ece65143de8fe3663e3f70a7f70ecb7ee5b30f1`
- JSONL: `da394dd75a7cf94dd33957cf73d160457e02e1773eef932a03c2247039c788f0`

The timestamps and latency observations are expected to change on rerun; the
protocol hash, semantic inputs, target hashes, and deterministic Plan identities
are the replay-relevant evidence.
