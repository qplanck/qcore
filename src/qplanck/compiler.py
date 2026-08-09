"""Typed Python adapter for QCore's deterministic compiler contracts.

The required Rust kernel owns static validation, O0/O1/O2 compilation,
canonical hashing, resource analysis, routing, basis lowering, and pass
evidence. The Python algorithms remain available only through the explicit
private ``_compile_reference`` differential/benchmark oracle.

Rotation elision uses :attr:`CompileOptions.angle_tolerance` as an absolute
zero tolerance after compatible rotations are summed. The default is ``0.0`` so
the standard pipeline removes only an exactly represented zero. A nonzero value
is an explicit approximation policy. The compiler never reduces angles modulo a
period.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qplanck._native import compile_ir as _native_compile_ir
from qplanck.circuit import Circuit
from qplanck.errors import CircuitError
from qplanck.ir import CircuitIR, MeasurementSpec, Operation, Parameter
from qplanck.routing import RoutingTrace, route
from qplanck.targets import Layout, Target

_SELF_INVERSE_GATES = frozenset({"h", "x", "y", "z", "cx", "cz", "swap"})
_ROTATION_GATES = frozenset({"rx", "ry", "rz"})
COMPILATION_TRACE_SCHEMA_VERSION = "qplanck.compilation.trace.v0.2"
COMPILED_CIRCUIT_SCHEMA_VERSION = "qplanck.compiled.v0.2"


@dataclass(frozen=True)
class CompileOptions:
    """Options for the deterministic reference pipeline.

    Level ``0`` validates and analyzes without changing the circuit.  Level
    ``1`` additionally enables exact self-inverse cancellation and compatible
    numeric rotation merging. Level ``2`` adds deterministic target placement,
    routing, and exact basis lowering. ``angle_tolerance`` only controls zero
    elision after a merge; it does not make unlike rotations compatible.
    """

    optimization_level: int = 1
    angle_tolerance: float = 0.0
    initial_layout: Layout | None = None
    routing_seed: int = 0
    placement_trials: int = 4
    max_inserted_swaps: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.optimization_level, bool) or self.optimization_level not in {0, 1, 2}:
            raise ValueError("optimization_level must be 0, 1, or 2.")
        if isinstance(self.angle_tolerance, bool):
            raise ValueError("angle_tolerance must be a finite, non-negative number.")
        tolerance = float(self.angle_tolerance)
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("angle_tolerance must be a finite, non-negative number.")
        object.__setattr__(self, "angle_tolerance", tolerance)

        if self.initial_layout is not None and not isinstance(self.initial_layout, Layout):
            raise TypeError("initial_layout must be a Layout or None.")
        if (
            isinstance(self.routing_seed, bool)
            or not isinstance(self.routing_seed, int)
            or not 0 <= self.routing_seed < 2**64
        ):
            raise ValueError("routing_seed must be an unsigned 64-bit integer.")
        if (
            isinstance(self.placement_trials, bool)
            or not isinstance(self.placement_trials, int)
            or self.placement_trials < 1
        ):
            raise ValueError("placement_trials must be a positive integer.")
        if self.max_inserted_swaps is not None and (
            isinstance(self.max_inserted_swaps, bool)
            or not isinstance(self.max_inserted_swaps, int)
            or self.max_inserted_swaps < 0
        ):
            raise ValueError("max_inserted_swaps must be a non-negative integer or None.")
        if self.optimization_level < 2 and (
            self.initial_layout is not None
            or self.routing_seed != 0
            or self.placement_trials != 4
            or self.max_inserted_swaps is not None
        ):
            raise ValueError("Routing options require optimization_level=2.")

    def to_dict(self) -> dict[str, object]:
        return {
            "optimization_level": self.optimization_level,
            "angle_tolerance": self.angle_tolerance,
            "initial_layout": (
                None if self.initial_layout is None else self.initial_layout.to_dict()
            ),
            "routing_seed": self.routing_seed,
            "placement_trials": self.placement_trials,
            "max_inserted_swaps": self.max_inserted_swaps,
        }


@dataclass(frozen=True)
class PassInfo:
    """Stable identity and analysis contract for a compiler pass."""

    id: str
    version: str
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    preserves: frozenset[str] = frozenset()
    deterministic: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("PassInfo.id must be non-empty.")
        if not self.version.strip():
            raise ValueError("PassInfo.version must be non-empty.")
        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "version", self.version.strip())
        object.__setattr__(self, "requires", frozenset(self.requires))
        object.__setattr__(self, "provides", frozenset(self.provides))
        object.__setattr__(self, "preserves", frozenset(self.preserves))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version,
            "requires": sorted(self.requires),
            "provides": sorted(self.provides),
            "preserves": sorted(self.preserves),
            "deterministic": self.deterministic,
        }


@dataclass(frozen=True)
class DependencyGraph:
    """Immutable operation dependency graph.

    Nodes are operation indices in source order.  An edge ``(a, b)`` means that
    ``b`` is the next operation after ``a`` on at least one of ``a``'s qubits.
    Consequently, operations on disjoint qubits do not receive an artificial
    dependency merely because one appears first in the serialized IR.
    """

    operation_count: int
    edges: tuple[tuple[int, int], ...] = ()
    predecessors: tuple[tuple[int, ...], ...] = field(init=False)
    successors: tuple[tuple[int, ...], ...] = field(init=False)

    def __post_init__(self) -> None:
        operation_count = int(self.operation_count)
        if operation_count < 0:
            raise ValueError("operation_count must be non-negative.")

        edges = tuple(sorted(set(self.edges)))
        predecessor_lists: list[list[int]] = [[] for _ in range(operation_count)]
        successor_lists: list[list[int]] = [[] for _ in range(operation_count)]
        for source, target in edges:
            if source < 0 or target < 0 or source >= operation_count or target >= operation_count:
                raise ValueError("Dependency edge references an unknown operation.")
            if source >= target:
                raise ValueError("Dependency edges must follow source operation order.")
            predecessor_lists[target].append(source)
            successor_lists[source].append(target)

        object.__setattr__(self, "operation_count", operation_count)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(
            self,
            "predecessors",
            tuple(tuple(items) for items in predecessor_lists),
        )
        object.__setattr__(
            self,
            "successors",
            tuple(tuple(items) for items in successor_lists),
        )

    @classmethod
    def from_ir(cls, ir: CircuitIR) -> DependencyGraph:
        """Build the canonical conflict graph for ``ir``."""

        last_on_qubit: dict[int, int] = {}
        edges: list[tuple[int, int]] = []
        for index, operation in enumerate(ir.operations):
            predecessors = {
                last_on_qubit[qubit] for qubit in operation.qubits if qubit in last_on_qubit
            }
            edges.extend((predecessor, index) for predecessor in sorted(predecessors))
            for qubit in sorted(set(operation.qubits)):
                last_on_qubit[qubit] = index
        return cls(operation_count=len(ir.operations), edges=tuple(edges))

    @property
    def nodes(self) -> tuple[int, ...]:
        """Return operation indices in their canonical topological order."""

        return tuple(range(self.operation_count))

    @property
    def depth(self) -> int:
        """Return gate depth implied by the dependency graph."""

        depths: list[int] = []
        for node in self.nodes:
            node_depth = 1 + max((depths[item] for item in self.predecessors[node]), default=0)
            depths.append(node_depth)
        return max(depths, default=0)

    def predecessors_of(self, node: int) -> tuple[int, ...]:
        """Return direct predecessors of an operation node."""

        return self.predecessors[node]

    def successors_of(self, node: int) -> tuple[int, ...]:
        """Return direct successors of an operation node."""

        return self.successors[node]

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_count": self.operation_count,
            "edges": [list(edge) for edge in self.edges],
        }


@dataclass(frozen=True)
class ResourceMetrics:
    """Deterministic structural metrics for a static circuit."""

    qubit_count: int
    operation_count: int
    measurement_count: int
    depth: int
    single_qubit_gate_count: int
    two_qubit_gate_count: int
    gate_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        numeric_fields = (
            self.qubit_count,
            self.operation_count,
            self.measurement_count,
            self.depth,
            self.single_qubit_gate_count,
            self.two_qubit_gate_count,
        )
        if any(value < 0 for value in numeric_fields):
            raise ValueError("Resource metrics must be non-negative.")
        counts = {str(name): int(count) for name, count in sorted(self.gate_counts.items())}
        if any(count < 0 for count in counts.values()):
            raise ValueError("Gate counts must be non-negative.")
        object.__setattr__(self, "gate_counts", MappingProxyType(counts))

    @classmethod
    def from_ir(
        cls,
        ir: CircuitIR,
        graph: DependencyGraph | None = None,
    ) -> ResourceMetrics:
        """Analyze ``ir`` without changing it."""

        dependency_graph = DependencyGraph.from_ir(ir) if graph is None else graph
        if dependency_graph.operation_count != len(ir.operations):
            raise ValueError("Dependency graph does not describe this circuit's operation count.")
        counts = Counter(operation.name for operation in ir.operations)
        return cls(
            qubit_count=ir.qubit_count,
            operation_count=len(ir.operations),
            measurement_count=len(ir.measurements),
            depth=dependency_graph.depth,
            single_qubit_gate_count=sum(len(operation.qubits) == 1 for operation in ir.operations),
            two_qubit_gate_count=sum(len(operation.qubits) == 2 for operation in ir.operations),
            gate_counts=dict(counts),
        )

    def gate_count(self, name: str) -> int:
        """Return the count for a normalized gate name."""

        return self.gate_counts.get(name.strip().lower(), 0)

    def to_dict(self) -> dict[str, object]:
        return {
            "qubit_count": self.qubit_count,
            "operation_count": self.operation_count,
            "measurement_count": self.measurement_count,
            "depth": self.depth,
            "single_qubit_gate_count": self.single_qubit_gate_count,
            "two_qubit_gate_count": self.two_qubit_gate_count,
            "gate_counts": dict(self.gate_counts),
        }


@dataclass(frozen=True)
class RewriteEvidence:
    """Operation-level provenance for a local compiler rewrite."""

    rule: str
    source_indices: tuple[int, ...]
    before: tuple[Operation, ...]
    after: tuple[Operation, ...]

    def __post_init__(self) -> None:
        if not self.rule.strip():
            raise ValueError("RewriteEvidence.rule must be non-empty.")
        object.__setattr__(self, "rule", self.rule.strip())
        object.__setattr__(self, "source_indices", tuple(self.source_indices))
        object.__setattr__(self, "before", tuple(self.before))
        object.__setattr__(self, "after", tuple(self.after))

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "source_indices": list(self.source_indices),
            "before": [operation.to_dict() for operation in self.before],
            "after": [operation.to_dict() for operation in self.after],
        }


@dataclass(frozen=True)
class CompilationEvent:
    """Deterministic evidence emitted for one compiler pass execution."""

    index: int
    pass_info: PassInfo
    input_ir_hash: str
    output_ir_hash: str
    changed: bool
    metrics_before: ResourceMetrics
    metrics_after: ResourceMetrics
    rewrites: tuple[RewriteEvidence, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("CompilationEvent.index must be non-negative.")
        if not self.input_ir_hash.startswith("sha256:"):
            raise ValueError("input_ir_hash must be a SHA-256 identity.")
        if not self.output_ir_hash.startswith("sha256:"):
            raise ValueError("output_ir_hash must be a SHA-256 identity.")
        object.__setattr__(self, "rewrites", tuple(self.rewrites))

    @property
    def pass_id(self) -> str:
        """Return the stable pass identifier."""

        return self.pass_info.id

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "pass": self.pass_info.to_dict(),
            "input_ir_hash": self.input_ir_hash,
            "output_ir_hash": self.output_ir_hash,
            "changed": self.changed,
            "metrics_before": self.metrics_before.to_dict(),
            "metrics_after": self.metrics_after.to_dict(),
            "rewrites": [rewrite.to_dict() for rewrite in self.rewrites],
            "message": self.message,
        }


@dataclass(frozen=True)
class CompilationTrace:
    """Pass-by-pass provenance for a compilation."""

    pipeline_id: str
    input_ir_hash: str
    output_ir_hash: str
    events: tuple[CompilationEvent, ...]
    schema_version: str = COMPILATION_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.pipeline_id.strip():
            raise ValueError("pipeline_id must be non-empty.")
        if self.schema_version != COMPILATION_TRACE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported compilation trace schema: {self.schema_version}.")
        events = tuple(self.events)
        if tuple(event.index for event in events) != tuple(range(len(events))):
            raise ValueError("Compilation event indices must be contiguous and ordered.")
        object.__setattr__(self, "pipeline_id", self.pipeline_id.strip())
        object.__setattr__(self, "events", events)

    @property
    def passes(self) -> tuple[PassInfo, ...]:
        """Return pass identities in execution order."""

        return tuple(event.pass_info for event in self.events)

    @property
    def changed(self) -> bool:
        """Whether any pass changed the circuit IR."""

        return any(event.changed for event in self.events)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pipeline_id": self.pipeline_id,
            "input_ir_hash": self.input_ir_hash,
            "output_ir_hash": self.output_ir_hash,
            "changed": self.changed,
            "events": [event.to_dict() for event in self.events],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class CompiledCircuit:
    """Immutable result of the deterministic compiler pipeline."""

    source_ir: CircuitIR
    ir: CircuitIR
    source_graph: DependencyGraph
    dependency_graph: DependencyGraph
    before_metrics: ResourceMetrics
    after_metrics: ResourceMetrics
    trace: CompilationTrace
    options: CompileOptions
    target: Target | None = None
    routed_ir: CircuitIR | None = None
    routed_metrics: ResourceMetrics | None = None
    initial_layout: Layout | None = None
    final_layout: Layout | None = None
    routing_trace: RoutingTrace | None = None
    native_implementation: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = COMPILED_CIRCUIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COMPILED_CIRCUIT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported compiled circuit schema: {self.schema_version}.")
        object.__setattr__(
            self,
            "native_implementation",
            MappingProxyType(dict(sorted(self.native_implementation.items()))),
        )
        routed_fields = (
            self.target,
            self.routed_ir,
            self.routed_metrics,
            self.initial_layout,
            self.final_layout,
            self.routing_trace,
        )
        if self.options.optimization_level == 2 and any(item is None for item in routed_fields):
            raise ValueError("O2 compiled circuits require target, layout, and routing artifacts.")
        if self.options.optimization_level < 2 and any(item is not None for item in routed_fields):
            raise ValueError("O0/O1 compiled circuits cannot contain routing artifacts.")

    @property
    def compiled_ir(self) -> CircuitIR:
        """Alias that makes the output IR role explicit."""

        return self.ir

    @property
    def graph(self) -> DependencyGraph:
        """Return the dependency graph for the compiled IR."""

        return self.dependency_graph

    @property
    def metrics(self) -> ResourceMetrics:
        """Return metrics for the compiled IR."""

        return self.after_metrics

    @property
    def target_hash(self) -> str | None:
        return None if self.target is None else self.target.content_hash

    @property
    def operations(self) -> tuple[Operation, ...]:
        """Return compiled operations."""

        return self.ir.operations

    @property
    def measurements(self) -> tuple[MeasurementSpec, ...]:
        """Return preserved terminal measurements."""

        return self.ir.measurements

    def to_circuit(self) -> Circuit:
        """Create a mutable public ``Circuit`` view of the compiled IR."""

        return Circuit.from_ir(self.ir)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_ir": self.source_ir.to_dict(),
            "compiled_ir": self.ir.to_dict(),
            "source_graph": self.source_graph.to_dict(),
            "compiled_graph": self.dependency_graph.to_dict(),
            "before_metrics": self.before_metrics.to_dict(),
            "after_metrics": self.after_metrics.to_dict(),
            "routed_ir": None if self.routed_ir is None else self.routed_ir.to_dict(),
            "routed_metrics": (
                None if self.routed_metrics is None else self.routed_metrics.to_dict()
            ),
            "target": None if self.target is None else self.target.to_dict(),
            "target_hash": self.target_hash,
            "initial_layout": (
                None if self.initial_layout is None else self.initial_layout.to_dict()
            ),
            "final_layout": None if self.final_layout is None else self.final_layout.to_dict(),
            "routing_trace": (None if self.routing_trace is None else self.routing_trace.to_dict()),
            "native_implementation": dict(self.native_implementation),
            "trace": self.trace.to_dict(),
            "options": self.options.to_dict(),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @property
    def content_hash(self) -> str:
        """Hash semantic compilation evidence, excluding native build identity."""

        payload = self.to_dict()
        payload.pop("native_implementation", None)
        encoded = json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


_VALIDATION_PASS = PassInfo(
    id="validate.static",
    version="1",
    provides=frozenset({"static-validity/v1"}),
    preserves=frozenset({"circuit-ir"}),
)
_LOCAL_OPTIMIZATION_PASS = PassInfo(
    id="opt.local-exact",
    version="1",
    requires=frozenset({"static-validity/v1"}),
    provides=frozenset({"local-rewrite-provenance/v1"}),
    preserves=frozenset({"qubit-count", "measurements", "circuit-metadata"}),
)
_ROUTING_PASS = PassInfo(
    id="route.target-deterministic",
    version="1",
    requires=frozenset({"static-validity/v1"}),
    provides=frozenset({"physical-layout/v1", "routing-provenance/v1"}),
    preserves=frozenset({"logical-semantics", "classical-bit-mapping"}),
)
_NATIVE_LOWERING_PASS = PassInfo(
    id="lower.target-basis-exact",
    version="1",
    requires=frozenset({"physical-layout/v1"}),
    provides=frozenset({"target-conformance/v1"}),
    preserves=frozenset({"logical-semantics", "classical-bit-mapping"}),
)
_RESOURCE_ANALYSIS_PASS = PassInfo(
    id="analyze.resources",
    version="1",
    requires=frozenset({"static-validity/v1"}),
    provides=frozenset({"structure.resources/v1"}),
    preserves=frozenset({"circuit-ir"}),
)


@dataclass
class _TrackedOperation:
    operation: Operation
    source_indices: tuple[int, ...]
    rotation_terms: tuple[float, ...] = ()


def _ir_hash(ir: CircuitIR) -> str:
    payload = ir.to_json().encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _validate_ir(ir: CircuitIR) -> None:
    if ir.schema_version != CircuitIR.SUPPORTED_SCHEMA:
        raise CircuitError(f"Unsupported IR schema version: {ir.schema_version}.")

    # Reuse the public API's gate arity, qubit, parameter, and terminal
    # measurement checks so compilation cannot drift from Circuit semantics.
    Circuit.from_ir(ir)
    for operation_index, operation in enumerate(ir.operations):
        for parameter in operation.params:
            if isinstance(parameter, Parameter) or not math.isfinite(parameter):
                raise CircuitError(
                    "Compiler requires finite numeric gate parameters; "
                    f"operation {operation_index} ({operation.name!r}) is invalid."
                )
    try:
        ir.to_json()
    except (TypeError, ValueError) as error:
        raise CircuitError("Circuit IR metadata must be JSON-serializable.") from error


def _candidate_slot(
    operation: Operation,
    qubit_history: dict[int, list[int]],
) -> int | None:
    slots: list[int] = []
    for qubit in operation.qubits:
        history = qubit_history[qubit]
        if not history:
            return None
        slots.append(history[-1])
    if slots and all(slot == slots[0] for slot in slots):
        return slots[0]
    return None


def _same_rewrite_boundary(left: Operation, right: Operation) -> bool:
    return (
        left.name == right.name and left.qubits == right.qubits and left.metadata == right.metadata
    )


def _remove_slot(
    slot: int,
    tracked: _TrackedOperation,
    live_operations: list[_TrackedOperation | None],
    qubit_history: dict[int, list[int]],
) -> None:
    for qubit in tracked.operation.qubits:
        history = qubit_history[qubit]
        if not history or history[-1] != slot:
            raise RuntimeError("Compiler dependency history is inconsistent.")
        history.pop()
    live_operations[slot] = None


def _finite_sum(values: tuple[float, ...]) -> float | None:
    try:
        result = math.fsum(values)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _rotation_angle(operation: Operation) -> float:
    parameter = operation.params[0]
    if isinstance(parameter, Parameter):
        raise RuntimeError("Validated rotation unexpectedly contains a symbolic parameter.")
    return float(parameter)


def _optimize_local(
    ir: CircuitIR,
    options: CompileOptions,
) -> tuple[CircuitIR, tuple[RewriteEvidence, ...]]:
    live_operations: list[_TrackedOperation | None] = []
    qubit_history: dict[int, list[int]] = {qubit: [] for qubit in range(ir.qubit_count)}
    rewrites: list[RewriteEvidence] = []

    for source_index, operation in enumerate(ir.operations):
        slot = _candidate_slot(operation, qubit_history)
        candidate = live_operations[slot] if slot is not None else None
        if (
            slot is not None
            and candidate is not None
            and _same_rewrite_boundary(candidate.operation, operation)
        ):
            source_indices = (*candidate.source_indices, source_index)
            if operation.name in _SELF_INVERSE_GATES:
                rewrites.append(
                    RewriteEvidence(
                        rule="self-inverse-adjacent",
                        source_indices=source_indices,
                        before=(candidate.operation, operation),
                        after=(),
                    )
                )
                _remove_slot(slot, candidate, live_operations, qubit_history)
                continue

            if operation.name in _ROTATION_GATES:
                current_angle = _rotation_angle(operation)
                terms = (*candidate.rotation_terms, current_angle)
                merged_angle = _finite_sum(terms)
                if merged_angle is not None:
                    if abs(merged_angle) <= options.angle_tolerance:
                        rewrites.append(
                            RewriteEvidence(
                                rule="remove-near-zero-rotation",
                                source_indices=source_indices,
                                before=(candidate.operation, operation),
                                after=(),
                            )
                        )
                        _remove_slot(slot, candidate, live_operations, qubit_history)
                        continue

                    merged = Operation(
                        operation.name,
                        operation.qubits,
                        (merged_angle,),
                        metadata=operation.metadata,
                    )
                    rewrites.append(
                        RewriteEvidence(
                            rule="merge-adjacent-rotation",
                            source_indices=source_indices,
                            before=(candidate.operation, operation),
                            after=(merged,),
                        )
                    )
                    live_operations[slot] = _TrackedOperation(
                        operation=merged,
                        source_indices=source_indices,
                        rotation_terms=terms,
                    )
                    continue

        rotation_terms: tuple[float, ...] = ()
        if operation.name in _ROTATION_GATES:
            rotation_terms = (_rotation_angle(operation),)
        new_slot = len(live_operations)
        live_operations.append(
            _TrackedOperation(
                operation=operation,
                source_indices=(source_index,),
                rotation_terms=rotation_terms,
            )
        )
        for qubit in operation.qubits:
            qubit_history[qubit].append(new_slot)

    optimized = CircuitIR(
        qubit_count=ir.qubit_count,
        operations=tuple(tracked.operation for tracked in live_operations if tracked is not None),
        measurements=ir.measurements,
        metadata=ir.metadata,
        schema_version=ir.schema_version,
    )
    return optimized, tuple(rewrites)


def _coerce_ir(circuit_or_ir: Circuit | CircuitIR) -> CircuitIR:
    if isinstance(circuit_or_ir, Circuit):
        return circuit_or_ir.ir
    if isinstance(circuit_or_ir, CircuitIR):
        return circuit_or_ir
    raise TypeError("compile() expects a qplanck.Circuit or qplanck.ir.CircuitIR.")


def _graph_from_native(data: Mapping[str, Any]) -> DependencyGraph:
    raw_edges = data.get("edges", [])
    edges: list[tuple[int, int]] = []
    for edge in raw_edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("Native dependency edges must contain two operation indices.")
        edges.append((int(edge[0]), int(edge[1])))
    return DependencyGraph(
        operation_count=int(data["operation_count"]),
        edges=tuple(edges),
    )


def _metrics_from_native(data: Mapping[str, Any]) -> ResourceMetrics:
    return ResourceMetrics(
        qubit_count=int(data["qubit_count"]),
        operation_count=int(data["operation_count"]),
        measurement_count=int(data["measurement_count"]),
        depth=int(data["depth"]),
        single_qubit_gate_count=int(data["single_qubit_gate_count"]),
        two_qubit_gate_count=int(data["two_qubit_gate_count"]),
        gate_counts={str(key): int(value) for key, value in data["gate_counts"].items()},
    )


def _event_from_native(data: Mapping[str, Any]) -> CompilationEvent:
    raw_pass = data["pass"]
    pass_info = PassInfo(
        id=str(raw_pass["id"]),
        version=str(raw_pass["version"]),
        requires=frozenset(str(item) for item in raw_pass.get("requires", [])),
        provides=frozenset(str(item) for item in raw_pass.get("provides", [])),
        preserves=frozenset(str(item) for item in raw_pass.get("preserves", [])),
        deterministic=bool(raw_pass.get("deterministic", True)),
    )
    rewrites = tuple(
        RewriteEvidence(
            rule=str(item["rule"]),
            source_indices=tuple(int(index) for index in item["source_indices"]),
            before=tuple(Operation.from_dict(operation) for operation in item["before"]),
            after=tuple(Operation.from_dict(operation) for operation in item["after"]),
        )
        for item in data.get("rewrites", [])
    )
    return CompilationEvent(
        index=int(data["index"]),
        pass_info=pass_info,
        input_ir_hash=str(data["input_ir_hash"]),
        output_ir_hash=str(data["output_ir_hash"]),
        changed=bool(data["changed"]),
        metrics_before=_metrics_from_native(data["metrics_before"]),
        metrics_after=_metrics_from_native(data["metrics_after"]),
        rewrites=rewrites,
        message=str(data.get("message", "")),
    )


def _compile_native(
    source_ir: CircuitIR,
    options: CompileOptions,
    target: Target | None,
) -> CompiledCircuit:
    try:
        ir_json = source_ir.to_json()
    except (TypeError, ValueError) as error:
        raise CircuitError("Circuit IR metadata must be JSON-serializable.") from error
    response = _native_compile_ir(
        ir_json,
        options.to_dict(),
        target=None if target is None else target.to_dict(),
    )
    parsed_ir = CircuitIR.from_dict(response["compiled_ir"])
    compiled_ir = source_ir if parsed_ir.to_dict() == source_ir.to_dict() else parsed_ir
    events = tuple(_event_from_native(item) for item in response["events"])
    trace = CompilationTrace(
        pipeline_id=str(response["pipeline_id"]),
        input_ir_hash=str(response["input_ir_hash"]),
        output_ir_hash=str(response["output_ir_hash"]),
        events=events,
    )
    implementation = response.get("implementation", {})
    routed_payload = response.get("routed_ir")
    routed_metrics_payload = response.get("routed_metrics")
    initial_layout_payload = response.get("initial_layout")
    final_layout_payload = response.get("final_layout")
    routing_trace_payload = response.get("routing_trace")
    return CompiledCircuit(
        source_ir=source_ir,
        ir=compiled_ir,
        source_graph=_graph_from_native(response["source_graph"]),
        dependency_graph=_graph_from_native(response["compiled_graph"]),
        before_metrics=_metrics_from_native(response["before_metrics"]),
        after_metrics=_metrics_from_native(response["after_metrics"]),
        trace=trace,
        options=options,
        target=target,
        routed_ir=(None if routed_payload is None else CircuitIR.from_dict(routed_payload)),
        routed_metrics=(
            None if routed_metrics_payload is None else _metrics_from_native(routed_metrics_payload)
        ),
        initial_layout=(
            None
            if initial_layout_payload is None
            else Layout(tuple(initial_layout_payload["logical_to_physical"]))
        ),
        final_layout=(
            None
            if final_layout_payload is None
            else Layout(tuple(final_layout_payload["logical_to_physical"]))
        ),
        routing_trace=(
            None if routing_trace_payload is None else RoutingTrace.from_dict(routing_trace_payload)
        ),
        native_implementation={str(key): str(value) for key, value in implementation.items()},
    )


def compile(
    circuit_or_ir: Circuit | CircuitIR,
    options: CompileOptions | None = None,
    *,
    target: Target | None = None,
) -> CompiledCircuit:
    """Compile a circuit with the deterministic O0/O1/O2 pipeline.

    The input is never mutated.  Measurements and circuit metadata are copied to
    the output IR unchanged.  Annotated operations are rewritten only when both
    candidates carry equal metadata, preventing a merge from silently choosing
    between different annotations. O2 requires an explicit immutable target.
    """

    compile_options = CompileOptions() if options is None else options
    if not isinstance(compile_options, CompileOptions):
        raise TypeError("options must be a CompileOptions instance.")
    if target is not None and not isinstance(target, Target):
        raise TypeError("target must be a Target or None.")
    if compile_options.optimization_level == 2 and target is None:
        raise ValueError("optimization_level=2 requires a target.")
    if compile_options.optimization_level < 2 and target is not None:
        raise ValueError("A target is accepted only with optimization_level=2.")
    source_ir = _coerce_ir(circuit_or_ir)
    return _compile_native(source_ir, compile_options, target)


def _compile_reference(
    circuit_or_ir: Circuit | CircuitIR,
    options: CompileOptions | None = None,
    *,
    target: Target | None = None,
) -> CompiledCircuit:
    """Run the frozen Python oracle without touching the production native path."""

    compile_options = CompileOptions() if options is None else options
    if not isinstance(compile_options, CompileOptions):
        raise TypeError("options must be a CompileOptions instance.")
    if target is not None and not isinstance(target, Target):
        raise TypeError("target must be a Target or None.")
    if compile_options.optimization_level == 2 and target is None:
        raise ValueError("optimization_level=2 requires a target.")
    if compile_options.optimization_level < 2 and target is not None:
        raise ValueError("A target is accepted only with optimization_level=2.")
    source_ir = _coerce_ir(circuit_or_ir)
    _validate_ir(source_ir)

    source_graph = DependencyGraph.from_ir(source_ir)
    before_metrics = ResourceMetrics.from_ir(source_ir, source_graph)
    source_hash = _ir_hash(source_ir)
    events: list[CompilationEvent] = [
        CompilationEvent(
            index=0,
            pass_info=_VALIDATION_PASS,
            input_ir_hash=source_hash,
            output_ir_hash=source_hash,
            changed=False,
            metrics_before=before_metrics,
            metrics_after=before_metrics,
            message="Static gate, parameter, qubit, schema, and measurement validation passed.",
        )
    ]

    compiled_ir = source_ir
    if compile_options.optimization_level >= 1:
        optimized_ir, rewrites = _optimize_local(source_ir, compile_options)
        optimized_graph = DependencyGraph.from_ir(optimized_ir)
        optimized_metrics = ResourceMetrics.from_ir(optimized_ir, optimized_graph)
        optimized_hash = _ir_hash(optimized_ir)
        events.append(
            CompilationEvent(
                index=len(events),
                pass_info=_LOCAL_OPTIMIZATION_PASS,
                input_ir_hash=source_hash,
                output_ir_hash=optimized_hash,
                changed=optimized_hash != source_hash,
                metrics_before=before_metrics,
                metrics_after=optimized_metrics,
                rewrites=rewrites,
                message=f"Applied {len(rewrites)} conservative local rewrite(s).",
            )
        )
        compiled_ir = optimized_ir

    routed_ir: CircuitIR | None = None
    routed_metrics: ResourceMetrics | None = None
    initial_layout: Layout | None = None
    final_layout: Layout | None = None
    routing_trace: RoutingTrace | None = None
    if compile_options.optimization_level == 2:
        if target is None:  # pragma: no cover - narrowed above for type checkers
            raise RuntimeError("O2 target validation was bypassed.")
        pre_route_graph = DependencyGraph.from_ir(compiled_ir)
        pre_route_metrics = ResourceMetrics.from_ir(compiled_ir, pre_route_graph)
        pre_route_hash = _ir_hash(compiled_ir)
        routing_result = route(
            compiled_ir,
            target,
            initial_layout=compile_options.initial_layout,
            routing_seed=compile_options.routing_seed,
            placement_trials=compile_options.placement_trials,
            max_inserted_swaps=compile_options.max_inserted_swaps,
        )
        routed_ir = routing_result.routed_ir
        routed_graph = DependencyGraph.from_ir(routed_ir)
        routed_metrics = ResourceMetrics.from_ir(routed_ir, routed_graph)
        routed_hash = _ir_hash(routed_ir)
        events.append(
            CompilationEvent(
                index=len(events),
                pass_info=_ROUTING_PASS,
                input_ir_hash=pre_route_hash,
                output_ir_hash=routed_hash,
                changed=routed_hash != pre_route_hash,
                metrics_before=pre_route_metrics,
                metrics_after=routed_metrics,
                message=(
                    f"Selected deterministic routing trial with "
                    f"{len(routing_result.trace.steps)} inserted SWAP(s)."
                ),
            )
        )

        final_ir = routing_result.final_ir
        final_graph = DependencyGraph.from_ir(final_ir)
        final_metrics = ResourceMetrics.from_ir(final_ir, final_graph)
        final_hash = _ir_hash(final_ir)
        events.append(
            CompilationEvent(
                index=len(events),
                pass_info=_NATIVE_LOWERING_PASS,
                input_ir_hash=routed_hash,
                output_ir_hash=final_hash,
                changed=final_hash != routed_hash,
                metrics_before=routed_metrics,
                metrics_after=final_metrics,
                message="Lowered routed operations exactly into the target instruction basis.",
            )
        )
        compiled_ir = final_ir
        initial_layout = routing_result.initial_layout
        final_layout = routing_result.final_layout
        routing_trace = routing_result.trace

    dependency_graph = DependencyGraph.from_ir(compiled_ir)
    after_metrics = ResourceMetrics.from_ir(compiled_ir, dependency_graph)
    output_hash = _ir_hash(compiled_ir)
    events.append(
        CompilationEvent(
            index=len(events),
            pass_info=_RESOURCE_ANALYSIS_PASS,
            input_ir_hash=output_hash,
            output_ir_hash=output_hash,
            changed=False,
            metrics_before=after_metrics,
            metrics_after=after_metrics,
            message="Collected deterministic gate counts and dependency depth.",
        )
    )

    trace = CompilationTrace(
        pipeline_id=f"qplanck.default-o{compile_options.optimization_level}.v1",
        input_ir_hash=source_hash,
        output_ir_hash=output_hash,
        events=tuple(events),
    )
    return CompiledCircuit(
        source_ir=source_ir,
        ir=compiled_ir,
        source_graph=source_graph,
        dependency_graph=dependency_graph,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        trace=trace,
        options=compile_options,
        target=target,
        routed_ir=routed_ir,
        routed_metrics=routed_metrics,
        initial_layout=initial_layout,
        final_layout=final_layout,
        routing_trace=routing_trace,
    )


__all__ = [
    "CompilationEvent",
    "CompilationTrace",
    "CompileOptions",
    "CompiledCircuit",
    "DependencyGraph",
    "PassInfo",
    "ResourceMetrics",
    "RewriteEvidence",
    "compile",
]
