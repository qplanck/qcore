from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import Any

import pytest

from qplanck.circuit import Circuit
from qplanck.planning import (
    CompilerStrategy,
    Program,
    StrategyUnavailableError,
    StrategyUnsupportedError,
)
from qplanck.qiskit_strategy import QiskitCompilerStrategy, qiskit_strategies
from qplanck.targets import Target, Topology

pytest.importorskip("qiskit")


def target(
    qubits: int,
    *,
    topology: Topology | None = None,
    basis: frozenset[str] = frozenset({"h", "x", "cx", "swap"}),
) -> Target:
    return Target.testing(
        qubits,
        topology=topology or Topology.complete(qubits),
        basis_gates=basis,
        target_id=f"ibm:fake-{qubits}",
    )


@pytest.mark.parametrize("optimization_level", range(4))
def test_all_optimization_levels_produce_equivalent_target_conformant_artifacts(
    optimization_level: int,
) -> None:
    program = Program.from_input(Circuit(2).h(0).cx(0, 1).measure_all())
    selected_target = target(2)
    strategy = QiskitCompilerStrategy(optimization_level=optimization_level, seed=7)

    assert isinstance(strategy, CompilerStrategy)
    result = strategy.run(program, selected_target)

    assert result.semantic_equivalent is True
    assert sorted(item.cbit for item in result.artifact.measurements) == [0, 1]
    assert all(
        selected_target.supports_operation(operation) for operation in result.artifact.operations
    )
    assert result.provenance["compiler"] == "qiskit.transpile"
    assert result.provenance["compiler_version"] == metadata.version("qiskit")
    assert result.provenance["effective_options"]["optimization_level"] == optimization_level
    assert result.provenance["effective_options"]["seed_transpiler"] == 7
    assert result.provenance["semantic_validation"]["equivalent"] is True


def test_routing_records_only_explicit_inserted_swaps() -> None:
    program = Program.from_input(Circuit(3).cx(0, 1).cx(1, 2).cx(0, 2).measure_all())
    selected_target = target(3, topology=Topology.line(3))

    result = QiskitCompilerStrategy(optimization_level=1, seed=0).run(program, selected_target)

    assert result.semantic_equivalent is True
    assert result.inserted_swap_count == 1
    assert result.inserted_swap_unknown_reason is None
    assert sum(operation.name == "swap" for operation in result.artifact.operations) == 1


def test_absent_explicit_swap_is_unknown_not_zero() -> None:
    program = Program.from_input(Circuit(2).h(0).cx(0, 1).measure_all())

    result = QiskitCompilerStrategy().run(program, target(2))

    assert result.inserted_swap_count is None
    assert result.inserted_swap_unknown_reason is not None
    assert "no explicit SWAP" in result.inserted_swap_unknown_reason


def test_nontrivial_terminal_classical_mapping_is_validated() -> None:
    source = Circuit(3).h(0).cx(0, 2).x(1).measure(2, 4).measure(0, 1)
    program = Program.from_input(source)

    result = QiskitCompilerStrategy(optimization_level=2, seed=9).run(
        program, target(3, topology=Topology.line(3))
    )

    assert result.semantic_equivalent is True
    validation = result.provenance["semantic_validation"]
    assert validation["classical_bits"] == (1, 4)
    assert validation["maximum_probability_delta"] <= 1e-10


def test_output_is_deterministic_for_fixed_seed() -> None:
    program = Program.from_input(Circuit(3).h(0).cx(0, 1).cx(0, 2).measure_all())
    selected_target = target(3, topology=Topology.line(3))
    strategy = QiskitCompilerStrategy(optimization_level=3, seed=123)

    first = strategy.run(program, selected_target)
    second = strategy.run(program, selected_target)

    assert first.artifact.to_json() == second.artifact.to_json()
    assert first.provenance["artifact_hash"] == second.provenance["artifact_hash"]
    assert dict(strategy.options) == {
        "optimization_level": 3,
        "seed_transpiler": 123,
        "layout_method": "sabre",
        "routing_method": "sabre",
        "num_processes": 1,
    }


def test_portfolio_generator_is_deterministic_and_covers_multiple_levels() -> None:
    strategies = qiskit_strategies((3, 0, 3, 1), seed=11)

    assert [item.optimization_level for item in strategies] == [0, 1, 3]
    assert [item.seed for item in strategies] == [11, 11, 11]
    assert len(qiskit_strategies()) == 4
    with pytest.raises(ValueError, match="at least one"):
        qiskit_strategies(())


def test_missing_qiskit_has_clean_optional_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import: Callable[..., Any] = __import__("importlib").import_module

    def unavailable(name: str, package: str | None = None) -> Any:
        if name == "qiskit":
            raise ModuleNotFoundError("simulated missing optional dependency")
        return real_import(name, package)

    monkeypatch.setattr("qplanck.qiskit_strategy.importlib.import_module", unavailable)
    program = Program.from_input(Circuit(1).h(0).measure_all())

    with pytest.raises(StrategyUnavailableError, match=r"qplanck\[qiskit\]") as captured:
        QiskitCompilerStrategy().run(program, target(1))
    assert captured.value.reason_code == "qiskit.dependency_unavailable"


@pytest.mark.parametrize("value", [-1, 4, True, 1.5])
def test_rejects_invalid_optimization_level(value: Any) -> None:
    with pytest.raises(ValueError, match="optimization_level"):
        QiskitCompilerStrategy(optimization_level=value)


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_rejects_invalid_seed(value: Any) -> None:
    with pytest.raises(ValueError, match="seed"):
        QiskitCompilerStrategy(seed=value)


def test_semantic_validation_fails_closed_above_eight_qubits() -> None:
    program = Program.from_input(Circuit(9).x(0).measure(0, 0))

    with pytest.raises(StrategyUnsupportedError, match="8 logical qubits") as captured:
        QiskitCompilerStrategy().run(program, target(9))
    assert captured.value.reason_code == "qiskit.semantic_validation_logical_width_exceeded"


def test_semantic_validation_requires_terminal_measurements() -> None:
    program = Program.from_input(Circuit(1).h(0))

    with pytest.raises(StrategyUnsupportedError, match="terminal measurements") as captured:
        QiskitCompilerStrategy().run(program, target(1))
    assert captured.value.reason_code == "qiskit.semantic_validation_measurements_required"


def test_target_conformance_fails_closed_for_unsupported_qiskit_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qiskit = pytest.importorskip("qiskit")
    original = qiskit.transpile

    def wrong_output(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        output = qiskit.QuantumCircuit(2, 2)
        output.cx(1, 0)
        output.measure([0, 1], [0, 1])
        return output

    monkeypatch.setattr(qiskit, "transpile", wrong_output)
    directed = Target.testing(
        2,
        topology=Topology(2, ((0, 1),), directed=True),
        basis_gates=frozenset({"x", "cx"}),
    )
    program = Program.from_input(Circuit(2).x(0).measure_all())

    with pytest.raises(StrategyUnsupportedError, match="does not conform") as captured:
        QiskitCompilerStrategy().run(program, directed)
    assert captured.value.reason_code == "qiskit.target_conformance_failed"

    monkeypatch.setattr(qiskit, "transpile", original)


def test_semantic_mismatch_is_retained_as_rejection_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qiskit = pytest.importorskip("qiskit")

    def inequivalent_output(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        output = qiskit.QuantumCircuit(1, 1)
        output.x(0)
        output.measure(0, 0)
        return output

    monkeypatch.setattr(qiskit, "transpile", inequivalent_output)
    program = Program.from_input(Circuit(1).h(0).measure_all())
    selected_target = target(1, basis=frozenset({"h", "x"}))

    result = QiskitCompilerStrategy().run(program, selected_target)

    assert result.semantic_equivalent is False
    assert result.diagnostics == (
        "Qiskit output classical marginal did not match the normalized Program.",
    )
    assert result.provenance["semantic_validation"]["equivalent"] is False
