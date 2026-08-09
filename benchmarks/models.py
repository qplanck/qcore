"""Typed benchmark corpus and compiler outcome models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from qplanck.ir import CircuitIR
from qplanck.targets import Target


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class Workload:
    name: str
    qubit_count: int
    ir: CircuitIR
    seed: int
    category: str = "application"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Workload name must be non-empty.")
        if self.qubit_count != self.ir.qubit_count:
            raise ValueError("Workload qubit_count must match its circuit IR.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Workload seed must be a non-negative integer.")
        json.dumps(self.metadata, allow_nan=False, sort_keys=True)

    @property
    def operation_count(self) -> int:
        return len(self.ir.operations)

    @property
    def semantic_hash(self) -> str:
        return canonical_hash(self.ir.to_dict())

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "qubit_count": self.qubit_count,
            "operation_count": self.operation_count,
            "seed": self.seed,
            "semantic_hash": self.semantic_hash,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BenchmarkTarget:
    name: str
    target: Target

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Benchmark target name must be non-empty.")

    def to_metadata(self) -> dict[str, Any]:
        topology = self.target.topology
        degrees = [len(topology.neighbors(qubit)) for qubit in range(topology.qubit_count)]
        return {
            "name": self.name,
            "target_id": self.target.target_id,
            "target_hash": self.target.content_hash,
            "qubit_count": self.target.qubit_count,
            "directed": topology.directed,
            "edge_count": len(topology.edges),
            "diameter": topology.diameter,
            "maximum_degree": max(degrees, default=0),
            "basis_gates": sorted(self.target.basis_gates),
        }


@dataclass(frozen=True)
class BenchmarkCase:
    suite: str
    workload: Workload
    target: BenchmarkTarget | None
    optimization_level: int

    def __post_init__(self) -> None:
        if self.optimization_level not in {0, 1, 2}:
            raise ValueError("Benchmark optimization level must be 0, 1, or 2.")
        if self.optimization_level == 2 and self.target is None:
            raise ValueError("O2 benchmark cases require a target.")
        if self.optimization_level < 2 and self.target is not None:
            raise ValueError("O0/O1 benchmark cases must not carry a target.")
        if self.target is not None and self.target.target.qubit_count < self.workload.qubit_count:
            raise ValueError("Benchmark target is smaller than its workload.")

    @property
    def case_id(self) -> str:
        target_name = "none" if self.target is None else self.target.name
        return (
            f"{self.suite}/{self.workload.name}/q{self.workload.qubit_count}/"
            f"{target_name}/o{self.optimization_level}"
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "suite": self.suite,
            "optimization_level": self.optimization_level,
            "workload": self.workload.to_metadata(),
            "target": None if self.target is None else self.target.to_metadata(),
        }


@dataclass(frozen=True)
class QualityMetrics:
    source_operations: int
    output_operations: int
    source_two_qubit_gates: int
    output_two_qubit_gates: int
    added_two_qubit_gates: int
    depth: int
    conceptual_swaps: int | None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "source_operations": self.source_operations,
            "output_operations": self.output_operations,
            "source_two_qubit_gates": self.source_two_qubit_gates,
            "output_two_qubit_gates": self.output_two_qubit_gates,
            "added_two_qubit_gates": self.added_two_qubit_gates,
            "depth": self.depth,
            "conceptual_swaps": self.conceptual_swaps,
        }


@dataclass(frozen=True)
class CompilerOutcome:
    artifact_hash: str
    semantic_hash: str
    quality: QualityMetrics
    correctness_passed: bool
    correctness_method: str
    correctness_detail: str = ""
    semantic_evidence: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "BenchmarkCase",
    "BenchmarkTarget",
    "CompilerOutcome",
    "QualityMetrics",
    "Workload",
    "canonical_hash",
]
