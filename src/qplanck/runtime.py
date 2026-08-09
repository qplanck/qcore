"""Provider-neutral execution, job, manifest, and calibration contracts.

The runtime module deliberately contains no provider SDK imports.  Backends may
use these immutable contracts while retaining provider-specific identifiers in
namespaced metadata or :class:`ExternalArtifactRef` values.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from qplanck.errors import (
    BackendError,
    JobCancelledError,
    JobError,
    JobFailedError,
    JobTimeoutError,
)
from qplanck.pulse import CalibrationLibrary

if TYPE_CHECKING:
    from qplanck.compiler import CompiledCircuit
    from qplanck.results import RunResult
    from qplanck.targets import Target


MANIFEST_SCHEMA_VERSION = "qplanck.experiment-manifest.v0.1"
CALIBRATED_CIRCUIT_SCHEMA_VERSION = "qplanck.calibrated-circuit.v0.1"
TraceMode = Literal["off", "summary", "full"]

_SECRET_KEY_PARTS = (
    "access_key",
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "session_token",
    "token",
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _canonical_json(value: object, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        indent=indent,
        separators=None if indent is not None else (",", ":"),
        sort_keys=True,
    )


def _sha256(value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def _looks_like_local_path(value: str) -> bool:
    if value.startswith(("http://", "https://", "s3://", "arn:")):
        return False
    return value.startswith(("/", "~/")) or bool(_WINDOWS_ABSOLUTE_PATH.match(value))


def _sanitize_json(value: Any, *, key: str | None = None) -> Any:
    """Return canonical JSON data with secrets and local paths removed."""

    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Runtime metadata must not contain NaN or infinity.")
        return value
    if isinstance(value, str):
        return "[REDACTED_PATH]" if _looks_like_local_path(value) else value
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key in sorted(value, key=lambda item: str(item)):
            if not isinstance(raw_key, str):
                raise TypeError("Runtime metadata object keys must be strings.")
            sanitized[raw_key] = _sanitize_json(value[raw_key], key=raw_key)
        return sanitized
    if isinstance(value, tuple | list):
        return [_sanitize_json(item) for item in value]
    raise TypeError(f"Runtime metadata must be JSON-compatible, not {type(value).__name__}.")


def _freeze_json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    sanitized = _sanitize_json(value)
    if not isinstance(sanitized, dict):  # pragma: no cover - guarded by the input annotation
        raise TypeError("Expected a JSON object.")
    frozen = _freeze_json(sanitized)
    if not isinstance(frozen, Mapping):  # pragma: no cover - sanitized is known to be a dict
        raise TypeError("Expected a frozen JSON object.")
    return frozen


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_json(item) for item in value]
    return value


def _strict_optional_int(value: int | None, *, label: str, minimum: int = 0) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise ValueError(f"{label} must be a {qualifier} integer or None.")
    return value


def _strict_optional_positive_float(value: float | None, *, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a finite, positive number or None.")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{label} must be a finite, positive number or None.")
    return normalized


@dataclass(frozen=True)
class ExecutionOptions:
    """Canonical, provider-neutral execution options and client-side budgets."""

    shots: int | None = None
    seed: int | None = None
    trace: TraceMode = "off"
    timeout_seconds: float | None = None
    max_memory_bytes: int | None = None
    max_result_bytes: int | None = None
    backend_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        shots = _strict_optional_int(self.shots, label="shots")
        seed = _strict_optional_int(self.seed, label="seed")
        if self.trace not in {"off", "summary", "full"}:
            raise ValueError("trace must be 'off', 'summary', or 'full'.")
        timeout = _strict_optional_positive_float(
            self.timeout_seconds,
            label="timeout_seconds",
        )
        max_memory = _strict_optional_int(
            self.max_memory_bytes,
            label="max_memory_bytes",
            minimum=1,
        )
        max_result = _strict_optional_int(
            self.max_result_bytes,
            label="max_result_bytes",
            minimum=1,
        )
        raw_backend_options = dict(self.backend_options)
        for key in raw_backend_options:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("backend_options keys must be non-empty strings.")
            if "." not in key:
                raise ValueError(
                    f"Backend option {key!r} must use a namespace such as 'vendor.option'."
                )
            if _is_secret_key(key):
                raise ValueError(
                    f"Backend option {key!r} looks secret-bearing; use the provider credential chain."
                )
        try:
            backend_options = _freeze_json_mapping(raw_backend_options)
        except (TypeError, ValueError) as error:
            raise ValueError("backend_options must contain finite JSON values.") from error
        object.__setattr__(self, "shots", shots)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "max_memory_bytes", max_memory)
        object.__setattr__(self, "max_result_bytes", max_result)
        object.__setattr__(self, "backend_options", backend_options)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shots": self.shots,
            "seed": self.seed,
            "trace": self.trace,
            "timeout_seconds": self.timeout_seconds,
            "max_memory_bytes": self.max_memory_bytes,
            "max_result_bytes": self.max_result_bytes,
            "backend_options": _thaw_json(self.backend_options),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionOptions:
        raw_backend_options = data.get("backend_options", {})
        if not isinstance(raw_backend_options, Mapping):
            raise ValueError("backend_options must be an object.")
        return cls(
            shots=data.get("shots"),
            seed=data.get("seed"),
            trace=data.get("trace", "off"),
            timeout_seconds=data.get("timeout_seconds"),
            max_memory_bytes=data.get("max_memory_bytes"),
            max_result_bytes=data.get("max_result_bytes"),
            backend_options=raw_backend_options,
        )

    @property
    def content_hash(self) -> str:
        return _sha256(self.to_dict())


class JobStatus(StrEnum):
    """Stable QCore job lifecycle states."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


_ALLOWED_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = MappingProxyType(
    {
        JobStatus.CREATED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
        JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
        JobStatus.RUNNING: frozenset(
            {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCEL_REQUESTED,
            }
        ),
        JobStatus.CANCEL_REQUESTED: frozenset(
            {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED}
        ),
        JobStatus.SUCCEEDED: frozenset(),
        JobStatus.FAILED: frozenset(),
        JobStatus.CANCELLED: frozenset(),
    }
)


def validate_job_transition(current: JobStatus, following: JobStatus) -> None:
    """Validate one transition against the stable monotonic state machine."""

    if following not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid job transition: {current.value} -> {following.value}.")


@runtime_checkable
class Job(Protocol):
    """Provider-neutral asynchronous job handle."""

    @property
    def id(self) -> str: ...

    def status(self) -> JobStatus: ...

    def cancel(self) -> bool: ...

    def result(self, *, timeout: float | None = None) -> RunResult: ...


@runtime_checkable
class Backend(Protocol):
    """Capability-bearing execution backend."""

    @property
    def backend_id(self) -> str: ...

    @property
    def backend_version(self) -> str: ...

    @property
    def target(self) -> Target: ...

    def run(
        self,
        program: CompiledCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> RunResult: ...

    def submit(
        self,
        program: CompiledCircuit,
        *,
        options: ExecutionOptions | None = None,
    ) -> Job: ...


@dataclass(frozen=True)
class Diagnostic:
    """Stable machine-readable runtime diagnostic."""

    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "error"
    context: Mapping[str, Any] = field(default_factory=dict)
    remediation: str | None = None

    def __post_init__(self) -> None:
        code = self.code.strip()
        message = self.message.strip()
        if not code or not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
            raise ValueError("Diagnostic code must use uppercase snake case.")
        if not message:
            raise ValueError("Diagnostic message must be non-empty.")
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("Diagnostic severity must be info, warning, or error.")
        remediation = self.remediation
        if remediation is not None and not remediation.strip():
            raise ValueError("Diagnostic remediation must be non-empty when provided.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "context", _freeze_json_mapping(self.context))
        object.__setattr__(self, "remediation", remediation.strip() if remediation else None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "context": _thaw_json(self.context),
            "remediation": self.remediation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Diagnostic:
        context = data.get("context", {})
        if not isinstance(context, Mapping):
            raise ValueError("Diagnostic context must be an object.")
        return cls(
            code=str(data["code"]),
            message=str(data["message"]),
            severity=data.get("severity", "error"),
            context=context,
            remediation=data.get("remediation"),
        )


@dataclass(frozen=True)
class ExternalArtifactRef:
    """Reference to a provider-owned or content-addressed external artifact."""

    reference: str
    content_hash: str | None = None
    media_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reference = self.reference.strip()
        if not reference:
            raise ValueError("External artifact reference must be non-empty.")
        content_hash = self.content_hash
        if content_hash is not None and not content_hash.strip():
            raise ValueError("External artifact content_hash must be non-empty when provided.")
        media_type = self.media_type
        if media_type is not None and not media_type.strip():
            raise ValueError("External artifact media_type must be non-empty when provided.")
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "content_hash", content_hash.strip() if content_hash else None)
        object.__setattr__(self, "media_type", media_type.strip() if media_type else None)
        object.__setattr__(self, "metadata", _freeze_json_mapping(self.metadata))

    def to_dict(self, *, redact_reference: bool = False) -> dict[str, Any]:
        return {
            "reference": "[REDACTED]" if redact_reference else self.reference,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "metadata": _thaw_json(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalArtifactRef:
        metadata = data.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("External artifact metadata must be an object.")
        return cls(
            reference=str(data["reference"]),
            content_hash=data.get("content_hash"),
            media_type=data.get("media_type"),
            metadata=metadata,
        )


def _default_environment() -> dict[str, Any]:
    try:
        version = importlib_metadata.version("qplanck")
    except importlib_metadata.PackageNotFoundError:
        version = "development"
    return {
        "qplanck_version": version,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system().lower(),
        "machine": platform.machine().lower(),
    }


@dataclass(frozen=True)
class ExperimentManifest:
    """Canonical reproducibility record for one execution."""

    source: Mapping[str, Any]
    compilation: Mapping[str, Any]
    target: Mapping[str, Any]
    execution: Mapping[str, Any]
    result: Mapping[str, Any]
    environment: Mapping[str, Any] = field(default_factory=_default_environment)
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported manifest schema version: {self.schema_version}.")
        for name in ("source", "compilation", "target", "execution", "environment", "result"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"Manifest {name} section must be an object.")
            object.__setattr__(self, name, _freeze_json_mapping(value))
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, Diagnostic) for item in diagnostics):
            raise TypeError("Manifest diagnostics must contain Diagnostic values.")
        object.__setattr__(self, "diagnostics", diagnostics)

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": _thaw_json(self.source),
            "compilation": _thaw_json(self.compilation),
            "target": _thaw_json(self.target),
            "execution": _thaw_json(self.execution),
            "environment": _thaw_json(self.environment),
            "result": _thaw_json(self.result),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    @property
    def content_hash(self) -> str:
        return _sha256(self._payload_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload_dict()
        payload["integrity"] = {"manifest_hash": self.content_hash}
        return payload

    def to_json(self, *, indent: int | None = None) -> str:
        return _canonical_json(self.to_dict(), indent=indent)

    def write(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> Path:
        """Write the canonical manifest without silently replacing an existing file."""

        destination = Path(path)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Manifest already exists: {destination}.")
        destination.write_text(self.to_json(indent=2) + "\n", encoding="utf-8")
        return destination

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExperimentManifest:
        diagnostics = data.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            raise ValueError("Manifest diagnostics must be a list.")
        sections: dict[str, Mapping[str, Any]] = {}
        for name in ("source", "compilation", "target", "execution", "environment", "result"):
            section = data.get(name, {})
            if not isinstance(section, Mapping):
                raise ValueError(f"Manifest {name} section must be an object.")
            sections[name] = section
        manifest = cls(
            source=sections["source"],
            compilation=sections["compilation"],
            target=sections["target"],
            execution=sections["execution"],
            environment=sections["environment"],
            result=sections["result"],
            diagnostics=tuple(Diagnostic.from_dict(item) for item in diagnostics),
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
        )
        integrity = data.get("integrity")
        if integrity is not None:
            if not isinstance(integrity, Mapping):
                raise ValueError("Manifest integrity section must be an object.")
            expected = integrity.get("manifest_hash")
            if expected != manifest.content_hash:
                raise ValueError("Manifest integrity hash does not match its content.")
        return manifest

    @classmethod
    def from_json(cls, text: str) -> ExperimentManifest:
        data = json.loads(text)
        if not isinstance(data, Mapping):
            raise ValueError("Manifest JSON must contain an object.")
        return cls.from_dict(data)


def _object_dict(value: object) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        raise TypeError(f"{type(value).__name__} does not provide to_dict().")
    payload = to_dict()
    if not isinstance(payload, dict):
        raise TypeError(f"{type(value).__name__}.to_dict() must return a dictionary.")
    return payload


@dataclass(frozen=True)
class CalibratedCircuit:
    """Bind a physical compiled circuit to immutable pulse calibration evidence."""

    compiled_circuit: CompiledCircuit
    calibrations: CalibrationLibrary
    target_hash: str
    pulse_snapshot_hash: str
    schema_version: str = CALIBRATED_CIRCUIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATED_CIRCUIT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported calibrated-circuit schema: {self.schema_version}.")
        if not isinstance(self.calibrations, CalibrationLibrary):
            raise TypeError("calibrations must be a CalibrationLibrary.")
        target_hash = self.target_hash.strip()
        pulse_snapshot_hash = self.pulse_snapshot_hash.strip()
        if not target_hash or not pulse_snapshot_hash:
            raise ValueError("target_hash and pulse_snapshot_hash must be non-empty.")
        _object_dict(self.compiled_circuit)

        compiled_target = getattr(self.compiled_circuit, "target", None)
        compiled_target_hash = getattr(compiled_target, "content_hash", None)
        if compiled_target_hash is None:
            compiled_target_hash = getattr(self.compiled_circuit, "target_hash", None)
        if compiled_target_hash is not None and str(compiled_target_hash) != target_hash:
            raise ValueError("target_hash does not match the compiled circuit target snapshot.")
        object.__setattr__(self, "target_hash", target_hash)
        object.__setattr__(self, "pulse_snapshot_hash", pulse_snapshot_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "compiled_circuit": _object_dict(self.compiled_circuit),
            "calibrations": self.calibrations.to_dict(),
            "target_hash": self.target_hash,
            "pulse_snapshot_hash": self.pulse_snapshot_hash,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _canonical_json(self.to_dict(), indent=indent)

    @property
    def content_hash(self) -> str:
        return _sha256(self.to_dict())


__all__ = [
    "Backend",
    "BackendError",
    "CALIBRATED_CIRCUIT_SCHEMA_VERSION",
    "CalibratedCircuit",
    "Diagnostic",
    "ExecutionOptions",
    "ExperimentManifest",
    "ExternalArtifactRef",
    "Job",
    "JobCancelledError",
    "JobError",
    "JobFailedError",
    "JobStatus",
    "JobTimeoutError",
    "MANIFEST_SCHEMA_VERSION",
    "TraceMode",
    "validate_job_transition",
]
