"""Deterministic NumPy statevector simulator."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, cast

import numpy as np
from numpy.typing import NDArray

from qplanck.errors import ResourceLimitError, UnsupportedOperationError
from qplanck.results import (
    ExecutionTrace,
    ProbabilityResult,
    RunResult,
    StatevectorResult,
    TraceStep,
)

if TYPE_CHECKING:
    from qplanck.circuit import Circuit
    from qplanck.ir import Operation


ComplexArray = NDArray[np.complex128]
DEFAULT_MAX_STATEVECTOR_BYTES = 256 * 1024 * 1024


class Simulator:
    """Simulator facade.

    The core package ships only the exact NumPy statevector backend.
    """

    def __init__(
        self,
        backend: str = "statevector",
        *,
        max_statevector_bytes: int = DEFAULT_MAX_STATEVECTOR_BYTES,
    ):
        if backend != "statevector":
            raise UnsupportedOperationError("QCore supports only the statevector backend.")
        if max_statevector_bytes <= 0:
            raise ValueError("max_statevector_bytes must be positive.")
        self.backend = backend
        self.max_statevector_bytes = int(max_statevector_bytes)

    def run(
        self,
        circuit: Circuit,
        *,
        shots: int | None = None,
        seed: int | None = None,
        trace: bool = False,
        max_trace_qubits: int = 8,
    ) -> RunResult:
        if shots is not None and shots < 0:
            raise ValueError("shots must be non-negative when provided.")

        state, execution_trace = self._simulate(
            circuit, trace=trace, max_trace_qubits=max_trace_qubits
        )
        probabilities = _probability_dict(state, circuit.qubit_count)
        measurements: list[str] = []
        counts: dict[str, int] = {}

        if shots is not None:
            rng = np.random.default_rng(seed)
            basis_states = np.arange(2**circuit.qubit_count)
            probability_vector = np.abs(state) ** 2
            probability_vector = probability_vector / probability_vector.sum()
            samples = rng.choice(basis_states, size=shots, p=probability_vector)
            measurements = [_measurement_key(int(sample), circuit) for sample in samples]
            counts = dict(sorted(Counter(measurements).items()))

        return RunResult(
            counts=counts,
            probabilities=probabilities,
            measurements=measurements,
            metadata={
                "backend": self.backend,
                "shots": shots,
                "seed": seed,
                "endianness": "little",
                "basis_key_order": ("c[n-1]...c[0]" if circuit.measurements else "q[n-1]...q[0]"),
                "measurement_mode": "explicit" if circuit.measurements else "implicit-all-qubits",
            },
            trace=execution_trace,
        )

    def statevector(self, circuit: Circuit) -> StatevectorResult:
        state, _ = self._simulate(circuit, trace=False)
        return StatevectorResult(
            statevector=tuple(complex(value) for value in state),
            metadata={"backend": self.backend, "endianness": "little"},
        )

    def probabilities(self, circuit: Circuit) -> ProbabilityResult:
        state, _ = self._simulate(circuit, trace=False)
        return ProbabilityResult(
            probabilities=_probability_dict(state, circuit.qubit_count),
            metadata={"backend": self.backend, "basis_key_order": "q[n-1]...q[0]"},
        )

    def _simulate(
        self,
        circuit: Circuit,
        *,
        trace: bool,
        max_trace_qubits: int = 8,
    ) -> tuple[ComplexArray, ExecutionTrace | None]:
        if trace and circuit.qubit_count > max_trace_qubits:
            raise UnsupportedOperationError(
                f"Trace JSON defaults to at most {max_trace_qubits} qubits; "
                "rerun with a larger max_trace_qubits only if the payload size is acceptable."
            )
        statevector_bytes = (1 << circuit.qubit_count) * np.dtype(np.complex128).itemsize
        if statevector_bytes > self.max_statevector_bytes:
            raise ResourceLimitError(
                f"Statevector requires {statevector_bytes} bytes, exceeding the "
                f"configured {self.max_statevector_bytes}-byte limit."
            )
        state = np.zeros(2**circuit.qubit_count, dtype=np.complex128)
        state[0] = 1.0 + 0.0j

        steps: list[TraceStep] = []
        if trace:
            steps.append(_trace_step(0, None, state, circuit.qubit_count))

        for index, operation in enumerate(circuit.operations, start=1):
            state = _apply_operation(state, circuit.qubit_count, operation)
            if trace:
                steps.append(_trace_step(index, operation, state, circuit.qubit_count))

        execution_trace = None
        if trace:
            execution_trace = ExecutionTrace(
                circuit=circuit.ir,
                steps=tuple(steps),
                metadata={
                    "backend": self.backend,
                    "endianness": "little",
                    "basis_key_order": "q[n-1]...q[0]",
                    "statevector_encoding": "array[{real, imag}]",
                },
            )
        return state, execution_trace


def _basis_key(index: int, qubit_count: int) -> str:
    return "".join(str((index >> qubit) & 1) for qubit in reversed(range(qubit_count)))


def _measurement_key(index: int, circuit: Circuit) -> str:
    """Map a sampled basis state into dense classical-register display order."""

    if not circuit.measurements:
        return _basis_key(index, circuit.qubit_count)
    classical_count = max(measurement.cbit for measurement in circuit.measurements) + 1
    values = [0] * classical_count
    for measurement in circuit.measurements:
        values[measurement.cbit] = (index >> measurement.qubit) & 1
    return "".join(str(values[cbit]) for cbit in reversed(range(classical_count)))


def _probability_dict(state: ComplexArray, qubit_count: int) -> dict[str, float]:
    probabilities = np.abs(state) ** 2
    return {
        _basis_key(index, qubit_count): float(probabilities[index])
        for index in range(2**qubit_count)
    }


def _trace_step(
    index: int,
    operation: Operation | None,
    state: ComplexArray,
    qubit_count: int,
) -> TraceStep:
    return TraceStep(
        index=index,
        operation=operation.to_dict() if operation is not None else None,
        statevector=tuple(complex(value) for value in state),
        probabilities=_probability_dict(state, qubit_count),
    )


def _apply_operation(state: ComplexArray, qubit_count: int, operation: Operation) -> ComplexArray:
    name = operation.name
    if name == "h":
        matrix = (1 / math.sqrt(2)) * np.array([[1, 1], [1, -1]], dtype=np.complex128)
        return _apply_single(state, qubit_count, operation.qubits[0], matrix)
    if name == "x":
        return _apply_single(
            state,
            qubit_count,
            operation.qubits[0],
            np.array([[0, 1], [1, 0]], dtype=np.complex128),
        )
    if name == "y":
        return _apply_single(
            state,
            qubit_count,
            operation.qubits[0],
            np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
        )
    if name == "z":
        return _apply_single(
            state,
            qubit_count,
            operation.qubits[0],
            np.array([[1, 0], [0, -1]], dtype=np.complex128),
        )
    if name == "s":
        return _apply_single(
            state,
            qubit_count,
            operation.qubits[0],
            np.array([[1, 0], [0, 1j]], dtype=np.complex128),
        )
    if name == "t":
        return _apply_single(
            state,
            qubit_count,
            operation.qubits[0],
            np.array([[1, 0], [0, np.exp(1j * math.pi / 4)]], dtype=np.complex128),
        )
    if name == "rx":
        theta = float(cast(float, operation.params[0]))
        matrix = np.array(
            [
                [math.cos(theta / 2), -1j * math.sin(theta / 2)],
                [-1j * math.sin(theta / 2), math.cos(theta / 2)],
            ],
            dtype=np.complex128,
        )
        return _apply_single(state, qubit_count, operation.qubits[0], matrix)
    if name == "ry":
        theta = float(cast(float, operation.params[0]))
        matrix = np.array(
            [
                [math.cos(theta / 2), -math.sin(theta / 2)],
                [math.sin(theta / 2), math.cos(theta / 2)],
            ],
            dtype=np.complex128,
        )
        return _apply_single(state, qubit_count, operation.qubits[0], matrix)
    if name == "rz":
        theta = float(cast(float, operation.params[0]))
        matrix = np.array(
            [[np.exp(-0.5j * theta), 0], [0, np.exp(0.5j * theta)]],
            dtype=np.complex128,
        )
        return _apply_single(state, qubit_count, operation.qubits[0], matrix)
    if name == "cx":
        return _apply_controlled_x(state, operation.qubits[0], operation.qubits[1])
    if name == "cz":
        return _apply_controlled_z(state, operation.qubits[0], operation.qubits[1])
    raise UnsupportedOperationError(f"Unsupported operation {name!r}.")


def _apply_single(
    state: ComplexArray,
    qubit_count: int,
    qubit: int,
    matrix: ComplexArray,
) -> ComplexArray:
    out = state.copy()
    step = 1 << qubit
    size = 1 << qubit_count
    for base in range(0, size, step * 2):
        for offset in range(step):
            i0 = base + offset
            i1 = i0 + step
            a0 = state[i0]
            a1 = state[i1]
            out[i0] = matrix[0, 0] * a0 + matrix[0, 1] * a1
            out[i1] = matrix[1, 0] * a0 + matrix[1, 1] * a1
    return out


def _apply_controlled_x(state: ComplexArray, control: int, target: int) -> ComplexArray:
    out = state.copy()
    control_mask = 1 << control
    target_mask = 1 << target
    for index in range(state.size):
        if (index & control_mask) and not (index & target_mask):
            partner = index | target_mask
            out[index] = state[partner]
            out[partner] = state[index]
    return out


def _apply_controlled_z(state: ComplexArray, control: int, target: int) -> ComplexArray:
    out = state.copy()
    mask = (1 << control) | (1 << target)
    for index in range(state.size):
        if (index & mask) == mask:
            out[index] = -state[index]
    return out
