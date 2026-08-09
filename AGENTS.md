# QCore Agent Guide

## Product truth

QCore is the open-source, vendor-neutral **adaptive execution layer for quantum
computing**. Its core promise is **adaptive performance portability**: one
program should receive strong, explainable execution plans as compilers,
providers, devices, calibrations, constraints, and user objectives change.

The execution planner is the strategic control point. It accepts a `Program`,
candidate immutable `Target` snapshots, and an `Objective`; generates and
validates candidate `Plan` objects; measures and ranks them deterministically;
explains the selected plan and alternatives; and preserves provenance through
`Execution` and `Result`.

QCore is the product. `qplanck` is the current PyPI distribution, Python import,
and CLI. Do not imply that a QPlanck-owned `qcore` package or CLI exists.

## Status discipline

The repository contains substantial `qplanck 0.3.0a1` alpha work, including
circuit/IR, Rust/PyO3 compilation, target routing, QIR lowering, local runtime
contracts, and an offline-tested Braket pulse adapter. The multi-strategy
planner and IBM execution path described by the v0.1 product specification must
not be called implemented unless source, tests, artifacts, and claim gates prove
it.

Before changing any implementation-status or performance claim:

1. inspect the relevant source and public API;
2. inspect tests and the most recent reproducible evidence artifacts;
3. read `docs/claims.json`, `docs/claims.md`, and `docs/sdk-standards.md`;
4. distinguish code presence, offline validation, live provider evidence, and
   released availability;
5. update machine-readable and human-readable claim records together when the
   evidence state legitimately changes.

Never claim that QCore beats another tool, improves hardware outcomes, supports
universal QIR/OpenQASM/pulse semantics, or executed on hardware without the
specified `qcore-bench` or protected-provider evidence. Estimated metrics are
models, not hardware guarantees.

## Documentation hierarchy

Use these sources in this order:

1. `docs/QCORE_MASTER_SPECIFICATION.md` — the exact, governing product/build
   specification. Its canonical SHA-256 is
   `af572397159bb86641b488c9366fdf6ea89e36a589cc7dfd3ec773788bebe73d`.
   Do not silently weaken, abbreviate, or rewrite it to match current code.
   Repository-specific adaptations and implementation gaps belong in accepted
   ADRs/RFCs or implementation-status and conformance documents.
2. `docs/spec-v0.1.md` — a repository-local companion for planner milestone
   requirements and acceptance criteria; the master specification prevails if
   the two conflict.
3. `docs/thesis.md` — Product North Star and strategic rationale.
4. `docs/architecture.md` — target architecture and implemented/planned
   boundaries.
5. `docs/roadmap.md` — canonical staged strategy and evidence gates.
6. `docs/claims.json` and `docs/claims.md` — allowed public claims.
7. Accepted RFCs — binding subsystem decisions; proposed RFCs remain proposals.
8. Detailed architecture, research, and `docs/roadmap/` material — supporting
   design and planning history.

The planner milestone name `v0.1` is a product/software specification version;
it is not the Python package semantic version and does not replace the current
`qplanck 0.3.0a1` history.

## v0.1 planner boundary

v0.1 must:

- accept Qiskit input and treat OpenQASM as a first-class frontend contract;
- normalize input to a versioned QCore program/IR;
- compare multiple compiler strategies over accessible immutable IBM target
  snapshots through optional, normalized plugin boundaries;
- report at least two-qubit gate count, depth, SWAP count, and a named,
  limitation-aware estimated-error model;
- apply explicit constraints and weights, rank valid candidates
  deterministically, retain evidence and useful alternatives, and explain the
  selection and rejections;
- emit complete, secret-free reproducibility/provenance manifests; and
- keep offline planning distinct from optional hardware submission.

v0.1 is not a giant IDE or Academy, a universal proprietary language, a
replacement for every compiler, an unverified AI optimizer, or permission to
make unsupported superiority claims.

## Engineering principles

- Correctness before optimization.
- Explainability and retained candidate evidence.
- Provider neutrality with provider richness isolated behind plugins.
- Deterministic, reproducible-by-default behavior and stable tie-breaking.
- Progressive lowering through explicit, versioned, multi-level IR boundaries.
- Explicit unknowns, assumptions, estimation models, and confidence limits.
- Fail-closed validation for semantic, target, calibration, and capability
  mismatches.
- Measurable execution advantage, with claims gated by reproducible evidence.
- Small modular plugin boundaries; provider SDK objects and credentials never
  enter core abstractions or manifests.

Python is the ergonomic public surface. Rust/PyO3 owns performance-critical
validated models, hashing, graph/IR transformations, deterministic artifact
generation, and planning/scoring kernels where benchmarks justify the boundary.
Qiskit, TKET, BQSKit, provider SDKs, and other external systems remain optional
strategies/adapters normalized at explicit interfaces. MLIR/LLVM/QIR compatibility
is an architectural direction and interoperability boundary, not proof that all
of MLIR or every QIR profile is implemented.

## Working rules

- Preserve unrelated dirty-worktree changes; never reset or discard them.
- Reconcile documentation instead of erasing useful implementation history.
- Label conceptual or future API examples explicitly.
- Add schema versions, stable identifiers, hashes, provenance, and redaction
  rules to every durable artifact design.
- Run the narrowest relevant validation. For documentation changes, run
  `python tools/check_docs.py`; run implementation tests only when implementation
  changes require them.
