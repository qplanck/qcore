"""Offline IBM backend capability normalization.

This module deliberately depends on object capabilities instead of IBM or Qiskit
SDK classes.  Importing it never imports a provider SDK, discovers devices,
loads credentials, or performs network I/O.  A BackendV2-like object is read
once and converted into QCore's immutable, JSON-only :class:`~qplanck.targets.Target`.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from typing import Any, Final

from qplanck.circuit import SUPPORTED_GATES
from qplanck.errors import TargetError
from qplanck.targets import InstructionSupport, Target, TargetLimit, TargetLimits, Topology

IBM_TARGET_METADATA_SCHEMA_VERSION: Final = "qplanck.ibm-target-metadata.v0.1"

_MISSING: Final = object()
_PROVIDER_ID: Final = "ibm"
_EXCLUDED_FIELDS: Final = (
    "credentials",
    "provider_sdk_objects",
    "provider_service_instances",
    "queue_state",
    "live_job_state",
    "pulse_calibrations",
    "backend_defaults",
)


@dataclass(frozen=True)
class _InstructionRecord:
    name: str
    location: tuple[int, ...] | None
    error: float | None
    duration: float | None


def _canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _sha256(value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _optional_attr(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except AttributeError:
        return _MISSING
    except Exception as error:  # pragma: no cover - defensive provider boundary
        raise TargetError(f"IBM backend attribute {name!r} could not be inspected.") from error


def _required_positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TargetError(f"{label} must be a positive integer.")
    return value


def _optional_positive_int(value: object, *, label: str) -> int | None:
    if value is _MISSING or value is None:
        return None
    return _required_positive_int(value, label=label)


def _optional_float(
    value: object,
    *,
    label: str,
    minimum: float = 0.0,
    maximum: float | None = None,
    strictly_positive: bool = False,
) -> float | None:
    if value is _MISSING or value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TargetError(f"{label} must be a finite number or None.")
    result = float(value)
    if not math.isfinite(result):
        raise TargetError(f"{label} must be finite.")
    if strictly_positive and result <= minimum:
        raise TargetError(f"{label} must be greater than {minimum}.")
    if not strictly_positive and result < minimum:
        raise TargetError(f"{label} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise TargetError(f"{label} must be at most {maximum}.")
    return result


def _optional_string(value: object, *, label: str) -> str | None:
    if value is _MISSING or value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TargetError(f"{label} must be a non-empty string or None.")
    return value.strip()


def _captured_at(value: datetime | str | None) -> str:
    if value is None:
        parsed = datetime.now(UTC)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise TargetError("captured_at must be an RFC 3339 timestamp.") from error
    else:
        raise TargetError(
            "captured_at must be a timezone-aware datetime, RFC 3339 string, or None."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TargetError("captured_at must include a timezone offset.")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _qubit_count(backend: object, provider_target: object | None) -> int:
    raw = _optional_attr(backend, "num_qubits")
    if raw is _MISSING and provider_target is not None:
        raw = _optional_attr(provider_target, "num_qubits")
    if raw is _MISSING:
        raise TargetError("IBM backend does not expose a target width.")
    return _required_positive_int(raw, label="IBM backend num_qubits")


def _operation_names(backend: object, provider_target: object | None) -> tuple[str, ...]:
    raw = _MISSING
    if provider_target is not None:
        raw = _optional_attr(provider_target, "operation_names")
    if raw is _MISSING:
        raw = _optional_attr(backend, "operation_names")
    if raw is _MISSING or isinstance(raw, str) or not isinstance(raw, Iterable):
        raise TargetError("IBM backend must expose an iterable of operation names.")
    names: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise TargetError("IBM backend operation names must be non-empty strings.")
        names.add(item.strip().lower())
    if not names:
        raise TargetError("IBM backend declares no operations.")
    return tuple(sorted(names))


def _location(value: object, *, arity: int, width: int, name: str) -> tuple[int, ...] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TargetError(f"IBM instruction {name!r} has a malformed physical location.")
    location = tuple(value)
    if len(location) != arity:
        raise TargetError(f"IBM instruction {name!r} has a malformed physical location.")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in location):
        raise TargetError(f"IBM instruction {name!r} locations must contain integers.")
    if len(set(location)) != arity:
        raise TargetError(f"IBM instruction {name!r} has a malformed physical location.")
    if any(item < 0 or item >= width for item in location):
        raise TargetError(f"IBM instruction {name!r} references a qubit outside the target.")
    return location


def _property_number(
    properties: object,
    name: str,
    *,
    label: str,
    probability: bool = False,
) -> float | None:
    if properties is None:
        return None
    raw = _optional_attr(properties, name)
    return _optional_float(
        raw,
        label=label,
        maximum=1.0 if probability else None,
    )


def _instruction_records(
    provider_target: object | None,
    operation_names: tuple[str, ...],
    *,
    width: int,
) -> tuple[_InstructionRecord, ...]:
    records: list[_InstructionRecord] = []
    for name in operation_names:
        spec = SUPPORTED_GATES.get(name)
        if spec is None:
            continue
        properties_by_location: object = _MISSING
        if provider_target is not None:
            try:
                properties_by_location = provider_target[name]  # type: ignore[index]
            except (KeyError, TypeError):
                properties_by_location = _MISSING
            except Exception as exc:
                raise TargetError(
                    f"IBM target properties for instruction {name!r} could not be inspected."
                ) from exc

        if properties_by_location is _MISSING:
            records.append(_InstructionRecord(name, None, None, None))
            continue
        if not isinstance(properties_by_location, Mapping):
            raise TargetError(f"IBM target properties for instruction {name!r} must be a mapping.")
        if not properties_by_location:
            raise TargetError(f"IBM target declares instruction {name!r} without any support.")
        for raw_location, properties in properties_by_location.items():
            location = _location(raw_location, arity=spec.qubits, width=width, name=name)
            error_probability = _property_number(
                properties,
                "error",
                label=f"IBM {name} error at {location}",
                probability=True,
            )
            duration = _property_number(
                properties,
                "duration",
                label=f"IBM {name} duration at {location}",
            )
            records.append(_InstructionRecord(name, location, error_probability, duration))
    if not records:
        raise TargetError("IBM backend exposes no operations supported by QCore.")
    return tuple(
        sorted(records, key=lambda item: (item.name, item.location is not None, item.location))
    )


def _instruction_support(records: tuple[_InstructionRecord, ...]) -> tuple[InstructionSupport, ...]:
    result: list[InstructionSupport] = []
    for name in sorted({record.name for record in records}):
        selected = tuple(record for record in records if record.name == name)
        locations = None
        if not any(record.location is None for record in selected):
            locations = tuple(record.location for record in selected if record.location is not None)
        result.append(InstructionSupport(name, SUPPORTED_GATES[name].qubits, locations))
    return tuple(result)


def _raw_coupling_edges(backend: object, *, width: int) -> tuple[tuple[int, int], ...] | None:
    coupling = _optional_attr(backend, "coupling_map")
    if coupling is _MISSING:
        return None
    if coupling is None:
        return None
    raw_edges: object = coupling
    get_edges = _optional_attr(coupling, "get_edges")
    if get_edges is not _MISSING:
        if not callable(get_edges):
            raise TargetError("IBM coupling map get_edges must be callable.")
        try:
            raw_edges = get_edges()
        except Exception as error:
            raise TargetError("IBM coupling-map edges could not be inspected.") from error
    if isinstance(raw_edges, str) or not isinstance(raw_edges, Iterable):
        raise TargetError("IBM coupling map must expose an iterable of edges.")
    edges: set[tuple[int, int]] = set()
    for raw_edge in raw_edges:
        location = _location(raw_edge, arity=2, width=width, name="coupling_map")
        if location is None:  # pragma: no cover - impossible for an edge
            raise TargetError("IBM coupling-map edges cannot be global.")
        edges.add((location[0], location[1]))
    return tuple(sorted(edges))


def _coupling_is_symmetric(backend: object) -> bool | None:
    coupling = _optional_attr(backend, "coupling_map")
    if coupling is _MISSING or coupling is None:
        return None
    raw = _optional_attr(coupling, "is_symmetric")
    if raw is _MISSING:
        return None
    if callable(raw):
        try:
            raw = raw()
        except Exception as error:
            raise TargetError("IBM coupling-map symmetry could not be inspected.") from error
    if not isinstance(raw, bool):
        raise TargetError("IBM coupling-map is_symmetric must be a boolean.")
    return raw


def _topology(
    backend: object,
    records: tuple[_InstructionRecord, ...],
    *,
    width: int,
) -> tuple[Topology, str]:
    coupling_edges = _raw_coupling_edges(backend, width=width)
    two_qubit = tuple(record for record in records if SUPPORTED_GATES[record.name].qubits == 2)
    global_two_qubit = any(record.location is None for record in two_qubit)
    instruction_edges = {
        (record.location[0], record.location[1])
        for record in two_qubit
        if record.location is not None
    }

    if coupling_edges is not None:
        edges = set(coupling_edges) | instruction_edges
        symmetric = _coupling_is_symmetric(backend)
        directed = (
            (not symmetric)
            if symmetric is not None
            else any((right, left) not in edges for left, right in edges)
        )
        source = "backend.coupling_map"
    elif instruction_edges:
        edges = instruction_edges
        directional = {
            edge
            for record in two_qubit
            if record.name == "cx" and record.location is not None
            for edge in ((record.location[0], record.location[1]),)
        }
        directed = any((right, left) not in directional for left, right in directional)
        source = "target.instruction_locations"
    elif global_two_qubit:
        return Topology.complete(width), "global_two_qubit_instruction"
    elif width == 1:
        return Topology(1), "single_qubit_target"
    else:
        raise TargetError(
            "IBM backend topology is unknown: expose coupling_map or two-qubit instruction locations."
        )
    return Topology(width, tuple(edges), directed=directed), source


def _qubit_property_rows(
    provider_target: object | None,
    operation_names: tuple[str, ...],
    *,
    width: int,
    unknown_fields: list[str],
) -> list[dict[str, Any]]:
    raw_properties: object = _MISSING
    if provider_target is not None:
        raw_properties = _optional_attr(provider_target, "qubit_properties")
    if raw_properties is _MISSING or raw_properties is None:
        properties: tuple[object | None, ...] = (None,) * width
    else:
        if isinstance(raw_properties, str) or not isinstance(raw_properties, Iterable):
            raise TargetError("IBM target qubit_properties must be an iterable or None.")
        properties = tuple(raw_properties)
        if len(properties) != width:
            raise TargetError("IBM target qubit_properties width does not match num_qubits.")

    readout_errors: dict[int, float] = {}
    if provider_target is not None and "measure" in operation_names:
        try:
            measurement_properties = provider_target["measure"]  # type: ignore[index]
        except (KeyError, TypeError):
            measurement_properties = _MISSING
        except Exception as error:
            raise TargetError("IBM measurement properties could not be inspected.") from error
        if measurement_properties is not _MISSING:
            if not isinstance(measurement_properties, Mapping):
                raise TargetError("IBM measurement properties must be a mapping.")
            for raw_location, properties_item in measurement_properties.items():
                location = _location(raw_location, arity=1, width=width, name="measure")
                if location is None:
                    continue
                readout_error = _property_number(
                    properties_item,
                    "error",
                    label=f"IBM readout error at {location}",
                    probability=True,
                )
                if readout_error is not None:
                    readout_errors[location[0]] = readout_error
    rows: list[dict[str, Any]] = []
    for qubit, item in enumerate(properties):
        t1 = _property_number(item, "t1", label=f"IBM qubit {qubit} T1")
        t2 = _property_number(item, "t2", label=f"IBM qubit {qubit} T2")
        frequency = _property_number(item, "frequency", label=f"IBM qubit {qubit} frequency")
        readout_error = readout_errors.get(qubit)
        row = {
            "qubit": qubit,
            "t1_seconds": t1,
            "t2_seconds": t2,
            "frequency_hz": frequency,
            "readout_error_probability": readout_error,
        }
        for key, value in row.items():
            if key != "qubit" and value is None:
                unknown_fields.append(f"calibrated.qubits[{qubit}].{key}")
        rows.append(row)
    return rows


def _instruction_evidence(
    records: tuple[_InstructionRecord, ...], unknown_fields: list[str]
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    rows: list[dict[str, Any]] = []
    errors: dict[str, float] = {}
    for record in records:
        location = None if record.location is None else list(record.location)
        suffix = "" if record.location is None else ":" + ",".join(map(str, record.location))
        key = f"{record.name}{suffix}"
        if record.error is not None:
            errors[key] = record.error
        else:
            unknown_fields.append(f"calibrated.instructions.{key}.error_probability")
        if record.duration is None:
            unknown_fields.append(f"calibrated.instructions.{key}.duration_seconds")
        rows.append(
            {
                "name": record.name,
                "location": location,
                "error_probability": record.error,
                "duration_seconds": record.duration,
                "evidence_kind": (
                    "calibrated"
                    if record.error is not None or record.duration is not None
                    else "declared_only"
                ),
            }
        )
    return rows, dict(sorted(errors.items()))


def _backend_dt(backend: object, provider_target: object | None) -> float | None:
    raw = _optional_attr(backend, "dt")
    if (raw is _MISSING or raw is None) and provider_target is not None:
        raw = _optional_attr(provider_target, "dt")
    return _optional_float(raw, label="IBM backend dt", strictly_positive=True)


def _limits(backend: object, unknown_fields: list[str]) -> TargetLimits:
    max_shots = _optional_positive_int(
        _optional_attr(backend, "max_shots"), label="IBM backend max_shots"
    )
    max_circuits = _optional_positive_int(
        _optional_attr(backend, "max_circuits"), label="IBM backend max_circuits"
    )
    if max_shots is None:
        unknown_fields.append("limits.max_shots")
    if max_circuits is None:
        unknown_fields.append("limits.max_circuits_per_job")
    unknown_fields.append("limits.max_payload_bytes")
    return TargetLimits(
        max_shots=TargetLimit() if max_shots is None else TargetLimit.exact(max_shots),
        max_circuits_per_job=(
            TargetLimit() if max_circuits is None else TargetLimit.exact(max_circuits)
        ),
    )


def target_from_ibm_backend(
    backend: object, *, captured_at: datetime | str | None = None
) -> Target:
    """Normalize one already-obtained IBM BackendV2-like object offline.

    The adapter performs no discovery, authentication, or submission.  Only a
    small allowlist of scalar capabilities and calibration properties is read;
    provider objects, credentials, options, and arbitrary backend metadata are
    intentionally excluded from the durable snapshot.
    """

    provider_target_raw = _optional_attr(backend, "target")
    provider_target = None if provider_target_raw is _MISSING else provider_target_raw
    width = _qubit_count(backend, provider_target)
    names = _operation_names(backend, provider_target)
    records = _instruction_records(provider_target, names, width=width)
    instructions = _instruction_support(records)
    topology, topology_source = _topology(backend, records, width=width)
    timestamp = _captured_at(captured_at)

    backend_name = _optional_string(_optional_attr(backend, "name"), label="IBM backend name")
    if backend_name is None:
        raise TargetError("IBM backend must expose a non-empty name.")
    backend_version = _optional_string(
        _optional_attr(backend, "backend_version"), label="IBM backend version"
    )
    dt = _backend_dt(backend, provider_target)

    unknown_fields: list[str] = []
    if backend_version is None:
        unknown_fields.append("identity.backend_version")
    if dt is None:
        unknown_fields.append("declared.dt_seconds")
    limits = _limits(backend, unknown_fields)
    instruction_rows, instruction_errors = _instruction_evidence(records, unknown_fields)
    qubit_rows = _qubit_property_rows(
        provider_target, names, width=width, unknown_fields=unknown_fields
    )

    versions = {
        "qplanck": _distribution_version("qplanck"),
        "qiskit": _distribution_version("qiskit"),
        "qiskit_ibm_runtime": _distribution_version("qiskit-ibm-runtime"),
    }
    for name, value in versions.items():
        if value is None:
            unknown_fields.append(f"source_versions.{name}")

    supported_names = sorted({record.name for record in records})
    excluded_operations = sorted(set(names) - set(supported_names))
    metadata_payload: dict[str, Any] = {
        "schema_version": IBM_TARGET_METADATA_SCHEMA_VERSION,
        "adapter": "qplanck.ibm.target_from_ibm_backend",
        "identity": {
            "provider": _PROVIDER_ID,
            "backend": backend_name,
            "backend_version": backend_version,
        },
        "snapshot": {
            "captured_at": timestamp,
            "source": "offline_backend_capability_inspection",
        },
        "source_versions": versions,
        "declared": {
            "qubit_count": width,
            "operation_names": list(names),
            "normalized_operations": supported_names,
            "excluded_operations": excluded_operations,
            "dt_seconds": dt,
            "topology_source": topology_source,
            "topology_directed": topology.directed,
        },
        "calibrated": {
            "instructions": instruction_rows,
            "qubits": qubit_rows,
        },
        "observed": {
            "available": False,
            "metrics": [],
            "note": "No execution outcomes are inferred from provider calibration data.",
        },
        # Planner compatibility: absent calibration values remain absent, never zero.
        "instruction_errors": instruction_errors,
        "unknown_fields": sorted(set(unknown_fields)),
        "excluded_fields": list(_EXCLUDED_FIELDS),
    }
    target_id = f"ibm:{backend_name}"
    snapshot_payload = {
        "target_id": target_id,
        "provider": _PROVIDER_ID,
        "model": backend_name,
        "topology": topology.to_dict(),
        "instructions": [instruction.to_dict() for instruction in instructions],
        "limits": limits.to_dict(),
        "metadata": metadata_payload,
    }
    return Target(
        target_id=target_id,
        provider=_PROVIDER_ID,
        model=backend_name,
        snapshot_id=_sha256(snapshot_payload),
        topology=topology,
        instructions=instructions,
        limits=limits,
        metadata=metadata_payload,
    )


__all__ = ["IBM_TARGET_METADATA_SCHEMA_VERSION", "target_from_ibm_backend"]
