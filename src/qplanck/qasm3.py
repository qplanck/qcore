"""OpenQASM 3 subset import/export for QCore v0.1."""

from __future__ import annotations

import ast
import math
import re

from qplanck.circuit import SUPPORTED_GATES, Circuit
from qplanck.errors import QASMError
from qplanck.ir import Parameter

_QUBIT_RE = re.compile(r"^qubit\[(?P<size>\d+)\]\s+(?P<name>[A-Za-z_]\w*)$")
_BIT_RE = re.compile(r"^bit\[(?P<size>\d+)\]\s+(?P<name>[A-Za-z_]\w*)$")
_ARG_RE = re.compile(r"^(?P<name>[A-Za-z_]\w*)\[(?P<index>\d+)\]$")
_MEASURE_ARROW_RE = re.compile(
    r"^measure\s+(?P<qreg>[A-Za-z_]\w*)\[(?P<qubit>\d+)\]\s*->\s*"
    r"(?P<creg>[A-Za-z_]\w*)\[(?P<cbit>\d+)\]$"
)
_MEASURE_ASSIGN_RE = re.compile(
    r"^(?P<creg>[A-Za-z_]\w*)\[(?P<cbit>\d+)\]\s*=\s*measure\s+"
    r"(?P<qreg>[A-Za-z_]\w*)\[(?P<qubit>\d+)\]$"
)


def dumps(circuit: Circuit) -> str:
    """Export a circuit to the supported OpenQASM 3 subset."""

    lines = [
        "OPENQASM 3.0;",
        'include "stdgates.inc";',
        f"qubit[{circuit.qubit_count}] q;",
    ]
    if circuit.measurements:
        bit_count = max(measurement.cbit for measurement in circuit.measurements) + 1
        lines.append(f"bit[{bit_count}] c;")

    for operation in circuit.operations:
        name = operation.name
        if name not in SUPPORTED_GATES:
            raise QASMError(f"Cannot export unsupported operation {name!r}.")
        if name in {"rx", "ry", "rz"}:
            lines.append(
                f"{name}({_format_float(_numeric_param(operation.params[0]))}) "
                f"q[{operation.qubits[0]}];"
            )
        elif name in {"cx", "cz"}:
            lines.append(f"{name} q[{operation.qubits[0]}], q[{operation.qubits[1]}];")
        else:
            lines.append(f"{name} q[{operation.qubits[0]}];")

    for measurement in circuit.measurements:
        lines.append(f"measure q[{measurement.qubit}] -> c[{measurement.cbit}];")

    return "\n".join(lines) + "\n"


def loads(text: str) -> Circuit:
    """Parse the supported OpenQASM 3 subset."""

    statements = _statements(text)
    if not statements:
        raise QASMError("OpenQASM input is empty.")
    if statements[0] != "OPENQASM 3.0":
        raise QASMError("Only OpenQASM 3.0 input is supported.")

    qreg_name: str | None = None
    creg_name: str | None = None
    circuit: Circuit | None = None

    for statement in statements[1:]:
        if statement == 'include "stdgates.inc"':
            continue

        qubit_match = _QUBIT_RE.match(statement)
        if qubit_match:
            if circuit is not None:
                raise QASMError("QCore v0.1 supports exactly one qubit register.")
            qreg_name = qubit_match.group("name")
            circuit = Circuit(int(qubit_match.group("size")))
            continue

        bit_match = _BIT_RE.match(statement)
        if bit_match:
            if creg_name is not None:
                raise QASMError("QCore v0.1 supports exactly one classical bit register.")
            creg_name = bit_match.group("name")
            continue

        if circuit is None or qreg_name is None:
            raise QASMError("Declare a qubit register before operations.")

        measurement = _parse_measurement(statement)
        if measurement is not None:
            parsed_qreg, qubit, parsed_creg, cbit = measurement
            _validate_register(parsed_qreg, qreg_name, "qubit")
            if creg_name is not None:
                _validate_register(parsed_creg, creg_name, "classical")
            circuit.measure(qubit, cbit)
            continue

        name, params, args = _parse_gate(statement)
        if name not in SUPPORTED_GATES:
            raise QASMError(
                f"Unsupported OpenQASM operation {name!r}. "
                f"Supported gates: {', '.join(sorted(SUPPORTED_GATES))}."
            )
        qubits = [_parse_arg(arg, qreg_name) for arg in args]
        _add_gate(circuit, name, params, qubits)

    if circuit is None:
        raise QASMError("OpenQASM input must declare a qubit register.")
    return circuit


def _format_float(value: float) -> str:
    return f"{value:.17g}"


def _numeric_param(value: float | Parameter) -> float:
    if isinstance(value, Parameter):
        raise QASMError("QCore v0.1 exports numeric gate parameters only.")
    return float(value)


def _statements(text: str) -> list[str]:
    stripped_lines = []
    for line in text.splitlines():
        stripped_lines.append(line.split("//", 1)[0])
    cleaned = "\n".join(stripped_lines)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]


def _parse_measurement(statement: str) -> tuple[str, int, str, int] | None:
    arrow_match = _MEASURE_ARROW_RE.match(statement)
    if arrow_match:
        return (
            arrow_match.group("qreg"),
            int(arrow_match.group("qubit")),
            arrow_match.group("creg"),
            int(arrow_match.group("cbit")),
        )
    assign_match = _MEASURE_ASSIGN_RE.match(statement)
    if assign_match:
        return (
            assign_match.group("qreg"),
            int(assign_match.group("qubit")),
            assign_match.group("creg"),
            int(assign_match.group("cbit")),
        )
    return None


def _parse_gate(statement: str) -> tuple[str, list[float], list[str]]:
    gate_match = re.match(
        r"^(?P<name>[A-Za-z_]\w*)(?:\((?P<params>[^)]*)\))?\s+(?P<args>.+)$", statement
    )
    if gate_match is None:
        raise QASMError(f"Could not parse OpenQASM statement: {statement!r}.")
    name = gate_match.group("name").lower()
    params_text = gate_match.group("params")
    params = []
    if params_text:
        params = [
            _parse_numeric_expr(item.strip()) for item in params_text.split(",") if item.strip()
        ]
    args = [arg.strip() for arg in gate_match.group("args").split(",")]
    return name, params, args


def _parse_arg(text: str, expected_register: str) -> int:
    match = _ARG_RE.match(text)
    if match is None:
        raise QASMError(f"Invalid qubit argument {text!r}.")
    _validate_register(match.group("name"), expected_register, "qubit")
    return int(match.group("index"))


def _validate_register(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise QASMError(f"Unsupported {label} register {actual!r}; expected {expected!r}.")


def _add_gate(circuit: Circuit, name: str, params: list[float], qubits: list[int]) -> None:
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
        raise QASMError(f"Unsupported gate {name!r}.")


def _one_param(name: str, params: list[float]) -> float:
    if len(params) != 1:
        raise QASMError(f"Gate {name!r} expects exactly one numeric parameter.")
    return params[0]


def _parse_numeric_expr(text: str) -> float:
    try:
        node = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise QASMError(f"Invalid numeric parameter {text!r}.") from exc
    return float(_eval_numeric_node(node.body))


def _eval_numeric_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id == "pi":
        return math.pi
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_numeric_node(node.operand)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _eval_numeric_node(node.operand)
    if isinstance(node, ast.BinOp):
        left = _eval_numeric_node(node.left)
        right = _eval_numeric_node(node.right)
        return _apply_numeric_operator(node.op, left, right)
    raise QASMError("Only numeric OpenQASM parameters are supported.")


def _apply_numeric_operator(operator: ast.operator, left: float, right: float) -> float:
    if isinstance(operator, ast.Add):
        return left + right
    if isinstance(operator, ast.Sub):
        return left - right
    if isinstance(operator, ast.Mult):
        return left * right
    if isinstance(operator, ast.Div):
        return left / right
    raise QASMError("Only +, -, *, and / are supported in numeric OpenQASM parameters.")
