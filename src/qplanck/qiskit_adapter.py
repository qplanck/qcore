"""Optional Qiskit import/export adapter."""

from __future__ import annotations

from typing import Any

from qplanck.circuit import SUPPORTED_GATES, Circuit
from qplanck.errors import InteropError
from qplanck.interop import ConversionResult, InteropIssue, InteropIssueKind, LossReport
from qplanck.ir import Parameter


def from_qiskit(quantum_circuit: Any) -> Circuit:
    """Convert a supported Qiskit QuantumCircuit into a QCore circuit."""

    _require_qiskit()
    try:
        qubit_count = int(quantum_circuit.num_qubits)
    except AttributeError as exc:
        raise InteropError("Expected a qiskit.QuantumCircuit-like object.") from exc

    circuit = Circuit(qubit_count, name=getattr(quantum_circuit, "name", None) or None)
    for item in quantum_circuit.data:
        operation, qargs, cargs = _unpack_instruction(item)
        name = operation.name.lower()
        if name == "cnot":
            name = "cx"
        qubits = [_bit_index(quantum_circuit, bit, "qubits") for bit in qargs]

        if name == "measure":
            if len(qubits) != 1 or len(cargs) != 1:
                raise InteropError("QCore supports one-qubit measurements only.")
            cbit = _bit_index(quantum_circuit, cargs[0], "clbits")
            circuit.measure(qubits[0], cbit)
            continue

        if name not in SUPPORTED_GATES:
            raise InteropError(
                f"Unsupported Qiskit operation {operation.name!r}. "
                f"Supported gates: {', '.join(sorted(SUPPORTED_GATES))}."
            )

        params = [float(param) for param in getattr(operation, "params", [])]
        _add_supported_gate(circuit, name, params, qubits)
    return circuit


def to_qiskit(circuit: Circuit) -> Any:
    """Convert a QCore circuit into a Qiskit QuantumCircuit."""

    qiskit = _require_qiskit()
    classical_count = 0
    if circuit.measurements:
        classical_count = max(measurement.cbit for measurement in circuit.measurements) + 1
    quantum_circuit = qiskit.QuantumCircuit(circuit.qubit_count, classical_count, name=circuit.name)

    for operation in circuit.operations:
        name = operation.name
        if name in {"h", "x", "y", "z", "s", "t"}:
            getattr(quantum_circuit, name)(operation.qubits[0])
        elif name in {"rx", "ry", "rz"}:
            getattr(quantum_circuit, name)(_numeric_param(operation.params[0]), operation.qubits[0])
        elif name == "cx":
            quantum_circuit.cx(operation.qubits[0], operation.qubits[1])
        elif name == "cz":
            quantum_circuit.cz(operation.qubits[0], operation.qubits[1])
        else:
            raise InteropError(f"Unsupported QCore operation {name!r}.")

    for measurement in circuit.measurements:
        quantum_circuit.measure(measurement.qubit, measurement.cbit)
    return quantum_circuit


def to_qiskit_with_report(circuit: Circuit) -> ConversionResult[Any]:
    """Convert to Qiskit and return explicit round-trip fidelity evidence."""

    issues: list[InteropIssue] = []
    extra_circuit_metadata = set(circuit.ir.metadata) - {"name"}
    if extra_circuit_metadata:
        issues.append(
            InteropIssue(
                code="QCORE-INTEROP-CIRCUIT-METADATA-DROPPED",
                kind=InteropIssueKind.LOSS,
                message="Only the QCore circuit name is mapped to Qiskit.",
                path="metadata",
            )
        )
    for index, operation in enumerate(circuit.operations):
        if operation.metadata:
            issues.append(
                InteropIssue(
                    code="QCORE-INTEROP-OPERATION-METADATA-DROPPED",
                    kind=InteropIssueKind.LOSS,
                    message="QCore operation metadata is not mapped to Qiskit instructions.",
                    path=f"operations[{index}].metadata",
                )
            )
    for index, measurement in enumerate(circuit.measurements):
        if measurement.metadata:
            issues.append(
                InteropIssue(
                    code="QCORE-INTEROP-MEASUREMENT-METADATA-DROPPED",
                    kind=InteropIssueKind.LOSS,
                    message="QCore measurement metadata is not mapped to Qiskit instructions.",
                    path=f"measurements[{index}].metadata",
                )
            )

    report = LossReport(
        source_format=circuit.ir.schema_version,
        target_format="qiskit-quantum-circuit-supported-subset",
        preserved=(
            "circuit name",
            "operation order",
            "supported gate semantics",
            "numeric parameters",
            "terminal measurement mapping",
            "qubit count",
        ),
        issues=tuple(issues),
    )
    return ConversionResult(value=to_qiskit(circuit), report=report)


def _require_qiskit() -> Any:
    try:
        import qiskit
    except ImportError as exc:
        raise InteropError(
            "Qiskit interop requires the optional dependency: "
            'python -m pip install "qplanck[qiskit]".'
        ) from exc
    return qiskit


def _unpack_instruction(item: Any) -> tuple[Any, list[Any], list[Any]]:
    operation = getattr(item, "operation", None)
    if operation is not None:
        return operation, list(item.qubits), list(item.clbits)
    operation, qargs, cargs = item
    return operation, list(qargs), list(cargs)


def _bit_index(quantum_circuit: Any, bit: Any, attr: str) -> int:
    try:
        return int(quantum_circuit.find_bit(bit).index)
    except Exception:
        return list(getattr(quantum_circuit, attr)).index(bit)


def _add_supported_gate(
    circuit: Circuit, name: str, params: list[float], qubits: list[int]
) -> None:
    if name == "h":
        circuit.h(qubits[0])
    elif name == "x":
        circuit.x(qubits[0])
    elif name == "y":
        circuit.y(qubits[0])
    elif name == "z":
        circuit.z(qubits[0])
    elif name == "s":
        circuit.s(qubits[0])
    elif name == "t":
        circuit.t(qubits[0])
    elif name == "rx":
        circuit.rx(_one_param(name, params), qubits[0])
    elif name == "ry":
        circuit.ry(_one_param(name, params), qubits[0])
    elif name == "rz":
        circuit.rz(_one_param(name, params), qubits[0])
    elif name == "cx":
        circuit.cx(qubits[0], qubits[1])
    elif name == "cz":
        circuit.cz(qubits[0], qubits[1])
    else:
        raise InteropError(f"Unsupported Qiskit operation {name!r}.")


def _one_param(name: str, params: list[float]) -> float:
    if len(params) != 1:
        raise InteropError(f"Gate {name!r} expects exactly one parameter.")
    return params[0]


def _numeric_param(value: float | Parameter) -> float:
    if isinstance(value, Parameter):
        raise InteropError("QCore exports numeric gate parameters only.")
    return float(value)
