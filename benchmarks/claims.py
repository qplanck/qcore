"""Fail-closed evaluator for QCore benchmark and competitive claims."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.adapters import CIRQ_ENGINE, QISKIT_ENGINE, QPLANCK_ENGINE
from benchmarks.corpus import benchmark_cases

CLAIM_SCHEMA_VERSION = "qplanck.benchmark.claims.v0.1"
NATIVE_ORACLE_ENGINE = "python-oracle"
BOOTSTRAP_RESAMPLES = 10_000


def _geometric_mean(values: Sequence[float]) -> float:
    if not values or any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("Geometric means require finite positive values.")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a quantile without values.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _check(
    identifier: str,
    passed: bool,
    *,
    observed: Any,
    required: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "passed": bool(passed),
        "observed": observed,
        "required": required,
    }


def _records(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = report.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Benchmark report records must be a list.")
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("Each benchmark record must be an object.")
    return records


def _operation_count(record: Mapping[str, Any]) -> int | None:
    workload = record.get("workload")
    if not isinstance(workload, Mapping):
        return None
    value = workload.get("operation_count")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _median_ns(record: Mapping[str, Any]) -> float | None:
    stats = record.get("statistics")
    if not isinstance(stats, Mapping):
        return None
    value = stats.get("median_ns")
    if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _rss_bytes(record: Mapping[str, Any]) -> int | None:
    memory = record.get("memory")
    if not isinstance(memory, Mapping):
        return None
    value = memory.get("peak_rss_bytes")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _passed_evidence(record: Mapping[str, Any]) -> bool:
    correctness = record.get("correctness")
    determinism = record.get("determinism")
    return (
        record.get("status") == "success"
        and isinstance(correctness, Mapping)
        and correctness.get("passed") is True
        and isinstance(determinism, Mapping)
        and determinism.get("passed") is True
    )


def _semantic_evidence_passed(record: Mapping[str, Any]) -> bool:
    workload = record.get("workload")
    correctness = record.get("correctness")
    if not isinstance(workload, Mapping) or not isinstance(correctness, Mapping):
        return False
    qubit_count = workload.get("qubit_count")
    source_hash = workload.get("semantic_hash")
    evidence = correctness.get("semantic_evidence")
    if (
        isinstance(qubit_count, bool)
        or not isinstance(qubit_count, int)
        or qubit_count <= 0
        or not isinstance(source_hash, str)
        or not source_hash
        or not isinstance(evidence, Mapping)
        or evidence.get("verified") is not True
        or evidence.get("source_semantic_hash") != source_hash
        or evidence.get("mapping_bijective") is not True
        or evidence.get("topology_conformant") is not True
    ):
        return False

    kind = evidence.get("kind")
    if qubit_count <= 5:
        return (
            kind in {"exact-statevector-matrix-equivalence", "exact-operator-equivalence"}
            and evidence.get("logical_dimension") == 1 << qubit_count
        )

    required_hashes = {
        "qplanck-routing-permutation-invariant": (
            "initial_layout_hash",
            "final_layout_hash",
            "routing_trace_hash",
        ),
        "qiskit-layout-permutation-invariant": ("layout_hash",),
        "cirq-router-permutation-invariant": (
            "initial_mapping_hash",
            "swap_mapping_hash",
        ),
    }
    names = required_hashes.get(kind) if isinstance(kind, str) else None
    hashes_present = names is not None and all(
        isinstance(evidence.get(name), str) and str(evidence[name]).startswith("sha256:")
        for name in names
    )
    if kind == "qplanck-routing-permutation-invariant":
        return hashes_present and all(
            evidence.get(name) is True
            for name in (
                "routing_symbolic_consistent",
                "basis_lowering_exact",
                "measurement_remap_consistent",
            )
        )
    return hashes_present


def _semantic_hash(record: Mapping[str, Any]) -> str | None:
    correctness = record.get("correctness")
    if not isinstance(correctness, Mapping):
        return None
    value = correctness.get("semantic_hash")
    return value if isinstance(value, str) and value else None


def _native_pairs(
    report: Mapping[str, Any],
) -> dict[int, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    by_engine: dict[str, dict[int, Mapping[str, Any]]] = {
        QPLANCK_ENGINE: {},
        NATIVE_ORACLE_ENGINE: {},
    }
    for record in _records(report):
        engine = record.get("engine")
        if engine not in by_engine or record.get("suite") != "native-gate":
            continue
        operations = _operation_count(record)
        if operations is not None:
            by_engine[str(engine)][operations] = record
    return {
        operations: (native, by_engine[NATIVE_ORACLE_ENGINE][operations])
        for operations, native in by_engine[QPLANCK_ENGINE].items()
        if operations in by_engine[NATIVE_ORACLE_ENGINE]
    }


def evaluate_native_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate every approved native-admission threshold without approximation."""

    pairs = _native_pairs(report)
    speedups: dict[int, float] = {}
    rss_ratios: dict[int, float] = {}
    for operations, (native, oracle) in pairs.items():
        native_time = _median_ns(native)
        oracle_time = _median_ns(oracle)
        if native_time is not None and oracle_time is not None:
            speedups[operations] = oracle_time / native_time
        native_rss = _rss_bytes(native)
        oracle_rss = _rss_bytes(oracle)
        if native_rss is not None and oracle_rss is not None:
            rss_ratios[operations] = native_rss / oracle_rss

    hundred_k_speedup = speedups.get(100_000)
    selected_speedups = [speedups[count] for count in (10_000, 100_000) if count in speedups]
    geometric_speedup = _geometric_mean(selected_speedups) if len(selected_speedups) == 2 else None
    small_ratios = {count: 1 / speedup for count, speedup in speedups.items() if count < 10_000}
    small_regression_passed = bool(small_ratios) and all(
        ratio <= 1.10 for ratio in small_ratios.values()
    )
    rss_passed = (
        set(rss_ratios) == set(pairs)
        and bool(rss_ratios)
        and all(ratio <= 1.25 for ratio in rss_ratios.values())
    )
    evidence_passed = bool(pairs) and all(
        _passed_evidence(native)
        and _passed_evidence(oracle)
        and _semantic_hash(native) is not None
        and _semantic_hash(native) == _semantic_hash(oracle)
        for native, oracle in pairs.values()
    )

    checks = [
        _check(
            "native.speedup-100k",
            hundred_k_speedup is not None and hundred_k_speedup >= 2.0,
            observed=hundred_k_speedup,
            required="oracle/native median speedup >= 2.0 at exactly 100,000 operations",
        ),
        _check(
            "native.geomean-speedup-10k-100k",
            geometric_speedup is not None and geometric_speedup >= 1.5,
            observed=geometric_speedup,
            required="geometric-mean speedup across 10,000 and 100,000 operations >= 1.5",
        ),
        _check(
            "native.small-case-regression",
            small_regression_passed,
            observed=small_ratios,
            required="every measured case below 10,000 operations has native/oracle time <= 1.10",
        ),
        _check(
            "native.peak-rss",
            rss_passed,
            observed=rss_ratios,
            required="native/oracle peak RSS <= 1.25 for every matched case",
        ),
        _check(
            "native.correctness-determinism",
            evidence_passed and {1_000, 10_000, 100_000}.issubset(pairs),
            observed={
                "matched_operation_counts": sorted(pairs),
                "semantic_hashes_match": evidence_passed,
            },
            required="zero correctness or determinism drift at 1k, 10k, and 100k operations",
        ),
    ]
    eligible = all(check["passed"] for check in checks)
    return {
        "gate": "native-release",
        "eligible": eligible,
        "checks": checks,
        "claim": (
            "QCore's native compiler meets the published native release gate on this environment."
            if eligible
            else None
        ),
    }


def _case_pairs(
    report: Mapping[str, Any],
    comparator: str,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    qcore: dict[str, Mapping[str, Any]] = {}
    other: dict[str, Mapping[str, Any]] = {}
    for record in _records(report):
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or record.get("suite") != "routing":
            continue
        if record.get("engine") == QPLANCK_ENGINE:
            qcore[case_id] = record
        elif record.get("engine") == comparator:
            other[case_id] = record
    return [(qcore[case_id], other[case_id]) for case_id in sorted(qcore.keys() & other.keys())]


def _case_timing_ratio(pair: tuple[Mapping[str, Any], Mapping[str, Any]]) -> float | None:
    qcore_time = _median_ns(pair[0])
    comparator_time = _median_ns(pair[1])
    if qcore_time is None or comparator_time is None:
        return None
    return qcore_time / comparator_time


def bootstrap_ratio_interval(
    ratios: Sequence[float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = 0x51434F5245,
) -> tuple[float, float]:
    """Return a deterministic case-stratified 95% bootstrap interval."""

    if not ratios or any(not math.isfinite(value) or value <= 0.0 for value in ratios):
        raise ValueError("Bootstrap ratios must be finite positive values.")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 100:
        raise ValueError("Bootstrap requires at least 100 resamples.")
    rng = random.Random(seed)
    estimates = [
        _geometric_mean([ratios[rng.randrange(len(ratios))] for _ in ratios])
        for _ in range(resamples)
    ]
    return (_quantile(estimates, 0.025), _quantile(estimates, 0.975))


def _quality_ratio(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> float | None:
    qcore_total = 0
    comparator_total = 0
    for qcore, comparator in pairs:
        qcore_quality = qcore.get("quality")
        comparator_quality = comparator.get("quality")
        if not isinstance(qcore_quality, Mapping) or not isinstance(comparator_quality, Mapping):
            return None
        left = qcore_quality.get("added_two_qubit_gates")
        right = comparator_quality.get("added_two_qubit_gates")
        if not isinstance(left, int) or not isinstance(right, int) or left < 0 or right < 0:
            return None
        qcore_total += left
        comparator_total += right
    if comparator_total == 0:
        return 1.0 if qcore_total == 0 else math.inf
    return qcore_total / comparator_total


def _pin_passed(report: Mapping[str, Any], comparator: str) -> tuple[bool, Any]:
    environment = report.get("environment")
    engines = environment.get("engines") if isinstance(environment, Mapping) else None
    status = engines.get(comparator) if isinstance(engines, Mapping) else None
    if not isinstance(status, Mapping):
        return False, None
    requested = status.get("requested_version")
    installed = status.get("installed_version")
    passed = status.get("available") is True and requested is not None and requested == installed
    return passed, dict(status)


def evaluate_competitive_gate(
    report: Mapping[str, Any],
    comparator: str,
) -> dict[str, Any]:
    """Evaluate whether one narrowly named comparator claim may be published."""

    pairs = _case_pairs(report, comparator)
    successful_pairs = [
        pair
        for pair in pairs
        if pair[0].get("status") == "success" and pair[1].get("status") == "success"
    ]
    ratios = [ratio for pair in successful_pairs if (ratio := _case_timing_ratio(pair)) is not None]
    runtime_ratio = (
        _geometric_mean(ratios) if ratios and len(ratios) == len(successful_pairs) else None
    )
    interval = bootstrap_ratio_interval(ratios) if ratios else None
    quality_ratio = _quality_ratio(successful_pairs) if successful_pairs else None

    all_records = _records(report)
    qcore_timeouts = sum(
        record.get("suite") == "routing"
        and record.get("engine") == QPLANCK_ENGINE
        and record.get("status") == "timeout"
        for record in all_records
    )
    comparator_timeouts = sum(
        record.get("suite") == "routing"
        and record.get("engine") == comparator
        and record.get("status") == "timeout"
        for record in all_records
    )
    correctness_passed = bool(successful_pairs) and all(
        _passed_evidence(qcore)
        and _semantic_evidence_passed(qcore)
        and _passed_evidence(other)
        and _semantic_evidence_passed(other)
        for qcore, other in successful_pairs
    )
    expected_case_ids = {case.case_id for case in benchmark_cases()}
    paired_case_ids = {
        str(qcore.get("case_id"))
        for qcore, _other in pairs
        if isinstance(qcore.get("case_id"), str)
    }
    no_missing_cases = paired_case_ids == expected_case_ids and len(successful_pairs) == len(
        expected_case_ids
    )
    pin_passed, pin_observed = _pin_passed(report, comparator)

    checks = [
        _check(
            "competitive.exact-pin",
            pin_passed,
            observed=pin_observed,
            required="comparator installed version exactly equals the published pin",
        ),
        _check(
            "competitive.runtime",
            runtime_ratio is not None and runtime_ratio < 0.8,
            observed=runtime_ratio,
            required="geometric mean QCore/comparator median runtime ratio < 0.8",
        ),
        _check(
            "competitive.two-qubit-quality",
            quality_ratio is not None and quality_ratio <= 1.05,
            observed=quality_ratio,
            required="aggregate QCore/comparator added two-qubit gate ratio <= 1.05",
        ),
        _check(
            "competitive.bootstrap-95",
            interval is not None and interval[1] < 1.0,
            observed=(None if interval is None else {"lower": interval[0], "upper": interval[1]}),
            required="deterministic case-stratified 95% bootstrap interval excludes parity below 1.0",
        ),
        _check(
            "competitive.correctness",
            correctness_passed and no_missing_cases,
            observed={
                "matched_cases": len(pairs),
                "successful_cases": len(successful_pairs),
                "expected_cases": len(expected_case_ids),
                "semantic_evidence_passed": correctness_passed,
            },
            required=(
                "zero correctness/determinism failures, required source-to-output semantic "
                "evidence, and no missing matched cases"
            ),
        ),
        _check(
            "competitive.timeouts",
            qcore_timeouts == 0 and qcore_timeouts <= comparator_timeouts,
            observed={"qcore": qcore_timeouts, "comparator": comparator_timeouts},
            required="QCore has zero timeouts and no timeout deficit versus comparator",
        ),
    ]
    eligible = all(check["passed"] for check in checks)
    return {
        "gate": "competitive",
        "comparator": comparator,
        "eligible": eligible,
        "checks": checks,
        "claim": (
            f"QCore beat {comparator} on the published, pinned routing corpus."
            if eligible
            else None
        ),
    }


def evaluate_claims(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "qplanck.benchmark.raw.v0.1":
        raise ValueError("Unsupported raw benchmark schema version.")
    return {
        "schema_version": CLAIM_SCHEMA_VERSION,
        "native_release": evaluate_native_gate(report),
        "competitive": {
            comparator: evaluate_competitive_gate(report, comparator)
            for comparator in (QISKIT_ENGINE, CIRQ_ENGINE)
        },
    }


def merge_raw_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge separately isolated suites only when environment identity agrees."""

    if not reports:
        raise ValueError("At least one raw benchmark report is required.")
    for report in reports:
        if report.get("schema_version") != "qplanck.benchmark.raw.v0.1":
            raise ValueError("Unsupported raw benchmark schema version.")
    identity_keys = (
        "python_version",
        "python_implementation",
        "platform",
        "machine",
        "processor",
        "logical_cpu_count",
        "thread_environment",
        "git",
        "engines",
    )
    raw_environments = [report.get("environment") for report in reports]
    if any(not isinstance(environment, Mapping) for environment in raw_environments):
        raise ValueError("Every raw report must include environment metadata.")
    environments = [
        environment for environment in raw_environments if isinstance(environment, Mapping)
    ]
    identities = [
        {key: environment.get(key) for key in identity_keys} for environment in environments
    ]
    if any(identity != identities[0] for identity in identities[1:]):
        raise ValueError("Raw reports were captured in different benchmark environments.")
    records = [record for report in reports for record in _records(report)]
    return {
        "schema_version": "qplanck.benchmark.raw.v0.1",
        "suite": {
            "merged_report_count": len(reports),
            "source_suites": [report.get("suite") for report in reports],
        },
        "environment": dict(environments[0]),
        "records": records,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="+", help="One or more raw QCore benchmark JSON files.")
    parser.add_argument("--output", required=True, help="Claim decision JSON destination.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    reports: list[Mapping[str, Any]] = []
    for input_path in args.input:
        raw_report = json.loads(Path(input_path).read_text(encoding="utf-8"))
        if not isinstance(raw_report, Mapping):
            raise ValueError("Raw benchmark JSON must contain an object.")
        reports.append(raw_report)
    raw = reports[0] if len(reports) == 1 else merge_raw_reports(reports)
    result = evaluate_claims(raw)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if result["native_release"]["eligible"] else 2


if __name__ == "__main__":  # pragma: no cover - command-line entry point
    raise SystemExit(main())


__all__ = [
    "BOOTSTRAP_RESAMPLES",
    "CLAIM_SCHEMA_VERSION",
    "bootstrap_ratio_interval",
    "evaluate_claims",
    "evaluate_competitive_gate",
    "evaluate_native_gate",
    "main",
    "merge_raw_reports",
]
