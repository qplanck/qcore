from __future__ import annotations

import json
from pathlib import Path

from benchmarks.planner import run_planner_gate, write_planner_gate_artifacts


def test_planner_gate_records_material_correctness_preserving_improvement() -> None:
    report = run_planner_gate()

    assert report["gate"]["passed"] is True
    assert report["gate"]["decision"] == "vertical-slice-go"
    assert report["master_spec_v0_1_gate"]["status"] == "not_evaluated"
    assert report["master_spec_v0_1_gate"]["decision"] is None
    assert report["comparison"]["correctness_preserved"] is True
    assert report["comparison"]["adaptive_candidate_selected"] is True
    improvements = report["comparison"]["improvements_baseline_minus_adaptive"]
    assert improvements["two_qubit_gate_count"] > 0
    assert improvements["inserted_swap_count"] > 0
    assert improvements["estimated_error"] > 0
    assert "neither hardware-performance evidence" in report["scope"]
    assert "complete master-spec" in report["scope"]
    checked = [
        item for item in report["adaptive"]["correctness"]["candidates"].values() if item["checked"]
    ]
    assert checked
    assert all(item["exact_probability_equivalent"] for item in checked)
    assert all(item["maximum_probability_delta"] <= 1e-12 for item in checked)


def test_planner_gate_semantic_identities_are_reproducible() -> None:
    first = run_planner_gate()
    second = run_planner_gate()

    assert first["target_hash"] == second["target_hash"]
    assert first["baseline"]["plan_hash"] == second["baseline"]["plan_hash"]
    assert first["adaptive"]["plan_hash"] == second["adaptive"]["plan_hash"]
    assert (
        first["baseline"]["manifest"]["manifest_hash"]
        == second["baseline"]["manifest"]["manifest_hash"]
    )
    assert (
        first["adaptive"]["manifest"]["manifest_hash"]
        == second["adaptive"]["manifest"]["manifest_hash"]
    )


def test_planner_gate_writes_json_and_jsonl_artifacts(tmp_path: Path) -> None:
    report = run_planner_gate()
    json_path = tmp_path / "planner-gate.json"
    jsonl_path = tmp_path / "planner-gate.jsonl"

    write_planner_gate_artifacts(report, json_path=json_path, jsonl_path=jsonl_path)

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["gate"]["passed"] is True
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert [item["record_type"] for item in records] == [
        "metadata",
        "baseline",
        "adaptive",
        "gate",
        "master_spec_gate",
    ]
