"""Serializable internal representation for QCore circuits."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar

from qplanck.errors import CircuitError

SCHEMA_VERSION = "qplanck.ir.v0.1"


def _freeze_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if metadata is None:
        return MappingProxyType({})
    return MappingProxyType(dict(metadata))


def _metadata_to_dict(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {key: metadata[key] for key in sorted(metadata)}


@dataclass(frozen=True)
class Parameter:
    """A named parameter placeholder.

    The current public circuit API accepts numeric parameters only, but the IR keeps
    this type so future importer/exporter work has a stable extension point.
    """

    name: str
    value: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise CircuitError("Parameter name must be non-empty.")
        if self.value is not None:
            value = float(self.value)
            if not math.isfinite(value):
                raise CircuitError("Parameter values must be finite.")
            object.__setattr__(self, "value", value)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "parameter", "name": self.name, "value": self.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Parameter:
        if data.get("kind") != "parameter":
            raise CircuitError("Invalid parameter payload.")
        return cls(name=str(data["name"]), value=data.get("value"))


@dataclass(frozen=True)
class Operation:
    """A quantum operation in QCore IR."""

    name: str
    qubits: tuple[int, ...]
    params: tuple[float | Parameter, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = self.name.strip().lower()
        if not name:
            raise CircuitError("Operation name must be non-empty.")
        qubits = tuple(int(qubit) for qubit in self.qubits)
        if any(qubit < 0 for qubit in qubits):
            raise CircuitError("Operation qubits must be non-negative.")

        params: list[float | Parameter] = []
        for param in self.params:
            if isinstance(param, Parameter):
                params.append(param)
            elif isinstance(param, int | float):
                value = float(param)
                if not math.isfinite(value):
                    raise CircuitError("Operation parameters must be finite.")
                params.append(value)
            else:
                raise CircuitError(f"Unsupported parameter type: {type(param).__name__}.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "qubits", qubits)
        object.__setattr__(self, "params", tuple(params))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        params: list[float | dict[str, Any]] = []
        for param in self.params:
            params.append(param.to_dict() if isinstance(param, Parameter) else param)
        return {
            "name": self.name,
            "qubits": list(self.qubits),
            "params": params,
            "metadata": _metadata_to_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Operation:
        params: list[float | Parameter] = []
        for param in data.get("params", []):
            if isinstance(param, Mapping):
                params.append(Parameter.from_dict(param))
            else:
                params.append(float(param))
        return cls(
            name=str(data["name"]),
            qubits=tuple(int(qubit) for qubit in data.get("qubits", [])),
            params=tuple(params),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class MeasurementSpec:
    """A terminal measurement from a qubit into a classical bit."""

    qubit: int
    cbit: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        qubit = int(self.qubit)
        cbit = int(self.cbit)
        if qubit < 0 or cbit < 0:
            raise CircuitError("Measurement qubit and classical bit must be non-negative.")
        object.__setattr__(self, "qubit", qubit)
        object.__setattr__(self, "cbit", cbit)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "qubit": self.qubit,
            "cbit": self.cbit,
            "metadata": _metadata_to_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MeasurementSpec:
        return cls(
            qubit=int(data["qubit"]),
            cbit=int(data["cbit"]),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class CircuitIR:
    """Stable, JSON-serializable circuit representation."""

    qubit_count: int
    operations: tuple[Operation, ...] = ()
    measurements: tuple[MeasurementSpec, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    SUPPORTED_SCHEMA: ClassVar[str] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        qubit_count = int(self.qubit_count)
        if qubit_count <= 0:
            raise CircuitError("Circuit must contain at least one qubit.")
        operations = tuple(self.operations)
        measurements = tuple(self.measurements)

        for operation in operations:
            for qubit in operation.qubits:
                if qubit >= qubit_count:
                    raise CircuitError(
                        f"Operation {operation.name!r} references qubit {qubit}, "
                        f"but the circuit has {qubit_count} qubits."
                    )
        for measurement in measurements:
            if measurement.qubit >= qubit_count:
                raise CircuitError(
                    f"Measurement references qubit {measurement.qubit}, "
                    f"but the circuit has {qubit_count} qubits."
                )

        object.__setattr__(self, "qubit_count", qubit_count)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "measurements", measurements)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def with_operation(self, operation: Operation) -> CircuitIR:
        return CircuitIR(
            qubit_count=self.qubit_count,
            operations=(*self.operations, operation),
            measurements=self.measurements,
            metadata=self.metadata,
            schema_version=self.schema_version,
        )

    def with_measurement(self, measurement: MeasurementSpec) -> CircuitIR:
        return CircuitIR(
            qubit_count=self.qubit_count,
            operations=self.operations,
            measurements=(*self.measurements, measurement),
            metadata=self.metadata,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "qubit_count": self.qubit_count,
            "operations": [operation.to_dict() for operation in self.operations],
            "measurements": [measurement.to_dict() for measurement in self.measurements],
            "metadata": _metadata_to_dict(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CircuitIR:
        schema_version = str(data.get("schema_version", SCHEMA_VERSION))
        if schema_version != SCHEMA_VERSION:
            raise CircuitError(f"Unsupported IR schema version: {schema_version}.")
        return cls(
            qubit_count=int(data["qubit_count"]),
            operations=tuple(Operation.from_dict(item) for item in data.get("operations", [])),
            measurements=tuple(
                MeasurementSpec.from_dict(item) for item in data.get("measurements", [])
            ),
            metadata=dict(data.get("metadata", {})),
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, text: str) -> CircuitIR:
        return cls.from_dict(json.loads(text))
