"""Immutable, secret-free Amazon Braket pulse capability snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .errors import BraketCapabilityError

BRAKET_PULSE_SNAPSHOT_SCHEMA = "qplanck.braket.pulse-snapshot.v0.1"


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BraketCapabilityError(f"{label} must be a mapping.")
    return value


def _clean_reference(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        raise BraketCapabilityError("Native gate calibration reference must be a string.")
    parts = urlsplit(value.strip())
    if parts.scheme and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return value.split("?", 1)[0]


def _json_scalar(value: object, *, label: str) -> bool | int | float | str | None:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise BraketCapabilityError(f"{label} must be a JSON scalar.")


@dataclass(frozen=True, order=True)
class BraketPort:
    """Secret-free provider port metadata required for safe timing lowering."""

    port_id: str
    dt_seconds: float
    direction: str | None = None
    port_type: str | None = None
    qubits: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.port_id, str) or not self.port_id.strip():
            raise BraketCapabilityError("Braket port ID must be a non-empty string.")
        dt = float(self.dt_seconds)
        if not 0 < dt < float("inf"):
            raise BraketCapabilityError("Braket port dt must be positive and finite.")
        qubits = tuple(int(qubit) for qubit in self.qubits)
        if any(qubit < 0 for qubit in qubits) or len(set(qubits)) != len(qubits):
            raise BraketCapabilityError(
                "Braket port qubit mappings must be unique and non-negative."
            )
        object.__setattr__(self, "port_id", self.port_id.strip())
        object.__setattr__(self, "dt_seconds", dt)
        object.__setattr__(self, "qubits", qubits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "dt_seconds": self.dt_seconds,
            "direction": self.direction,
            "port_type": self.port_type,
            "qubits": list(self.qubits),
        }


@dataclass(frozen=True, order=True)
class BraketFrame:
    """A predefined provider frame captured from device capabilities."""

    frame_id: str
    port_id: str
    frequency_hz: float
    phase: float = 0.0
    associated_gate: str | None = None
    qubits: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.frame_id, str) or not self.frame_id.strip():
            raise BraketCapabilityError("Braket frame ID must be a non-empty string.")
        if not isinstance(self.port_id, str) or not self.port_id.strip():
            raise BraketCapabilityError("Braket frame port ID must be a non-empty string.")
        frequency = float(self.frequency_hz)
        phase = float(self.phase)
        if not abs(frequency) < float("inf") or not abs(phase) < float("inf"):
            raise BraketCapabilityError("Braket frame frequency and phase must be finite.")
        qubits = tuple(int(qubit) for qubit in self.qubits)
        if any(qubit < 0 for qubit in qubits) or len(set(qubits)) != len(qubits):
            raise BraketCapabilityError(
                "Braket frame qubit mappings must be unique and non-negative."
            )
        object.__setattr__(self, "frame_id", self.frame_id.strip())
        object.__setattr__(self, "port_id", self.port_id.strip())
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "qubits", qubits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "port_id": self.port_id,
            "frequency_hz": self.frequency_hz,
            "phase": self.phase,
            "associated_gate": self.associated_gate,
            "qubits": list(self.qubits),
        }


@dataclass(frozen=True)
class BraketPulseSnapshot:
    """Immutable subset of Braket capabilities used during pulse lowering.

    ``captured_at`` is observational and deliberately excluded from
    ``snapshot_hash``. Refreshing unchanged provider metadata therefore produces
    the same semantic identity.
    """

    device_arn: str
    ports: tuple[BraketPort, ...]
    frames: tuple[BraketFrame, ...]
    supported_functions: frozenset[str]
    supported_waveforms: frozenset[str]
    supports_dynamic_frames: bool
    supports_local_pulse_elements: bool
    supports_non_native_gates_with_pulses: bool
    validation_parameters: tuple[tuple[str, bool | int | float | str | None], ...] = ()
    calibration_reference: str | None = None
    calibration_digest: str | None = None
    captured_at: str | None = None
    schema_version: str = BRAKET_PULSE_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != BRAKET_PULSE_SNAPSHOT_SCHEMA:
            raise BraketCapabilityError(
                f"Unsupported Braket pulse snapshot schema: {self.schema_version!r}."
            )
        if not isinstance(self.device_arn, str) or not self.device_arn.strip():
            raise BraketCapabilityError("Braket device ARN must be a non-empty string.")
        ports = tuple(sorted(self.ports))
        frames = tuple(sorted(self.frames))
        port_ids = [port.port_id for port in ports]
        frame_ids = [frame.frame_id for frame in frames]
        if not ports or not frames:
            raise BraketCapabilityError("Braket pulse capabilities must define ports and frames.")
        if len(set(port_ids)) != len(port_ids):
            raise BraketCapabilityError("Braket pulse capabilities contain duplicate port IDs.")
        if len(set(frame_ids)) != len(frame_ids):
            raise BraketCapabilityError("Braket pulse capabilities contain duplicate frame IDs.")
        unknown_ports = sorted({frame.port_id for frame in frames}.difference(port_ids))
        if unknown_ports:
            raise BraketCapabilityError(
                f"Braket frames reference unknown ports: {', '.join(unknown_ports)}."
            )
        functions = frozenset(str(name) for name in self.supported_functions)
        waveforms = frozenset(str(name) for name in self.supported_waveforms)
        if any(not name for name in functions | waveforms):
            raise BraketCapabilityError("Supported Braket functions and waveforms must be named.")
        validation = tuple(sorted(self.validation_parameters))
        if len({key for key, _ in validation}) != len(validation):
            raise BraketCapabilityError("Braket validation parameters contain duplicate names.")
        if self.calibration_digest is not None:
            digest = self.calibration_digest.lower()
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise BraketCapabilityError("Calibration digest must be a SHA-256 hex digest.")
            object.__setattr__(self, "calibration_digest", digest)
        object.__setattr__(self, "device_arn", self.device_arn.strip())
        object.__setattr__(self, "ports", ports)
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "supported_functions", functions)
        object.__setattr__(self, "supported_waveforms", waveforms)
        object.__setattr__(self, "validation_parameters", validation)
        object.__setattr__(
            self, "calibration_reference", _clean_reference(self.calibration_reference)
        )

    @property
    def snapshot_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(include_observational=False),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def port_by_id(self) -> dict[str, BraketPort]:
        return {port.port_id: port for port in self.ports}

    @property
    def frame_by_id(self) -> dict[str, BraketFrame]:
        return {frame.frame_id: frame for frame in self.frames}

    def to_dict(self, *, include_observational: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "device_arn": self.device_arn,
            "ports": [port.to_dict() for port in self.ports],
            "frames": [frame.to_dict() for frame in self.frames],
            "supported_functions": sorted(self.supported_functions),
            "supported_waveforms": sorted(self.supported_waveforms),
            "supports_dynamic_frames": self.supports_dynamic_frames,
            "supports_local_pulse_elements": self.supports_local_pulse_elements,
            "supports_non_native_gates_with_pulses": self.supports_non_native_gates_with_pulses,
            "validation_parameters": dict(self.validation_parameters),
            "calibration_reference": self.calibration_reference,
            "calibration_digest": self.calibration_digest,
        }
        if include_observational:
            data["captured_at"] = self.captured_at
            data["snapshot_hash"] = self.snapshot_hash
        return data

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), allow_nan=False, indent=indent, sort_keys=True)

    @classmethod
    def from_capabilities(
        cls,
        device_arn: str,
        capabilities: object,
        *,
        calibration_digest: str | None = None,
        captured_at: str | None = None,
    ) -> BraketPulseSnapshot:
        pulse = _field(capabilities, "pulse")
        if pulse is None:
            raise BraketCapabilityError("Braket device does not advertise pulse capabilities.")

        raw_ports = _mapping(_field(pulse, "ports"), label="Braket pulse ports")
        ports = []
        for key, raw in raw_ports.items():
            port_id = _field(raw, "portId", key)
            raw_qubits = _field(raw, "qubitMappings", ()) or ()
            ports.append(
                BraketPort(
                    port_id=str(port_id),
                    dt_seconds=float(_field(raw, "dt")),
                    direction=_field(raw, "direction"),
                    port_type=_field(raw, "portType"),
                    qubits=tuple(int(qubit) for qubit in raw_qubits),
                )
            )

        raw_frames = _mapping(_field(pulse, "frames"), label="Braket pulse frames")
        frames = []
        for key, raw in raw_frames.items():
            frame_id = _field(raw, "frameId", key)
            raw_qubits = _field(raw, "qubitMappings", ()) or ()
            frames.append(
                BraketFrame(
                    frame_id=str(frame_id),
                    port_id=str(_field(raw, "portId")),
                    frequency_hz=float(_field(raw, "frequency")),
                    phase=float(_field(raw, "phase", 0.0)),
                    associated_gate=_field(raw, "associatedGate"),
                    qubits=tuple(int(qubit) for qubit in raw_qubits),
                )
            )

        raw_functions = _field(pulse, "supportedFunctions", {}) or {}
        raw_waveforms = _field(pulse, "supportedQhpTemplateWaveforms", {}) or {}
        functions = frozenset(str(key) for key in _mapping(raw_functions, label="functions"))
        waveforms = frozenset(str(key) for key in _mapping(raw_waveforms, label="waveforms"))
        raw_validation = _field(pulse, "validationParameters", {}) or {}
        validation = tuple(
            (str(key), _json_scalar(value, label=f"Validation parameter {key}"))
            for key, value in _mapping(raw_validation, label="validation parameters").items()
        )
        if captured_at is None:
            captured_at = datetime.now(UTC).isoformat()
        return cls(
            device_arn=device_arn,
            ports=tuple(ports),
            frames=tuple(frames),
            supported_functions=functions,
            supported_waveforms=waveforms,
            supports_dynamic_frames=bool(_field(pulse, "supportsDynamicFrames", False)),
            supports_local_pulse_elements=bool(_field(pulse, "supportsLocalPulseElements", False)),
            supports_non_native_gates_with_pulses=bool(
                _field(pulse, "supportsNonNativeGatesWithPulses", False)
            ),
            validation_parameters=validation,
            calibration_reference=_field(pulse, "nativeGateCalibrationsRef"),
            calibration_digest=calibration_digest,
            captured_at=captured_at,
        )

    @classmethod
    def from_aws_device(
        cls,
        device: object,
        *,
        calibration_digest: str | None = None,
        captured_at: str | None = None,
    ) -> BraketPulseSnapshot:
        arn = _field(device, "arn")
        capabilities = _field(device, "properties")
        if not isinstance(arn, str) or capabilities is None:
            raise BraketCapabilityError("Expected an initialized braket.aws.AwsDevice.")
        return cls.from_capabilities(
            arn,
            capabilities,
            calibration_digest=calibration_digest,
            captured_at=captured_at,
        )
