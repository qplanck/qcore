# QCore reproducible compiler benchmarks

## v0.1 offline planner vertical slice

The smallest adaptive-selection smoke is executable without provider credentials
or network access after installing QCore:

```bash
python -m benchmarks.planner \
  --output artifacts/planner-gate.json \
  --jsonl artifacts/planner-gate.jsonl
```

It compares a single canonical-layout QCore-native strategy with a two-candidate
portfolio that may select adaptive placement on a fixed five-qubit line target.
The report records manifests, candidate metrics, frozen-seed terminal-measurement
correctness checks, raw JSON/JSONL evidence, and an explicit vertical-slice
decision. This fixture tests offline planning behavior only; it is not evidence
of IBM or other hardware advantage, and it does not close the master
specification's v0.1 go/no-go gate. That full gate still requires preregistered
fair equal-budget baselines, a locked held-out cohort, the stated correctness
floor, 100% offline replay, complete statistical reporting, and independent
human review.

## Exact-small planner development cohort

The next research increment is a versioned **development** cohort—not an
untouched held-out benchmark. It runs five measured workload families across
line, ring, and sparse degree-three five-qubit targets with asymmetric synthetic
instruction-error evidence:

```bash
python -m benchmarks.planner_acceptance \
  --output artifacts/planner-development.json \
  --jsonl artifacts/planner-development.jsonl \
  --quiet
```

Each pair compares:

1. one ordinary Qiskit level-1 recipe;
2. eight Qiskit level/seed attempts as the stronger single-family baseline; and
3. eight mixed attempts split between Qiskit and QCore-native routing.

Candidate-attempt counts are equal between the strong and mixed portfolios, but
wall time is not equalized, so this is a protocol dry run rather than the final
fair-resource experiment. Every valid candidate is rechecked with an exact
terminal classical marginal for the all-zero input. Every generated manifest
also passes a hash-integrity round trip and an offline compiler-reexecution
replay with exact caller-supplied strategy descriptors in the current
environment. The compact committed report is not yet a complete locked replay
bundle.

The committed [development JSON](results/planner-development.json) and
[JSONL](results/planner-development.jsonl) record all 15 workload/target pairs.
The mixed portfolio produced six material wins and no material losses versus the
ordinary recipe. Against the stronger same-attempt Qiskit baseline it produced
two material wins, twelve ties, and one material loss. This is a useful signal
and a concrete portfolio-design warning; it is not a superiority claim. See the
[founder-readable development report](../docs/planner-development-report-v0.1.md).

The planner-development cohort runs in-process, records compiler latency as an
observation, and performs its additional correctness and replay checks before it
accepts the development result. It equalizes candidate attempts only; it does
not claim process isolation or wall-time equivalence.

The general routing/performance benchmark runner described below has the stricter
timing protocol: correctness runs before timed samples, each ordinary raw record
runs in an isolated process, dependency versions must exactly match
`requirements.lock`, and the claim evaluator fails closed when evidence is
missing. Neither suite emits a superiority claim merely because it completed.

The routing corpus contains GHZ, Bernstein–Vazirani, decomposed QFT, two-layer
ring-MaxCut QAOA, and seeded random circuits at 5, 16, 27, and 65 qubits. Every
workload runs against line, ring, truncated-grid, and explicitly named
heavy-hex-style topologies. The heavy-hex-style graph models sparse degree-three
routing pressure; it is not represented as a provider topology.

## Environment

Create a clean supported CPython environment, install the QCore wheel being
measured, then install the locked benchmark tools:

```bash
python -m pip install -r benchmarks/requirements.lock
```

The public comparison pins are Qiskit 2.5.1 and Cirq Core 1.7.0. Their release
versions can be verified on [Qiskit's PyPI page](https://pypi.org/project/qiskit/)
and [Cirq's PyPI page](https://pypi.org/project/cirq-core/). The raw pyperf tool is
pinned to 2.10.0 from [pyperf on PyPI](https://pypi.org/project/pyperf/).

Set CPU affinity/frequency policy outside this harness when the operating system
supports it. The harness fixes `PYTHONHASHSEED` and common numerical-library
thread counts to one inside isolated workers and records the effective values.

## Raw evidence

Run the native admission cases, including exact 1k, 10k, and 100k operation
inputs:

```bash
python -m benchmarks native-gate --output artifacts/native-gate.json
```

Run the full target-routing comparison:

```bash
python -m benchmarks run --output artifacts/routing.json
```

For pyperf-calibrated timing of one case, configure it through environment
variables and use normal pyperf output arguments:

```bash
QPLANCK_BENCH_ENGINE=qplanck-native \
QPLANCK_BENCH_WORKLOAD=ghz \
QPLANCK_BENCH_SIZE=27 \
QPLANCK_BENCH_TARGET=heavy-hex-style \
python -m benchmarks.pyperf_runner -o artifacts/ghz-q27.pyperf.json
```

The standard raw report includes all samples, median, MAD, p95, process peak RSS,
source/output/two-qubit/depth/SWAP quality metrics, semantic and artifact hashes,
dependency pins, timer details, machine metadata, Git identity, failures, and
timeouts. Provider credentials and environment-variable contents are never
collected.

## Claim decision

Evaluate a raw report independently:

```bash
python -m benchmarks.claims artifacts/native-gate.json artifacts/routing.json \
  --output artifacts/claim-decision.json
```

Native admission requires all approved thresholds: 2× median speedup at 100k
operations, 1.5× geometric-mean speedup over 10k/100k, no small-case regression
above 10%, peak RSS at most 1.25× the oracle, and no semantic or determinism drift.

A named competitor claim additionally requires an exact dependency pin, QCore
runtime below 0.8× the comparator, added two-qubit gates at most 1.05×, a
deterministic case-stratified 95% bootstrap interval wholly below parity, and no
correctness, determinism, missing-case, or timeout deficit. Failed or incomplete
gates return `claim: null`.
