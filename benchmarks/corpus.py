"""Deterministic application corpus and topology fixtures."""

from __future__ import annotations

import hashlib
import math
import random

from benchmarks.models import BenchmarkCase, BenchmarkTarget, Workload, canonical_hash
from qplanck.circuit import SUPPORTED_GATES
from qplanck.ir import CircuitIR, Operation
from qplanck.targets import Target, Topology

BENCHMARK_SIZES = (5, 16, 27, 65)
WORKLOAD_NAMES = ("ghz", "bernstein-vazirani", "decomposed-qft", "qaoa", "random")
TARGET_NAMES = ("line", "ring", "grid", "heavy-hex-style")
NATIVE_STRESS_OPERATION_COUNTS = (1_000, 10_000, 100_000)
CORPUS_SCHEMA_VERSION = "qplanck.benchmark.corpus.v0.1"

_TARGET_BASIS = frozenset(SUPPORTED_GATES).difference({"swap"})


def _seed(name: str, size: int) -> int:
    digest = hashlib.sha256(f"qplanck-benchmark:{name}:{size}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _ir(name: str, qubits: int, operations: list[Operation], seed: int) -> CircuitIR:
    return CircuitIR(
        qubit_count=qubits,
        operations=tuple(operations),
        metadata={
            "benchmark": name,
            "benchmark_seed": seed,
            "corpus_schema": CORPUS_SCHEMA_VERSION,
        },
    )


def ghz_workload(qubits: int) -> Workload:
    seed = _seed("ghz", qubits)
    operations = [Operation("h", (0,))]
    operations.extend(Operation("cx", (index, index + 1)) for index in range(qubits - 1))
    return Workload("ghz", qubits, _ir("ghz", qubits, operations, seed), seed)


def bernstein_vazirani_workload(qubits: int) -> Workload:
    seed = _seed("bernstein-vazirani", qubits)
    rng = random.Random(seed)
    ancilla = qubits - 1
    secret = tuple(rng.randrange(2) for _ in range(ancilla))
    if not any(secret):
        secret = (*secret[:-1], 1)
    operations = [Operation("x", (ancilla,))]
    operations.extend(Operation("h", (qubit,)) for qubit in range(qubits))
    operations.extend(
        Operation("cx", (qubit, ancilla)) for qubit, enabled in enumerate(secret) if enabled
    )
    operations.extend(Operation("h", (qubit,)) for qubit in range(ancilla))
    return Workload(
        "bernstein-vazirani",
        qubits,
        _ir("bernstein-vazirani", qubits, operations, seed),
        seed,
        metadata={"secret_sha256": canonical_hash(list(secret))},
    )


def decomposed_qft_workload(qubits: int) -> Workload:
    seed = _seed("decomposed-qft", qubits)
    operations: list[Operation] = []
    for target in range(qubits):
        operations.append(Operation("h", (target,)))
        for control in range(target + 1, qubits):
            theta = math.pi / (2 ** (control - target))
            operations.extend(
                (
                    Operation("rz", (target,), (theta / 2,)),
                    Operation("cx", (control, target)),
                    Operation("rz", (target,), (-theta / 2,)),
                    Operation("cx", (control, target)),
                    Operation("rz", (control,), (theta / 2,)),
                )
            )
    operations.extend(Operation("swap", (left, qubits - left - 1)) for left in range(qubits // 2))
    return Workload(
        "decomposed-qft",
        qubits,
        _ir("decomposed-qft", qubits, operations, seed),
        seed,
        metadata={"controlled_phase_decomposition": "rz-cx-rz-cx-rz"},
    )


def qaoa_workload(qubits: int) -> Workload:
    seed = _seed("qaoa", qubits)
    rng = random.Random(seed)
    operations = [Operation("h", (qubit,)) for qubit in range(qubits)]
    edges = tuple((qubit, (qubit + 1) % qubits) for qubit in range(qubits))
    parameters: list[tuple[float, float]] = []
    for _layer in range(2):
        gamma = rng.uniform(0.1, math.pi - 0.1)
        beta = rng.uniform(0.1, math.pi / 2 - 0.1)
        parameters.append((gamma, beta))
        for left, right in edges:
            operations.extend(
                (
                    Operation("cx", (left, right)),
                    Operation("rz", (right,), (2 * gamma,)),
                    Operation("cx", (left, right)),
                )
            )
        operations.extend(Operation("rx", (qubit,), (2 * beta,)) for qubit in range(qubits))
    return Workload(
        "qaoa",
        qubits,
        _ir("qaoa", qubits, operations, seed),
        seed,
        metadata={"layers": 2, "parameter_hash": canonical_hash(parameters)},
    )


def random_workload(qubits: int) -> Workload:
    seed = _seed("random", qubits)
    rng = random.Random(seed)
    operations: list[Operation] = []
    single_gates = ("h", "x", "y", "z", "s", "t")
    rotations = ("rx", "ry", "rz")
    for _ in range(8 * qubits):
        choice = rng.randrange(10)
        if choice < 3:
            left = rng.randrange(qubits)
            right = rng.randrange(qubits - 1)
            if right >= left:
                right += 1
            operations.append(Operation("cx" if choice < 2 else "cz", (left, right)))
        elif choice < 7:
            operations.append(Operation(rng.choice(single_gates), (rng.randrange(qubits),)))
        else:
            operations.append(
                Operation(
                    rng.choice(rotations),
                    (rng.randrange(qubits),),
                    (rng.uniform(-math.pi, math.pi),),
                )
            )
    return Workload("random", qubits, _ir("random", qubits, operations, seed), seed)


def benchmark_workloads(size: int) -> tuple[Workload, ...]:
    if size not in BENCHMARK_SIZES:
        raise ValueError(f"Benchmark size must be one of {BENCHMARK_SIZES}.")
    return (
        ghz_workload(size),
        bernstein_vazirani_workload(size),
        decomposed_qft_workload(size),
        qaoa_workload(size),
        random_workload(size),
    )


def _grid_topology(qubits: int) -> Topology:
    columns = math.ceil(math.sqrt(qubits))
    edges: list[tuple[int, int]] = []
    for node in range(qubits):
        _row, column = divmod(node, columns)
        right = node + 1
        below = node + columns
        if column + 1 < columns and right < qubits:
            edges.append((node, right))
        if below < qubits:
            edges.append((node, below))
    return Topology(qubits, tuple(edges))


def _heavy_hex_style_topology(qubits: int) -> Topology:
    # A deterministic sparse degree-three chain of four-cycles.  It models the
    # routing pressure of heavy-hex without claiming to reproduce a provider chip.
    edges = [(node, node + 1) for node in range(qubits - 1)]
    edges.extend((start, start + 3) for start in range(1, qubits - 3, 4))
    return Topology(qubits, tuple(edges))


def benchmark_targets(size: int) -> tuple[BenchmarkTarget, ...]:
    if size not in BENCHMARK_SIZES:
        raise ValueError(f"Benchmark size must be one of {BENCHMARK_SIZES}.")
    topologies = {
        "line": Topology.line(size),
        "ring": Topology.ring(size),
        "grid": _grid_topology(size),
        "heavy-hex-style": _heavy_hex_style_topology(size),
    }
    return tuple(
        BenchmarkTarget(
            name,
            Target.testing(
                size,
                topology=topology,
                basis_gates=_TARGET_BASIS,
                target_id=f"qplanck.benchmark.{name}.q{size}",
            ),
        )
        for name, topology in topologies.items()
    )


def benchmark_cases(sizes: tuple[int, ...] = BENCHMARK_SIZES) -> tuple[BenchmarkCase, ...]:
    cases: list[BenchmarkCase] = []
    for size in sizes:
        workloads = benchmark_workloads(size)
        targets = benchmark_targets(size)
        cases.extend(
            BenchmarkCase("routing", workload, target, 2)
            for workload in workloads
            for target in targets
        )
    return tuple(cases)


def native_stress_workload(operation_count: int, *, qubits: int = 65) -> Workload:
    if operation_count not in NATIVE_STRESS_OPERATION_COUNTS:
        raise ValueError(
            f"Native stress operation_count must be one of {NATIVE_STRESS_OPERATION_COUNTS}."
        )
    seed = _seed("native-stress", operation_count)
    operations: list[Operation] = []
    for index in range(operation_count):
        qubit = (index * 17 + 3) % qubits
        selector = index % 5
        if selector == 0:
            operation = Operation("h", (qubit,))
        elif selector == 1:
            operation = Operation("rz", (qubit,), (((index % 31) + 1) / 32,))
        elif selector == 2:
            operation = Operation("cx", (qubit, (qubit + 1) % qubits))
        elif selector == 3:
            operation = Operation("x", (qubit,))
        else:
            operation = Operation("ry", (qubit,), (-((index % 29) + 1) / 30,))
        operations.append(operation)
    return Workload(
        "native-stress",
        qubits,
        _ir("native-stress", qubits, operations, seed),
        seed,
        category="compiler-kernel",
        metadata={"exact_operation_count": operation_count},
    )


def native_stress_cases() -> tuple[BenchmarkCase, ...]:
    return tuple(
        BenchmarkCase("native-gate", native_stress_workload(count), None, 1)
        for count in NATIVE_STRESS_OPERATION_COUNTS
    )


def corpus_manifest() -> dict[str, object]:
    workload_inventory = [
        workload.to_metadata() for size in BENCHMARK_SIZES for workload in benchmark_workloads(size)
    ]
    target_inventory = [
        target.to_metadata() for size in BENCHMARK_SIZES for target in benchmark_targets(size)
    ]
    stress_inventory = [case.workload.to_metadata() for case in native_stress_cases()]
    identity = {
        "workloads": workload_inventory,
        "targets": target_inventory,
        "native_stress": stress_inventory,
        "matrix": {
            "sizes": list(BENCHMARK_SIZES),
            "workloads": list(WORKLOAD_NAMES),
            "targets": list(TARGET_NAMES),
        },
    }
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "sizes": list(BENCHMARK_SIZES),
        "workloads": list(WORKLOAD_NAMES),
        "targets": list(TARGET_NAMES),
        "native_stress_operation_counts": list(NATIVE_STRESS_OPERATION_COUNTS),
        "case_count": (
            len(BENCHMARK_SIZES) * len(WORKLOAD_NAMES) * len(TARGET_NAMES)
            + len(NATIVE_STRESS_OPERATION_COUNTS)
        ),
        "corpus_hash": canonical_hash(identity),
    }


def case_from_spec(
    *,
    suite: str,
    workload_name: str,
    size: int,
    target_name: str | None,
) -> BenchmarkCase:
    if suite == "native-gate":
        return BenchmarkCase("native-gate", native_stress_workload(size), None, 1)
    workload = next(
        (item for item in benchmark_workloads(size) if item.name == workload_name),
        None,
    )
    if workload is None:
        raise ValueError(f"Unknown benchmark workload {workload_name!r}.")
    target = next(
        (item for item in benchmark_targets(size) if item.name == target_name),
        None,
    )
    if target is None:
        raise ValueError(f"Unknown benchmark target {target_name!r}.")
    return BenchmarkCase("routing", workload, target, 2)


__all__ = [
    "BENCHMARK_SIZES",
    "CORPUS_SCHEMA_VERSION",
    "NATIVE_STRESS_OPERATION_COUNTS",
    "TARGET_NAMES",
    "WORKLOAD_NAMES",
    "benchmark_cases",
    "benchmark_targets",
    "benchmark_workloads",
    "case_from_spec",
    "corpus_manifest",
    "native_stress_cases",
    "native_stress_workload",
]
