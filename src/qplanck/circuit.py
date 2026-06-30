"""Public circuit API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from qplanck.errors import CircuitError, UnsupportedOperationError
from qplanck.ir import CircuitIR, MeasurementSpec, Operation, Parameter

if TYPE_CHECKING:
    from qplanck.results import ExecutionTrace


@dataclass(frozen=True)
class GateSpec:
    qubits: int
    params: int


SUPPORTED_GATES: dict[str, GateSpec] = {
    "h": GateSpec(qubits=1, params=0),
    "x": GateSpec(qubits=1, params=0),
    "y": GateSpec(qubits=1, params=0),
    "z": GateSpec(qubits=1, params=0),
    "s": GateSpec(qubits=1, params=0),
    "t": GateSpec(qubits=1, params=0),
    "rx": GateSpec(qubits=1, params=1),
    "ry": GateSpec(qubits=1, params=1),
    "rz": GateSpec(qubits=1, params=1),
    "cx": GateSpec(qubits=2, params=0),
    "cz": GateSpec(qubits=2, params=0),
}


class Circuit:
    """A small, fluent quantum circuit API for QCore v0.1."""

    _ir: CircuitIR
    supported_gates: ClassVar[frozenset[str]] = frozenset(SUPPORTED_GATES)

    def __init__(self, qubits: int, *, name: str | None = None):
        metadata: dict[str, Any] = {}
        if name is not None:
            if not name:
                raise CircuitError("Circuit name must be non-empty when provided.")
            metadata["name"] = name
        self._ir = CircuitIR(qubit_count=qubits, metadata=metadata)

    @classmethod
    def from_ir(cls, ir: CircuitIR) -> Circuit:
        circuit = cls(ir.qubit_count, name=ir.metadata.get("name"))
        circuit._ir = ir
        for operation in ir.operations:
            circuit._validate_operation(operation)
        circuit._validate_measurements()
        return circuit

    @classmethod
    def from_json(cls, text: str) -> Circuit:
        return cls.from_ir(CircuitIR.from_json(text))

    def to_json(self, *, indent: int | None = None) -> str:
        return self._ir.to_json(indent=indent)

    @classmethod
    def from_qasm3(cls, text: str) -> Circuit:
        from qplanck.qasm3 import loads

        return loads(text)

    def to_qasm3(self) -> str:
        from qplanck.qasm3 import dumps

        return dumps(self)

    @classmethod
    def from_qiskit(cls, quantum_circuit: Any) -> Circuit:
        from qplanck.qiskit_adapter import from_qiskit

        return from_qiskit(quantum_circuit)

    def to_qiskit(self) -> Any:
        from qplanck.qiskit_adapter import to_qiskit

        return to_qiskit(self)

    @property
    def ir(self) -> CircuitIR:
        return self._ir

    @property
    def qubit_count(self) -> int:
        return self._ir.qubit_count

    @property
    def name(self) -> str | None:
        value = self._ir.metadata.get("name")
        return str(value) if value is not None else None

    @property
    def operations(self) -> tuple[Operation, ...]:
        return self._ir.operations

    @property
    def measurements(self) -> tuple[MeasurementSpec, ...]:
        return self._ir.measurements

    def add(self, op: Operation) -> Circuit:
        if not isinstance(op, Operation):
            raise CircuitError("Circuit.add() expects a qplanck.ir.Operation.")
        if self._ir.measurements:
            raise UnsupportedOperationError(
                "QCore v0.1 supports terminal measurements only; add gates before measure()."
            )
        self._validate_operation(op)
        self._ir = self._ir.with_operation(op)
        return self

    def h(self, q: int) -> Circuit:
        return self.add(Operation("h", (q,)))

    def x(self, q: int) -> Circuit:
        return self.add(Operation("x", (q,)))

    def y(self, q: int) -> Circuit:
        return self.add(Operation("y", (q,)))

    def z(self, q: int) -> Circuit:
        return self.add(Operation("z", (q,)))

    def s(self, q: int) -> Circuit:
        return self.add(Operation("s", (q,)))

    def t(self, q: int) -> Circuit:
        return self.add(Operation("t", (q,)))

    def rx(self, theta: float, q: int) -> Circuit:
        return self.add(Operation("rx", (q,), (theta,)))

    def ry(self, theta: float, q: int) -> Circuit:
        return self.add(Operation("ry", (q,), (theta,)))

    def rz(self, theta: float, q: int) -> Circuit:
        return self.add(Operation("rz", (q,), (theta,)))

    def cx(self, control: int, target: int) -> Circuit:
        return self.add(Operation("cx", (control, target)))

    def cz(self, control: int, target: int) -> Circuit:
        return self.add(Operation("cz", (control, target)))

    def measure(self, q: int, c: int | None = None) -> Circuit:
        q = int(q)
        cbit = len(self._ir.measurements) if c is None else int(c)
        measurement = MeasurementSpec(q, cbit)
        existing_qubits = {item.qubit for item in self._ir.measurements}
        existing_cbits = {item.cbit for item in self._ir.measurements}
        if q in existing_qubits:
            raise CircuitError(f"Qubit {q} has already been measured.")
        if cbit in existing_cbits:
            raise CircuitError(f"Classical bit {cbit} is already assigned.")
        self._ir = self._ir.with_measurement(measurement)
        self._validate_measurements()
        return self

    def measure_all(self) -> Circuit:
        for q in range(self.qubit_count):
            if q not in {item.qubit for item in self._ir.measurements}:
                self.measure(q, q)
        return self

    def draw(self, style: str = "ascii") -> str:
        if style != "ascii":
            raise UnsupportedOperationError("QCore v0.1 supports only ASCII drawing.")
        from qplanck.draw import draw_ascii

        return draw_ascii(self)

    def trace(self) -> ExecutionTrace | None:
        from qplanck.simulator import Simulator

        return Simulator("statevector").run(self, trace=True).trace

    def to_dict(self) -> dict[str, Any]:
        return self._ir.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Circuit:
        return cls.from_ir(CircuitIR.from_dict(data))

    def copy(self) -> Circuit:
        return Circuit.from_ir(CircuitIR.from_dict(json.loads(self.to_json())))

    def _validate_operation(self, operation: Operation) -> None:
        if operation.name not in SUPPORTED_GATES:
            raise UnsupportedOperationError(
                f"Unsupported operation {operation.name!r}. "
                f"Supported gates: {', '.join(sorted(SUPPORTED_GATES))}."
            )
        spec = SUPPORTED_GATES[operation.name]
        if len(operation.qubits) != spec.qubits:
            raise CircuitError(
                f"Gate {operation.name!r} expects {spec.qubits} qubit(s), "
                f"got {len(operation.qubits)}."
            )
        if len(operation.params) != spec.params:
            raise CircuitError(
                f"Gate {operation.name!r} expects {spec.params} parameter(s), "
                f"got {len(operation.params)}."
            )
        if any(qubit >= self.qubit_count for qubit in operation.qubits):
            raise CircuitError(f"Gate {operation.name!r} references a qubit outside this circuit.")
        if operation.name in {"cx", "cz"} and operation.qubits[0] == operation.qubits[1]:
            raise CircuitError(f"Gate {operation.name!r} requires distinct qubits.")
        if any(isinstance(param, Parameter) for param in operation.params):
            raise UnsupportedOperationError("QCore v0.1 supports numeric gate parameters only.")

    def _validate_measurements(self) -> None:
        seen_qubits: set[int] = set()
        seen_cbits: set[int] = set()
        for measurement in self._ir.measurements:
            if measurement.qubit >= self.qubit_count:
                raise CircuitError("Measurement references a qubit outside this circuit.")
            if measurement.qubit in seen_qubits:
                raise CircuitError(f"Qubit {measurement.qubit} has already been measured.")
            if measurement.cbit in seen_cbits:
                raise CircuitError(f"Classical bit {measurement.cbit} is already assigned.")
            seen_qubits.add(measurement.qubit)
            seen_cbits.add(measurement.cbit)
