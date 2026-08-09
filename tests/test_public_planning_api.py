from __future__ import annotations

import qplanck


def test_top_level_planning_api_runs_the_default_offline_portfolio() -> None:
    circuit = qplanck.Circuit(3).h(0).cx(0, 2).measure_all()
    target = qplanck.Target.testing(
        3,
        topology=qplanck.Topology.line(3),
        basis_gates=frozenset({"h", "x", "rz", "cx"}),
        target_id="public-api-offline",
    )

    decision = qplanck.plan(
        circuit,
        targets=[target],
        objective="minimize_depth",
    )

    assert isinstance(decision, qplanck.Plan)
    assert isinstance(decision.program, qplanck.Program)
    assert isinstance(decision.manifest, qplanck.Manifest)
    assert decision.selected.rank == 1
    assert "no remote execution occurred" in str(decision.explain())


def test_top_level_qiskit_portfolio_builder_exposes_all_default_levels() -> None:
    strategies = qplanck.qiskit_strategies(seed=17)

    assert [item.optimization_level for item in strategies] == [0, 1, 2, 3]
    assert all(isinstance(item, qplanck.QiskitCompilerStrategy) for item in strategies)
    assert all(item.seed == 17 for item in strategies)
