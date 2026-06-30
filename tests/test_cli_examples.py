import runpy

from qplanck.cli import main


def test_cli_doctor(capsys) -> None:
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "QCore doctor" in captured.out
    assert "trace: ok" in captured.out


def test_cli_draw_and_trace(tmp_path, capsys) -> None:
    qasm_path = tmp_path / "bell.qasm"
    trace_path = tmp_path / "trace.json"
    qasm_path.write_text(
        "\n".join(
            [
                "OPENQASM 3.0;",
                'include "stdgates.inc";',
                "qubit[2] q;",
                "bit[2] c;",
                "h q[0];",
                "cx q[0], q[1];",
                "measure q[0] -> c[0];",
                "measure q[1] -> c[1];",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["draw", str(qasm_path)]) == 0
    assert "q0" in capsys.readouterr().out

    assert main(["trace", str(qasm_path), "--output", str(trace_path)]) == 0
    assert '"schema_version": "qplanck.trace.v0.1"' in trace_path.read_text(encoding="utf-8")


def test_examples_run() -> None:
    runpy.run_path("examples/bell_state.py", run_name="__main__")
    runpy.run_path("examples/qiskit_roundtrip.py", run_name="__main__")
