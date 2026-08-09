"""Immutable target, topology, and layout contracts.

The types in this module are deliberately provider-neutral.  They contain only
the capability data that participates in compilation and preflight identity;
volatile queue data and credentials never belong in a :class:`Target`.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar

from qplanck.circuit import SUPPORTED_GATES
from qplanck.errors import TargetError
from qplanck.ir import Operation

TOPOLOGY_SCHEMA_VERSION = "qplanck.topology.v0.1"
TARGET_SCHEMA_VERSION = "qplanck.target.v0.1"
LAYOUT_SCHEMA_VERSION = "qplanck.layout.v0.1"


def _canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _sha256(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


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


def _strict_non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TargetError(f"{label} must be a non-negative integer.")
    return value


@dataclass(frozen=True)
class Topology:
    """Canonical physical-qubit connectivity graph."""

    qubit_count: int
    edges: tuple[tuple[int, int], ...] = ()
    directed: bool = False
    schema_version: str = TOPOLOGY_SCHEMA_VERSION

    SUPPORTED_SCHEMA: ClassVar[str] = TOPOLOGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        count = _strict_non_negative_int(self.qubit_count, label="Topology qubit_count")
        if count == 0:
            raise TargetError("Topology must contain at least one qubit.")
        if not isinstance(self.directed, bool):
            raise TargetError("Topology directed must be a boolean.")
        if self.schema_version != self.SUPPORTED_SCHEMA:
            raise TargetError(f"Unsupported topology schema: {self.schema_version}.")

        normalized: set[tuple[int, int]] = set()
        for raw_edge in self.edges:
            if not isinstance(raw_edge, tuple) or len(raw_edge) != 2:
                raise TargetError("Every topology edge must be a two-integer tuple.")
            left = _strict_non_negative_int(raw_edge[0], label="Topology edge endpoint")
            right = _strict_non_negative_int(raw_edge[1], label="Topology edge endpoint")
            if left >= count or right >= count:
                raise TargetError("Topology edge references a qubit outside the topology.")
            if left == right:
                raise TargetError("Topology self-loops are not allowed.")
            if not self.directed and left > right:
                left, right = right, left
            normalized.add((left, right))

        object.__setattr__(self, "qubit_count", count)
        object.__setattr__(self, "edges", tuple(sorted(normalized)))

    @classmethod
    def complete(cls, qubit_count: int, *, directed: bool = False) -> Topology:
        count = _strict_non_negative_int(qubit_count, label="Topology qubit_count")
        if directed:
            edges = tuple((a, b) for a in range(count) for b in range(count) if a != b)
        else:
            edges = tuple((a, b) for a in range(count) for b in range(a + 1, count))
        return cls(count, edges, directed)

    @classmethod
    def line(cls, qubit_count: int, *, directed: bool = False) -> Topology:
        count = _strict_non_negative_int(qubit_count, label="Topology qubit_count")
        return cls(count, tuple((index, index + 1) for index in range(count - 1)), directed)

    @classmethod
    def ring(cls, qubit_count: int, *, directed: bool = False) -> Topology:
        count = _strict_non_negative_int(qubit_count, label="Topology qubit_count")
        if count < 3:
            raise TargetError("A ring topology requires at least three qubits.")
        return cls(
            count,
            (*tuple((index, index + 1) for index in range(count - 1)), (count - 1, 0)),
            directed,
        )

    @classmethod
    def grid(cls, rows: int, columns: int, *, directed: bool = False) -> Topology:
        row_count = _strict_non_negative_int(rows, label="Grid rows")
        column_count = _strict_non_negative_int(columns, label="Grid columns")
        if row_count == 0 or column_count == 0:
            raise TargetError("Grid rows and columns must be positive.")
        edges: list[tuple[int, int]] = []
        for row in range(row_count):
            for column in range(column_count):
                node = row * column_count + column
                if column + 1 < column_count:
                    edges.append((node, node + 1))
                if row + 1 < row_count:
                    edges.append((node, node + column_count))
        return cls(row_count * column_count, tuple(edges), directed)

    def has_arc(self, left: int, right: int) -> bool:
        if self.directed:
            return (left, right) in self.edges
        return (min(left, right), max(left, right)) in self.edges

    def has_weak_edge(self, left: int, right: int) -> bool:
        return self.has_arc(left, right) or (self.directed and self.has_arc(right, left))

    def neighbors(self, qubit: int, *, weak: bool = True) -> tuple[int, ...]:
        node = _strict_non_negative_int(qubit, label="Topology qubit")
        if node >= self.qubit_count:
            raise TargetError("Topology qubit is out of range.")
        result: set[int] = set()
        for left, right in self.edges:
            if left == node:
                result.add(right)
            if weak and right == node:
                result.add(left)
            if not self.directed and right == node:
                result.add(left)
        return tuple(sorted(result))

    @property
    def components(self) -> tuple[tuple[int, ...], ...]:
        remaining = set(range(self.qubit_count))
        components: list[tuple[int, ...]] = []
        while remaining:
            start = min(remaining)
            queue = deque([start])
            found = {start}
            while queue:
                current = queue.popleft()
                for neighbor in self.neighbors(current, weak=True):
                    if neighbor not in found:
                        found.add(neighbor)
                        queue.append(neighbor)
            remaining.difference_update(found)
            components.append(tuple(sorted(found)))
        return tuple(components)

    def shortest_path(self, source: int, target: int) -> tuple[int, ...]:
        source = _strict_non_negative_int(source, label="Topology path source")
        target = _strict_non_negative_int(target, label="Topology path target")
        if source >= self.qubit_count or target >= self.qubit_count:
            raise TargetError("Topology path endpoint is out of range.")
        if source == target:
            return (source,)
        queue = deque([source])
        previous: dict[int, int | None] = {source: None}
        while queue:
            current = queue.popleft()
            for neighbor in self.neighbors(current, weak=True):
                if neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == target:
                    path = [target]
                    cursor: int | None = target
                    while cursor is not None and previous[cursor] is not None:
                        cursor = previous[cursor]
                        if cursor is not None:
                            path.append(cursor)
                    return tuple(reversed(path))
                queue.append(neighbor)
        raise TargetError(f"No topology path connects physical qubits {source} and {target}.")

    def distance(self, source: int, target: int) -> int:
        return len(self.shortest_path(source, target)) - 1

    @property
    def diameter(self) -> int:
        maximum = 0
        for component in self.components:
            for index, source in enumerate(component):
                for target in component[index + 1 :]:
                    maximum = max(maximum, self.distance(source, target))
        return maximum

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "qubit_count": self.qubit_count,
            "directed": self.directed,
            "edges": [list(edge) for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Topology:
        raw_edges = data.get("edges", [])
        if not isinstance(raw_edges, list):
            raise TargetError("Topology edges must be a list.")
        raw_qubit_count = data.get("qubit_count")
        if isinstance(raw_qubit_count, bool) or not isinstance(raw_qubit_count, int):
            raise TargetError("Topology qubit_count must be a non-negative integer.")
        return cls(
            qubit_count=raw_qubit_count,
            edges=tuple(tuple(edge) for edge in raw_edges),
            directed=data.get("directed", False),
            schema_version=data.get("schema_version", TOPOLOGY_SCHEMA_VERSION),
        )

    @property
    def content_hash(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class Layout:
    """Injective logical-to-physical qubit mapping."""

    logical_to_physical: tuple[int, ...]
    schema_version: str = LAYOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LAYOUT_SCHEMA_VERSION:
            raise TargetError(f"Unsupported layout schema: {self.schema_version}.")
        values = tuple(
            _strict_non_negative_int(item, label="Physical qubit")
            for item in self.logical_to_physical
        )
        if len(set(values)) != len(values):
            raise TargetError("Layout physical qubits must be unique.")
        object.__setattr__(self, "logical_to_physical", values)

    @classmethod
    def identity(cls, logical_qubits: int) -> Layout:
        count = _strict_non_negative_int(logical_qubits, label="Logical qubit count")
        return cls(tuple(range(count)))

    def validate(self, *, logical_qubits: int, physical_qubits: int) -> None:
        if len(self.logical_to_physical) != logical_qubits:
            raise TargetError(
                f"Layout maps {len(self.logical_to_physical)} logical qubits; "
                f"the circuit requires {logical_qubits}."
            )
        if any(item >= physical_qubits for item in self.logical_to_physical):
            raise TargetError("Layout references a physical qubit outside the target.")

    def inverse(self, physical_qubits: int) -> tuple[int | None, ...]:
        count = _strict_non_negative_int(physical_qubits, label="Physical qubit count")
        if any(item >= count for item in self.logical_to_physical):
            raise TargetError("Layout references a physical qubit outside the target.")
        result: list[int | None] = [None] * count
        for logical, physical in enumerate(self.logical_to_physical):
            result[physical] = logical
        return tuple(result)

    def swap_physical(self, left: int, right: int) -> Layout:
        values = list(self.logical_to_physical)
        for index, physical in enumerate(values):
            if physical == left:
                values[index] = right
            elif physical == right:
                values[index] = left
        return Layout(tuple(values))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logical_to_physical": list(self.logical_to_physical),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layout:
        raw_values = data.get("logical_to_physical")
        if not isinstance(raw_values, list):
            raise TargetError("Layout logical_to_physical must be a list.")
        return cls(
            tuple(raw_values),
            schema_version=data.get("schema_version", LAYOUT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class InstructionSupport:
    """One target instruction and optional physical-location restriction."""

    name: str
    arity: int
    locations: tuple[tuple[int, ...], ...] | None = None

    def __post_init__(self) -> None:
        name = self.name.strip().lower()
        if name not in SUPPORTED_GATES:
            raise TargetError(f"Unknown target instruction {name!r}.")
        arity = _strict_non_negative_int(self.arity, label="Instruction arity")
        expected = SUPPORTED_GATES[name].qubits
        if arity != expected:
            raise TargetError(f"Instruction {name!r} requires arity {expected}, not {arity}.")
        locations = self.locations
        if locations is not None:
            normalized: set[tuple[int, ...]] = set()
            for location in locations:
                values = tuple(
                    _strict_non_negative_int(item, label="Instruction location")
                    for item in location
                )
                if len(values) != arity or len(set(values)) != len(values):
                    raise TargetError(f"Invalid physical location for instruction {name!r}.")
                if name in {"cz", "swap"}:
                    values = tuple(sorted(values))
                normalized.add(values)
            locations = tuple(sorted(normalized))
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "arity", arity)
        object.__setattr__(self, "locations", locations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arity": self.arity,
            "locations": (
                None if self.locations is None else [list(item) for item in self.locations]
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstructionSupport:
        raw_name = data.get("name")
        raw_arity = data.get("arity")
        raw_locations = data.get("locations")
        if not isinstance(raw_name, str):
            raise TargetError("Instruction name must be a string.")
        if isinstance(raw_arity, bool) or not isinstance(raw_arity, int):
            raise TargetError("Instruction arity must be a non-negative integer.")
        if raw_locations is not None and not isinstance(raw_locations, list):
            raise TargetError("Instruction locations must be a list or null.")
        locations: tuple[tuple[int, ...], ...] | None = None
        if raw_locations is not None:
            if any(not isinstance(location, list) for location in raw_locations):
                raise TargetError("Every instruction location must be a list.")
            locations = tuple(tuple(location) for location in raw_locations)
        return cls(raw_name, raw_arity, locations)


class LimitKind(StrEnum):
    UNKNOWN = "unknown"
    UNLIMITED = "unlimited"
    VALUE = "value"


@dataclass(frozen=True)
class TargetLimit:
    """A target limit that distinguishes unknown from unlimited."""

    kind: LimitKind = LimitKind.UNKNOWN
    value: int | None = None

    def __post_init__(self) -> None:
        try:
            kind = LimitKind(self.kind)
        except ValueError as error:
            raise TargetError(f"Unknown target limit kind {self.kind!r}.") from error
        value = self.value
        if kind is LimitKind.VALUE:
            value = _strict_non_negative_int(value, label="Target limit")
        elif value is not None:
            raise TargetError("Unknown and unlimited target limits cannot carry a value.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", value)

    @classmethod
    def exact(cls, value: int) -> TargetLimit:
        return cls(LimitKind.VALUE, value)

    @classmethod
    def unlimited(cls) -> TargetLimit:
        return cls(LimitKind.UNLIMITED)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetLimit:
        return cls(data.get("kind", LimitKind.UNKNOWN), data.get("value"))


@dataclass(frozen=True)
class TargetLimits:
    max_shots: TargetLimit = field(default_factory=TargetLimit)
    max_circuits_per_job: TargetLimit = field(default_factory=TargetLimit)
    max_payload_bytes: TargetLimit = field(default_factory=TargetLimit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_shots": self.max_shots.to_dict(),
            "max_circuits_per_job": self.max_circuits_per_job.to_dict(),
            "max_payload_bytes": self.max_payload_bytes.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetLimits:
        def decode(name: str) -> TargetLimit:
            value = data.get(name, {})
            if not isinstance(value, dict):
                raise TargetError(f"Target limit {name!r} must be an object.")
            return TargetLimit.from_dict(value)

        return cls(
            max_shots=decode("max_shots"),
            max_circuits_per_job=decode("max_circuits_per_job"),
            max_payload_bytes=decode("max_payload_bytes"),
        )


@dataclass(frozen=True)
class Target:
    """Immutable compilation capability snapshot."""

    target_id: str
    topology: Topology
    instructions: tuple[InstructionSupport, ...]
    provider: str | None = None
    model: str | None = None
    snapshot_id: str | None = None
    pulse_profile_hash: str | None = None
    limits: TargetLimits = field(default_factory=TargetLimits)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = TARGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        target_id = self.target_id.strip()
        if not target_id:
            raise TargetError("Target ID must be non-empty.")
        if not isinstance(self.topology, Topology):
            raise TargetError("Target topology must be a Topology instance.")
        if self.schema_version != TARGET_SCHEMA_VERSION:
            raise TargetError(f"Unsupported target schema: {self.schema_version}.")
        for label, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("snapshot_id", self.snapshot_id),
            ("pulse_profile_hash", self.pulse_profile_hash),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise TargetError(f"Target {label} must be a non-empty string or None.")
        if not isinstance(self.limits, TargetLimits):
            raise TargetError("Target limits must be a TargetLimits instance.")
        instructions = tuple(sorted(self.instructions, key=lambda item: item.name))
        if not instructions:
            raise TargetError("Target must declare at least one instruction.")
        if any(not isinstance(item, InstructionSupport) for item in instructions):
            raise TargetError("Target instructions must be InstructionSupport instances.")
        names = [item.name for item in instructions]
        if len(set(names)) != len(names):
            raise TargetError("Target instruction names must be unique.")
        for instruction in instructions:
            if instruction.locations is not None and any(
                any(qubit >= self.topology.qubit_count for qubit in location)
                for location in instruction.locations
            ):
                raise TargetError(
                    f"Instruction {instruction.name!r} references a qubit outside the topology."
                )
        if not isinstance(self.metadata, Mapping):
            raise TargetError("Target metadata must be a JSON object.")
        metadata = _thaw_json(self.metadata)
        try:
            _canonical_json(metadata)
        except (TypeError, ValueError) as error:
            raise TargetError("Target metadata must be JSON-serializable.") from error
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "provider", self.provider.strip() if self.provider else None)
        object.__setattr__(self, "model", self.model.strip() if self.model else None)
        object.__setattr__(
            self, "snapshot_id", self.snapshot_id.strip() if self.snapshot_id else None
        )
        object.__setattr__(
            self,
            "pulse_profile_hash",
            self.pulse_profile_hash.strip() if self.pulse_profile_hash else None,
        )
        object.__setattr__(self, "metadata", _freeze_json(metadata))

    @classmethod
    def testing(
        cls,
        qubits: int,
        *,
        topology: Topology | None = None,
        basis_gates: frozenset[str] | None = None,
        directed: bool = False,
        target_id: str = "qplanck.testing",
    ) -> Target:
        selected_topology = topology or Topology.complete(qubits, directed=directed)
        if selected_topology.qubit_count != qubits:
            raise TargetError("Testing target qubit count must match the supplied topology width.")
        gates = frozenset(SUPPORTED_GATES) if basis_gates is None else basis_gates
        unknown = sorted(gates - SUPPORTED_GATES.keys())
        if unknown:
            raise TargetError(f"Unknown testing target instructions: {unknown!r}.")
        return cls(
            target_id=target_id,
            topology=selected_topology,
            instructions=tuple(
                InstructionSupport(name, SUPPORTED_GATES[name].qubits) for name in sorted(gates)
            ),
            provider="qplanck",
            model="testing",
        )

    @property
    def qubit_count(self) -> int:
        return self.topology.qubit_count

    @property
    def basis_gates(self) -> frozenset[str]:
        return frozenset(item.name for item in self.instructions)

    def instruction(self, name: str) -> InstructionSupport | None:
        normalized = name.strip().lower()
        return next((item for item in self.instructions if item.name == normalized), None)

    def supports_operation(self, operation: Operation) -> bool:
        support = self.instruction(operation.name)
        if support is None or len(operation.qubits) != support.arity:
            return False
        qubits = operation.qubits
        if any(qubit >= self.qubit_count for qubit in qubits):
            return False
        if support.locations is not None:
            location = tuple(sorted(qubits)) if operation.name in {"cz", "swap"} else qubits
            return location in support.locations
        if len(qubits) == 1:
            return True
        if operation.name == "cx" and self.topology.directed:
            return self.topology.has_arc(qubits[0], qubits[1])
        return self.topology.has_weak_edge(qubits[0], qubits[1])

    @property
    def content_hash(self) -> str:
        return _sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_id": self.target_id,
            "provider": self.provider,
            "model": self.model,
            "snapshot_id": self.snapshot_id,
            "pulse_profile_hash": self.pulse_profile_hash,
            "topology": self.topology.to_dict(),
            "instructions": [item.to_dict() for item in self.instructions],
            "limits": self.limits.to_dict(),
            "metadata": _thaw_json(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Target:
        topology = data.get("topology")
        instructions = data.get("instructions")
        limits = data.get("limits", {})
        metadata = data.get("metadata", {})
        if not isinstance(topology, dict):
            raise TargetError("Target topology must be an object.")
        if not isinstance(instructions, list) or any(
            not isinstance(item, dict) for item in instructions
        ):
            raise TargetError("Target instructions must be a list of objects.")
        if not isinstance(limits, dict):
            raise TargetError("Target limits must be an object.")
        if not isinstance(metadata, dict):
            raise TargetError("Target metadata must be an object.")
        target_id = data.get("target_id")
        if not isinstance(target_id, str):
            raise TargetError("Target ID must be a string.")
        return cls(
            target_id=target_id,
            topology=Topology.from_dict(topology),
            instructions=tuple(InstructionSupport.from_dict(item) for item in instructions),
            provider=data.get("provider"),
            model=data.get("model"),
            snapshot_id=data.get("snapshot_id"),
            pulse_profile_hash=data.get("pulse_profile_hash"),
            limits=TargetLimits.from_dict(limits),
            metadata=metadata,
            schema_version=data.get("schema_version", TARGET_SCHEMA_VERSION),
        )


__all__ = [
    "InstructionSupport",
    "LAYOUT_SCHEMA_VERSION",
    "Layout",
    "LimitKind",
    "TARGET_SCHEMA_VERSION",
    "TOPOLOGY_SCHEMA_VERSION",
    "Target",
    "TargetLimit",
    "TargetLimits",
    "Topology",
]
