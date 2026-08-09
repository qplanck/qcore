"""Result and execution trace types."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qplanck.ir import CircuitIR
from qplanck.runtime import (
    Diagnostic,
    ExperimentManifest,
    ExternalArtifactRef,
    _freeze_json_mapping,
    _thaw_json,
)

TRACE_SCHEMA_VERSION = "qplanck.trace.v0.1"


def _complex_to_dict(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _complex_from_dict(data: Mapping[str, Any]) -> complex:
    return complex(float(data["real"]), float(data["imag"]))


def _freeze_mapping(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True)
class TraceStep:
    index: int
    operation: Mapping[str, Any] | None
    statevector: tuple[complex, ...]
    probabilities: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "statevector", tuple(complex(value) for value in self.statevector))
        object.__setattr__(
            self,
            "probabilities",
            MappingProxyType({key: float(value) for key, value in self.probabilities.items()}),
        )
        if self.operation is not None:
            object.__setattr__(self, "operation", _freeze_mapping(self.operation))

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "operation": dict(self.operation) if self.operation is not None else None,
            "statevector": [_complex_to_dict(value) for value in self.statevector],
            "probabilities": {key: self.probabilities[key] for key in sorted(self.probabilities)},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TraceStep:
        return cls(
            index=int(data["index"]),
            operation=data.get("operation"),
            statevector=tuple(_complex_from_dict(item) for item in data["statevector"]),
            probabilities={str(key): float(value) for key, value in data["probabilities"].items()},
        )


@dataclass(frozen=True)
class ExecutionTrace:
    circuit: CircuitIR
    steps: tuple[TraceStep, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "circuit": self.circuit.to_dict(),
            "metadata": {key: self.metadata[key] for key in sorted(self.metadata)},
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionTrace:
        schema_version = str(data.get("schema_version", TRACE_SCHEMA_VERSION))
        if schema_version != TRACE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported trace schema version: {schema_version}.")
        return cls(
            circuit=CircuitIR.from_dict(data["circuit"]),
            steps=tuple(TraceStep.from_dict(item) for item in data["steps"]),
            metadata=dict(data.get("metadata", {})),
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, text: str) -> ExecutionTrace:
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True)
class StatevectorResult:
    statevector: tuple[complex, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbabilityResult:
    probabilities: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


class _ImmutableMeasurements(list[str]):
    """An immutable list that preserves the v0.x list equality contract."""

    @staticmethod
    def _reject(*_args: object, **_kwargs: object) -> None:
        raise TypeError("RunResult measurements are immutable.")

    __delitem__ = _reject
    __iadd__ = _reject  # type: ignore[assignment]
    __imul__ = _reject  # type: ignore[assignment]
    __setitem__ = _reject
    append = _reject
    clear = _reject
    extend = _reject
    insert = _reject
    pop = _reject  # type: ignore[assignment]
    remove = _reject
    reverse = _reject
    sort = _reject


@dataclass(frozen=True, init=False)
class RunResult:
    """Normalized immutable execution result.

    ``trace`` remains a constructor argument and property for v0.x callers;
    ``execution_trace`` is the clearer provider-neutral spelling.
    """

    counts: Mapping[str, int]
    probabilities: Mapping[str, float]
    measurements: list[str]
    metadata: Mapping[str, Any]
    diagnostics: tuple[Diagnostic, ...]
    execution_trace: ExecutionTrace | None
    manifest: ExperimentManifest | None
    raw_result: ExternalArtifactRef | None

    def __init__(
        self,
        counts: Mapping[str, int],
        probabilities: Mapping[str, float],
        measurements: list[str] | tuple[str, ...],
        metadata: Mapping[str, Any] | None = None,
        trace: ExecutionTrace | None = None,
        *,
        diagnostics: tuple[Diagnostic, ...] = (),
        execution_trace: ExecutionTrace | None = None,
        manifest: ExperimentManifest | None = None,
        raw_result: ExternalArtifactRef | None = None,
    ) -> None:
        if trace is not None and execution_trace is not None and trace is not execution_trace:
            raise ValueError("trace and execution_trace cannot contain different traces.")
        selected_trace = execution_trace if execution_trace is not None else trace

        normalized_counts: dict[str, int] = {}
        for key, count_value in counts.items():
            if not isinstance(key, str) or not key or any(bit not in "01" for bit in key):
                raise ValueError("RunResult count keys must be non-empty bit strings.")
            if isinstance(count_value, bool) or not isinstance(count_value, int) or count_value < 0:
                raise ValueError("RunResult counts must be non-negative integers.")
            normalized_counts[key] = count_value

        normalized_probabilities: dict[str, float] = {}
        for key, probability_value in probabilities.items():
            if not isinstance(key, str) or not key or any(bit not in "01" for bit in key):
                raise ValueError("RunResult probability keys must be non-empty bit strings.")
            probability = float(probability_value)
            if probability < 0.0 or probability > 1.0 or not math.isfinite(probability):
                raise ValueError("RunResult probabilities must be finite values in [0, 1].")
            normalized_probabilities[key] = probability

        normalized_measurements = _ImmutableMeasurements()
        list.extend(normalized_measurements, measurements)
        if any(
            not isinstance(item, str) or not item or any(bit not in "01" for bit in item)
            for item in normalized_measurements
        ):
            raise ValueError("RunResult measurements must be non-empty bit strings.")

        try:
            normalized_metadata = _freeze_json_mapping(metadata or {})
        except (TypeError, ValueError) as error:
            raise ValueError("RunResult metadata must contain finite JSON values.") from error
        normalized_diagnostics = tuple(diagnostics)
        if any(not isinstance(item, Diagnostic) for item in normalized_diagnostics):
            raise TypeError("RunResult diagnostics must contain Diagnostic values.")
        if manifest is not None and not isinstance(manifest, ExperimentManifest):
            raise TypeError("RunResult manifest must be an ExperimentManifest or None.")
        if raw_result is not None and not isinstance(raw_result, ExternalArtifactRef):
            raise TypeError("RunResult raw_result must be an ExternalArtifactRef or None.")

        object.__setattr__(
            self, "counts", MappingProxyType(dict(sorted(normalized_counts.items())))
        )
        object.__setattr__(
            self,
            "probabilities",
            MappingProxyType(dict(sorted(normalized_probabilities.items()))),
        )
        object.__setattr__(self, "measurements", normalized_measurements)
        object.__setattr__(self, "metadata", normalized_metadata)
        object.__setattr__(self, "diagnostics", normalized_diagnostics)
        object.__setattr__(self, "execution_trace", selected_trace)
        object.__setattr__(self, "manifest", manifest)
        object.__setattr__(self, "raw_result", raw_result)

    @property
    def trace(self) -> ExecutionTrace | None:
        """Compatibility alias for :attr:`execution_trace`."""

        return self.execution_trace

    def to_dict(self, *, include_manifest: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "counts": dict(self.counts),
            "probabilities": dict(self.probabilities),
            "measurements": list(self.measurements),
            "metadata": _thaw_json(self.metadata),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "execution_trace": (
                None if self.execution_trace is None else self.execution_trace.to_dict()
            ),
            "raw_result": None if self.raw_result is None else self.raw_result.to_dict(),
        }
        if include_manifest:
            data["manifest"] = None if self.manifest is None else self.manifest.to_dict()
        return data

    def to_json(self, *, indent: int | None = None, include_manifest: bool = True) -> str:
        return json.dumps(
            self.to_dict(include_manifest=include_manifest),
            allow_nan=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            sort_keys=True,
        )

    @property
    def content_hash(self) -> str:
        import hashlib

        payload = self.to_json(include_manifest=False)
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunResult:
        raw_trace = data.get("execution_trace")
        raw_manifest = data.get("manifest")
        raw_artifact = data.get("raw_result")
        raw_diagnostics = data.get("diagnostics", [])
        if not isinstance(raw_diagnostics, list):
            raise ValueError("RunResult diagnostics must be a list.")
        return cls(
            counts=data.get("counts", {}),
            probabilities=data.get("probabilities", {}),
            measurements=data.get("measurements", []),
            metadata=data.get("metadata", {}),
            execution_trace=(None if raw_trace is None else ExecutionTrace.from_dict(raw_trace)),
            diagnostics=tuple(Diagnostic.from_dict(item) for item in raw_diagnostics),
            manifest=(None if raw_manifest is None else ExperimentManifest.from_dict(raw_manifest)),
            raw_result=(
                None if raw_artifact is None else ExternalArtifactRef.from_dict(raw_artifact)
            ),
        )

    @classmethod
    def from_json(cls, text: str) -> RunResult:
        data = json.loads(text)
        if not isinstance(data, Mapping):
            raise ValueError("RunResult JSON must contain an object.")
        return cls.from_dict(data)

    @classmethod
    def testing(
        cls,
        *,
        counts: Mapping[str, int],
        probabilities: Mapping[str, float] | None = None,
        measurements: list[str] | tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> RunResult:
        """Build a concise deterministic fixture for mock backend scenarios."""

        return cls(
            counts=counts,
            probabilities=probabilities or {},
            measurements=measurements,
            metadata=metadata,
        )
