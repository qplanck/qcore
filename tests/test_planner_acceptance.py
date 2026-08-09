from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.planner_acceptance import (
    ACCEPTANCE_COHORT,
    ACCEPTANCE_PROTOCOL_ID,
    MATERIAL_IMPROVEMENT_THRESHOLD,
    TARGET_NAMES,
    WORKLOAD_NAMES,
    acceptance_protocol,
    acceptance_targets,
    acceptance_workloads,
    mixed_portfolio_strategies,
    run_acceptance_suite,
    strong_qiskit_strategies,
    write_acceptance_artifacts,
)


def test_development_protocol_is_frozen_hashable_and_attempt_fair() -> None:
    first = acceptance_protocol()
    second = acceptance_protocol()

    assert first == second
    assert first["protocol_id"] == ACCEPTANCE_PROTOCOL_ID
    assert first["protocol_status"] == "draft"
    assert first["ratified_at"] is None
    assert first["review_attestation"] is None
    assert first["held_out_commitment"] is None
    assert first["reference_environment"]["status"] == "unlocked"
    assert first["reference_environment"]["qiskit"] == "2.5.1"
    assert first["proposed_master_thresholds"]["ratified"] is False
    assert first["cohort"] == ACCEPTANCE_COHORT == "development"
    assert first["protocol_hash"].startswith("sha256:")
    assert [item.name for item in acceptance_workloads()] == list(WORKLOAD_NAMES)
    assert [item.name for item in acceptance_targets()] == list(TARGET_NAMES)
    assert len(strong_qiskit_strategies()) == len(mixed_portfolio_strategies()) == 8
    assert first["candidate_attempt_budget"] == {
        "strong_qiskit": 8,
        "mixed_portfolio": 8,
        "wall_time_equalized": False,
        "wall_time_budget_seconds": None,
    }
    assert first["material_improvement_threshold"] == MATERIAL_IMPROVEMENT_THRESHOLD


def test_protocol_targets_preserve_asymmetric_evidence_and_unknowns() -> None:
    for fixture in acceptance_targets():
        metadata = fixture.target.metadata
        errors = metadata["instruction_errors"]
        assert errors["cx"] == 0.02
        assert any(str(key).startswith("cx:") for key in errors)
        assert "hardware fidelity" in metadata["unknown_fields"]
        assert metadata["declared"]["available"] is False
        assert fixture.target.snapshot_id is not None


def test_one_case_dry_run_preserves_correctness_and_refuses_master_go() -> None:
    pytest.importorskip("qiskit")

    report = run_acceptance_suite(workload_names=("ghz",), target_names=("line",))

    assert report["development_gate"]["passed"] is True
    assert report["development_gate"]["decision"] == "research-continue"
    assert report["master_spec_v0_1_gate"]["status"] == "not_evaluated"
    assert report["master_spec_v0_1_gate"]["decision"] is None
    assert report["summary"]["case_count"] == 1
    assert report["summary"]["correctness_passed"] is True
    assert report["summary"]["artifact_integrity_passed"] is True
    assert report["summary"]["offline_replay_passed"] is True
    assert report["summary"]["replayed_plan_count"] == 3
    assert report["summary"]["candidate_attempt_parity"] is True
    case = report["cases"][0]
    assert case["correctness_passed"] is True
    assert case["artifact_integrity_passed"] is True
    assert case["strong_qiskit"]["candidate_attempts"] == 8
    assert case["mixed_portfolio"]["candidate_attempts"] == 8
    assert all(
        item["recompilation_replay"]["passed"] is True
        and item["recompilation_replay"]["environment_compatible"] is True
        for item in case["artifact_integrity"].values()
    )
    assert "not an untouched held-out run" in report["scope"]
    assert (
        "independent quantum/compiler methodology review"
        in report["master_spec_v0_1_gate"]["open_requirements"]
    )


def test_acceptance_artifacts_are_complete_json_and_case_jsonl(tmp_path: Path) -> None:
    pytest.importorskip("qiskit")
    report = run_acceptance_suite(workload_names=("ghz",), target_names=("line",))
    json_path = tmp_path / "planner-development.json"
    jsonl_path = tmp_path / "planner-development.jsonl"

    write_acceptance_artifacts(report, json_path=json_path, jsonl_path=jsonl_path)

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert loaded["protocol"]["protocol_hash"] == report["protocol"]["protocol_hash"]
    assert [item["record_type"] for item in records] == ["protocol", "case", "summary"]
    assert records[-1]["master_spec_v0_1_gate"]["status"] == "not_evaluated"


@pytest.mark.parametrize(
    ("workloads", "targets", "message"),
    [
        (("unknown",), ("line",), "Unknown acceptance workloads"),
        (("ghz",), ("unknown",), "Unknown acceptance targets"),
        ((), ("line",), "requires workloads and targets"),
        (("ghz",), (), "requires workloads and targets"),
    ],
)
def test_acceptance_selection_rejects_unknown_or_empty_cohorts(
    workloads: tuple[str, ...], targets: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_acceptance_suite(workload_names=workloads, target_names=targets)
