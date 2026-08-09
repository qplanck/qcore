from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("braket", reason="amazon-braket-sdk is an adapter runtime dependency")

from braket.pulse import Frame, Port
from qplanck.ir import CircuitIR, MeasurementSpec, Operation
from qplanck.pulse import (
    CalibrationKey,
    CalibrationLibrary,
    ConstantWaveform,
    DriveChannel,
    GaussianWaveform,
    PulseProgram,
    SampledWaveform,
)
from qplanck.runtime import CalibratedCircuit
from qplanck.targets import Target

from qplanck_braket import BraketChannelMap, BraketPulseSnapshot, lower_pulse_program
from qplanck_braket.backend import _build_provider_payload, _load_circuit_sdk


@dataclass(frozen=True)
class _Trace:
    def to_dict(self) -> dict[str, object]:
        return {"events": []}


@dataclass(frozen=True)
class _Compiled:
    source_ir: CircuitIR
    ir: CircuitIR
    target: Target
    trace: _Trace = _Trace()

    def to_dict(self) -> dict[str, object]:
        return {"source_ir": self.source_ir.to_dict(), "compiled_ir": self.ir.to_dict()}


def test_pinned_sdk_emits_deterministic_openpulse(
    snapshot: BraketPulseSnapshot,
) -> None:
    channel = DriveChannel(0)
    channel_map = BraketChannelMap.from_mapping({channel: "q0_drive"}, snapshot=snapshot)
    frame = Frame(
        "q0_drive",
        Port("q0_rf", 1e-9),
        frequency=5e9,
        is_predefined=True,
    )
    program = (
        PulseProgram()
        .play(0, channel, ConstantWaveform(4, 0.2 + 0.1j))
        .play(4, channel, GaussianWaveform(8, 2.0, 0.3))
        .play(12, channel, SampledWaveform((0.1, 0.2j)))
    )
    sequence = lower_pulse_program(
        program,
        channel_map=channel_map,
        snapshot=snapshot,
        frames={"q0_drive": frame},
    )
    source = sequence.to_ir()
    assert "waveform qplanck_w0 = constant(4.0ns, 0.2 + 0.1im);" in source
    assert "waveform qplanck_w1 = gaussian(8.0ns, 2.0ns, 0.3, false);" in source
    assert "waveform qplanck_w2 = {0.1, 0.2im};" in source
    assert source.count("play(q0_drive") == 3


def test_pinned_sdk_composes_physical_circuit_and_defcal(
    snapshot: BraketPulseSnapshot,
) -> None:
    channel = DriveChannel(0)
    channel_map = BraketChannelMap.from_mapping({channel: "q0_drive"}, snapshot=snapshot)
    frame = Frame(
        "q0_drive",
        Port("q0_rf", 1e-9),
        frequency=5e9,
        is_predefined=True,
    )
    target = Target.testing(1, basis_gates=frozenset({"x"}))
    ir = CircuitIR(
        1,
        operations=(Operation("x", (0,)),),
        measurements=(MeasurementSpec(0, 0),),
    )
    compiled = _Compiled(ir, ir, target)
    calibrations = CalibrationLibrary.from_mapping(
        {CalibrationKey("x", (0,)): PulseProgram().play(0, channel, ConstantWaveform(4, 0.2))}
    )
    calibrated = CalibratedCircuit(
        compiled,  # type: ignore[arg-type]
        calibrations,
        target.content_hash,
        snapshot.snapshot_hash,
    )
    circuit, gate_definitions = _build_provider_payload(
        calibrated,
        channel_map=channel_map,
        snapshot=snapshot,
        frames={"q0_drive": frame},
        sdk=_load_circuit_sdk(),
    )
    source = circuit.to_ir(gate_definitions=gate_definitions).source
    assert "defcal x $0" in source
    assert "x $0;" in source
    assert "measure $0;" in source
