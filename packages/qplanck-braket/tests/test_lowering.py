from __future__ import annotations

import pytest
from qplanck.pulse import (
    AcquireChannel,
    ConstantWaveform,
    DriveChannel,
    GaussianWaveform,
    PulseProgram,
    SampledWaveform,
)

from qplanck_braket import (
    BraketCapabilityError,
    BraketChannelMap,
    BraketPulseSnapshot,
    lower_pulse_program,
)
from qplanck_braket.lowering import _BraketSDK

from .fakes import (
    FakeFrame,
    FakePort,
    FakePulseSequence,
    arbitrary_waveform,
    constant_waveform,
    gaussian_waveform,
)


@pytest.fixture
def sdk() -> _BraketSDK:
    return _BraketSDK(
        pulse_sequence=FakePulseSequence,
        arbitrary_waveform=arbitrary_waveform,  # type: ignore[arg-type]
        constant_waveform=constant_waveform,  # type: ignore[arg-type]
        gaussian_waveform=gaussian_waveform,  # type: ignore[arg-type]
    )


@pytest.fixture
def frames() -> dict[str, FakeFrame]:
    return {
        "q0_drive": FakeFrame("q0_drive", FakePort("q0_rf", 1e-9)),
        "q1_drive": FakeFrame("q1_drive", FakePort("q1_rf", 1e-9)),
        "q0_readout": FakeFrame("q0_readout", FakePort("q0_rx", 1e-9)),
    }


def test_lowering_preserves_absolute_timing_and_waveforms(
    snapshot: BraketPulseSnapshot,
    frames: dict[str, FakeFrame],
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping(
        {DriveChannel(0): "q0_drive", DriveChannel(1): "q1_drive"},
        snapshot=snapshot,
    )
    program = (
        PulseProgram()
        .play(4, DriveChannel(0), ConstantWaveform(4, 0.2 + 0.1j))
        .shift_phase(8, DriveChannel(0), 0.25)
        .set_phase(8, DriveChannel(0), 0.5)
        .shift_frequency(8, DriveChannel(0), 1e6)
        .set_frequency(8, DriveChannel(0), 5e9)
        .delay(2, DriveChannel(1), 2)
        .play(4, DriveChannel(1), SampledWaveform((0.1, 0.2j)))
    )

    lowered = lower_pulse_program(
        program,
        channel_map=channel_map,
        snapshot=snapshot,
        frames=frames,
        _sdk=sdk,
    )

    assert [(kind, frame) for kind, frame, _ in lowered.operations] == [
        ("delay", "q1_drive"),
        ("delay", "q1_drive"),
        ("delay", "q0_drive"),
        ("play", "q0_drive"),
        ("play", "q1_drive"),
        ("shift_phase", "q0_drive"),
        ("set_phase", "q0_drive"),
        ("shift_frequency", "q0_drive"),
        ("set_frequency", "q0_drive"),
    ]
    assert lowered.operations[0][2] == (2e-9,)
    assert lowered.operations[1][2] == (2e-9,)
    constant = lowered.operations[3][2][0]
    sampled = lowered.operations[4][2][0]
    assert constant.kind == "constant"
    assert constant.kwargs == {"length": 4e-9, "iq": 0.2 + 0.1j, "id": "qplanck_w1"}
    assert sampled.kind == "arbitrary"
    assert sampled.kwargs["amplitudes"] == [0.1 + 0j, 0.2j]


def test_real_gaussian_uses_seconds(
    snapshot: BraketPulseSnapshot,
    frames: dict[str, FakeFrame],
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    program = PulseProgram().play(
        0,
        DriveChannel(0),
        GaussianWaveform(40, 10.0, 0.2),
    )
    lowered = lower_pulse_program(
        program,
        channel_map=channel_map,
        snapshot=snapshot,
        frames=frames,
        _sdk=sdk,
    )
    waveform = lowered.operations[0][2][0]
    assert waveform.kind == "gaussian"
    assert waveform.kwargs["length"] == 40e-9
    assert waveform.kwargs["sigma"] == 10e-9
    assert waveform.kwargs["amplitude"] == 0.2


def test_complex_gaussian_is_rejected(
    snapshot: BraketPulseSnapshot,
    frames: dict[str, FakeFrame],
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    program = PulseProgram().play(0, DriveChannel(0), GaussianWaveform(8, 2.0, 0.2j))
    with pytest.raises(BraketCapabilityError, match="real amplitude only"):
        lower_pulse_program(
            program,
            channel_map=channel_map,
            snapshot=snapshot,
            frames=frames,
            _sdk=sdk,
        )


def test_acquire_is_rejected_without_semantic_approximation(
    snapshot: BraketPulseSnapshot,
    frames: dict[str, FakeFrame],
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping(
        {AcquireChannel(0): "q0_readout"}, snapshot=snapshot
    )
    program = PulseProgram().acquire(0, AcquireChannel(0), 8, memory_slot=0)
    with pytest.raises(BraketCapabilityError, match="capture_v0"):
        lower_pulse_program(
            program,
            channel_map=channel_map,
            snapshot=snapshot,
            frames=frames,
            _sdk=sdk,
        )


def test_provider_frame_dt_must_match_snapshot(
    snapshot: BraketPulseSnapshot,
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    frames = {"q0_drive": FakeFrame("q0_drive", FakePort("q0_rf", 2e-9))}
    program = PulseProgram().delay(0, DriveChannel(0), 4)
    with pytest.raises(BraketCapabilityError, match="port dt"):
        lower_pulse_program(
            program,
            channel_map=channel_map,
            snapshot=snapshot,
            frames=frames,
            _sdk=sdk,
        )


def test_frame_change_at_play_start_is_emitted_before_play(
    snapshot: BraketPulseSnapshot,
    frames: dict[str, FakeFrame],
    sdk: _BraketSDK,
) -> None:
    channel_map = BraketChannelMap.from_mapping({DriveChannel(0): "q0_drive"}, snapshot=snapshot)
    program = (
        PulseProgram()
        .play(0, DriveChannel(0), ConstantWaveform(4, 0.2))
        .shift_phase(0, DriveChannel(0), 0.5)
    )
    lowered = lower_pulse_program(
        program,
        channel_map=channel_map,
        snapshot=snapshot,
        frames=frames,
        _sdk=sdk,
    )
    assert [operation[0] for operation in lowered.operations] == ["shift_phase", "play"]
