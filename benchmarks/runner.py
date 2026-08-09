"""Raw benchmark runner with process isolation and reproducibility metadata."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.adapters import (
    CIRQ_ENGINE,
    ORACLE_ENGINE,
    QISKIT_ENGINE,
    QPLANCK_ENGINE,
    engine_status,
    pinned_environment,
    run_engine,
)
from benchmarks.corpus import (
    BENCHMARK_SIZES,
    TARGET_NAMES,
    WORKLOAD_NAMES,
    benchmark_cases,
    case_from_spec,
    corpus_manifest,
    native_stress_cases,
)
from benchmarks.models import BenchmarkCase, CompilerOutcome

RAW_SCHEMA_VERSION = "qplanck.benchmark.raw.v0.1"
DEFAULT_ITERATIONS = 10
DEFAULT_WARMUPS = 2
THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "PYTHONHASHSEED": "0",
}


def _percentile(values: Sequence[int], percentile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile of no values.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def summarize_samples(samples_ns: Sequence[int]) -> dict[str, float | int]:
    if not samples_ns:
        raise ValueError("At least one timing sample is required.")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in samples_ns
    ):
        raise ValueError("Timing samples must be positive integer nanoseconds.")
    median = float(statistics.median(samples_ns))
    deviations = [abs(value - median) for value in samples_ns]
    return {
        "sample_count": len(samples_ns),
        "minimum_ns": min(samples_ns),
        "median_ns": median,
        "mad_ns": float(statistics.median(deviations)),
        "p95_ns": _percentile(samples_ns, 0.95),
        "maximum_ns": max(samples_ns),
    }


def _peak_rss() -> tuple[int | None, str]:
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows has no resource module
        return None, "unavailable"
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return peak, "getrusage.ru_maxrss-bytes"
    return peak * 1024, "getrusage.ru_maxrss-kibibytes"


def _base_record(case: BenchmarkCase, engine: str) -> dict[str, Any]:
    return {
        **case.to_metadata(),
        "engine": engine,
        "status": "created",
        "samples_ns": [],
        "statistics": None,
        "memory": {"peak_rss_bytes": None, "method": "unavailable"},
        "quality": None,
        "correctness": {"passed": False, "method": "not-run", "detail": ""},
        "determinism": {"passed": False, "artifact_hashes": [], "semantic_hashes": []},
        "error": None,
    }


def _outcome_correctness(outcome: CompilerOutcome) -> dict[str, Any]:
    return {
        "passed": outcome.correctness_passed,
        "method": outcome.correctness_method,
        "detail": outcome.correctness_detail,
        "semantic_hash": outcome.semantic_hash,
        "semantic_evidence": dict(outcome.semantic_evidence),
    }


def measure_case(
    case: BenchmarkCase,
    engine: str,
    *,
    iterations: int = DEFAULT_ITERATIONS,
    warmups: int = DEFAULT_WARMUPS,
) -> dict[str, Any]:
    """Measure a case in the current process, checking correctness first."""

    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError("iterations must be a positive integer.")
    if isinstance(warmups, bool) or not isinstance(warmups, int) or warmups < 0:
        raise ValueError("warmups must be a non-negative integer.")
    record = _base_record(case, engine)
    status = engine_status(engine)
    if not status.available:
        record["status"] = "unavailable"
        record["error"] = {"type": "EngineUnavailableError", "message": status.reason}
        return record

    try:
        evidence = run_engine(engine, case)
    except Exception as error:
        record["status"] = "error"
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        return record
    record["correctness"] = _outcome_correctness(evidence)
    record["quality"] = evidence.quality.to_dict()
    if not evidence.correctness_passed:
        record["status"] = "correctness-failed"
        return record

    try:
        for _ in range(warmups):
            run_engine(engine, case, validate=False)
        samples: list[int] = []
        outcomes: list[CompilerOutcome] = []
        gc.collect()
        gc_enabled = gc.isenabled()
        gc.disable()
        try:
            for _ in range(iterations):
                started = time.perf_counter_ns()
                outcome = run_engine(engine, case, validate=False)
                elapsed = time.perf_counter_ns() - started
                if elapsed <= 0:  # pragma: no cover - supported timers are monotonic
                    raise RuntimeError("The monotonic timer returned a non-positive sample.")
                samples.append(elapsed)
                outcomes.append(outcome)
        finally:
            if gc_enabled:
                gc.enable()
        peak_rss, rss_method = _peak_rss()
        artifact_hashes = [item.artifact_hash for item in outcomes]
        semantic_hashes = [item.semantic_hash for item in outcomes]
        correctness = all(item.correctness_passed for item in outcomes)
        deterministic = len(set(artifact_hashes)) == 1 and len(set(semantic_hashes)) == 1
        record.update(
            {
                "status": "success" if correctness and deterministic else "evidence-failed",
                "samples_ns": samples,
                "statistics": summarize_samples(samples),
                "memory": {
                    "peak_rss_bytes": peak_rss,
                    "method": rss_method,
                    "scope": "isolated-process"
                    if os.environ.get("QPLANCK_BENCH_WORKER")
                    else "current-process",
                },
                "correctness": {
                    **_outcome_correctness(evidence),
                    "passed": correctness,
                },
                "determinism": {
                    "passed": deterministic,
                    "artifact_hashes": artifact_hashes,
                    "semantic_hashes": semantic_hashes,
                },
            }
        )
    except Exception as error:
        record["status"] = "error"
        record["error"] = {"type": type(error).__name__, "message": str(error)}
    return record


def _git_metadata() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "diff", "--quiet", "--ignore-submodules", "HEAD"],
                cwd=root,
                check=False,
                timeout=5,
            ).returncode
            != 0
        )
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


def environment_metadata() -> dict[str, Any]:
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "timer": {
            "name": "perf_counter_ns",
            "resolution_seconds": time.get_clock_info("perf_counter").resolution,
            "monotonic": time.get_clock_info("perf_counter").monotonic,
        },
        "thread_environment": {
            key: os.environ.get(key, value) for key, value in THREAD_ENVIRONMENT.items()
        },
        "git": _git_metadata(),
        "engines": pinned_environment(),
    }


def _timeout_record(case: BenchmarkCase, engine: str, timeout_seconds: float) -> dict[str, Any]:
    record = _base_record(case, engine)
    record["status"] = "timeout"
    record["error"] = {
        "type": "TimeoutExpired",
        "message": f"Isolated case exceeded {timeout_seconds:g} seconds.",
    }
    return record


def _isolated_record(
    case: BenchmarkCase,
    engine: str,
    *,
    iterations: int,
    warmups: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    status = engine_status(engine)
    if not status.available:
        return measure_case(case, engine, iterations=iterations, warmups=warmups)
    target_name = "none" if case.target is None else case.target.name
    size = (
        case.workload.operation_count if case.suite == "native-gate" else case.workload.qubit_count
    )
    command = [
        sys.executable,
        "-m",
        "benchmarks.runner",
        "worker",
        "--suite",
        case.suite,
        "--workload",
        case.workload.name,
        "--size",
        str(size),
        "--target",
        target_name,
        "--engine",
        engine,
        "--iterations",
        str(iterations),
        "--warmups",
        str(warmups),
    ]
    environment = os.environ.copy()
    environment.update(THREAD_ENVIRONMENT)
    environment["QPLANCK_BENCH_WORKER"] = "1"
    try:
        process = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _timeout_record(case, engine, timeout_seconds)
    if process.returncode != 0:
        record = _base_record(case, engine)
        record["status"] = "error"
        record["error"] = {
            "type": "WorkerProcessError",
            "message": f"Benchmark worker exited with status {process.returncode}.",
        }
        return record
    try:
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        record = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        record = _base_record(case, engine)
        record["status"] = "error"
        record["error"] = {
            "type": "WorkerProtocolError",
            "message": "Benchmark worker did not return its JSON record.",
        }
    return record


def run_report(
    cases: Sequence[BenchmarkCase],
    engines: Sequence[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    warmups: int = DEFAULT_WARMUPS,
    isolate: bool = True,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in cases:
        for engine in engines:
            if isolate:
                record = _isolated_record(
                    case,
                    engine,
                    iterations=iterations,
                    warmups=warmups,
                    timeout_seconds=timeout_seconds,
                )
            else:
                record = measure_case(case, engine, iterations=iterations, warmups=warmups)
            records.append(record)
    return {
        "schema_version": RAW_SCHEMA_VERSION,
        "suite": {
            "corpus": corpus_manifest(),
            "iterations": iterations,
            "warmups": warmups,
            "process_isolation": isolate,
            "case_timeout_seconds": timeout_seconds if isolate else None,
            "correctness_before_timing": True,
        },
        "environment": environment_metadata(),
        "records": records,
    }


def _write_json(path: str, value: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    routing = subparsers.add_parser("run", help="Run the routing application corpus.")
    routing.add_argument("--output", required=True)
    routing.add_argument(
        "--engines", nargs="+", default=[QPLANCK_ENGINE, QISKIT_ENGINE, CIRQ_ENGINE]
    )
    routing.add_argument("--sizes", nargs="+", type=int, default=list(BENCHMARK_SIZES))
    routing.add_argument("--workloads", nargs="+", default=list(WORKLOAD_NAMES))
    routing.add_argument("--targets", nargs="+", default=list(TARGET_NAMES))

    native = subparsers.add_parser("native-gate", help="Run the native-versus-oracle gate.")
    native.add_argument("--output", required=True)
    native.add_argument("--engines", nargs="+", default=[QPLANCK_ENGINE, ORACLE_ENGINE])

    for command in (routing, native):
        command.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
        command.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
        command.add_argument("--timeout-seconds", type=float, default=300.0)
        command.add_argument("--no-isolation", action="store_true")

    worker = subparsers.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--suite", required=True)
    worker.add_argument("--workload", required=True)
    worker.add_argument("--size", required=True, type=int)
    worker.add_argument("--target", required=True)
    worker.add_argument("--engine", required=True)
    worker.add_argument("--iterations", required=True, type=int)
    worker.add_argument("--warmups", required=True, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "worker":
        case = case_from_spec(
            suite=args.suite,
            workload_name=args.workload,
            size=args.size,
            target_name=None if args.target == "none" else args.target,
        )
        print(
            json.dumps(
                measure_case(
                    case,
                    args.engine,
                    iterations=args.iterations,
                    warmups=args.warmups,
                ),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0

    if args.command == "native-gate":
        cases = native_stress_cases()
    else:
        selected_sizes = tuple(args.sizes)
        invalid_sizes = sorted(set(selected_sizes).difference(BENCHMARK_SIZES))
        if invalid_sizes:
            raise SystemExit(f"Unsupported sizes: {invalid_sizes}.")
        cases = tuple(
            case
            for case in benchmark_cases(selected_sizes)
            if case.workload.name in args.workloads
            and case.target is not None
            and case.target.name in args.targets
        )
    report = run_report(
        cases,
        args.engines,
        iterations=args.iterations,
        warmups=args.warmups,
        isolate=not args.no_isolation,
        timeout_seconds=args.timeout_seconds,
    )
    _write_json(args.output, report)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess use
    raise SystemExit(main())


__all__ = [
    "DEFAULT_ITERATIONS",
    "DEFAULT_WARMUPS",
    "RAW_SCHEMA_VERSION",
    "environment_metadata",
    "main",
    "measure_case",
    "run_report",
    "summarize_samples",
]
