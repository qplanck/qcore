import math

import pytest

from qplanck import Circuit
from qplanck.errors import QASMError


def test_qasm3_export_and_round_trip() -> None:
    circuit = Circuit(2).h(0).cx(0, 1).measure_all()

    qasm = circuit.to_qasm3()
    assert "OPENQASM 3.0;" in qasm
    assert "cx q[0], q[1];" in qasm
    assert "measure q[1] -> c[1];" in qasm

    restored = Circuit.from_qasm3(qasm)
    assert restored.to_dict() == circuit.to_dict()


def test_qasm3_assignment_measurements_and_pi_params() -> None:
    qasm = """
    OPENQASM 3.0;
    include "stdgates.inc";
    qubit[1] q;
    bit[1] c;
    rx(pi/2) q[0];
    c[0] = measure q[0];
    """

    circuit = Circuit.from_qasm3(qasm)
    assert circuit.operations[0].name == "rx"
    assert circuit.operations[0].params[0] == pytest.approx(math.pi / 2)
    assert circuit.measurements[0].cbit == 0


def test_qasm3_rejects_unsupported_operations() -> None:
    qasm = """
    OPENQASM 3.0;
    include "stdgates.inc";
    qubit[1] q;
    barrier q[0];
    """

    with pytest.raises(QASMError, match="Unsupported OpenQASM operation"):
        Circuit.from_qasm3(qasm)


def test_qasm3_rejects_wrong_version() -> None:
    with pytest.raises(QASMError, match="Only OpenQASM 3.0"):
        Circuit.from_qasm3("OPENQASM 2.0; qreg q[1];")


def test_qasm3_export_reports_metadata_loss() -> None:
    circuit = Circuit(1, name="metadata-is-not-qasm").h(0).measure_all()

    exported = circuit.to_qasm3_with_report()

    assert exported.value == circuit.to_qasm3()
    assert not exported.report.is_lossless
    assert exported.report.losses[0].code == "QCORE-INTEROP-CIRCUIT-METADATA-DROPPED"


def test_qasm3_export_reports_lossless_semantic_subset() -> None:
    circuit = Circuit(2).h(0).cx(0, 1).measure_all()

    exported = circuit.to_qasm3_with_report()

    assert exported.report.is_lossless
    assert "supported gate semantics" in exported.report.preserved
