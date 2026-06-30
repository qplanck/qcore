"""Result and execution trace types."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qplanck.ir import CircuitIR

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


@dataclass(frozen=True)
class RunResult:
    counts: dict[str, int]
    probabilities: dict[str, float]
    measurements: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    trace: ExecutionTrace | None = None
