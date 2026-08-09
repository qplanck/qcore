from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import qplanck
from qplanck import Circuit
from qplanck.ir import CircuitIR
from qplanck.planning import (
    Plan,
    Program,
    StrategyResult,
    StrategyUnavailableError,
    plan,
)
from qplanck.replay import (
    REPLAY_MISMATCH_SCHEMA_VERSION,
    REPLAY_REPORT_SCHEMA_VERSION,
    ReplayError,
    replay,
)
from qplanck.targets import Target


@dataclass(frozen=True)
class _StaticStrategy:
    artifact: CircuitIR
    strategy_id: str = "fixture.static"
    strategy_version: str = "1"
    mode: str = "stable"
    latency_ms: float = 1.0

    @property
    def options(self) -> dict[str, object]:
        return {"mode": self.mode}

    def run(self, program: Program, target: Target) -> StrategyResult:
        return StrategyResult(
            artifact=self.artifact,
            semantic_equivalent=True,
            semantic_evidence=("offline fixture equivalence",),
            inserted_swap_count=0,
            compilation_latency_ms=self.latency_ms,
            provenance={"fixture": "static"},
        )


@dataclass(frozen=True)
class _UnavailableStrategy:
    strategy_id: str = "fixture.static"
    strategy_version: str = "1"
    mode: str = "stable"

    @property
    def options(self) -> dict[str, object]:
        return {"mode": self.mode}

    def run(self, program: Program, target: Target) -> StrategyResult:
        raise StrategyUnavailableError(reason_code="fixture.offline_unavailable")


def _decision(*, latency_ms: float = 1.0) -> tuple[Plan, _StaticStrategy]:
    circuit = Circuit(1).x(0)
    strategy = _StaticStrategy(circuit.ir, latency_ms=latency_ms)
    decision = plan(
        circuit,
        targets=[Target.testing(1, target_id="offline.replay")],
        strategies=[strategy],
        objective="minimize_depth",
    )
    return decision, strategy


def test_replay_accepts_plan_manifest_json_and_path(tmp_path: Path) -> None:
    decision, strategy = _decision()
    manifest_path = tmp_path / "planning-manifest.json"
    decision.manifest.write(manifest_path)

    reports = (
        replay(decision, strategies=[strategy]),
        replay(decision.manifest, strategies=[strategy]),
        replay(decision.manifest.to_json(), strategies=[strategy]),
        replay(manifest_path, strategies=[strategy]),
        replay(str(manifest_path), strategies=[strategy]),
    )

    assert all(report.passed for report in reports)
    assert all(report.environment_compatible for report in reports)
    assert all(report.matched_candidate_count == 1 for report in reports)
    assert reports[0].schema_version == REPLAY_REPORT_SCHEMA_VERSION
    assert json.loads(reports[0].to_json())["passed"] is True
    assert qplanck.replay is replay
    assert qplanck.ReplayError is ReplayError


def test_replay_ignores_latency_and_wall_clock_observations() -> None:
    decision, _ = _decision(latency_ms=1.0)
    replay_strategy = _StaticStrategy(decision.program.ir, latency_ms=999_999.0)

    report = replay(decision, strategies=[replay_strategy])

    assert report.passed
    assert report.saved_plan_hash == report.replayed_plan_hash
    assert report.saved_manifest_hash == report.replayed_manifest_hash
    assert report.mismatches == ()


def test_replay_reports_candidate_artifact_and_hash_drift() -> None:
    decision, _ = _decision()
    changed_artifact = Circuit(1).x(0).h(0).ir

    report = replay(
        decision.manifest,
        strategies=[_StaticStrategy(changed_artifact)],
    )

    categories = {item.category for item in report.mismatches}
    assert not report.passed
    assert "candidate_hash" in categories
    assert "candidate_artifact_hash" in categories
    assert "plan_hash" in categories
    assert "manifest_hash" in categories
    assert all(item.schema_version == REPLAY_MISMATCH_SCHEMA_VERSION for item in report.mismatches)


def test_replay_preserves_failed_candidate_evidence_when_no_selection_remains() -> None:
    decision, _ = _decision()

    report = replay(decision.manifest, strategies=[_UnavailableStrategy()])

    categories = {item.category for item in report.mismatches}
    assert not report.passed
    assert report.replayed_plan_hash is None
    assert report.replayed_manifest_hash is None
    assert report.replayed_selected_candidate_id is None
    assert "candidate_disposition" in categories
    assert "selection" in categories


@pytest.mark.parametrize("kind", ["missing", "changed", "extra", "ambiguous"])
def test_replay_requires_exact_strategy_descriptor_coverage(kind: str) -> None:
    decision, strategy = _decision()
    extra = _StaticStrategy(
        decision.program.ir,
        strategy_id="fixture.extra",
    )
    portfolios = {
        "missing": [],
        "changed": [replace(strategy, mode="changed")],
        "extra": [strategy, extra],
        "ambiguous": [strategy, strategy],
    }

    with pytest.raises(ReplayError, match="strateg"):
        replay(decision.manifest, strategies=portfolios[kind])


def test_replay_rejects_tampering_unknown_fields_and_schema_drift() -> None:
    decision, strategy = _decision()
    payload = decision.manifest.to_dict()

    tampered_hash = dict(payload)
    tampered_hash["manifest_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ReplayError, match="integrity"):
        replay(json.dumps(tampered_hash), strategies=[strategy])

    unknown_field = dict(payload)
    unknown_field["unverified_extension"] = "not-covered-by-the-schema"
    with pytest.raises(ReplayError, match="exact canonical schema"):
        replay(json.dumps(unknown_field), strategies=[strategy])

    schema_drift = dict(payload)
    schema_drift["schema_version"] = "qcore.planning-manifest.v9"
    with pytest.raises(ReplayError, match="unsupported"):
        replay(json.dumps(schema_drift), strategies=[strategy])


def test_replay_rejects_secret_shaped_serialized_fields_before_deserialization() -> None:
    decision, strategy = _decision()
    payload = decision.manifest.to_dict()
    payload["accessToken"] = "canary"

    with pytest.raises(ReplayError, match="Secret-bearing field"):
        replay(json.dumps(payload), strategies=[strategy])


def test_environment_compatibility_is_reported_separately() -> None:
    decision, strategy = _decision()
    changed_environment = {
        **dict(decision.manifest.environment),
        "python_version": "0.0-incompatible",
    }
    saved = replace(decision.manifest, environment=changed_environment)

    report = replay(saved, strategies=[strategy])

    assert not report.environment_compatible
    assert report.environment_mismatches[0].category == "environment"
    assert report.environment_mismatches[0].subject == "environment.python_version"
    assert not report.passed
    assert any(item.category == "manifest_hash" for item in report.mismatches)
