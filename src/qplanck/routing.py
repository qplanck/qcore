"""Deterministic target-aware placement, routing, and basis lowering.

This module is also the readable reference for the required native kernel.  The
production compiler invokes the Rust implementation; differential tests keep
the two implementations behaviorally aligned.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from qplanck.errors import RoutingError, TargetError
from qplanck.ir import CircuitIR, MeasurementSpec, Operation
from qplanck.targets import Layout, Target, Topology

ROUTING_TRACE_SCHEMA_VERSION = "qplanck.routing.trace.v0.1"


def _ir_hash(ir: CircuitIR) -> str:
    return f"sha256:{hashlib.sha256(ir.to_json().encode('utf-8')).hexdigest()}"


def _canonical_edge(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


@dataclass(frozen=True)
class RoutingStep:
    index: int
    physical_edge: tuple[int, int]
    trigger_source_indices: tuple[int, ...]
    layout_before: Layout
    layout_after: Layout
    reason: Literal["heuristic", "release-valve", "canonical-baseline"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "physical_edge": list(self.physical_edge),
            "trigger_source_indices": list(self.trigger_source_indices),
            "layout_before": self.layout_before.to_dict(),
            "layout_after": self.layout_after.to_dict(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingStep:
        physical_edge = data["physical_edge"]
        if not isinstance(physical_edge, list) or len(physical_edge) != 2:
            raise ValueError("Routing step physical_edge must contain two qubits.")
        return cls(
            index=int(data["index"]),
            physical_edge=(int(physical_edge[0]), int(physical_edge[1])),
            trigger_source_indices=tuple(
                int(item) for item in data.get("trigger_source_indices", [])
            ),
            layout_before=Layout(tuple(data["layout_before"]["logical_to_physical"])),
            layout_after=Layout(tuple(data["layout_after"]["logical_to_physical"])),
            reason=data["reason"],
        )


@dataclass(frozen=True)
class RoutingTrial:
    trial: int
    seed: int
    initial_layout: Layout
    final_layout: Layout
    inserted_swaps: int
    routed_depth: int
    two_qubit_depth: int
    selected: bool = False
    baseline: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial": self.trial,
            "seed": self.seed,
            "initial_layout": self.initial_layout.to_dict(),
            "final_layout": self.final_layout.to_dict(),
            "inserted_swaps": self.inserted_swaps,
            "routed_depth": self.routed_depth,
            "two_qubit_depth": self.two_qubit_depth,
            "selected": self.selected,
            "baseline": self.baseline,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingTrial:
        return cls(
            trial=int(data["trial"]),
            seed=int(data["seed"]),
            initial_layout=Layout(tuple(data["initial_layout"]["logical_to_physical"])),
            final_layout=Layout(tuple(data["final_layout"]["logical_to_physical"])),
            inserted_swaps=int(data["inserted_swaps"]),
            routed_depth=int(data["routed_depth"]),
            two_qubit_depth=int(data["two_qubit_depth"]),
            selected=bool(data.get("selected", False)),
            baseline=bool(data.get("baseline", False)),
        )


@dataclass(frozen=True)
class RoutingTrace:
    initial_layout: Layout
    final_layout: Layout
    steps: tuple[RoutingStep, ...]
    trials: tuple[RoutingTrial, ...]
    source_to_routed_indices: tuple[tuple[int, ...], ...]
    routed_to_final_indices: tuple[tuple[int, ...], ...]
    measurement_map: tuple[tuple[int, int, int], ...]
    schema_version: str = ROUTING_TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "initial_layout": self.initial_layout.to_dict(),
            "final_layout": self.final_layout.to_dict(),
            "steps": [item.to_dict() for item in self.steps],
            "trials": [item.to_dict() for item in self.trials],
            "source_to_routed_indices": [list(item) for item in self.source_to_routed_indices],
            "routed_to_final_indices": [list(item) for item in self.routed_to_final_indices],
            "measurement_map": [
                {"logical_qubit": logical, "physical_qubit": physical, "classical_bit": cbit}
                for logical, physical, cbit in self.measurement_map
            ],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingTrace:
        measurement_map = tuple(
            (
                int(item["logical_qubit"]),
                int(item["physical_qubit"]),
                int(item["classical_bit"]),
            )
            for item in data.get("measurement_map", [])
        )
        return cls(
            initial_layout=Layout(tuple(data["initial_layout"]["logical_to_physical"])),
            final_layout=Layout(tuple(data["final_layout"]["logical_to_physical"])),
            steps=tuple(RoutingStep.from_dict(item) for item in data.get("steps", [])),
            trials=tuple(RoutingTrial.from_dict(item) for item in data.get("trials", [])),
            source_to_routed_indices=tuple(
                tuple(int(index) for index in item)
                for item in data.get("source_to_routed_indices", [])
            ),
            routed_to_final_indices=tuple(
                tuple(int(index) for index in item)
                for item in data.get("routed_to_final_indices", [])
            ),
            measurement_map=measurement_map,
            schema_version=str(data.get("schema_version", ROUTING_TRACE_SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class RoutingResult:
    routed_ir: CircuitIR
    final_ir: CircuitIR
    initial_layout: Layout
    final_layout: Layout
    trace: RoutingTrace


@dataclass
class _TrialResult:
    trial: int
    seed: int
    initial_layout: Layout
    final_layout: Layout
    routed_ir: CircuitIR
    steps: tuple[RoutingStep, ...]
    source_to_routed_indices: tuple[tuple[int, ...], ...]
    inserted_swaps: int
    routed_depth: int
    two_qubit_depth: int
    baseline: bool


def route(
    ir: CircuitIR,
    target: Target,
    *,
    initial_layout: Layout | None = None,
    routing_seed: int = 0,
    placement_trials: int = 4,
    max_inserted_swaps: int | None = None,
) -> RoutingResult:
    """Place, route, and exactly lower a static circuit for ``target``."""

    if not isinstance(ir, CircuitIR):
        raise TypeError("route() expects a CircuitIR.")
    if not isinstance(target, Target):
        raise TypeError("route() expects a Target.")
    if (
        isinstance(routing_seed, bool)
        or not isinstance(routing_seed, int)
        or not 0 <= routing_seed < 2**64
    ):
        raise RoutingError("routing_seed must be an unsigned 64-bit integer.")
    if (
        isinstance(placement_trials, bool)
        or not isinstance(placement_trials, int)
        or placement_trials < 1
    ):
        raise RoutingError("placement_trials must be a positive integer.")
    if max_inserted_swaps is not None and (
        isinstance(max_inserted_swaps, bool)
        or not isinstance(max_inserted_swaps, int)
        or max_inserted_swaps < 0
    ):
        raise RoutingError("max_inserted_swaps must be a non-negative integer or None.")
    if ir.qubit_count > target.qubit_count:
        raise RoutingError(
            f"Circuit width {ir.qubit_count} exceeds target width {target.qubit_count}."
        )

    _validate_routing_feasibility(ir, target)
    if initial_layout is not None:
        initial_layout.validate(
            logical_qubits=ir.qubit_count,
            physical_qubits=target.qubit_count,
        )

    source_hash = _ir_hash(ir)
    greedy = initial_layout or _interaction_greedy_layout(ir, target)
    source_two_qubit_count = sum(len(operation.qubits) == 2 for operation in ir.operations)
    default_budget = max(
        64,
        8 * max(1, source_two_qubit_count) * max(1, target.topology.diameter),
    )
    resolved_budget = max_inserted_swaps if max_inserted_swaps is not None else default_budget
    candidates: list[Layout] = []
    for trial in range(placement_trials):
        if initial_layout is not None:
            candidate = initial_layout
        elif trial == 0:
            candidate = greedy
        elif trial == 1 and _layout_connects_components(
            Layout.identity(ir.qubit_count), ir, target
        ):
            candidate = Layout.identity(ir.qubit_count)
        else:
            candidate = _hashed_layout(ir, target, routing_seed, trial, source_hash)
        if initial_layout is None:
            candidate = _refine_layout(
                ir,
                target,
                candidate,
                trial=trial,
                seed=routing_seed,
                swap_budget=default_budget,
                rounds=2,
            )
        candidates.append(candidate)

    results: list[_TrialResult] = []
    for trial, candidate in enumerate(candidates):
        results.append(
            _route_trial(
                ir,
                target,
                candidate,
                trial=trial,
                seed=routing_seed,
                swap_budget=resolved_budget,
                baseline=False,
            )
        )
    results.append(
        _route_trial(
            ir,
            target,
            greedy,
            trial=placement_trials,
            seed=routing_seed,
            swap_budget=resolved_budget,
            baseline=True,
        )
    )

    winner = min(
        results,
        key=lambda item: (
            item.inserted_swaps,
            item.two_qubit_depth,
            item.routed_depth,
            _ir_hash(item.routed_ir),
            item.trial,
        ),
    )
    final_ir, routed_to_final = _lower_to_target_basis(winner.routed_ir, target)
    trials = tuple(
        RoutingTrial(
            trial=item.trial,
            seed=item.seed,
            initial_layout=item.initial_layout,
            final_layout=item.final_layout,
            inserted_swaps=item.inserted_swaps,
            routed_depth=item.routed_depth,
            two_qubit_depth=item.two_qubit_depth,
            selected=item is winner,
            baseline=item.baseline,
        )
        for item in results
    )
    measurement_map = tuple(
        (
            measurement.qubit,
            winner.final_layout.logical_to_physical[measurement.qubit],
            measurement.cbit,
        )
        for measurement in ir.measurements
    )
    trace = RoutingTrace(
        initial_layout=winner.initial_layout,
        final_layout=winner.final_layout,
        steps=winner.steps,
        trials=trials,
        source_to_routed_indices=winner.source_to_routed_indices,
        routed_to_final_indices=routed_to_final,
        measurement_map=measurement_map,
    )
    return RoutingResult(
        routed_ir=winner.routed_ir,
        final_ir=final_ir,
        initial_layout=winner.initial_layout,
        final_layout=winner.final_layout,
        trace=trace,
    )


def _validate_routing_feasibility(ir: CircuitIR, target: Target) -> None:
    _component_assignment_indices(ir, target.topology)

    for operation in ir.operations:
        if len(operation.qubits) > 2:
            raise RoutingError("The O2 router supports only one- and two-qubit operations.")
        if len(operation.qubits) == 1 and operation.name not in target.basis_gates:
            raise RoutingError(f"Target cannot exactly lower single-qubit gate {operation.name!r}.")
        if len(operation.qubits) == 2 and operation.name not in {"cx", "cz", "swap"}:
            raise RoutingError(f"Target cannot route unsupported gate {operation.name!r}.")
    for edge in target.topology.edges:
        if not _can_lower_swap(target, *edge):
            raise RoutingError(
                f"Target basis cannot implement an exact SWAP on topology edge {edge}."
            )


def _logical_components(ir: CircuitIR) -> tuple[tuple[int, ...], ...]:
    neighbors: dict[int, set[int]] = {index: set() for index in range(ir.qubit_count)}
    for operation in ir.operations:
        if len(operation.qubits) == 2:
            left, right = operation.qubits
            neighbors[left].add(right)
            neighbors[right].add(left)
    remaining = set(neighbors)
    components: list[tuple[int, ...]] = []
    while remaining:
        start = min(remaining)
        pending = [start]
        found = {start}
        while pending:
            current = pending.pop()
            for neighbor in sorted(neighbors[current]):
                if neighbor not in found:
                    found.add(neighbor)
                    pending.append(neighbor)
        remaining.difference_update(found)
        components.append(tuple(sorted(found)))
    return tuple(sorted(components, key=lambda item: (-len(item), item[0])))


def _component_assignment_indices(ir: CircuitIR, topology: Topology) -> tuple[int, ...]:
    """Exactly assign logical components to disconnected physical components.

    Best-fit decreasing is not complete for this bin-packing problem.  The exact
    search retains its deterministic best-fit ordering, memoizes failed capacity
    states, and skips only capacity-symmetric branches.
    """

    logical_components = _logical_components(ir)
    physical_components = tuple(sorted(topology.components, key=lambda item: item[0]))
    remaining = [len(component) for component in physical_components]
    assignments = [-1] * len(logical_components)
    failed: set[tuple[int, tuple[int, ...]]] = set()

    def assign(index: int) -> bool:
        if index == len(logical_components):
            return True
        state = (index, tuple(remaining))
        if state in failed:
            return False

        required = len(logical_components[index])
        candidates = sorted(
            (position for position, capacity in enumerate(remaining) if capacity >= required),
            key=lambda position: (
                remaining[position] - required,
                physical_components[position][0],
            ),
        )
        seen_capacities: set[int] = set()
        for position in candidates:
            capacity = remaining[position]
            if capacity in seen_capacities:
                continue
            seen_capacities.add(capacity)
            remaining[position] -= required
            assignments[index] = position
            if assign(index + 1):
                return True
            assignments[index] = -1
            remaining[position] = capacity

        failed.add(state)
        return False

    if not assign(0):
        raise RoutingError(
            "Logical interaction components cannot fit the target's disconnected topology."
        )
    return tuple(assignments)


def _component_assignments(ir: CircuitIR, topology: Topology) -> dict[int, tuple[int, ...]]:
    physical_components = tuple(sorted(topology.components, key=lambda item: item[0]))
    assignment_indices = _component_assignment_indices(ir, topology)
    return {
        logical_index: physical_components[physical_index]
        for logical_index, physical_index in enumerate(assignment_indices)
    }


def _interaction_weights(ir: CircuitIR) -> Counter[tuple[int, int]]:
    return Counter(
        _canonical_edge(operation.qubits[0], operation.qubits[1])
        for operation in ir.operations
        if len(operation.qubits) == 2
    )


def _interaction_greedy_layout(ir: CircuitIR, target: Target) -> Layout:
    logical_components = _logical_components(ir)
    assignments = _component_assignments(ir, target.topology)
    weights = _interaction_weights(ir)
    mapped: dict[int, int] = {}
    used: set[int] = set()

    for component_index, component in enumerate(logical_components):
        allowed = set(assignments[component_index]) - used
        if len(allowed) < len(component):
            raise RoutingError(
                "Logical interaction components cannot fit the target's disconnected topology."
            )

        def weighted_degree(logical: int) -> int:
            return sum(weight for edge, weight in weights.items() if logical in edge)

        def distinct_neighbors(logical: int) -> int:
            return sum(1 for edge in weights if logical in edge)

        seed = max(
            component, key=lambda item: (weighted_degree(item), distinct_neighbors(item), -item)
        )

        def eccentricity(physical: int, allowed: set[int] = allowed) -> int:
            return max((target.topology.distance(physical, item) for item in allowed), default=0)

        seed_physical = min(
            allowed,
            key=lambda item: (
                eccentricity(item),
                -len(target.topology.neighbors(item, weak=True)),
                item,
            ),
        )
        mapped[seed] = seed_physical
        used.add(seed_physical)

        while any(logical not in mapped for logical in component):
            unmapped = [logical for logical in component if logical not in mapped]

            def weight_to_mapped(logical: int) -> int:
                return sum(weights.get(_canonical_edge(logical, other), 0) for other in mapped)

            logical = max(
                unmapped,
                key=lambda item: (weight_to_mapped(item), weighted_degree(item), -item),
            )
            physical_candidates = sorted(allowed - used)

            def placement_cost(
                physical: int,
                logical: int = logical,
                component: tuple[int, ...] = component,
            ) -> tuple[int, int, int, int]:
                distance_cost = sum(
                    weights.get(_canonical_edge(logical, other), 0)
                    * target.topology.distance(physical, mapped[other])
                    for other in mapped
                    if other in component
                )
                return (
                    distance_cost,
                    eccentricity(physical),
                    -len(target.topology.neighbors(physical, weak=True)),
                    physical,
                )

            selected = min(physical_candidates, key=placement_cost)
            mapped[logical] = selected
            used.add(selected)

    return Layout(tuple(mapped[index] for index in range(ir.qubit_count)))


def _hashed_layout(
    ir: CircuitIR,
    target: Target,
    seed: int,
    trial: int,
    source_hash: str,
) -> Layout:
    logical_components = _logical_components(ir)
    assignments = _component_assignments(ir, target.topology)
    used: set[int] = set()
    mapped: dict[int, int] = {}
    for component_index, component in enumerate(logical_components):
        allowed = set(assignments[component_index]) - used
        if len(allowed) < len(component):
            raise RoutingError("Hashed placement could not embed a logical component.")

        def key(physical: int) -> str:
            payload = f"{seed}:{trial}:{target.content_hash}:{source_hash}:{physical}"
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()

        selected = sorted(allowed, key=lambda item: (key(item), item))[: len(component)]
        logical_order = sorted(
            component,
            key=lambda item: (
                hashlib.sha256(f"{seed}:{trial}:logical:{item}".encode()).hexdigest(),
                item,
            ),
        )
        for logical, physical in zip(logical_order, selected, strict=True):
            mapped[logical] = physical
            used.add(physical)
    return Layout(tuple(mapped[index] for index in range(ir.qubit_count)))


def _refine_layout(
    ir: CircuitIR,
    target: Target,
    initial_layout: Layout,
    *,
    trial: int,
    seed: int,
    swap_budget: int,
    rounds: int,
) -> Layout:
    """Run deterministic forward/reverse SABRE-style layout refinements."""

    reverse_ir = CircuitIR(
        ir.qubit_count,
        tuple(reversed(ir.operations)),
        metadata=ir.metadata,
    )
    layout = initial_layout
    for _ in range(rounds):
        forward = _route_trial(
            ir,
            target,
            layout,
            trial=trial,
            seed=seed,
            swap_budget=swap_budget,
            baseline=False,
        )
        reverse = _route_trial(
            reverse_ir,
            target,
            forward.final_layout,
            trial=trial,
            seed=seed,
            swap_budget=swap_budget,
            baseline=False,
        )
        layout = reverse.final_layout
    return layout


def _layout_connects_components(layout: Layout, ir: CircuitIR, target: Target) -> bool:
    if len(layout.logical_to_physical) != ir.qubit_count:
        return False
    try:
        layout.validate(logical_qubits=ir.qubit_count, physical_qubits=target.qubit_count)
        for operation in ir.operations:
            if len(operation.qubits) == 2:
                target.topology.shortest_path(
                    layout.logical_to_physical[operation.qubits[0]],
                    layout.logical_to_physical[operation.qubits[1]],
                )
    except TargetError:
        return False
    return True


def _dependency_data(ir: CircuitIR) -> tuple[list[int], list[list[int]]]:
    predecessors: list[set[int]] = [set() for _ in ir.operations]
    successors: list[list[int]] = [[] for _ in ir.operations]
    last_on_qubit: dict[int, int] = {}
    for index, operation in enumerate(ir.operations):
        for qubit in operation.qubits:
            if qubit in last_on_qubit:
                predecessors[index].add(last_on_qubit[qubit])
            last_on_qubit[qubit] = index
    for target, values in enumerate(predecessors):
        for source in sorted(values):
            successors[source].append(target)
    return [len(item) for item in predecessors], successors


def _route_trial(
    ir: CircuitIR,
    target: Target,
    initial_layout: Layout,
    *,
    trial: int,
    seed: int,
    swap_budget: int,
    baseline: bool,
) -> _TrialResult:
    initial_layout.validate(logical_qubits=ir.qubit_count, physical_qubits=target.qubit_count)
    indegree, successors = _dependency_data(ir)
    pending = set(range(len(ir.operations)))
    layout = initial_layout
    routed: list[Operation] = []
    steps: list[RoutingStep] = []
    source_to_routed: list[list[int]] = [[] for _ in ir.operations]
    no_progress_swaps = 0
    layouts_since_progress = {layout.logical_to_physical}
    release_threshold = max(4, 2 * max(1, target.topology.diameter))

    def front_layer() -> list[int]:
        return sorted(index for index in pending if indegree[index] == 0)

    while pending:
        front = front_layer()
        executable = [
            index
            for index in front
            if len(ir.operations[index].qubits) < 2
            or target.topology.has_weak_edge(
                layout.logical_to_physical[ir.operations[index].qubits[0]],
                layout.logical_to_physical[ir.operations[index].qubits[1]],
            )
        ]
        if executable:
            for source_index in executable:
                operation = ir.operations[source_index]
                mapped = Operation(
                    operation.name,
                    tuple(layout.logical_to_physical[item] for item in operation.qubits),
                    operation.params,
                    metadata=operation.metadata,
                )
                source_to_routed[source_index].append(len(routed))
                routed.append(mapped)
                pending.remove(source_index)
                for successor in successors[source_index]:
                    indegree[successor] -= 1
            no_progress_swaps = 0
            layouts_since_progress = {layout.logical_to_physical}
            continue

        blocked = [index for index in front if len(ir.operations[index].qubits) == 2]
        if not blocked:
            raise RoutingError("Routing dependency graph made no progress.")
        if len(steps) >= swap_budget:
            raise RoutingError(f"Routing exceeded the {swap_budget}-SWAP budget before completing.")

        force_release = baseline or no_progress_swaps >= release_threshold
        reason: Literal["heuristic", "release-valve", "canonical-baseline"]
        if force_release:
            source_index = min(blocked)
            logical_left, logical_right = ir.operations[source_index].qubits
            path = target.topology.shortest_path(
                layout.logical_to_physical[logical_left],
                layout.logical_to_physical[logical_right],
            )
            edge = _canonical_edge(path[0], path[1])
            reason = "canonical-baseline" if baseline else "release-valve"
        else:
            candidates: set[tuple[int, int]] = set()
            for source_index in blocked:
                for logical in ir.operations[source_index].qubits:
                    physical = layout.logical_to_physical[logical]
                    for neighbor in target.topology.neighbors(physical, weak=True):
                        edge = _canonical_edge(physical, neighbor)
                        if _can_lower_swap(target, *edge):
                            candidates.add(edge)
            if not candidates:
                raise RoutingError("No exact SWAP candidate can advance the blocked front layer.")

            lookahead = [
                index
                for index in sorted(pending)
                if index not in front and len(ir.operations[index].qubits) == 2
            ][:20]

            def score(
                edge: tuple[int, int],
                layout: Layout = layout,
                blocked: tuple[int, ...] = tuple(blocked),
                lookahead: tuple[int, ...] = tuple(lookahead),
            ) -> tuple[int, int, tuple[int, int]]:
                candidate_layout = layout.swap_physical(*edge)
                front_distance = sum(
                    target.topology.distance(
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[0]],
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[1]],
                    )
                    for index in blocked
                )
                lookahead_distance = sum(
                    target.topology.distance(
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[0]],
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[1]],
                    )
                    for index in lookahead
                )
                newly_executable = sum(
                    target.topology.has_weak_edge(
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[0]],
                        candidate_layout.logical_to_physical[ir.operations[index].qubits[1]],
                    )
                    for index in blocked
                )
                return (2 * front_distance + lookahead_distance, -newly_executable, edge)

            edge = min(candidates, key=lambda candidate: score(candidate))
            reason = "heuristic"

        before = layout
        after = before.swap_physical(*edge)
        if after.logical_to_physical in layouts_since_progress and not baseline:
            source_index = min(blocked)
            left, right = ir.operations[source_index].qubits
            path = target.topology.shortest_path(
                layout.logical_to_physical[left], layout.logical_to_physical[right]
            )
            edge = _canonical_edge(path[0], path[1])
            after = before.swap_physical(*edge)
            reason = "release-valve"

        step = RoutingStep(
            index=len(steps),
            physical_edge=edge,
            trigger_source_indices=tuple(blocked),
            layout_before=before,
            layout_after=after,
            reason=reason,
        )
        routed.append(
            Operation(
                "swap",
                edge,
                metadata={"qplanck.inserted": "routing", "routing_step": step.index},
            )
        )
        steps.append(step)
        layout = after
        no_progress_swaps += 1
        layouts_since_progress.add(layout.logical_to_physical)

    measurements = tuple(
        MeasurementSpec(
            layout.logical_to_physical[measurement.qubit],
            measurement.cbit,
            metadata=measurement.metadata,
        )
        for measurement in ir.measurements
    )
    routed_ir = CircuitIR(
        target.qubit_count,
        tuple(routed),
        measurements,
        metadata=ir.metadata,
    )
    return _TrialResult(
        trial=trial,
        seed=seed,
        initial_layout=initial_layout,
        final_layout=layout,
        routed_ir=routed_ir,
        steps=tuple(steps),
        source_to_routed_indices=tuple(tuple(item) for item in source_to_routed),
        inserted_swaps=len(steps),
        routed_depth=_depth(routed_ir.operations),
        two_qubit_depth=_depth(
            tuple(item for item in routed_ir.operations if len(item.qubits) == 2)
        ),
        baseline=baseline,
    )


def _depth(operations: tuple[Operation, ...]) -> int:
    qubit_depth: dict[int, int] = {}
    maximum = 0
    for operation in operations:
        depth = 1 + max((qubit_depth.get(qubit, 0) for qubit in operation.qubits), default=0)
        for qubit in operation.qubits:
            qubit_depth[qubit] = depth
        maximum = max(maximum, depth)
    return maximum


def _can_apply_h(target: Target, qubit: int) -> bool:
    return target.supports_operation(Operation("h", (qubit,)))


def _can_lower_cx(target: Target, control: int, target_qubit: int) -> bool:
    direct = Operation("cx", (control, target_qubit))
    if target.supports_operation(direct):
        return True
    reverse = Operation("cx", (target_qubit, control))
    if (
        target.supports_operation(reverse)
        and _can_apply_h(target, control)
        and _can_apply_h(target, target_qubit)
    ):
        return True
    cz = Operation("cz", (control, target_qubit))
    return target.supports_operation(cz) and _can_apply_h(target, target_qubit)


def _can_lower_swap(target: Target, left: int, right: int) -> bool:
    if target.supports_operation(Operation("swap", (left, right))):
        return True
    return _can_lower_cx(target, left, right) and _can_lower_cx(target, right, left)


def _lower_cx(
    target: Target,
    control: int,
    target_qubit: int,
    metadata: dict[str, Any],
) -> tuple[Operation, ...]:
    direct = Operation("cx", (control, target_qubit), metadata=metadata)
    if target.supports_operation(direct):
        return (direct,)
    reverse = Operation("cx", (target_qubit, control), metadata=metadata)
    if (
        target.supports_operation(reverse)
        and _can_apply_h(target, control)
        and _can_apply_h(target, target_qubit)
    ):
        return (
            Operation("h", (control,), metadata=metadata),
            Operation("h", (target_qubit,), metadata=metadata),
            reverse,
            Operation("h", (control,), metadata=metadata),
            Operation("h", (target_qubit,), metadata=metadata),
        )
    cz = Operation("cz", (control, target_qubit), metadata=metadata)
    if target.supports_operation(cz) and _can_apply_h(target, target_qubit):
        return (
            Operation("h", (target_qubit,), metadata=metadata),
            cz,
            Operation("h", (target_qubit,), metadata=metadata),
        )
    raise RoutingError(f"Target cannot exactly lower CX({control}, {target_qubit}).")


def _lower_operation(operation: Operation, target: Target) -> tuple[Operation, ...]:
    if target.supports_operation(operation):
        return (operation,)
    metadata = dict(operation.metadata)
    if operation.name == "cx":
        return _lower_cx(target, operation.qubits[0], operation.qubits[1], metadata)
    if operation.name == "cz":
        left, right = operation.qubits
        if _can_apply_h(target, right):
            lowered_cx = _lower_cx(target, left, right, metadata)
            return (
                Operation("h", (right,), metadata=metadata),
                *lowered_cx,
                Operation("h", (right,), metadata=metadata),
            )
    if operation.name == "swap":
        left, right = operation.qubits
        return (
            *_lower_cx(target, left, right, metadata),
            *_lower_cx(target, right, left, metadata),
            *_lower_cx(target, left, right, metadata),
        )
    raise RoutingError(
        f"Target basis cannot exactly lower operation {operation.name!r} on {operation.qubits}."
    )


def _lower_to_target_basis(
    routed_ir: CircuitIR,
    target: Target,
) -> tuple[CircuitIR, tuple[tuple[int, ...], ...]]:
    operations: list[Operation] = []
    mapping: list[tuple[int, ...]] = []
    for operation in routed_ir.operations:
        start = len(operations)
        lowered = _lower_operation(operation, target)
        operations.extend(lowered)
        mapping.append(tuple(range(start, len(operations))))
    for operation in operations:
        if not target.supports_operation(operation):
            raise RoutingError(
                f"Native lowering emitted nonconforming {operation.name!r}{operation.qubits}."
            )
    return (
        CircuitIR(
            routed_ir.qubit_count,
            tuple(operations),
            routed_ir.measurements,
            metadata=routed_ir.metadata,
        ),
        tuple(mapping),
    )


__all__ = [
    "ROUTING_TRACE_SCHEMA_VERSION",
    "RoutingResult",
    "RoutingStep",
    "RoutingTrace",
    "RoutingTrial",
    "route",
]
