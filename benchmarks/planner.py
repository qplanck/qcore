"""Executable offline vertical-slice benchmark for the QCore v0.1 research kernel."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qplanck import Circuit, Layout, Simulator
from qplanck.compiler import CompileOptions
from qplanck.planning import Objective, Plan, QCoreNativeStrategy, plan
from qplanck.targets import InstructionSupport, Target, Topology

PLANNER_GATE_SCHEMA_VERSION = "qcore.benchmark.planner-slice-gate.v0.1"
PLANNER_WORKLOAD_ID = "qcore-bench.routing-placement-line5.v0.1"
PLANNER_TARGET_ID = "qcore-bench.offline-line5"
_SEED = 9
_SHOTS = 4096
_PROBABILITY_ATOL = 1e-12


def planner_gate_circuit() -> Circuit:
    """Return a small nontrivial fixture with placement-sensitive interactions."""

    return Circuit(5, name="planner-gate").h(0).cx(0, 4).cx(1, 3).cx(4, 2).measure_all()


def planner_gate_target() -> Target:
    """Return the immutable offline target snapshot used by the gate."""

    basis = frozenset({"h", "x", "rz", "cx"})
    return Target(
        target_id=PLANNER_TARGET_ID,
        provider="qcore-bench",
        model="offline-line5",
        snapshot_id="qcore-bench.offline-line5.2026-08-09",
        topology=Topology.line(5),
        instructions=tuple(
            InstructionSupport(name, 2 if name == "cx" else 1) for name in sorted(basis)
        ),
        metadata={
            "schema_version": "qcore.benchmark.target-evidence.v0.1",
            "captured_at": "2026-08-09T00:00:00Z",
            "declared": {"source": "versioned offline fixture"},
            "observed": {"available": False},
            "instruction_errors": {
                "h": 0.001,
                "x": 0.001,
                "rz": 0.0001,
                "cx": 0.01,
            },
        },
    )


def _baseline_strategy() -> QCoreNativeStrategy:
    return QCoreNativeStrategy(
        CompileOptions(
            optimization_level=2,
            initial_layout=Layout.identity(5),
            routing_seed=_SEED,
            placement_trials=1,
        ),
        strategy_id="qcore-native.canonical-layout",
    )


def _adaptive_strategy() -> QCoreNativeStrategy:
    return QCoreNativeStrategy(
        CompileOptions(
            optimization_level=2,
            routing_seed=_SEED,
            placement_trials=1,
        ),
        strategy_id="qcore-native.adaptive-placement",
    )


def _terminal_probabilities(circuit: Circuit) -> dict[str, float]:
    """Return the exact terminal classical marginal from a local statevector."""

    measurements = tuple(sorted(circuit.measurements, key=lambda item: item.cbit))
    if not measurements:
        raise ValueError("Planner benchmark correctness requires terminal measurements.")
    width = max(item.cbit for item in measurements) + 1
    qubit_by_cbit = {item.cbit: item.qubit for item in measurements}
    probabilities: dict[str, float] = {}
    statevector = Simulator().statevector(circuit).statevector
    for basis_index, amplitude in enumerate(statevector):
        probability = float(abs(amplitude) ** 2)
        if probability <= _PROBABILITY_ATOL:
            continue
        key = "".join(
            str((basis_index >> qubit_by_cbit[cbit]) & 1) if cbit in qubit_by_cbit else "0"
            for cbit in reversed(range(width))
        )
        probabilities[key] = probabilities.get(key, 0.0) + probability
    return dict(sorted(probabilities.items()))


def _maximum_probability_delta(expected: dict[str, float], actual: dict[str, float]) -> float:
    outcomes = set(expected) | set(actual)
    return max(
        (abs(expected.get(outcome, 0.0) - actual.get(outcome, 0.0)) for outcome in outcomes),
        default=0.0,
    )


def _correctness_evidence(source: Circuit, decision: Plan) -> dict[str, Any]:
    expected_run = Simulator().run(source, shots=_SHOTS, seed=_SEED)
    expected_counts = dict(expected_run.counts)
    expected_probabilities = _terminal_probabilities(source)
    candidates: dict[str, Any] = {}
    for candidate in decision.candidates:
        if candidate.artifact_ir is None:
            candidates[candidate.candidate_id] = {
                "checked": False,
                "reason": "candidate has no transformed artifact",
            }
            continue
        artifact = Circuit.from_ir(candidate.artifact_ir)
        actual_counts = dict(Simulator().run(artifact, shots=_SHOTS, seed=_SEED).counts)
        actual_probabilities = _terminal_probabilities(artifact)
        maximum_delta = _maximum_probability_delta(expected_probabilities, actual_probabilities)
        candidates[candidate.candidate_id] = {
            "checked": True,
            "equivalent": (maximum_delta <= _PROBABILITY_ATOL and actual_counts == expected_counts),
            "exact_probability_equivalent": maximum_delta <= _PROBABILITY_ATOL,
            "maximum_probability_delta": maximum_delta,
            "probability_tolerance": _PROBABILITY_ATOL,
            "expected_probabilities": expected_probabilities,
            "actual_probabilities": actual_probabilities,
            "expected_counts": expected_counts,
            "actual_counts": actual_counts,
            "shots": _SHOTS,
            "seed": _SEED,
            "method": (
                "exact statevector-derived terminal classical marginal plus "
                "frozen-seed sampled-count equality"
            ),
        }
    return {
        "expected_probabilities": expected_probabilities,
        "expected_counts": expected_counts,
        "candidates": candidates,
    }


def _selected_metrics(decision: Plan) -> dict[str, int | float | None]:
    metrics = decision.selected.metrics
    if metrics is None:  # pragma: no cover - enforced by Plan invariants
        raise RuntimeError("Selected planning candidate has no metrics.")
    return {
        "two_qubit_gate_count": metrics.two_qubit_gate_count,
        "circuit_depth": metrics.circuit_depth,
        "inserted_swap_count": metrics.inserted_swap_count,
        "estimated_error": metrics.estimated_error,
        "compilation_latency_ms": metrics.compilation_latency_ms,
    }


def _all_correct(evidence: dict[str, Any]) -> bool:
    checked = [item for item in evidence["candidates"].values() if item.get("checked", False)]
    return bool(checked) and all(item.get("equivalent", False) for item in checked)


def run_planner_gate() -> dict[str, Any]:
    """Run the declared baseline and adaptive portfolio and return raw evidence."""

    source = planner_gate_circuit()
    target = planner_gate_target()
    objective = Objective.minimize_error()
    baseline = plan(
        source,
        targets=(target,),
        objective=objective,
        strategies=(_baseline_strategy(),),
    )
    adaptive = plan(
        source,
        targets=(target,),
        objective=objective,
        strategies=(_baseline_strategy(), _adaptive_strategy()),
    )

    baseline_metrics = _selected_metrics(baseline)
    adaptive_metrics = _selected_metrics(adaptive)
    baseline_correctness = _correctness_evidence(source, baseline)
    adaptive_correctness = _correctness_evidence(source, adaptive)

    metric_improvements = {
        "two_qubit_gate_count": int(baseline_metrics["two_qubit_gate_count"])
        - int(adaptive_metrics["two_qubit_gate_count"]),
        "circuit_depth": int(baseline_metrics["circuit_depth"])
        - int(adaptive_metrics["circuit_depth"]),
        "inserted_swap_count": (
            None
            if baseline_metrics["inserted_swap_count"] is None
            or adaptive_metrics["inserted_swap_count"] is None
            else int(baseline_metrics["inserted_swap_count"])
            - int(adaptive_metrics["inserted_swap_count"])
        ),
        "estimated_error": (
            None
            if baseline_metrics["estimated_error"] is None
            or adaptive_metrics["estimated_error"] is None
            else float(baseline_metrics["estimated_error"])
            - float(adaptive_metrics["estimated_error"])
        ),
    }
    improved = any(value is not None and value > 0 for value in metric_improvements.values())
    correctness_passed = _all_correct(baseline_correctness) and _all_correct(adaptive_correctness)
    selected_adaptive = adaptive.selected.strategy_id == "qcore-native.adaptive-placement"
    passed = improved and correctness_passed and selected_adaptive

    return {
        "schema_version": PLANNER_GATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "One offline compiler-placement fixture on one versioned synthetic target. "
            "This is neither hardware-performance evidence nor the complete master-spec "
            "v0.1 go/no-go experiment."
        ),
        "workload": {
            "id": PLANNER_WORKLOAD_ID,
            "program_ir": source.to_dict(),
            "shots": _SHOTS,
            "seed": _SEED,
        },
        "target": target.to_dict(),
        "target_hash": target.content_hash,
        "objective": objective.to_dict(),
        "baseline": {
            "kind": "single-strategy canonical-layout baseline",
            "selected": baseline.selected.to_dict(include_observations=True),
            "plan_hash": baseline.plan_hash,
            "manifest": baseline.manifest.to_dict(include_observations=True),
            "metrics": baseline_metrics,
            "correctness": baseline_correctness,
        },
        "adaptive": {
            "kind": "two-candidate adaptive portfolio",
            "selected": adaptive.selected.to_dict(include_observations=True),
            "candidate_count": len(adaptive.candidates),
            "plan_hash": adaptive.plan_hash,
            "manifest": adaptive.manifest.to_dict(include_observations=True),
            "metrics": adaptive_metrics,
            "correctness": adaptive_correctness,
            "explanation": adaptive.explain().to_dict(),
        },
        "comparison": {
            "improvements_baseline_minus_adaptive": metric_improvements,
            "adaptive_candidate_selected": selected_adaptive,
            "correctness_preserved": correctness_passed,
        },
        "gate": {
            "kind": "vertical_slice_smoke",
            "passed": passed,
            "decision": "vertical-slice-go" if passed else "vertical-slice-no-go",
            "criterion": (
                "Adaptive selection materially improves at least one declared metric "
                "over the single-strategy baseline while preserving correctness."
            ),
            "claim_boundary": (
                "A pass supports only an offline planning/compiler-selection claim "
                "for this fixture and environment. It does not close the master-spec "
                "v0.1 evidence gate."
            ),
        },
        "master_spec_v0_1_gate": {
            "status": "not_evaluated",
            "decision": None,
            "required_evidence": [
                "preregistered fair equal-budget baselines",
                "locked held-out benchmark cohort",
                "master-spec correctness floor",
                "100% offline replay on the locked reference environment",
                "statistical reporting across all eligible workloads",
                "independent human review",
            ],
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "operating_system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }


def write_planner_gate_artifacts(
    report: dict[str, Any], *, json_path: Path, jsonl_path: Path
) -> None:
    """Write one human-inspectable JSON report and five raw JSONL records."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    records = (
        {"record_type": "metadata", "schema_version": report["schema_version"]},
        {"record_type": "baseline", **report["baseline"]},
        {"record_type": "adaptive", **report["adaptive"]},
        {"record_type": "gate", **report["gate"], "comparison": report["comparison"]},
        {"record_type": "master_spec_gate", **report["master_spec_v0_1_gate"]},
    )
    jsonl_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the complete JSON report here.")
    parser.add_argument("--jsonl", type=Path, help="Write raw JSONL records here.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_planner_gate()
    if (args.output is None) != (args.jsonl is None):
        raise SystemExit("--output and --jsonl must be supplied together")
    if args.output is not None and args.jsonl is not None:
        write_planner_gate_artifacts(report, json_path=args.output, jsonl_path=args.jsonl)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gate"]["passed"] else 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())


__all__ = [
    "PLANNER_GATE_SCHEMA_VERSION",
    "PLANNER_TARGET_ID",
    "PLANNER_WORKLOAD_ID",
    "main",
    "planner_gate_circuit",
    "planner_gate_target",
    "run_planner_gate",
    "write_planner_gate_artifacts",
]
