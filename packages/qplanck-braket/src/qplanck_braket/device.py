"""Braket device wrapper that owns no credentials and preserves capability identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from qplanck.circuit import SUPPORTED_GATES
from qplanck.targets import (
    InstructionSupport,
    Target,
    TargetLimit,
    TargetLimits,
    Topology,
)

from .errors import BraketCapabilityError, BraketSnapshotMismatchError
from .snapshot import BraketPulseSnapshot


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _calibration_digest(calibrations: object) -> str:
    if calibrations is None:
        payload = b"none"
    else:
        sequences = getattr(calibrations, "pulse_sequences", None)
        if not isinstance(sequences, Mapping):
            raise BraketCapabilityError(
                "Braket native gate calibrations do not expose pulse_sequences."
            )
        entries = []
        for key, sequence in sequences.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise BraketCapabilityError("Braket native calibration key is invalid.")
            to_ir = getattr(sequence, "to_ir", None)
            if not callable(to_ir):
                raise BraketCapabilityError(
                    "Braket native gate calibration does not expose OpenPulse IR."
                )
            gate, qubits = key
            entries.append(
                {
                    "gate": repr(gate),
                    "qubits": [int(qubit) for qubit in qubits],
                    "pulse_ir": str(to_ir()),
                }
            )
        payload = json.dumps(
            sorted(entries, key=lambda item: (item["gate"], item["qubits"])),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    return hashlib.sha256(payload).hexdigest()


def _refresh_calibration_digest(provider_device: Any) -> str:
    refresh = getattr(provider_device, "refresh_gate_calibrations", None)
    if not callable(refresh):
        raise BraketCapabilityError("Provider device cannot refresh native gate calibrations.")
    try:
        calibrations = refresh()
    except Exception as error:
        raise BraketCapabilityError(
            f"Braket native calibration refresh failed ({type(error).__name__})."
        ) from None
    return _calibration_digest(calibrations)


def _openqasm_action(properties: object) -> object:
    actions = _field(properties, "action", {}) or {}
    if not isinstance(actions, Mapping):
        raise BraketCapabilityError("Braket device action capabilities must be a mapping.")
    for key, value in actions.items():
        if "openqasm" in str(key).lower():
            return value
    raise BraketCapabilityError("Braket device does not advertise an OpenQASM action.")


def target_from_aws_device(
    provider_device: Any,
    *,
    pulse_snapshot: BraketPulseSnapshot,
) -> Target:
    """Derive the exact provider-neutral compiler target from Braket metadata."""

    properties = getattr(provider_device, "properties", None)
    arn = getattr(provider_device, "arn", None)
    if properties is None or not isinstance(arn, str):
        raise BraketCapabilityError("Expected an initialized braket.aws.AwsDevice.")
    paradigm = _field(properties, "paradigm")
    if paradigm is None:
        raise BraketCapabilityError("Braket device does not advertise a gate-model paradigm.")
    qubit_count = int(_field(paradigm, "qubitCount"))
    connectivity = _field(paradigm, "connectivity")
    if connectivity is None:
        raise BraketCapabilityError("Braket device does not advertise connectivity.")
    fully_connected = bool(_field(connectivity, "fullyConnected", False))
    if fully_connected:
        topology = Topology.complete(qubit_count)
    else:
        graph = _field(connectivity, "connectivityGraph", {}) or {}
        if not isinstance(graph, Mapping):
            raise BraketCapabilityError("Braket connectivity graph must be a mapping.")
        edges: set[tuple[int, int]] = set()
        for raw_source, raw_targets in graph.items():
            if not isinstance(raw_targets, list | tuple):
                raise BraketCapabilityError("Braket connectivity adjacency must be a list.")
            source = int(raw_source)
            for raw_target in raw_targets:
                target = int(raw_target)
                edges.add((min(source, target), max(source, target)))
        topology = Topology(qubit_count, tuple(sorted(edges)), directed=False)

    action = _openqasm_action(properties)
    raw_operations = _field(action, "supportedOperations", ()) or ()
    operation_names = {
        "cx" if str(name).lower() == "cnot" else str(name).lower() for name in raw_operations
    }
    raw_native_gates = _field(paradigm, "nativeGateSet", ()) or ()
    if raw_native_gates:
        native_names = {
            "cx" if str(name).lower() == "cnot" else str(name).lower() for name in raw_native_gates
        }
        operation_names.intersection_update(native_names)
    supported = sorted(operation_names.intersection(SUPPORTED_GATES))
    if not supported:
        raise BraketCapabilityError("Braket OpenQASM action has no QPlanck-compatible gates.")
    instructions = tuple(
        InstructionSupport(name, SUPPORTED_GATES[name].qubits) for name in supported
    )

    maximum_shots: list[int] = []
    for result_type in _field(action, "supportedResultTypes", ()) or ():
        maximum = _field(result_type, "maxShots")
        if maximum is not None:
            maximum_shots.append(int(maximum))
    max_shots = TargetLimit.exact(max(maximum_shots)) if maximum_shots else TargetLimit()
    header = _field(properties, "braketSchemaHeader")
    header_name = _field(header, "name")
    header_version = _field(header, "version")
    snapshot_id = (
        f"{header_name}@{header_version}"
        if header_name is not None and header_version is not None
        else None
    )
    return Target(
        target_id=arn,
        topology=topology,
        instructions=instructions,
        provider=str(getattr(provider_device, "provider_name", "Amazon Braket")),
        model=str(getattr(provider_device, "name", arn.rsplit("/", 1)[-1])),
        snapshot_id=snapshot_id,
        pulse_profile_hash=pulse_snapshot.snapshot_hash,
        limits=TargetLimits(max_shots=max_shots),
        metadata={"device_arn": arn, "pulse_supported": True},
    )


def _content_hash(target: object) -> str:
    value = getattr(target, "content_hash", None)
    if callable(value):
        value = value()
    if not isinstance(value, str):
        raise BraketCapabilityError("BraketPulseDevice target must expose a SHA-256 content_hash.")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
        raise BraketCapabilityError("BraketPulseDevice target must expose a SHA-256 content_hash.")
    return value


@dataclass
class BraketPulseDevice:
    """An initialized SDK device plus exact QPlanck target and pulse snapshots.

    Constructing this wrapper never creates credentials or a network client. The
    caller supplies an initialized provider device, whose ambient AWS SDK session
    remains solely responsible for authentication.
    """

    provider_device: Any
    target: Target
    snapshot: BraketPulseSnapshot
    snapshot_loader: Callable[[Any], BraketPulseSnapshot] = field(
        default=BraketPulseSnapshot.from_aws_device,
        repr=False,
    )
    target_loader: Callable[[Any, BraketPulseSnapshot], Target] | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if getattr(self.provider_device, "arn", None) != self.snapshot.device_arn:
            raise BraketCapabilityError("Provider device ARN does not match pulse snapshot.")
        if not isinstance(self.target, Target):
            raise BraketCapabilityError("BraketPulseDevice target must be a qplanck Target.")
        _content_hash(self.target)
        if not callable(self.snapshot_loader):
            raise BraketCapabilityError("snapshot_loader must be callable.")

    @classmethod
    def from_aws_device(
        cls,
        provider_device: Any,
        *,
        target: Target | None = None,
        refresh_calibrations: bool = True,
    ) -> BraketPulseDevice:
        calibration_digest = (
            _refresh_calibration_digest(provider_device) if refresh_calibrations else None
        )
        snapshot = BraketPulseSnapshot.from_aws_device(
            provider_device,
            calibration_digest=calibration_digest,
        )
        derived_target = target_from_aws_device(provider_device, pulse_snapshot=snapshot)
        if target is not None and target.content_hash != derived_target.content_hash:
            raise BraketCapabilityError(
                "Provided target does not match the current Amazon Braket device capabilities."
            )

        def load_snapshot(current: Any) -> BraketPulseSnapshot:
            digest = _refresh_calibration_digest(current) if refresh_calibrations else None
            return BraketPulseSnapshot.from_aws_device(current, calibration_digest=digest)

        return cls(
            provider_device=provider_device,
            target=derived_target,
            snapshot=snapshot,
            snapshot_loader=load_snapshot,
            target_loader=lambda current, current_snapshot: target_from_aws_device(
                current,
                pulse_snapshot=current_snapshot,
            ),
        )

    @property
    def arn(self) -> str:
        return self.snapshot.device_arn

    @property
    def target_hash(self) -> str:
        return _content_hash(self.target)

    @property
    def frames(self) -> Mapping[str, Any]:
        try:
            frames = getattr(self.provider_device, "frames", None)
        except Exception as error:
            raise BraketCapabilityError(
                f"Braket frame refresh failed ({type(error).__name__})."
            ) from None
        if not isinstance(frames, Mapping):
            raise BraketCapabilityError("Initialized Braket device did not expose frame metadata.")
        return frames

    def refresh_snapshot(self) -> BraketPulseSnapshot:
        """Refresh provider metadata once and return a new immutable snapshot."""

        refresh = getattr(self.provider_device, "refresh_metadata", None)
        if not callable(refresh):
            raise BraketCapabilityError("Provider device cannot refresh capability metadata.")
        try:
            refresh()
            return self.snapshot_loader(self.provider_device)
        except BraketCapabilityError:
            raise
        except Exception as error:
            raise BraketCapabilityError(
                f"Braket capability refresh failed ({type(error).__name__})."
            ) from None

    def assert_submission_snapshot(
        self,
        *,
        expected_target_hash: str,
        expected_pulse_snapshot_hash: str,
    ) -> BraketPulseSnapshot:
        if expected_target_hash != self.target_hash:
            raise BraketSnapshotMismatchError(
                "Compiled circuit target hash does not match the Braket backend target."
            )
        refreshed = self.refresh_snapshot()
        if refreshed.snapshot_hash != expected_pulse_snapshot_hash:
            raise BraketSnapshotMismatchError(
                "Braket pulse capabilities or calibration identity changed before submission."
            )
        if self.target_loader is not None:
            refreshed_target = self.target_loader(self.provider_device, refreshed)
            if refreshed_target.content_hash != expected_target_hash:
                raise BraketSnapshotMismatchError(
                    "Braket circuit target capabilities changed before submission."
                )
        return refreshed


__all__ = ["BraketPulseDevice", "target_from_aws_device"]
