from __future__ import annotations

from typing import Any

import pytest

from benchmarks import adapters
from benchmarks.adapters import (
    CIRQ_ENGINE,
    QISKIT_ENGINE,
    QPLANCK_ENGINE,
    EngineStatus,
)
from benchmarks.claims import (
    bootstrap_ratio_interval,
    evaluate_claims,
    evaluate_competitive_gate,
    evaluate_native_gate,
)
from benchmarks.corpus import (
    BENCHMARK_SIZES,
    TARGET_NAMES,
    WORKLOAD_NAMES,
    benchmark_cases,
    benchmark_targets,
    benchmark_workloads,
    case_from_spec,
    corpus_manifest,
    native_stress_cases,
)
from benchmarks.models import CompilerOutcome, QualityMetrics
from benchmarks.runner import measure_case, summarize_samples


def test_application_corpus_is_complete_and_deterministic() -> None:
    first = benchmark_cases()
    second = benchmark_cases()

    assert len(first) == 4 * 5 * 4
    assert [case.case_id for case in first] == [case.case_id for case in second]
    assert [case.workload.semantic_hash for case in first] == [
        case.workload.semantic_hash for case in second
    ]
    assert {case.workload.name for case in first} == set(WORKLOAD_NAMES)
    assert {case.target.name for case in first if case.target is not None} == set(TARGET_NAMES)
    assert {case.workload.qubit_count for case in first} == set(BENCHMARK_SIZES)
    assert all(case.optimization_level == 2 for case in first)


def test_workloads_and_targets_have_expected_benchmark_pressure() -> None:
    workloads = {item.name: item for item in benchmark_workloads(65)}
    targets = {item.name: item for item in benchmark_targets(65)}

    assert workloads["ghz"].operation_count == 65
    assert workloads["decomposed-qft"].operation_count == 10_497
    assert workloads["random"].seed == benchmark_workloads(65)[4].seed
    assert all("swap" not in item.target.basis_gates for item in targets.values())
    assert (
        max(len(targets["heavy-hex-style"].target.topology.neighbors(qubit)) for qubit in range(65))
        <= 3
    )
    assert len(targets["grid"].target.topology.components) == 1


def test_native_stress_inputs_use_exact_release_gate_sizes() -> None:
    cases = native_stress_cases()

    assert [case.workload.operation_count for case in cases] == [1_000, 10_000, 100_000]
    assert all(case.optimization_level == 1 and case.target is None for case in cases)
    assert all(case.workload.category == "compiler-kernel" for case in cases)


def test_corpus_manifest_and_case_reconstruction_are_stable() -> None:
    manifest = corpus_manifest()
    case = case_from_spec(
        suite="routing",
        workload_name="qaoa",
        size=16,
        target_name="ring",
    )
    stress = case_from_spec(
        suite="native-gate",
        workload_name="native-stress",
        size=10_000,
        target_name=None,
    )

    assert manifest["case_count"] == 83
    assert str(manifest["corpus_hash"]).startswith("sha256:")
    assert case.case_id == "routing/qaoa/q16/ring/o2"
    assert stress.workload.operation_count == 10_000


def test_optional_engine_requires_exact_public_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapters.importlib_metadata, "version", lambda _name: "2.5.1")
    assert adapters.engine_status(QISKIT_ENGINE).available is True

    monkeypatch.setattr(adapters.importlib_metadata, "version", lambda _name: "2.5.0")
    status = adapters.engine_status(QISKIT_ENGINE)
    assert status.available is False
    assert status.requested_version == "2.5.1"
    assert status.reason == "Installed version differs from the benchmark pin."


def test_sample_statistics_include_median_mad_and_p95() -> None:
    summary = summarize_samples([100, 200, 300])

    assert summary == {
        "sample_count": 3,
        "minimum_ns": 100,
        "median_ns": 200.0,
        "mad_ns": 100.0,
        "p95_ns": pytest.approx(290.0),
        "maximum_ns": 300,
    }
    with pytest.raises(ValueError, match="positive integer"):
        summarize_samples([0])


def test_measure_case_checks_correctness_before_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    case = benchmark_cases((5,))[0]
    calls = 0
    quality = QualityMetrics(5, 5, 4, 4, 0, 5, 0)

    def fake_status(_engine: str) -> EngineStatus:
        return EngineStatus("fake", True, None, "test")

    def fake_engine(_engine: str, _case: Any, **_kwargs: Any) -> CompilerOutcome:
        nonlocal calls
        calls += 1
        return CompilerOutcome(
            artifact_hash="sha256:bad",
            semantic_hash="sha256:bad",
            quality=quality,
            correctness_passed=False,
            correctness_method="synthetic",
            correctness_detail="failed",
        )

    monkeypatch.setattr("benchmarks.runner.engine_status", fake_status)
    monkeypatch.setattr("benchmarks.runner.run_engine", fake_engine)

    record = measure_case(case, "fake", iterations=3, warmups=2)

    assert record["status"] == "correctness-failed"
    assert record["samples_ns"] == []
    assert calls == 1


def test_measure_case_records_raw_samples_quality_rss_and_determinism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = benchmark_cases((5,))[0]
    quality = QualityMetrics(5, 8, 4, 7, 3, 8, 1)

    monkeypatch.setattr(
        "benchmarks.runner.engine_status",
        lambda _engine: EngineStatus("fake", True, None, "test"),
    )
    monkeypatch.setattr(
        "benchmarks.runner.run_engine",
        lambda _engine, _case, **_kwargs: CompilerOutcome(
            artifact_hash="sha256:stable",
            semantic_hash="sha256:semantic",
            quality=quality,
            correctness_passed=True,
            correctness_method="synthetic",
        ),
    )
    monkeypatch.setattr("benchmarks.runner._peak_rss", lambda: (123_456, "synthetic"))

    record = measure_case(case, "fake", iterations=3, warmups=1)

    assert record["status"] == "success"
    assert len(record["samples_ns"]) == 3
    assert record["quality"] == quality.to_dict()
    assert record["memory"]["peak_rss_bytes"] == 123_456
    assert record["determinism"]["passed"] is True


def _record(
    *,
    engine: str,
    case_id: str,
    suite: str,
    operations: int,
    median_ns: float,
    rss: int,
    added_two_qubit: int = 10,
    semantic_hash: str = "sha256:same",
    qubit_count: int | None = None,
    source_semantic_hash: str | None = None,
    semantic_kind: str | None = None,
    status: str = "success",
) -> dict[str, Any]:
    semantic_evidence: dict[str, Any] = {}
    if qubit_count is not None and source_semantic_hash is not None and semantic_kind is not None:
        semantic_evidence = {
            "kind": semantic_kind,
            "verified": True,
            "source_semantic_hash": source_semantic_hash,
            "mapping_bijective": True,
            "topology_conformant": True,
        }
        if qubit_count <= 5:
            semantic_evidence["logical_dimension"] = 1 << qubit_count
        elif semantic_kind == "qplanck-routing-permutation-invariant":
            semantic_evidence.update(
                {
                    "initial_layout_hash": "sha256:initial",
                    "final_layout_hash": "sha256:final",
                    "routing_trace_hash": "sha256:trace",
                    "routing_symbolic_consistent": True,
                    "basis_lowering_exact": True,
                    "measurement_remap_consistent": True,
                }
            )
        elif semantic_kind == "qiskit-layout-permutation-invariant":
            semantic_evidence["layout_hash"] = "sha256:layout"
        elif semantic_kind == "cirq-router-permutation-invariant":
            semantic_evidence.update(
                {
                    "initial_mapping_hash": "sha256:initial",
                    "swap_mapping_hash": "sha256:swap",
                }
            )
    return {
        "case_id": case_id,
        "suite": suite,
        "engine": engine,
        "status": status,
        "workload": {
            "operation_count": operations,
            "qubit_count": qubit_count,
            "semantic_hash": source_semantic_hash,
        },
        "samples_ns": [int(median_ns * 0.99), int(median_ns), int(median_ns * 1.01)],
        "statistics": {"median_ns": median_ns},
        "memory": {"peak_rss_bytes": rss},
        "quality": {"added_two_qubit_gates": added_two_qubit},
        "correctness": {
            "passed": True,
            "semantic_hash": semantic_hash,
            "semantic_evidence": semantic_evidence,
        },
        "determinism": {"passed": True},
    }


def _native_report() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    timings = {
        1_000: (105.0, 100.0),
        10_000: (60.0, 100.0),
        100_000: (40.0, 100.0),
    }
    for operations, (native, oracle) in timings.items():
        case_id = f"native-gate/native-stress/q65/none/o1/{operations}"
        records.extend(
            (
                _record(
                    engine=QPLANCK_ENGINE,
                    case_id=case_id,
                    suite="native-gate",
                    operations=operations,
                    median_ns=native,
                    rss=125,
                ),
                _record(
                    engine="python-oracle",
                    case_id=case_id,
                    suite="native-gate",
                    operations=operations,
                    median_ns=oracle,
                    rss=100,
                ),
            )
        )
    return {"schema_version": "qplanck.benchmark.raw.v0.1", "records": records}


def test_native_claim_gate_applies_every_exact_threshold() -> None:
    report = _native_report()

    decision = evaluate_native_gate(report)

    assert decision["eligible"] is True
    assert all(check["passed"] for check in decision["checks"])
    assert decision["claim"] is not None

    report["records"][0]["statistics"]["median_ns"] = 111.0
    failed = evaluate_native_gate(report)
    assert failed["eligible"] is False
    assert (
        next(check for check in failed["checks"] if check["id"] == "native.small-case-regression")[
            "passed"
        ]
        is False
    )
    assert failed["claim"] is None


def _competitive_report(*, qcore_ratio: float = 0.7, qcore_quality: int = 100) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for index, case in enumerate(benchmark_cases()):
        case_id = case.case_id
        qubits = case.workload.qubit_count
        source_hash = case.workload.semantic_hash
        records.extend(
            (
                _record(
                    engine=QPLANCK_ENGINE,
                    case_id=case_id,
                    suite="routing",
                    operations=10 + index,
                    median_ns=100 * qcore_ratio,
                    rss=100,
                    added_two_qubit=qcore_quality,
                    semantic_hash=f"sha256:qcore-{index}",
                    qubit_count=qubits,
                    source_semantic_hash=source_hash,
                    semantic_kind=(
                        "exact-statevector-matrix-equivalence"
                        if qubits <= 5
                        else "qplanck-routing-permutation-invariant"
                    ),
                ),
                _record(
                    engine=QISKIT_ENGINE,
                    case_id=case_id,
                    suite="routing",
                    operations=10 + index,
                    median_ns=100,
                    rss=100,
                    added_two_qubit=100,
                    semantic_hash=f"sha256:qiskit-{index}",
                    qubit_count=qubits,
                    source_semantic_hash=source_hash,
                    semantic_kind=(
                        "exact-operator-equivalence"
                        if qubits <= 5
                        else "qiskit-layout-permutation-invariant"
                    ),
                ),
            )
        )
    return {
        "schema_version": "qplanck.benchmark.raw.v0.1",
        "environment": {
            "engines": {
                QISKIT_ENGINE: {
                    "available": True,
                    "requested_version": "2.5.1",
                    "installed_version": "2.5.1",
                }
            }
        },
        "records": records,
    }


def test_competitive_gate_requires_speed_quality_ci_correctness_and_pin() -> None:
    report = _competitive_report()

    decision = evaluate_competitive_gate(report, QISKIT_ENGINE)

    assert decision["eligible"] is True
    assert (
        decision["claim"] == f"QCore beat {QISKIT_ENGINE} on the published, pinned routing corpus."
    )
    assert all(check["passed"] for check in decision["checks"])

    parity = evaluate_competitive_gate(_competitive_report(qcore_ratio=0.8), QISKIT_ENGINE)
    assert parity["eligible"] is False
    assert (
        next(check for check in parity["checks"] if check["id"] == "competitive.runtime")["passed"]
        is False
    )

    topology_only = _competitive_report()
    topology_only["records"][0]["correctness"].pop("semantic_evidence")
    missing_semantics = evaluate_competitive_gate(topology_only, QISKIT_ENGINE)
    assert missing_semantics["eligible"] is False
    assert (
        next(
            check
            for check in missing_semantics["checks"]
            if check["id"] == "competitive.correctness"
        )["passed"]
        is False
    )


def test_claim_evaluator_fails_closed_for_missing_comparator_and_is_deterministic() -> None:
    report = _native_report()
    report["environment"] = {"engines": {}}

    result = evaluate_claims(report)
    first_interval = bootstrap_ratio_interval([0.6, 0.7, 0.8], resamples=500)
    second_interval = bootstrap_ratio_interval([0.6, 0.7, 0.8], resamples=500)

    assert result["native_release"]["eligible"] is True
    assert result["competitive"][QISKIT_ENGINE]["eligible"] is False
    assert result["competitive"][CIRQ_ENGINE]["claim"] is None
    assert first_interval == second_interval
    assert first_interval[1] < 1.0
