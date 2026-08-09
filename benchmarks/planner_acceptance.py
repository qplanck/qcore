"""Versioned development-cohort evidence for the QCore offline planner.

This module is deliberately stricter and broader than ``benchmarks.planner``:
it compares an ordinary Qiskit workflow, a same-attempt strong Qiskit portfolio,
and a mixed Qiskit/QCore portfolio over several small workloads and immutable
synthetic targets.  It is still a development experiment, not the untouched,
independently reviewed held-out run required by the master specification.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import statistics
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.corpus import benchmark_workloads
from benchmarks.models import BenchmarkTarget, Workload, canonical_hash
from qplanck import Circuit, Simulator
from qplanck.circuit import SUPPORTED_GATES
from qplanck.compiler import CompileOptions
from qplanck.planning import (
    CandidateDisposition,
    Objective,
    Plan,
    PlanningManifest,
    QCoreNativeStrategy,
    plan,
)
from qplanck.qiskit_strategy import QiskitCompilerStrategy
from qplanck.replay import replay
from qplanck.targets import InstructionSupport, Target, Topology

ACCEPTANCE_SCHEMA_VERSION = "qcore.benchmark.planner-development.v0.1"
ACCEPTANCE_PROTOCOL_ID = "qcore-bench.planner-development-small.v0.1"
ACCEPTANCE_COHORT = "development"
MATERIAL_IMPROVEMENT_THRESHOLD = 0.05
PROBABILITY_ATOL = 1e-10
QUBIT_COUNT = 5
WORKLOAD_NAMES = (
    "ghz",
    "bernstein-vazirani",
    "decomposed-qft",
    "qaoa",
    "random",
)
TARGET_NAMES = ("line", "ring", "sparse-degree-three")
QISKIT_SEEDS = (0, 17)
NATIVE_SEEDS = (0, 17, 101, 257)


def acceptance_workloads() -> tuple[Workload, ...]:
    """Return the frozen exact-small development workload cohort."""

    result: list[Workload] = []
    for source in benchmark_workloads(QUBIT_COUNT):
        measured = Circuit.from_ir(source.ir).measure_all().ir
        result.append(
            Workload(
                source.name,
                source.qubit_count,
                measured,
                source.seed,
                category=source.category,
                metadata={
                    **source.metadata,
                    "planner_cohort": ACCEPTANCE_COHORT,
                    "semantic_verification": "exact_terminal_marginal_all_zero",
                },
            )
        )
    return tuple(result)


def _edge_error_map(
    topology: Topology,
    values: Sequence[float],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for index, (left, right) in enumerate(topology.edges):
        error = values[index % len(values)]
        result[f"cx:{left},{right}"] = error
        result[f"cz:{left},{right}"] = error
        if not topology.directed:
            result[f"cx:{right},{left}"] = error
            result[f"cz:{right},{left}"] = error
    return result


def _acceptance_target(name: str, topology: Topology, errors: Sequence[float]) -> BenchmarkTarget:
    basis = tuple(sorted(SUPPORTED_GATES))
    instruction_errors: dict[str, float] = {
        gate: (0.02 if SUPPORTED_GATES[gate].qubits == 2 else 0.001) for gate in basis
    }
    instruction_errors["swap"] = 0.04
    instruction_errors.update(_edge_error_map(topology, errors))
    target = Target(
        target_id=f"qcore-bench.development.{name}.q{QUBIT_COUNT}",
        provider="qcore-bench",
        model=f"synthetic-{name}",
        snapshot_id=f"qcore-bench.development.{name}.q{QUBIT_COUNT}.2026-08-09",
        topology=topology,
        instructions=tuple(
            InstructionSupport(gate, SUPPORTED_GATES[gate].qubits) for gate in basis
        ),
        metadata={
            "schema_version": "qcore.benchmark.target-evidence.v0.1",
            "captured_at": "2026-08-09T00:00:00Z",
            "declared": {
                "source": "versioned synthetic IBM-style development fixture",
                "available": False,
            },
            "calibrated": {"model": "synthetic independent per-instruction error evidence"},
            "observed": {},
            "instruction_errors": instruction_errors,
            "unknown_fields": [
                "hardware fidelity",
                "queue",
                "price",
                "live operational status",
            ],
        },
    )
    return BenchmarkTarget(name, target)


def acceptance_targets() -> tuple[BenchmarkTarget, ...]:
    """Return frozen topology and asymmetric-error development fixtures."""

    return (
        _acceptance_target("line", Topology.line(QUBIT_COUNT), (0.004, 0.012, 0.025, 0.007)),
        _acceptance_target(
            "ring",
            Topology.ring(QUBIT_COUNT),
            (0.006, 0.02, 0.009, 0.03, 0.005),
        ),
        _acceptance_target(
            "sparse-degree-three",
            Topology(QUBIT_COUNT, ((0, 1), (1, 2), (1, 3), (3, 4))),
            (0.008, 0.022, 0.005, 0.017),
        ),
    )


def ordinary_qiskit_strategies() -> tuple[QiskitCompilerStrategy, ...]:
    """One documented practical default used as the ordinary baseline."""

    return (QiskitCompilerStrategy(optimization_level=1, seed=0),)


def strong_qiskit_strategies() -> tuple[QiskitCompilerStrategy, ...]:
    """Eight deterministic Qiskit attempts used as the single-family baseline."""

    return tuple(
        QiskitCompilerStrategy(optimization_level=level, seed=seed)
        for seed in QISKIT_SEEDS
        for level in range(4)
    )


def mixed_portfolio_strategies() -> tuple[QiskitCompilerStrategy | QCoreNativeStrategy, ...]:
    """Eight attempts split equally between Qiskit and QCore-native routing."""

    qiskit = tuple(QiskitCompilerStrategy(optimization_level=level, seed=0) for level in range(4))
    native = tuple(
        QCoreNativeStrategy(
            CompileOptions(
                optimization_level=2,
                routing_seed=seed,
                placement_trials=1,
            ),
            strategy_id="qcore-native.o2",
        )
        for seed in NATIVE_SEEDS
    )
    return (*qiskit, *native)


def _strategy_descriptors(strategies: Iterable[Any]) -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": strategy.strategy_id,
            "strategy_version": strategy.strategy_version,
            "options": dict(strategy.options),
        }
        for strategy in strategies
    ]


def acceptance_protocol() -> dict[str, Any]:
    """Return the immutable, machine-readable development protocol."""

    identity = {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "protocol_id": ACCEPTANCE_PROTOCOL_ID,
        "protocol_status": "draft",
        "ratified_at": None,
        "review_attestation": None,
        "held_out_commitment": None,
        "cohort": ACCEPTANCE_COHORT,
        "workloads": [item.to_metadata() for item in acceptance_workloads()],
        "targets": [item.to_metadata() for item in acceptance_targets()],
        "objective": Objective.minimize_error().to_dict(),
        "ordinary_qiskit_recipes": _strategy_descriptors(ordinary_qiskit_strategies()),
        "strong_qiskit_recipes": _strategy_descriptors(strong_qiskit_strategies()),
        "mixed_portfolio_recipes": _strategy_descriptors(mixed_portfolio_strategies()),
        "candidate_attempt_budget": {
            "strong_qiskit": len(strong_qiskit_strategies()),
            "mixed_portfolio": len(mixed_portfolio_strategies()),
            "wall_time_equalized": False,
            "wall_time_budget_seconds": None,
        },
        "execution_order_seed": 0,
        "reference_environment": {
            "status": "unlocked",
            "python": "CPython 3.14",
            "qplanck": "0.3.0a1",
            "qiskit": "2.5.1",
            "operating_system": None,
            "machine": None,
        },
        "correctness": {
            "level": "exact_small",
            "method": "exact terminal classical marginal from all-zero input",
            "absolute_tolerance": PROBABILITY_ATOL,
        },
        "primary_metric": "estimated_error",
        "material_improvement_threshold": MATERIAL_IMPROVEMENT_THRESHOLD,
        "proposed_master_thresholds": {
            "ratified": False,
            "source": "QCORE_MASTER_SPECIFICATION.md section 48",
            "ordinary_baseline_material_win_rate": 0.25,
            "strong_baseline_material_win_rate": 0.10,
            "median_improvement_among_material_wins": 0.05,
            "valid_plan_rate": 0.95,
            "adapter_uncaught_error_rate_maximum": 0.01,
            "locked_environment_replay_rate": 1.0,
        },
    }
    return {**identity, "protocol_hash": canonical_hash(identity)}


def _terminal_probabilities(circuit: Circuit) -> dict[str, float]:
    measurements = tuple(sorted(circuit.measurements, key=lambda item: item.cbit))
    if not measurements:
        raise ValueError("Acceptance correctness requires terminal measurements.")
    width = max(item.cbit for item in measurements) + 1
    qubit_by_cbit = {item.cbit: item.qubit for item in measurements}
    probabilities: dict[str, float] = {}
    statevector = Simulator().statevector(circuit).statevector
    for basis_index, amplitude in enumerate(statevector):
        probability = float(abs(amplitude) ** 2)
        if probability <= PROBABILITY_ATOL:
            continue
        key = "".join(
            str((basis_index >> qubit_by_cbit[cbit]) & 1) if cbit in qubit_by_cbit else "0"
            for cbit in reversed(range(width))
        )
        probabilities[key] = probabilities.get(key, 0.0) + probability
    return dict(sorted(probabilities.items()))


def _maximum_probability_delta(expected: Mapping[str, float], actual: Mapping[str, float]) -> float:
    outcomes = set(expected) | set(actual)
    return max(
        (abs(expected.get(item, 0.0) - actual.get(item, 0.0)) for item in outcomes),
        default=0.0,
    )


def _correctness(source: Circuit, decision: Plan) -> dict[str, Any]:
    expected = _terminal_probabilities(source)
    candidates: dict[str, Any] = {}
    for candidate in decision.candidates:
        if candidate.disposition is not CandidateDisposition.VALID or candidate.artifact_ir is None:
            continue
        actual = _terminal_probabilities(Circuit.from_ir(candidate.artifact_ir))
        delta = _maximum_probability_delta(expected, actual)
        candidates[candidate.candidate_id] = {
            "passed": delta <= PROBABILITY_ATOL,
            "maximum_probability_delta": delta,
            "absolute_tolerance": PROBABILITY_ATOL,
            "artifact_hash": candidate.artifact_hash,
        }
    return {
        "method": "independent QCore exact terminal classical marginal",
        "initial_state": "all_zero",
        "checked_candidate_count": len(candidates),
        "passed": bool(candidates) and all(item["passed"] for item in candidates.values()),
        "candidates": candidates,
    }


def _artifact_integrity(decision: Plan, strategies: Sequence[Any]) -> dict[str, Any]:
    manifest = decision.manifest
    restored = PlanningManifest.from_json(manifest.to_json(include_observations=True))
    candidate_hashes = [item.candidate_hash for item in restored.candidates]
    replay_report = replay(restored, strategies=strategies)
    round_trip_passed = (
        restored.manifest_hash == manifest.manifest_hash
        and restored.selected_plan_hash == decision.plan_hash
        and candidate_hashes == [item.candidate_hash for item in manifest.candidates]
    )
    return {
        "passed": (
            round_trip_passed and replay_report.passed and replay_report.environment_compatible
        ),
        "method": (
            "hash-verified manifest serialization round trip plus offline compiler "
            "re-execution replay"
        ),
        "round_trip_passed": round_trip_passed,
        "manifest_hash": manifest.manifest_hash,
        "selected_plan_hash": restored.selected_plan_hash,
        "candidate_hashes": candidate_hashes,
        "recompilation_replay": replay_report.to_dict(),
        "limitation": (
            "Replay ran in the current development environment from in-memory complete "
            "manifests; the committed compact report is not a locked replay bundle."
        ),
    }


def _selected_record(decision: Plan) -> dict[str, Any]:
    selected = decision.selected
    if selected.metrics is None:
        raise RuntimeError("Selected candidate has no metrics.")
    return {
        "candidate_id": selected.candidate_id,
        "candidate_hash": selected.candidate_hash,
        "target_id": selected.target.target_id,
        "strategy_id": selected.strategy_id,
        "strategy_version": selected.strategy_version,
        "strategy_options": dict(selected.strategy_options),
        "metrics": selected.metrics.to_dict(include_observations=True),
        "plan_hash": decision.plan_hash,
        "manifest_hash": decision.manifest.manifest_hash,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "candidate_hash": candidate.candidate_hash,
                "strategy_id": candidate.strategy_id,
                "strategy_version": candidate.strategy_version,
                "strategy_options": dict(candidate.strategy_options),
                "disposition": candidate.disposition.value,
                "artifact_hash": candidate.artifact_hash,
                "metrics": (
                    None
                    if candidate.metrics is None
                    else candidate.metrics.to_dict(include_observations=True)
                ),
                "rejection_reasons": list(candidate.rejection_reasons),
                "rank": candidate.rank,
            }
            for candidate in decision.candidates
        ],
        "artifact_boundary": (
            "The development report stores compact candidate evidence and hashes. "
            "It is not the complete replay artifact bundle."
        ),
    }


def _metric(decision: Plan) -> float:
    metrics = decision.selected.metrics
    if metrics is None or metrics.estimated_error is None:
        raise RuntimeError("Acceptance plans require a known selected estimated-error proxy.")
    return metrics.estimated_error


def _comparison(baseline: Plan, selected: Plan) -> dict[str, Any]:
    baseline_value = _metric(baseline)
    selected_value = _metric(selected)
    absolute_improvement = baseline_value - selected_value
    relative_improvement = 0.0 if baseline_value == 0.0 else absolute_improvement / baseline_value
    if relative_improvement >= MATERIAL_IMPROVEMENT_THRESHOLD:
        outcome = "material_win"
    elif relative_improvement <= -MATERIAL_IMPROVEMENT_THRESHOLD:
        outcome = "material_loss"
    else:
        outcome = "tie"
    return {
        "primary_metric": "estimated_error",
        "baseline_value": baseline_value,
        "selected_value": selected_value,
        "absolute_improvement": absolute_improvement,
        "relative_improvement": relative_improvement,
        "material_threshold": MATERIAL_IMPROVEMENT_THRESHOLD,
        "outcome": outcome,
    }


def _case_record(workload: Workload, target: BenchmarkTarget) -> dict[str, Any]:
    source = Circuit.from_ir(workload.ir)
    objective = Objective.minimize_error()
    ordinary_strategies = ordinary_qiskit_strategies()
    strong_strategies = strong_qiskit_strategies()
    portfolio_strategies = mixed_portfolio_strategies()
    ordinary = plan(
        source,
        targets=(target.target,),
        strategies=ordinary_strategies,
        objective=objective,
    )
    strong = plan(
        source,
        targets=(target.target,),
        strategies=strong_strategies,
        objective=objective,
    )
    portfolio = plan(
        source,
        targets=(target.target,),
        strategies=portfolio_strategies,
        objective=objective,
    )
    ordinary_correctness = _correctness(source, ordinary)
    strong_correctness = _correctness(source, strong)
    portfolio_correctness = _correctness(source, portfolio)
    integrity = {
        "ordinary_qiskit": _artifact_integrity(ordinary, ordinary_strategies),
        "strong_qiskit": _artifact_integrity(strong, strong_strategies),
        "mixed_portfolio": _artifact_integrity(portfolio, portfolio_strategies),
    }
    correctness_passed = all(
        item["passed"] for item in (ordinary_correctness, strong_correctness, portfolio_correctness)
    )
    integrity_passed = all(item["passed"] for item in integrity.values())
    return {
        "case_id": f"{ACCEPTANCE_PROTOCOL_ID}/{workload.name}/{target.name}",
        "cohort": ACCEPTANCE_COHORT,
        "workload": workload.to_metadata(),
        "target": target.to_metadata(),
        "objective": objective.to_dict(),
        "ordinary_qiskit": {
            "selected": _selected_record(ordinary),
            "correctness": ordinary_correctness,
        },
        "strong_qiskit": {
            "selected": _selected_record(strong),
            "candidate_attempts": len(strong_strategies),
            "correctness": strong_correctness,
        },
        "mixed_portfolio": {
            "selected": _selected_record(portfolio),
            "candidate_attempts": len(portfolio_strategies),
            "correctness": portfolio_correctness,
        },
        "comparisons": {
            "versus_ordinary_qiskit": _comparison(ordinary, portfolio),
            "versus_strong_equal_attempt_qiskit": _comparison(strong, portfolio),
        },
        "selection_regret": {
            "estimated_error": 0.0,
            "reason": "The selected Plan is rank one among the candidates it evaluated.",
        },
        "correctness_passed": correctness_passed,
        "artifact_integrity": integrity,
        "artifact_integrity_passed": integrity_passed,
    }


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * quantile) - 1e-12)))
    return ordered[index]


def _aggregate(cases: Sequence[Mapping[str, Any]], comparison: str) -> dict[str, Any]:
    rows = [item["comparisons"][comparison] for item in cases]
    improvements = [float(item["relative_improvement"]) for item in rows]
    wins = [
        value
        for item, value in zip(rows, improvements, strict=True)
        if item["outcome"] == "material_win"
    ]
    return {
        "eligible_pairs": len(rows),
        "material_wins": sum(item["outcome"] == "material_win" for item in rows),
        "ties": sum(item["outcome"] == "tie" for item in rows),
        "material_losses": sum(item["outcome"] == "material_loss" for item in rows),
        "material_win_rate": (
            0.0 if not rows else sum(item["outcome"] == "material_win" for item in rows) / len(rows)
        ),
        "median_relative_improvement": statistics.median(improvements) if improvements else None,
        "median_improvement_among_material_wins": statistics.median(wins) if wins else None,
        "p90_relative_improvement": _nearest_rank(improvements, 0.90),
        "all_relative_improvements": improvements,
    }


def _environment() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ("qplanck", "qiskit"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        commit = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "operating_system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "packages": packages,
        "git_commit": commit,
    }


def run_acceptance_suite(
    *,
    workload_names: Sequence[str] = WORKLOAD_NAMES,
    target_names: Sequence[str] = TARGET_NAMES,
) -> dict[str, Any]:
    """Execute the selected development cohort and return complete evidence."""

    known_workloads = {item.name: item for item in acceptance_workloads()}
    known_targets = {item.name: item for item in acceptance_targets()}
    unknown_workloads = sorted(set(workload_names) - known_workloads.keys())
    unknown_targets = sorted(set(target_names) - known_targets.keys())
    if unknown_workloads:
        raise ValueError(f"Unknown acceptance workloads: {unknown_workloads!r}.")
    if unknown_targets:
        raise ValueError(f"Unknown acceptance targets: {unknown_targets!r}.")
    if not workload_names or not target_names:
        raise ValueError("Acceptance execution requires workloads and targets.")

    cases = [
        _case_record(known_workloads[workload_name], known_targets[target_name])
        for workload_name in workload_names
        for target_name in target_names
    ]
    correctness_passed = all(item["correctness_passed"] for item in cases)
    integrity_passed = all(item["artifact_integrity_passed"] for item in cases)
    replay_records = [
        evidence["recompilation_replay"]
        for item in cases
        for evidence in item["artifact_integrity"].values()
    ]
    replay_passed = bool(replay_records) and all(
        item["passed"] and item["environment_compatible"] for item in replay_records
    )
    attempt_parity = all(
        item["strong_qiskit"]["candidate_attempts"] == item["mixed_portfolio"]["candidate_attempts"]
        for item in cases
    )
    ordinary = _aggregate(cases, "versus_ordinary_qiskit")
    strong = _aggregate(cases, "versus_strong_equal_attempt_qiskit")
    development_passed = (
        correctness_passed and integrity_passed and replay_passed and attempt_parity
    )
    return {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "protocol": acceptance_protocol(),
        "scope": (
            "Versioned exact-small development cohort. This is offline compiler-selection "
            "evidence only; it is not an untouched held-out run, hardware evidence, or an "
            "independently reviewed master-specification Go decision."
        ),
        "environment": _environment(),
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "correctness_passed": correctness_passed,
            "artifact_integrity_passed": integrity_passed,
            "offline_replay_passed": replay_passed,
            "replayed_plan_count": len(replay_records),
            "candidate_attempt_parity": attempt_parity,
            "versus_ordinary_qiskit": ordinary,
            "versus_strong_equal_attempt_qiskit": strong,
        },
        "development_gate": {
            "kind": "development_acceptance",
            "passed": development_passed,
            "decision": "research-continue" if development_passed else "stop-the-line",
            "criterion": (
                "All evaluated exact-small candidates preserve the terminal marginal, "
                "saved manifests pass hash-integrity and offline compiler-reexecution "
                "replay in the current environment, and compared search portfolios use "
                "the same number of candidate attempts."
            ),
        },
        "master_spec_v0_1_gate": {
            "status": "not_evaluated",
            "decision": None,
            "open_requirements": [
                "human-preregistered untouched held-out cohort",
                "wall-time/resource-equalized baselines",
                "TKET and BQSKit compiler families",
                "tiered medium/large verification and curated corruption floor",
                "locked-environment replay from committed complete artifact bundles",
                "complete statistical and falsification analysis",
                "independent quantum/compiler methodology review",
            ],
        },
    }


def write_acceptance_artifacts(
    report: Mapping[str, Any], *, json_path: Path, jsonl_path: Path
) -> None:
    """Write the complete report and case-oriented raw records."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    records = [
        {
            "record_type": "protocol",
            "schema_version": report["schema_version"],
            "protocol": report["protocol"],
            "scope": report["scope"],
            "environment": report["environment"],
        },
        *({"record_type": "case", **item} for item in report["cases"]),
        {
            "record_type": "summary",
            "summary": report["summary"],
            "development_gate": report["development_gate"],
            "master_spec_v0_1_gate": report["master_spec_v0_1_gate"],
        },
    ]
    jsonl_path.write_text(
        "".join(json.dumps(item, allow_nan=False, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the complete JSON report here.")
    parser.add_argument("--jsonl", type=Path, help="Write case-oriented JSONL here.")
    parser.add_argument("--workload", action="append", choices=WORKLOAD_NAMES)
    parser.add_argument("--target", action="append", choices=TARGET_NAMES)
    parser.add_argument("--quiet", action="store_true", help="Do not print the JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (args.output is None) != (args.jsonl is None):
        raise SystemExit("--output and --jsonl must be supplied together")
    report = run_acceptance_suite(
        workload_names=tuple(args.workload or WORKLOAD_NAMES),
        target_names=tuple(args.target or TARGET_NAMES),
    )
    if args.output is not None and args.jsonl is not None:
        write_acceptance_artifacts(report, json_path=args.output, jsonl_path=args.jsonl)
    if not args.quiet:
        print(json.dumps(report, allow_nan=False, indent=2, sort_keys=True))
    return 0 if report["development_gate"]["passed"] else 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())


__all__ = [
    "ACCEPTANCE_COHORT",
    "ACCEPTANCE_PROTOCOL_ID",
    "ACCEPTANCE_SCHEMA_VERSION",
    "MATERIAL_IMPROVEMENT_THRESHOLD",
    "TARGET_NAMES",
    "WORKLOAD_NAMES",
    "acceptance_protocol",
    "acceptance_targets",
    "acceptance_workloads",
    "main",
    "mixed_portfolio_strategies",
    "ordinary_qiskit_strategies",
    "run_acceptance_suite",
    "strong_qiskit_strategies",
    "write_acceptance_artifacts",
]
