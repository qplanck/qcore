from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

import pytest

from qplanck import Circuit
from qplanck.compiler import CompileOptions
from qplanck.ir import CircuitIR
from qplanck.planning import (
    ERROR_MODEL_VERSION,
    CandidateDisposition,
    MetricConstraint,
    Objective,
    Plan,
    PlanningError,
    PlanningManifest,
    Program,
    QCoreNativeStrategy,
    StrategyResult,
    StrategyUnavailableError,
    plan,
)
from qplanck.targets import InstructionSupport, Layout, Target, Topology


def _target(
    qubits: int = 3,
    *,
    topology: Topology | None = None,
    instruction_errors: dict[str, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Target:
    target_metadata = dict(metadata or {})
    if instruction_errors is not None:
        target_metadata["instruction_errors"] = instruction_errors
    return Target(
        "offline-target",
        topology or Topology.complete(qubits),
        (
            InstructionSupport("h", 1),
            InstructionSupport("x", 1),
            InstructionSupport("rz", 1),
            InstructionSupport("cx", 2),
        ),
        provider="offline-fixture",
        snapshot_id="fixture-1",
        metadata=target_metadata,
    )


@dataclass(frozen=True)
class _StaticStrategy:
    artifact: CircuitIR
    strategy_id: str
    latency: float = 1.0
    swaps: int | None = 0
    semantic_equivalent: bool = True
    strategy_version: str = "test-v1"

    @property
    def options(self) -> dict[str, object]:
        return {"fixture": self.strategy_id}

    def run(self, program: Program, target: Target) -> StrategyResult:
        return StrategyResult(
            artifact=self.artifact,
            semantic_equivalent=self.semantic_equivalent,
            semantic_evidence=("fixture exact-equivalence oracle",),
            inserted_swap_count=self.swaps,
            inserted_swap_unknown_reason=(
                "Fixture strategy cannot recover inserted SWAP provenance."
                if self.swaps is None
                else None
            ),
            compilation_latency_ms=self.latency,
            provenance={"fixture": True},
        )


@dataclass(frozen=True)
class _UnavailableStrategy:
    strategy_id: str = "optional.unavailable"
    strategy_version: str = "1"
    reason_code: str = "fixture.dependency_unavailable"

    @property
    def options(self) -> dict[str, object]:
        return {"dependency": "not-installed"}

    def run(self, program: Program, target: Target) -> StrategyResult:
        raise StrategyUnavailableError(reason_code=self.reason_code)


def test_program_normalizes_circuit_ir_and_openqasm_with_direct_provenance() -> None:
    circuit = Circuit(2, name="bell").h(0).cx(0, 1).measure_all()

    from_circuit = Program.from_input(circuit)
    from_ir = Program.from_input(circuit.ir)
    from_qasm = Program.from_input(circuit.to_qasm3())

    assert from_circuit.program_hash == from_ir.program_hash == from_qasm.program_hash
    assert from_qasm.frontend == "openqasm3"
    assert from_qasm.parser == "qplanck.qasm3.safe-subset"
    assert from_qasm.input_hash != from_circuit.input_hash
    assert Program.from_json(from_qasm.to_json()).to_dict() == from_qasm.to_dict()


def test_program_hash_tampering_fails_closed() -> None:
    payload = Program.from_input(Circuit(1).x(0)).to_dict()
    payload["program_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="hash does not match"):
        Program.from_dict(payload)


def test_program_accepts_qiskit_directly_when_optional_dependency_is_present() -> None:
    pytest.importorskip("qiskit")
    source = Circuit(2).h(0).cx(0, 1).measure_all()

    program = Program.from_input(source.to_qiskit())

    assert program.frontend == "qiskit"
    assert program.parser == "qplanck.qiskit-adapter.direct"
    assert program.program_hash == Program.from_input(source).program_hash


def test_objective_builtins_constraints_round_trip_and_observational_rejection() -> None:
    objective = Objective.minimize_error(
        constraints={"circuit_depth": MetricConstraint(maximum=20)}
    )

    assert Objective.from_dict(objective.to_dict()).to_dict() == objective.to_dict()
    assert Objective.from_name("minimize_depth").weights == {"circuit_depth": 1.0}
    assert Objective.from_name("minimize_two_qubit").weights == {"two_qubit_gate_count": 1.0}
    with pytest.raises(ValueError, match="Observational metric"):
        Objective.minimize("compilation_latency_ms")


def test_independent_error_model_is_named_and_missing_rates_stay_unknown() -> None:
    circuit = Circuit(2).h(0).cx(0, 1)
    known_target = _target(
        2,
        instruction_errors={"h:0": 0.01, "cx:0,1": 0.02},
    )
    known = plan(
        circuit,
        targets=[known_target],
        strategies=[_StaticStrategy(circuit.ir, "known")],
        objective=Objective.minimize_error(),
    )

    assert known.selected.metrics is not None
    assert known.selected.metrics.error_model == ERROR_MODEL_VERSION
    assert known.selected.metrics.estimated_error == pytest.approx(1 - (0.99 * 0.98))
    assert "not a hardware-fidelity guarantee" in known.selected.metrics.error_model_limitations[-1]

    with pytest.raises(PlanningError) as captured:
        plan(
            circuit,
            targets=[_target(2, instruction_errors={"h:0": 0.01})],
            strategies=[_StaticStrategy(circuit.ir, "missing")],
            objective="minimize_error",
        )
    rejected = captured.value.candidates[0]
    assert rejected.metrics is not None
    assert rejected.metrics.estimated_error is None
    assert "cx:0,1" in (rejected.metrics.estimated_error_unknown_reason or "")
    assert rejected.rejection_reasons == ("required_metric_unknown:estimated_error",)


def test_unknown_inserted_swaps_do_not_become_zero_or_block_unrelated_objective() -> None:
    circuit = Circuit(2).h(0).cx(0, 1)
    decision = plan(
        circuit,
        targets=[_target(2)],
        strategies=[_StaticStrategy(circuit.ir, "unknown-swaps", swaps=None)],
        objective="minimize_depth",
    )

    assert decision.selected.metrics is not None
    assert decision.selected.metrics.inserted_swap_count is None
    assert decision.selected.metrics.inserted_swap_unknown_reason is not None

    with pytest.raises(PlanningError, match="required_metric_unknown"):
        plan(
            circuit,
            targets=[_target(2)],
            strategies=[_StaticStrategy(circuit.ir, "unknown-swaps", swaps=None)],
            objective=Objective.minimize("inserted_swap_count"),
        )


def test_constraints_run_before_scoring_and_rejection_evidence_is_retained() -> None:
    source = Circuit(2).h(0)
    shallow = Circuit(2).h(0).ir
    deep = Circuit(2).h(0).x(0).h(0).ir
    decision = plan(
        source,
        targets=[_target(2)],
        strategies=[
            _StaticStrategy(deep, "deep"),
            _StaticStrategy(shallow, "shallow"),
        ],
        objective=Objective.minimize_depth(constraints={"circuit_depth": {"max": 1}}),
    )

    assert decision.selected.strategy_id == "shallow"
    assert len(decision.rejected) == 1
    assert decision.rejected[0].rejection_reasons == ("constraint_maximum_violated:circuit_depth",)


def test_target_validation_and_semantic_validation_fail_closed() -> None:
    source = Circuit(3).cx(0, 2)
    line_target = _target(3, topology=Topology.line(3))
    good = Circuit(3).cx(0, 1).ir
    decision = plan(
        source,
        targets=[line_target],
        strategies=[
            _StaticStrategy(source.ir, "non-local"),
            _StaticStrategy(good, "semantic-false", semantic_equivalent=False),
            _StaticStrategy(good, "valid"),
        ],
        objective="minimize_depth",
    )

    assert decision.selected.strategy_id == "valid"
    reasons = {reason for item in decision.rejected for reason in item.rejection_reasons}
    assert "target_validation_failed" in reasons
    assert "semantic_validation_failed" in reasons


def test_unavailable_strategy_is_not_silently_omitted() -> None:
    circuit = Circuit(1).x(0)
    decision = plan(
        circuit,
        targets=[_target(1)],
        strategies=[_StaticStrategy(circuit.ir, "valid"), _UnavailableStrategy()],
        objective="minimize_depth",
    )

    unavailable = next(
        item for item in decision.candidates if item.strategy_id.endswith("unavailable")
    )
    assert unavailable.disposition is CandidateDisposition.UNAVAILABLE
    assert unavailable.rejection_reasons == ("strategy_unavailable",)
    assert unavailable.diagnostics == ("strategy_reason_code:fixture.dependency_unavailable",)

    with pytest.raises(ValueError, match="stable lowercase identifier"):
        StrategyUnavailableError(reason_code="Raw provider message")


def test_ranking_hashes_ignore_completion_order_latency_and_wall_clock() -> None:
    source = Circuit(2).h(0)
    target = _target(2)
    first_strategies = [
        _StaticStrategy(Circuit(2).h(0).x(0).ir, "b", latency=999.0),
        _StaticStrategy(source.ir, "a", latency=1.0),
    ]
    second_strategies = [
        _StaticStrategy(source.ir, "a", latency=12345.0),
        _StaticStrategy(Circuit(2).h(0).x(0).ir, "b", latency=0.0),
    ]

    first = plan(
        source,
        targets=[target],
        strategies=first_strategies,
        objective="minimize_depth",
    )
    second = plan(
        source,
        targets=[target],
        strategies=second_strategies,
        objective="minimize_depth",
    )

    assert first.selected.strategy_id == second.selected.strategy_id == "a"
    assert first.plan_hash == second.plan_hash
    assert first.to_json() == second.to_json()
    assert first.manifest.manifest_hash == second.manifest.manifest_hash
    assert first.to_json(include_observations=True) != second.to_json(include_observations=True)


def test_candidate_hash_is_stable_before_and_after_ranking_fields() -> None:
    decision = plan(
        Circuit(1).x(0),
        targets=[_target(1)],
        strategies=[_StaticStrategy(Circuit(1).x(0).ir, "stable")],
        objective="minimize_depth",
    )
    candidate = decision.selected
    payload = candidate.to_dict()

    payload["score"] = "999"
    payload["score_components"] = {"circuit_depth": "999"}
    payload["rank"] = 77
    payload["pareto"] = False
    payload.pop("candidate_hash")
    altered = type(candidate).from_dict(payload)

    assert altered.candidate_hash == candidate.candidate_hash

    with pytest.raises(ValueError, match="positive integer"):
        replace(candidate, rank=True)
    with pytest.raises(TypeError, match="pareto must be a boolean"):
        replace(candidate, pareto=1)  # type: ignore[arg-type]


def test_explanation_covers_winner_alternative_rejections_and_hardware_caveat() -> None:
    source = Circuit(2).h(0)
    decision = plan(
        source,
        targets=[_target(2)],
        strategies=[
            _StaticStrategy(source.ir, "winner"),
            _StaticStrategy(Circuit(2).h(0).x(0).ir, "loser"),
            _UnavailableStrategy(),
        ],
        objective="minimize_depth",
    )

    explanation = decision.explain()
    structured = explanation.to_dict()
    assert structured["winner"]["strategy_id"] == "winner"
    assert structured["alternatives"][0]["strategy_id"] == "loser"
    assert "strategy_unavailable" in structured["rejected_by_reason"]
    assert "strategy_reason_code:fixture.dependency_unavailable" in structured["rejected_by_reason"]
    assert "no remote execution occurred" in str(explanation)
    assert "not a hardware-performance" in str(explanation)


def test_plan_and_manifest_round_trip_and_manifest_write(tmp_path) -> None:
    circuit = Circuit(2).h(0).cx(0, 1)
    decision = plan(
        circuit,
        targets=[_target(2)],
        strategies=[_StaticStrategy(circuit.ir, "roundtrip")],
        objective="minimize_depth",
    )

    restored_plan = Plan.from_json(decision.to_json())
    manifest = decision.manifest
    restored_manifest = PlanningManifest.from_json(manifest.to_json())
    path = tmp_path / "planning-manifest.json"
    manifest.write(path)

    assert restored_plan.plan_hash == decision.plan_hash
    assert restored_manifest.manifest_hash == manifest.manifest_hash
    assert json.loads(path.read_text())["observations"]["planning_started_at"]
    assert str(path) not in path.read_text()


def test_secret_shaped_fields_and_provider_objects_are_forbidden() -> None:
    circuit = Circuit(1).x(0)
    with pytest.raises(ValueError, match="Secret-bearing field"):
        plan(
            circuit,
            targets=[_target(1, metadata={"api_token": "canary"})],
            strategies=[_StaticStrategy(circuit.ir, "valid")],
            objective="minimize_depth",
        )

    decision = plan(
        circuit,
        targets=[_target(1)],
        strategies=[_StaticStrategy(circuit.ir, "valid")],
        objective="minimize_depth",
    )
    with pytest.raises(TypeError, match="Provider SDK object"):
        PlanningManifest(
            program=decision.program,
            objective=decision.objective,
            targets=(decision.selected.target,),
            candidates=decision.candidates,
            selected_plan_hash=decision.plan_hash,
            selected_candidate_id=decision.selected_candidate_id,
            planner_version="test",
            environment={"provider_session": object()},
        )


@pytest.mark.parametrize(
    "secret_key",
    ["credentials", "clientSecret", "accessToken", "APIKey", "authorization"],
)
def test_secret_key_styles_are_rejected_before_plan_serialization(secret_key: str) -> None:
    source = CircuitIR(
        qubit_count=1,
        operations=Circuit(1).x(0).operations,
        metadata={secret_key: "canary"},
    )

    with pytest.raises(ValueError, match="Secret-bearing field"):
        plan(
            source,
            targets=[_target(1)],
            strategies=[_StaticStrategy(source, "valid")],
            objective="minimize_depth",
        )


def test_nested_metadata_mutation_is_revalidated_at_serialization() -> None:
    nested: dict[str, object] = {"label": "safe"}
    source = CircuitIR(
        qubit_count=1,
        operations=Circuit(1).x(0).operations,
        metadata={"nested": nested},
    )
    decision = plan(
        source,
        targets=[_target(1)],
        strategies=[_StaticStrategy(source, "valid")],
        objective="minimize_depth",
    )

    nested["credentials"] = "canary"

    with pytest.raises(ValueError, match="Secret-bearing field"):
        decision.to_json()


def test_plan_rejects_non_winner_selection_and_tampered_ranking() -> None:
    source = Circuit(1).x(0)
    decision = plan(
        source,
        targets=[_target(1)],
        strategies=[
            _StaticStrategy(source.ir, "winner"),
            _StaticStrategy(Circuit(1).x(0).h(0).ir, "loser"),
        ],
        objective="minimize_depth",
    )
    loser = next(item for item in decision.candidates if item.rank == 2)

    with pytest.raises(ValueError, match="rank-one"):
        Plan(
            program=decision.program,
            objective=decision.objective,
            candidates=decision.candidates,
            selected_candidate_id=loser.candidate_id,
        )

    tampered = tuple(
        replace(item, score=item.score + 1) if item.rank == 1 and item.score is not None else item
        for item in decision.candidates
    )
    with pytest.raises(ValueError, match="ranking evidence"):
        Plan(
            program=decision.program,
            objective=decision.objective,
            candidates=tampered,
            selected_candidate_id=decision.selected_candidate_id,
        )


def test_manifest_rejects_mismatched_plan_hash_and_target_set() -> None:
    source = Circuit(1).x(0)
    decision = plan(
        source,
        targets=[_target(1)],
        strategies=[_StaticStrategy(source.ir, "valid")],
        objective="minimize_depth",
    )
    manifest = decision.manifest

    with pytest.raises(ValueError, match="reconstructed Plan"):
        replace(manifest, selected_plan_hash="sha256:" + "0" * 64)

    extra_target = Target(
        "extra-target",
        Topology.complete(1),
        (InstructionSupport("x", 1),),
    )
    with pytest.raises(ValueError, match="exactly match"):
        replace(manifest, targets=(*manifest.targets, extra_target))


def test_qcore_native_strategy_reports_routing_provenance_and_known_swaps() -> None:
    circuit = Circuit(3).h(0).cx(0, 2)
    target = _target(
        3,
        topology=Topology.line(3),
        instruction_errors={"h": 0.001, "x": 0.001, "rz": 0.0001, "cx": 0.01},
    )
    decision = plan(
        circuit,
        targets=[target],
        strategies=[
            QCoreNativeStrategy(
                CompileOptions(
                    optimization_level=2,
                    initial_layout=Layout.identity(3),
                    placement_trials=1,
                )
            )
        ],
        objective=Objective.minimize("inserted_swap_count"),
    )

    assert decision.selected.metrics is not None
    assert decision.selected.metrics.inserted_swap_count is not None
    assert decision.selected.provenance["compiler"] == "qplanck.native"
    assert decision.selected.validation_evidence == (
        "strategy_reported_semantic_equivalence",
        "all_final_operations_supported_by_target_snapshot",
    )


def test_default_portfolio_is_offline_deterministic_and_records_two_strategies() -> None:
    circuit = Circuit(5).cx(0, 4).cx(1, 3).cx(4, 2)
    target = _target(
        5,
        topology=Topology.line(5),
        instruction_errors={"h": 0.001, "x": 0.001, "rz": 0.0001, "cx": 0.01},
    )

    decision = plan(
        circuit,
        targets=[target],
        objective=Objective.minimize("inserted_swap_count"),
    )

    assert {item.strategy_id for item in decision.candidates} == {
        "qcore-native.adaptive",
        "qcore-native.identity-baseline",
    }
    assert all(item.disposition is CandidateDisposition.VALID for item in decision.candidates)
    metrics_by_strategy = {item.strategy_id: item.metrics for item in decision.candidates}
    assert metrics_by_strategy["qcore-native.adaptive"] is not None
    assert metrics_by_strategy["qcore-native.identity-baseline"] is not None
    assert metrics_by_strategy["qcore-native.adaptive"].inserted_swap_count == 0
    assert metrics_by_strategy["qcore-native.identity-baseline"].inserted_swap_count > 0
    assert decision.selected.strategy_id == "qcore-native.adaptive"
    assert "offline-planning-only" in decision.manifest.to_json()
