"""Reproducible compiler benchmark and evidence-gating utilities."""

from benchmarks.claims import (
    evaluate_claims,
    evaluate_competitive_gate,
    evaluate_native_gate,
    merge_raw_reports,
)
from benchmarks.corpus import (
    BENCHMARK_SIZES,
    TARGET_NAMES,
    WORKLOAD_NAMES,
    benchmark_cases,
    benchmark_targets,
    benchmark_workloads,
    native_stress_cases,
)

__all__ = [
    "BENCHMARK_SIZES",
    "TARGET_NAMES",
    "WORKLOAD_NAMES",
    "benchmark_cases",
    "benchmark_targets",
    "benchmark_workloads",
    "evaluate_claims",
    "evaluate_competitive_gate",
    "evaluate_native_gate",
    "merge_raw_reports",
    "native_stress_cases",
]
