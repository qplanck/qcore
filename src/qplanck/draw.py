"""ASCII circuit drawing."""

from __future__ import annotations

from qplanck.circuit import Circuit
from qplanck.errors import UnsupportedOperationError
from qplanck.ir import Operation, Parameter


def _format_param(value: float | Parameter) -> str:
    if isinstance(value, Parameter):
        raise UnsupportedOperationError("QCore v0.1 supports numeric gate parameters only.")
    return f"{value:.6g}"


def _operation_labels(operation: Operation) -> dict[int, str]:
    name = operation.name
    if name in {"rx", "ry", "rz"}:
        return {operation.qubits[0]: f"{name.upper()}({_format_param(operation.params[0])})"}
    if name in {"cx", "cz"}:
        target_label = "X" if name == "cx" else "Z"
        return {operation.qubits[0]: "*", operation.qubits[1]: target_label}
    return {operation.qubits[0]: name.upper()}


def draw_ascii(circuit: Circuit) -> str:
    """Return a compact ASCII drawing for a circuit."""

    lines = [f"q{q}: |0>" for q in range(circuit.qubit_count)]
    for operation in circuit.operations:
        labels = _operation_labels(operation)
        width = max(len(label) for label in labels.values())
        for q in range(circuit.qubit_count):
            label = labels.get(q)
            segment = "-" * (width + 2) if label is None else f"-{label.center(width)}-"
            lines[q] += segment

    for measurement in circuit.measurements:
        label = f"M{measurement.cbit}"
        width = len(label)
        for q in range(circuit.qubit_count):
            segment = f"-{label}-" if q == measurement.qubit else "-" * (width + 2)
            lines[q] += segment

    return "\n".join(lines)
