from __future__ import annotations

import json
import math
from dataclasses import dataclass
from importlib import metadata
from typing import Any

import pytest

from qplanck.errors import TargetError
from qplanck.ibm import IBM_TARGET_METADATA_SCHEMA_VERSION, target_from_ibm_backend
from qplanck.targets import LimitKind, Target


@dataclass
class FakeInstructionProperties:
    error: float | None = None
    duration: float | None = None


@dataclass
class FakeQubitProperties:
    t1: float | None = None
    t2: float | None = None
    frequency: float | None = None


class FakeProviderTarget:
    def __init__(
        self,
        width: int,
        instructions: dict[str, dict[tuple[int, ...] | None, object]],
        *,
        dt: float | None = None,
        qubit_properties: list[object | None] | None = None,
    ) -> None:
        self.num_qubits = width
        self._instructions = instructions
        self.operation_names = tuple(instructions)
        self.dt = dt
        self.qubit_properties = qubit_properties

    def __getitem__(self, name: str) -> dict[tuple[int, ...] | None, object]:
        return self._instructions[name]


class FakeCouplingMap:
    def __init__(self, edges: list[tuple[int, int]], *, symmetric: bool) -> None:
        self._edges = edges
        self.is_symmetric = symmetric

    def get_edges(self) -> list[tuple[int, int]]:
        return list(self._edges)


class FakeBackend:
    def __init__(
        self,
        target: FakeProviderTarget,
        *,
        name: str = "fake_sherbrooke",
        backend_version: str | None = "2.4.1",
        coupling_map: object = None,
        dt: float | None = None,
        max_shots: int | None = None,
        max_circuits: int | None = None,
    ) -> None:
        self.target = target
        self.num_qubits = target.num_qubits
        self.name = name
        self.backend_version = backend_version
        self.coupling_map = coupling_map
        self.dt = dt
        self.max_shots = max_shots
        self.max_circuits = max_circuits

    @property
    def provider(self) -> object:
        raise AssertionError("provider SDK objects must not be inspected")

    @property
    def credentials(self) -> object:
        raise AssertionError("credentials must not be inspected")


def rich_backend() -> FakeBackend:
    target = FakeProviderTarget(
        3,
        {
            "x": {
                (0,): FakeInstructionProperties(0.001, 3.5e-8),
                (1,): FakeInstructionProperties(0.002, 3.6e-8),
                (2,): FakeInstructionProperties(None, 3.7e-8),
            },
            "rz": {
                (0,): FakeInstructionProperties(0.0, 0.0),
                (1,): FakeInstructionProperties(0.0, 0.0),
                (2,): FakeInstructionProperties(0.0, 0.0),
            },
            "cx": {
                (0, 1): FakeInstructionProperties(0.012, 3.0e-7),
                (1, 2): FakeInstructionProperties(0.018, 3.2e-7),
            },
            "measure": {
                (0,): FakeInstructionProperties(0.03, 8.0e-7),
                (1,): FakeInstructionProperties(0.04, 8.1e-7),
                (2,): FakeInstructionProperties(0.05, 8.2e-7),
            },
            "ecr": {(0, 1): FakeInstructionProperties(0.02, 3.1e-7)},
        },
        qubit_properties=[
            FakeQubitProperties(1.0e-4, 8.0e-5, 5.0e9),
            FakeQubitProperties(1.1e-4, 8.5e-5, 5.1e9),
            FakeQubitProperties(1.2e-4, 9.0e-5, 5.2e9),
        ],
    )
    return FakeBackend(
        target,
        coupling_map=FakeCouplingMap([(0, 1), (1, 2)], symmetric=False),
        dt=2.22e-10,
        max_shots=100_000,
        max_circuits=300,
    )


def test_normalizes_backend_capabilities_and_calibration_evidence() -> None:
    result = target_from_ibm_backend(rich_backend(), captured_at="2026-08-09T12:34:56+01:00")

    assert result.target_id == "ibm:fake_sherbrooke"
    assert result.provider == "ibm"
    assert result.model == "fake_sherbrooke"
    assert result.snapshot_id is not None and result.snapshot_id.startswith("sha256:")
    assert result.qubit_count == 3
    assert result.topology.directed is True
    assert result.topology.edges == ((0, 1), (1, 2))
    assert result.basis_gates == frozenset({"x", "rz", "cx"})
    assert result.instruction("cx") is not None
    assert result.instruction("cx").locations == ((0, 1), (1, 2))  # type: ignore[union-attr]
    assert result.limits.max_shots.value == 100_000
    assert result.limits.max_circuits_per_job.value == 300

    payload = result.to_dict()
    metadata_payload = payload["metadata"]
    assert metadata_payload["schema_version"] == IBM_TARGET_METADATA_SCHEMA_VERSION
    assert metadata_payload["snapshot"]["captured_at"] == "2026-08-09T11:34:56.000000Z"
    assert metadata_payload["declared"]["dt_seconds"] == 2.22e-10
    assert metadata_payload["declared"]["excluded_operations"] == ["ecr", "measure"]
    assert metadata_payload["instruction_errors"] == {
        "cx:0,1": 0.012,
        "cx:1,2": 0.018,
        "rz:0": 0.0,
        "rz:1": 0.0,
        "rz:2": 0.0,
        "x:0": 0.001,
        "x:1": 0.002,
    }
    assert metadata_payload["calibrated"]["qubits"][1] == {
        "qubit": 1,
        "t1_seconds": 1.1e-4,
        "t2_seconds": 8.5e-5,
        "frequency_hz": 5.1e9,
        "readout_error_probability": 0.04,
    }
    assert metadata_payload["observed"]["available"] is False


def test_fixed_timestamp_is_deterministic_and_round_trips() -> None:
    first = target_from_ibm_backend(rich_backend(), captured_at="2026-08-09T00:00:00Z")
    second = target_from_ibm_backend(rich_backend(), captured_at="2026-08-09T00:00:00Z")

    assert first.to_json() == second.to_json()
    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash
    restored = Target.from_dict(first.to_dict())
    assert restored.to_dict() == first.to_dict()
    assert restored.content_hash == first.content_hash


def test_partial_data_remains_explicitly_unknown_not_zero() -> None:
    target = FakeProviderTarget(
        2,
        {
            "h": {(0,): FakeInstructionProperties(), (1,): FakeInstructionProperties()},
            "cx": {(0, 1): FakeInstructionProperties()},
        },
    )
    backend = FakeBackend(
        target,
        backend_version=None,
        coupling_map=FakeCouplingMap([(0, 1)], symmetric=False),
    )
    result = target_from_ibm_backend(backend, captured_at="2026-08-09T00:00:00Z")
    data = result.to_dict()["metadata"]

    assert data["instruction_errors"] == {}
    assert data["calibrated"]["instructions"][0]["error_probability"] is None
    assert "calibrated.instructions.cx:0,1.error_probability" in data["unknown_fields"]
    assert "declared.dt_seconds" in data["unknown_fields"]
    assert "identity.backend_version" in data["unknown_fields"]
    assert result.limits.max_shots.kind is LimitKind.UNKNOWN
    assert result.limits.max_circuits_per_job.kind is LimitKind.UNKNOWN


def test_global_support_uses_gate_wide_error_key_and_complete_topology() -> None:
    target = FakeProviderTarget(
        2,
        {
            "x": {None: FakeInstructionProperties(0.001, 3e-8)},
            "cz": {None: FakeInstructionProperties(0.02, 4e-7)},
        },
    )
    backend = FakeBackend(target, coupling_map=None)
    result = target_from_ibm_backend(backend, captured_at="2026-08-09T00:00:00Z")

    assert result.topology == result.topology.complete(2)
    assert result.instruction("cz").locations is None  # type: ignore[union-attr]
    assert result.to_dict()["metadata"]["instruction_errors"] == {"cz": 0.02, "x": 0.001}


def test_bidirectional_edge_list_infers_undirected_topology_without_symmetry_flag() -> None:
    target = FakeProviderTarget(
        2,
        {
            "x": {
                (0,): FakeInstructionProperties(),
                (1,): FakeInstructionProperties(),
            },
            "cx": {
                (0, 1): FakeInstructionProperties(),
                (1, 0): FakeInstructionProperties(),
            },
        },
    )
    backend = FakeBackend(target, coupling_map=[(0, 1), (1, 0)])

    result = target_from_ibm_backend(backend, captured_at="2026-08-09T00:00:00Z")

    assert result.topology.directed is False
    assert result.topology.edges == ((0, 1),)


def test_snapshot_is_json_only_and_does_not_inspect_provider_or_credentials() -> None:
    result = target_from_ibm_backend(rich_backend(), captured_at="2026-08-09T00:00:00Z")
    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert "credentials" in encoded  # appears only in the explicit exclusion policy
    assert "FakeInstructionProperties" not in encoded
    assert "FakeQubitProperties" not in encoded
    assert "FakeBackend" not in encoded
    assert "secret" not in encoded.lower()


def test_optional_sdk_distributions_are_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr("qplanck.ibm.metadata.version", unavailable)
    result = target_from_ibm_backend(rich_backend(), captured_at="2026-08-09T00:00:00Z")
    data = result.to_dict()["metadata"]

    assert data["source_versions"] == {
        "qplanck": None,
        "qiskit": None,
        "qiskit_ibm_runtime": None,
    }
    assert "source_versions.qiskit_ibm_runtime" in data["unknown_fields"]


@pytest.mark.parametrize(
    ("backend", "message"),
    [
        (
            FakeBackend(FakeProviderTarget(0, {"x": {None: FakeInstructionProperties()}})),
            "num_qubits",
        ),
        (
            FakeBackend(FakeProviderTarget(2, {"measure": {(0,): object()}})),
            "no operations supported",
        ),
        (
            FakeBackend(
                FakeProviderTarget(2, {"x": {(0,): FakeInstructionProperties()}}),
                coupling_map=None,
            ),
            "topology is unknown",
        ),
        (
            FakeBackend(
                FakeProviderTarget(
                    2,
                    {"cx": {(0, 2): FakeInstructionProperties()}},
                ),
                coupling_map=FakeCouplingMap([(0, 1)], symmetric=False),
            ),
            "outside the target",
        ),
        (
            FakeBackend(
                FakeProviderTarget(
                    2,
                    {"cx": {(0, 1): FakeInstructionProperties(math.nan, 1.0)}},
                ),
                coupling_map=FakeCouplingMap([(0, 1)], symmetric=False),
            ),
            "must be finite",
        ),
    ],
)
def test_malformed_backend_capabilities_fail_closed(backend: object, message: str) -> None:
    with pytest.raises(TargetError, match=message):
        target_from_ibm_backend(backend, captured_at="2026-08-09T00:00:00Z")


@pytest.mark.parametrize("captured_at", ["not-a-date", "2026-08-09T00:00:00", object()])
def test_invalid_snapshot_timestamp_fails_closed(captured_at: Any) -> None:
    with pytest.raises(TargetError, match="captured_at"):
        target_from_ibm_backend(rich_backend(), captured_at=captured_at)
