"""Optional pyperf entry point for publication-grade raw timing JSON.

The selected case is configured through environment variables so pyperf can
re-execute the command unchanged in calibrated worker processes.
"""

from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from benchmarks.adapters import QPLANCK_ENGINE, engine_status, run_engine
from benchmarks.corpus import case_from_spec, corpus_manifest


def _configuration() -> tuple[str, str, str, int, str | None]:
    engine = os.environ.get("QPLANCK_BENCH_ENGINE", QPLANCK_ENGINE)
    suite = os.environ.get("QPLANCK_BENCH_SUITE", "routing")
    workload = os.environ.get("QPLANCK_BENCH_WORKLOAD", "ghz")
    size = int(os.environ.get("QPLANCK_BENCH_SIZE", "27"))
    target = os.environ.get("QPLANCK_BENCH_TARGET", "heavy-hex-style")
    return engine, suite, workload, size, None if target == "none" else target


def main() -> None:
    try:
        pyperf = import_module("pyperf")
    except ImportError as error:  # pragma: no cover - optional locked benchmark environment
        raise SystemExit(
            "Install benchmarks/requirements.lock to run raw pyperf benchmarks."
        ) from error

    engine, suite, workload, size, target = _configuration()
    status = engine_status(engine)
    if not status.available:
        raise SystemExit(status.reason or f"Engine {engine} is unavailable.")
    case = case_from_spec(
        suite=suite,
        workload_name=workload,
        size=size,
        target_name=target,
    )
    correctness = run_engine(engine, case)
    if not correctness.correctness_passed:
        raise SystemExit(
            "Correctness preflight failed; timing was not started: "
            + correctness.correctness_detail
        )

    runner: Any = pyperf.Runner()
    manifest = corpus_manifest()
    runner.metadata.update(
        {
            "qplanck_benchmark_schema": "qplanck.benchmark.pyperf.v0.1",
            "qplanck_case_id": case.case_id,
            "qplanck_engine": engine,
            "qplanck_engine_version": status.installed_version or "in-tree",
            "qplanck_corpus_hash": str(manifest["corpus_hash"]),
            "qplanck_workload_hash": case.workload.semantic_hash,
            "qplanck_target_hash": (
                "none" if case.target is None else case.target.target.content_hash
            ),
            "qplanck_correctness_method": correctness.correctness_method,
        }
    )
    runner.bench_func(case.case_id, run_engine, engine, case)


if __name__ == "__main__":  # pragma: no cover - managed by pyperf workers
    main()
