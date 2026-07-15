from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from qplanck.pulse import (
    Acquire,
    AcquireChannel,
    CalibrationKey,
    CalibrationLibrary,
    ConstantWaveform,
    ControlChannel,
    Delay,
    DriveChannel,
    GaussianWaveform,
    MeasureChannel,
    Play,
    PulseError,
    PulseProgram,
    PulseTarget,
    SampledWaveform,
    SetFrequency,
    SetPhase,
    ShiftFrequency,
    ShiftPhase,
    channel_from_dict,
    instruction_from_dict,
    waveform_from_dict,
)


def test_channels_are_typed_immutable_and_round_trip() -> None:
    channels = (
        DriveChannel(0),
        MeasureChannel(1),
        AcquireChannel(2),
        ControlChannel(3),
    )

    assert tuple(channel_from_dict(channel.to_dict()) for channel in channels) == channels
    assert DriveChannel(0) != MeasureChannel(0)
    with pytest.raises(FrozenInstanceError):
        channels[0].index = 4  # type: ignore[misc]
    with pytest.raises(PulseError, match="non-negative"):
        DriveChannel(-1)
    with pytest.raises(PulseError, match="integer"):
        DriveChannel(True)  # type: ignore[arg-type]
    with pytest.raises(PulseError, match="Unsupported channel kind"):
        channel_from_dict({"kind": "flux", "index": 0})


@pytest.mark.parametrize(
    "waveform",
    [
        GaussianWaveform(duration=16, sigma=4.0, amplitude=0.5 + 0.25j),
        ConstantWaveform(duration=8, amplitude=-0.5j),
        SampledWaveform((0j, 0.25 + 0.5j, -1.0 + 0j)),
    ],
)
def test_waveforms_round_trip_with_finite_bounded_samples(waveform: object) -> None:
    assert waveform_from_dict(waveform.to_dict()) == waveform  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ConstantWaveform(0, 0.5), "positive"),
        (lambda: ConstantWaveform(4, 1.01), "must not exceed"),
        (lambda: ConstantWaveform(4, complex(float("nan"), 0)), "finite"),
        (lambda: GaussianWaveform(8, 0.0), "sigma must be positive"),
        (lambda: GaussianWaveform(8, float("inf")), "finite"),
        (lambda: SampledWaveform(()), "at least one"),
        (lambda: SampledWaveform((0j, complex(0, float("inf")))), "finite"),
    ],
)
def test_invalid_waveforms_are_rejected(factory: object, message: str) -> None:
    with pytest.raises(PulseError, match=message):
        factory()  # type: ignore[operator]


def test_all_instruction_types_round_trip() -> None:
    drive = DriveChannel(0)
    acquire = AcquireChannel(0)
    instructions = (
        Play(0, drive, ConstantWaveform(8, 0.25)),
        Delay(8, drive, 4),
        ShiftPhase(12, drive, 0.1),
        SetPhase(12, drive, 0.2),
        ShiftFrequency(12, drive, 1_000_000.0),
        SetFrequency(12, drive, 5_000_000_000.0),
        Acquire(0, acquire, 12, memory_slot=0),
    )

    assert tuple(instruction_from_dict(item.to_dict()) for item in instructions) == instructions
    assert instructions[0].end == 8
    assert instructions[2].duration == 0


def test_instruction_channel_roles_are_enforced() -> None:
    with pytest.raises(PulseError, match="drive, measure, or control"):
        Play(0, AcquireChannel(0), ConstantWaveform(4, 0.1))
    with pytest.raises(PulseError, match="acquire channel"):
        Acquire(0, DriveChannel(0), 4)  # type: ignore[arg-type]
    with pytest.raises(PulseError, match="non-negative"):
        Delay(-1, DriveChannel(0), 4)
    with pytest.raises(PulseError, match="finite"):
        SetPhase(0, DriveChannel(0), float("nan"))


def test_program_immutable_builder_orders_timeline_and_preserves_original() -> None:
    drive = DriveChannel(0)
    empty = PulseProgram(name="x_q0")
    program = (
        empty.play(8, drive, ConstantWaveform(4, 0.2)).shift_phase(0, drive, 0.5).delay(0, drive, 8)
    )

    assert empty.instructions == ()
    assert tuple(instruction.start for instruction in program.instructions) == (0, 0, 8)
    assert program.duration == 12
    with pytest.raises(FrozenInstanceError):
        program.name = "changed"  # type: ignore[misc]


def test_program_rejects_channel_overlap_but_allows_adjacency() -> None:
    drive = DriveChannel(0)
    waveform = ConstantWaveform(8, 0.5)

    adjacent = PulseProgram((Play(0, drive, waveform), Play(8, drive, waveform)))
    assert adjacent.duration == 16

    with pytest.raises(PulseError, match=r"overlap on drive\[0\]"):
        PulseProgram((Play(0, drive, waveform), Delay(7, drive, 2)))


def test_program_allows_parallel_channels_and_measure_acquire() -> None:
    program = PulseProgram(
        (
            Play(0, DriveChannel(0), ConstantWaveform(8, 0.25)),
            Play(0, DriveChannel(1), ConstantWaveform(8, 0.25)),
            Play(8, MeasureChannel(0), GaussianWaveform(16, 4.0, 0.4)),
            Acquire(8, AcquireChannel(0), 16, memory_slot=0),
        )
    )

    assert program.duration == 24


def test_frame_change_is_allowed_at_boundaries_not_inside_active_interval() -> None:
    drive = DriveChannel(0)
    waveform = ConstantWaveform(8, 0.5)

    PulseProgram(
        (
            SetPhase(0, drive, 0.0),
            Play(0, drive, waveform),
            ShiftPhase(8, drive, 0.2),
        )
    )
    with pytest.raises(PulseError, match="inside an active interval"):
        PulseProgram((Play(0, drive, waveform), ShiftFrequency(4, drive, 1e6)))


def test_program_json_is_canonical_and_round_trips() -> None:
    program = PulseProgram(
        (
            SetFrequency(0, DriveChannel(0), 5e9),
            Play(0, DriveChannel(0), SampledWaveform((0j, 0.5j, 0j))),
            Acquire(0, AcquireChannel(0), 3, memory_slot=2),
        ),
        name="readout",
    )

    encoded = program.to_json()

    assert encoded == program.to_json()
    assert " " not in encoded
    assert PulseProgram.from_json(encoded) == program
    assert json.loads(encoded) == program.to_dict()
    with pytest.raises(PulseError, match="Invalid pulse program JSON"):
        PulseProgram.from_json("{")
    with pytest.raises(PulseError, match="Unsupported pulse schema"):
        PulseProgram.from_dict({"schema_version": "future", "instructions": []})


def test_target_accepts_valid_program_and_round_trips() -> None:
    program = PulseProgram(
        (
            Play(0, DriveChannel(0), ConstantWaveform(8, 0.4)),
            Acquire(8, AcquireChannel(0), 8),
        )
    )
    target = PulseTarget(
        channels=frozenset({DriveChannel(0), AcquireChannel(0)}),
        dt_seconds=2.22e-10,
        granularity=4,
        min_duration=4,
        pulse_alignment=4,
        acquire_alignment=8,
        max_program_duration=32,
        max_amplitude=0.5,
    )

    program.validate(target)
    assert PulseTarget.from_dict(target.to_dict()) == target
    assert target.to_dict()["channels"] == [
        {"kind": "acquire", "index": 0},
        {"kind": "drive", "index": 0},
    ]


@pytest.mark.parametrize(
    ("program", "target", "message"),
    [
        (
            PulseProgram((Play(0, DriveChannel(1), ConstantWaveform(4, 0.2)),)),
            PulseTarget(frozenset({DriveChannel(0)})),
            r"does not define drive\[1\]",
        ),
        (
            PulseProgram((Play(2, DriveChannel(0), ConstantWaveform(4, 0.2)),)),
            PulseTarget(frozenset({DriveChannel(0)}), pulse_alignment=4),
            "not aligned",
        ),
        (
            PulseProgram((Play(0, DriveChannel(0), ConstantWaveform(6, 0.2)),)),
            PulseTarget(frozenset({DriveChannel(0)}), granularity=4),
            "not a multiple",
        ),
        (
            PulseProgram((Play(0, DriveChannel(0), ConstantWaveform(4, 0.6)),)),
            PulseTarget(frozenset({DriveChannel(0)}), max_amplitude=0.5),
            "exceeds target maximum",
        ),
        (
            PulseProgram((Delay(0, DriveChannel(0), 8),)),
            PulseTarget(frozenset({DriveChannel(0)}), max_program_duration=4),
            "exceeds target maximum",
        ),
    ],
)
def test_target_rejects_constraint_violations(
    program: PulseProgram,
    target: PulseTarget,
    message: str,
) -> None:
    with pytest.raises(PulseError, match=message):
        target.validate(program)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PulseTarget(frozenset()),
        lambda: PulseTarget(frozenset({DriveChannel(0)}), dt_seconds=0),
        lambda: PulseTarget(frozenset({DriveChannel(0)}), granularity=0),
        lambda: PulseTarget(frozenset({DriveChannel(0)}), max_amplitude=1.1),
    ],
)
def test_invalid_target_constraints_are_rejected(factory: object) -> None:
    with pytest.raises(PulseError):
        factory()  # type: ignore[operator]


def test_calibration_key_normalizes_and_validates_signature() -> None:
    key = CalibrationKey(" RX ", (1,), (0, 0.5))

    assert key == CalibrationKey.from_dict(key.to_dict())
    assert key.gate == "rx"
    assert key.parameters == (0.0, 0.5)
    with pytest.raises(PulseError, match="distinct"):
        CalibrationKey("cx", (0, 0))
    with pytest.raises(PulseError, match="at least one"):
        CalibrationKey("x", ())
    with pytest.raises(PulseError, match="finite"):
        CalibrationKey("rx", (0,), (float("nan"),))


def test_calibration_library_is_mapping_like_immutable_and_canonical() -> None:
    x_key = CalibrationKey("x", (0,))
    rx_key = CalibrationKey("rx", (0,), (0.5,))
    x_program = PulseProgram().play(0, DriveChannel(0), ConstantWaveform(4, 0.5))
    rx_program = PulseProgram().play(0, DriveChannel(0), GaussianWaveform(8, 2.0, 0.4))

    empty = CalibrationLibrary()
    library = empty.with_calibration(x_key, x_program).with_calibration(rx_key, rx_program)

    assert len(empty) == 0
    assert len(library) == 2
    assert library[x_key] == x_program
    assert library.resolve("rx", (0,), (0.5,)) == rx_program
    assert list(library) == [rx_key, x_key]
    assert CalibrationLibrary.from_json(library.to_json()) == library
    assert CalibrationLibrary.from_mapping(dict(library.items())) == library
    with pytest.raises(PulseError, match="already exists"):
        library.with_calibration(x_key, rx_program)
    replaced = library.with_calibration(x_key, rx_program, replace=True)
    assert replaced[x_key] == rx_program


def test_calibration_library_rejects_duplicates_and_validates_target() -> None:
    key = CalibrationKey("x", (0,))
    program = PulseProgram().play(0, DriveChannel(0), ConstantWaveform(4, 0.5))

    with pytest.raises(PulseError, match="Duplicate calibration"):
        CalibrationLibrary(((key, program), (key, program)))

    library = CalibrationLibrary(((key, program),))
    library.validate(PulseTarget(frozenset({DriveChannel(0)}), granularity=4))
    with pytest.raises(PulseError, match="does not define"):
        library.validate(PulseTarget(frozenset({DriveChannel(1)})))


def test_calibration_library_rejects_unknown_schema_and_invalid_json() -> None:
    with pytest.raises(PulseError, match="Unsupported calibration schema"):
        CalibrationLibrary.from_dict({"schema_version": "future", "calibrations": []})
    with pytest.raises(PulseError, match="Invalid calibration library JSON"):
        CalibrationLibrary.from_json("[")
