from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from qplanck.pulse import DriveChannel
from qplanck.targets import Target

from qplanck_braket import (
    BraketCapabilityError,
    BraketChannelMap,
    BraketPulseDevice,
    BraketPulseSnapshot,
    BraketSnapshotMismatchError,
)


def test_snapshot_is_canonical_and_redacts_presigned_query(
    capabilities: dict[str, object],
) -> None:
    first = BraketPulseSnapshot.from_capabilities(
        "arn:aws:braket:us-west-1::device/qpu/rigetti/Cepheus-1-108Q",
        capabilities,
        captured_at="2026-07-14T00:00:00+00:00",
    )
    second = BraketPulseSnapshot.from_capabilities(
        first.device_arn,
        capabilities,
        captured_at="2026-07-15T00:00:00+00:00",
    )

    assert first.snapshot_hash == second.snapshot_hash
    assert first.calibration_reference == "https://example.invalid/calibrations.json"
    assert "X-Amz-Signature" not in first.to_json()
    assert [port.port_id for port in first.ports] == ["q0_rf", "q0_rx", "q1_rf"]


def test_snapshot_hash_changes_with_port_timing(capabilities: dict[str, object]) -> None:
    changed = deepcopy(capabilities)
    changed["pulse"]["ports"]["q0_rf"]["dt"] = 2e-9  # type: ignore[index]
    first = BraketPulseSnapshot.from_capabilities("arn:test", capabilities)
    second = BraketPulseSnapshot.from_capabilities("arn:test", changed)
    assert first.snapshot_hash != second.snapshot_hash


def test_snapshot_rejects_frames_on_unknown_ports(capabilities: dict[str, object]) -> None:
    changed = deepcopy(capabilities)
    changed["pulse"]["frames"]["q0_drive"]["portId"] = "missing"  # type: ignore[index]
    with pytest.raises(BraketCapabilityError, match="unknown ports"):
        BraketPulseSnapshot.from_capabilities("arn:test", changed)


def test_channel_map_requires_predefined_unique_ports(snapshot: BraketPulseSnapshot) -> None:
    mapping = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    assert mapping[DriveChannel(0)].port_id == "q0_rf"

    with pytest.raises(BraketCapabilityError, match="not predefined"):
        BraketChannelMap.from_mapping({DriveChannel(0): "invented"}, snapshot=snapshot)

    with pytest.raises(BraketCapabilityError, match="may be bound only once"):
        BraketChannelMap.from_mapping(
            {DriveChannel(0): "q0_drive", DriveChannel(1): "q0_drive"},
            snapshot=snapshot,
        )


def test_channel_map_is_bound_to_snapshot(
    snapshot: BraketPulseSnapshot,
    capabilities: dict[str, object],
) -> None:
    mapping = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    changed = deepcopy(capabilities)
    changed["pulse"]["validationParameters"]["MAX_AMPLITUDE"] = 0.5  # type: ignore[index]
    newer = BraketPulseSnapshot.from_capabilities(snapshot.device_arn, changed)
    with pytest.raises(BraketSnapshotMismatchError, match="different"):
        mapping.validate_snapshot(newer)


def test_channel_map_rejects_mixed_sample_periods(
    capabilities: dict[str, object],
) -> None:
    changed = deepcopy(capabilities)
    changed["pulse"]["ports"]["q1_rf"]["dt"] = 2e-9  # type: ignore[index]
    snapshot = BraketPulseSnapshot.from_capabilities("arn:test", changed)
    with pytest.raises(BraketCapabilityError, match="share one dt"):
        BraketChannelMap.from_mapping(
            {DriveChannel(0): "q0_drive", DriveChannel(1): "q1_drive"},
            snapshot=snapshot,
        )


def test_device_derives_compiler_target_from_same_capabilities(
    capabilities: dict[str, object],
) -> None:
    provider = SimpleNamespace(
        arn="arn:aws:braket:us-west-1::device/qpu/rigetti/Cepheus-1-108Q",
        properties=capabilities,
        provider_name="Rigetti",
        name="Cepheus-1-108Q",
    )
    device = BraketPulseDevice.from_aws_device(provider, refresh_calibrations=False)
    assert device.target.qubit_count == 2
    assert device.target.basis_gates == frozenset({"rx", "cz"})
    assert device.target.topology.edges == ((0, 1),)
    assert device.target.limits.max_shots.value == 10_000
    assert device.target.pulse_profile_hash == device.snapshot.snapshot_hash

    with pytest.raises(BraketCapabilityError, match="does not match"):
        BraketPulseDevice.from_aws_device(
            provider,
            target=Target.testing(2),
            refresh_calibrations=False,
        )
