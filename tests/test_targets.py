import json

import pytest

from qplanck import Operation
from qplanck.errors import TargetError
from qplanck.targets import (
    InstructionSupport,
    Layout,
    LimitKind,
    Target,
    TargetLimit,
    TargetLimits,
    Topology,
)


def test_topology_canonical_paths_components_and_hash() -> None:
    topology = Topology(5, ((2, 1), (1, 0), (4, 3), (0, 1)))

    assert topology.edges == ((0, 1), (1, 2), (3, 4))
    assert topology.components == ((0, 1, 2), (3, 4))
    assert topology.shortest_path(2, 0) == (2, 1, 0)
    assert topology.distance(0, 2) == 2
    assert topology.diameter == 2
    assert topology.content_hash == Topology.from_dict(topology.to_dict()).content_hash


def test_topology_factories_are_deterministic() -> None:
    assert Topology.line(4).edges == ((0, 1), (1, 2), (2, 3))
    assert Topology.ring(4).edges == ((0, 1), (0, 3), (1, 2), (2, 3))
    assert Topology.grid(2, 3).edges == ((0, 1), (0, 3), (1, 2), (1, 4), (2, 5), (3, 4), (4, 5))
    assert len(Topology.complete(4).edges) == 6


def test_directed_topology_distinguishes_arcs_from_weak_edges() -> None:
    topology = Topology(3, ((0, 1), (2, 1)), directed=True)

    assert topology.has_arc(0, 1)
    assert not topology.has_arc(1, 0)
    assert topology.has_weak_edge(1, 0)
    assert topology.shortest_path(0, 2) == (0, 1, 2)


def test_topology_rejects_malformed_edges() -> None:
    with pytest.raises(TargetError, match="self-loops"):
        Topology(2, ((0, 0),))
    with pytest.raises(TargetError, match="outside"):
        Topology(2, ((0, 2),))
    with pytest.raises(TargetError, match="at least one"):
        Topology(0)


def test_layout_validation_inverse_and_swap() -> None:
    layout = Layout((2, 0))
    layout.validate(logical_qubits=2, physical_qubits=4)

    assert layout.inverse(4) == (1, None, 0, None)
    assert layout.swap_physical(0, 1).logical_to_physical == (2, 1)
    assert json.loads(json.dumps(layout.to_dict()))["logical_to_physical"] == [2, 0]

    with pytest.raises(TargetError, match="unique"):
        Layout((0, 0))
    with pytest.raises(TargetError, match="requires 3"):
        layout.validate(logical_qubits=3, physical_qubits=4)


def test_target_supports_directional_and_symmetric_instructions() -> None:
    target = Target(
        "directed",
        Topology(3, ((0, 1), (1, 2)), directed=True),
        (
            InstructionSupport("h", 1),
            InstructionSupport("cx", 2),
            InstructionSupport("cz", 2),
            InstructionSupport("swap", 2),
        ),
    )

    assert target.supports_operation(Operation("cx", (0, 1)))
    assert not target.supports_operation(Operation("cx", (1, 0)))
    assert target.supports_operation(Operation("cz", (1, 0)))
    assert target.supports_operation(Operation("swap", (2, 1)))
    assert not target.supports_operation(Operation("cx", (0, 2)))


def test_target_hash_and_explicit_limit_states() -> None:
    limits = TargetLimits(
        max_shots=TargetLimit.exact(50_000),
        max_circuits_per_job=TargetLimit.unlimited(),
    )
    target = Target.testing(3, target_id="stable")
    with_limits = Target(
        target.target_id,
        target.topology,
        target.instructions,
        limits=limits,
    )

    assert with_limits.content_hash == with_limits.content_hash
    assert with_limits.limits.max_shots.value == 50_000
    assert with_limits.limits.max_circuits_per_job.kind is LimitKind.UNLIMITED
    assert with_limits.limits.max_payload_bytes.kind is LimitKind.UNKNOWN


def test_target_artifact_round_trip_and_deep_immutability() -> None:
    target = Target(
        "roundtrip",
        Topology.line(3),
        (
            InstructionSupport("h", 1, ((0,), (1,), (2,))),
            InstructionSupport("cx", 2),
        ),
        provider="example",
        snapshot_id="snapshot-1",
        limits=TargetLimits(max_shots=TargetLimit.exact(100)),
        metadata={"nested": {"labels": ["a", "b"]}},
    )

    restored = Target.from_dict(json.loads(target.to_json()))

    assert restored.to_dict() == target.to_dict()
    assert restored.content_hash == target.content_hash
    with pytest.raises(TypeError):
        target.metadata["nested"]["labels"] = ("changed",)


def test_testing_target_rejects_inconsistent_or_empty_capabilities() -> None:
    with pytest.raises(TargetError, match="match the supplied topology"):
        Target.testing(2, topology=Topology.line(3))
    with pytest.raises(TargetError, match="at least one instruction"):
        Target.testing(2, basis_gates=frozenset())
    with pytest.raises(TargetError, match="Unknown testing target"):
        Target.testing(2, basis_gates=frozenset({"not-a-gate"}))
