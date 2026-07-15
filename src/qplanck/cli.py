"""Command-line interface for QCore."""

from __future__ import annotations

import argparse
import platform
import sys
from importlib.util import find_spec
from pathlib import Path

import numpy as np

from qplanck import __version__
from qplanck.circuit import Circuit
from qplanck.errors import QPlanckError
from qplanck.pulse import ConstantWaveform, DriveChannel, PulseProgram, PulseTarget
from qplanck.simulator import Simulator


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "doctor":
            return _doctor()
        if args.command == "draw":
            circuit = _load_circuit(Path(args.input))
            print(circuit.draw())
            return 0
        if args.command == "trace":
            circuit = _load_circuit(Path(args.input))
            trace = Simulator("statevector").run(circuit, trace=True).trace
            if trace is None:
                raise QPlanckError("Trace generation failed.")
            payload = trace.to_json(indent=2)
            if args.output:
                Path(args.output).write_text(payload + "\n", encoding="utf-8")
            else:
                print(payload)
            return 0
    except QPlanckError as exc:
        print(f"qplanck: error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qplanck", description="QCore command-line tools.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Check the local QCore environment.")

    draw = subparsers.add_parser("draw", help="Draw a QCore IR JSON or OpenQASM 3 circuit.")
    draw.add_argument("input", help="Path to circuit JSON or OpenQASM 3 input.")

    trace = subparsers.add_parser("trace", help="Emit portable trace JSON for a circuit.")
    trace.add_argument("input", help="Path to circuit JSON or OpenQASM 3 input.")
    trace.add_argument(
        "--output", "-o", help="Path to write trace JSON. Prints to stdout when omitted."
    )

    return parser


def _doctor() -> int:
    circuit = Circuit(2, name="doctor").h(0).cx(0, 1).measure_all()
    result = Simulator("statevector").run(circuit, shots=16, seed=7, trace=True)
    compiled = circuit.compile()
    qir_module = compiled.to_circuit().to_qir()
    drive = DriveChannel(0)
    pulse_program = PulseProgram(name="doctor").play(
        0, drive, ConstantWaveform(duration=4, amplitude=0.25)
    )
    pulse_program.validate(PulseTarget(channels=frozenset({drive})))
    qiskit_available = find_spec("qiskit") is not None
    print("QCore doctor")
    print(f"  qplanck: {__version__}")
    print(f"  python: {platform.python_version()}")
    print(f"  numpy: {np.__version__}")
    print(f"  qiskit optional dependency: {'available' if qiskit_available else 'not installed'}")
    print(f"  smoke test counts: {result.counts}")
    print("  trace: ok" if result.trace is not None else "  trace: failed")
    print(f"  compiler: {compiled.trace.pipeline_id}")
    print(f"  qir: {qir_module.manifest.qir_version} {qir_module.profile.value}")
    print(f"  pulse schema: {pulse_program.schema_version}")
    return 0 if result.trace is not None else 1


def _load_circuit(path: Path) -> Circuit:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json" or text.lstrip().startswith("{"):
        return Circuit.from_json(text)
    return Circuit.from_qasm3(text)


if __name__ == "__main__":
    raise SystemExit(main())
