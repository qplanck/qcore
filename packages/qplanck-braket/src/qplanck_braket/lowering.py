"""Capability-aware lowering from QPlanck pulse schedules to Braket PulseSequence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qplanck.pulse import (
    Acquire,
    ConstantWaveform,
    Delay,
    GaussianWaveform,
    Play,
    PulseProgram,
    SampledWaveform,
    SetFrequency,
    SetPhase,
    ShiftFrequency,
    ShiftPhase,
)

from .channel_map import BraketChannelMap
from .errors import BraketCapabilityError
from .snapshot import BraketPulseSnapshot


@dataclass(frozen=True)
class _BraketSDK:
    pulse_sequence: type[Any]
    arbitrary_waveform: type[Any]
    constant_waveform: type[Any]
    gaussian_waveform: type[Any]


def _load_sdk() -> _BraketSDK:
    try:
        from braket.pulse import (
            ArbitraryWaveform,
            PulseSequence,
        )
        from braket.pulse import (
            ConstantWaveform as BraketConstantWaveform,
        )
        from braket.pulse import (
            GaussianWaveform as BraketGaussianWaveform,
        )
    except ImportError as exc:  # pragma: no cover - packaging dependency provides it
        raise BraketCapabilityError(
            "amazon-braket-sdk is required to lower a Braket pulse program."
        ) from exc
    return _BraketSDK(
        pulse_sequence=PulseSequence,
        arbitrary_waveform=ArbitraryWaveform,
        constant_waveform=BraketConstantWaveform,
        gaussian_waveform=BraketGaussianWaveform,
    )


def _validate_functions(program: PulseProgram, snapshot: BraketPulseSnapshot) -> None:
    required = {
        instruction.kind
        for instruction in program.instructions
        if not isinstance(instruction, Delay)
    }
    # Delay is OpenPulse syntax and is not always repeated in supportedFunctions.
    missing = sorted(required.difference(snapshot.supported_functions))
    if missing:
        raise BraketCapabilityError(
            "Braket pulse snapshot does not support: " + ", ".join(missing) + "."
        )

    required_waveforms = set()
    for instruction in program.instructions:
        if not isinstance(instruction, Play):
            continue
        if isinstance(instruction.waveform, ConstantWaveform):
            required_waveforms.add("constant")
        elif isinstance(instruction.waveform, GaussianWaveform):
            required_waveforms.add("gaussian")
    missing_waveforms = sorted(required_waveforms.difference(snapshot.supported_waveforms))
    if missing_waveforms:
        raise BraketCapabilityError(
            "Braket pulse snapshot does not support waveform templates: "
            + ", ".join(missing_waveforms)
            + "."
        )


def _validate_provider_limits(
    program: PulseProgram,
    snapshot: BraketPulseSnapshot,
    channel_map: BraketChannelMap,
) -> None:
    validation = dict(snapshot.validation_parameters)
    maximum_amplitude = float(validation.get("MAX_AMPLITUDE", 1.0) or 1.0)
    minimum_duration = float(validation.get("MIN_PULSE_LENGTH", 0.0) or 0.0)
    maximum_duration = float(validation.get("MAX_PULSE_LENGTH", float("inf")) or float("inf"))
    for instruction in program.instructions:
        if not isinstance(instruction, Play):
            continue
        if instruction.waveform.max_abs_amplitude > maximum_amplitude:
            raise BraketCapabilityError(
                f"Waveform amplitude {instruction.waveform.max_abs_amplitude} exceeds Braket "
                f"maximum {maximum_amplitude}."
            )
        duration_seconds = instruction.duration * channel_map[instruction.channel].dt_seconds
        if duration_seconds < minimum_duration or duration_seconds > maximum_duration:
            raise BraketCapabilityError(
                f"Waveform duration {duration_seconds} seconds is outside Braket limits."
            )


def _provider_waveform(
    waveform: object,
    *,
    dt_seconds: float,
    identifier: str,
    sdk: _BraketSDK,
) -> Any:
    if isinstance(waveform, ConstantWaveform):
        return sdk.constant_waveform(
            length=waveform.duration * dt_seconds,
            iq=waveform.amplitude,
            id=identifier,
        )
    if isinstance(waveform, SampledWaveform):
        return sdk.arbitrary_waveform(amplitudes=list(waveform.samples), id=identifier)
    if isinstance(waveform, GaussianWaveform):
        if waveform.amplitude.imag != 0:
            raise BraketCapabilityError(
                "Braket GaussianWaveform supports real amplitude only; use SampledWaveform "
                "for a complex Gaussian envelope."
            )
        return sdk.gaussian_waveform(
            length=waveform.duration * dt_seconds,
            sigma=waveform.sigma * dt_seconds,
            amplitude=waveform.amplitude.real,
            zero_at_edges=False,
            id=identifier,
        )
    raise BraketCapabilityError(f"Unsupported QPlanck waveform: {type(waveform).__name__}.")


def lower_pulse_program(
    program: PulseProgram,
    *,
    channel_map: BraketChannelMap,
    snapshot: BraketPulseSnapshot,
    frames: Mapping[str, Any],
    _sdk: _BraketSDK | None = None,
) -> Any:
    """Lower a validated absolute schedule to a Braket ``PulseSequence``.

    No provider call is made. ``frames`` must be the predefined frame mapping
    obtained from the same device as ``snapshot``. Per-frame delays preserve the
    absolute QPlanck sample timeline.
    """

    if not isinstance(program, PulseProgram):
        raise BraketCapabilityError("lower_pulse_program() expects a PulseProgram.")
    if not isinstance(channel_map, BraketChannelMap):
        raise BraketCapabilityError("lower_pulse_program() expects a BraketChannelMap.")
    if not isinstance(snapshot, BraketPulseSnapshot):
        raise BraketCapabilityError("lower_pulse_program() expects a BraketPulseSnapshot.")
    channel_map.validate_snapshot(snapshot)
    if any(isinstance(instruction, Acquire) for instruction in program.instructions):
        raise BraketCapabilityError(
            "QPlanck Acquire cannot be lowered to Braket capture_v0 without losing "
            "duration and memory-slot semantics; use circuit measurement instead."
        )
    _validate_functions(program, snapshot)
    _validate_provider_limits(program, snapshot, channel_map)

    sdk = _sdk or _load_sdk()
    sequence = sdk.pulse_sequence()
    cursors: dict[object, int] = {}
    ordered_instructions = sorted(
        enumerate(program.instructions),
        key=lambda item: (item[1].start, item[1].duration != 0, item[0]),
    )
    for index, instruction in ordered_instructions:
        channel = instruction.channels[0]
        try:
            binding = channel_map[channel]
        except KeyError as exc:
            raise BraketCapabilityError(
                f"Pulse channel {channel.kind.value}[{channel.index}] is not mapped to Braket."
            ) from exc
        try:
            frame = frames[binding.frame_id]
        except KeyError as exc:
            raise BraketCapabilityError(
                f"Predefined Braket frame {binding.frame_id!r} was not supplied."
            ) from exc
        provider_port = getattr(frame, "port", None)
        if provider_port is None or getattr(provider_port, "id", None) != binding.port_id:
            raise BraketCapabilityError(
                f"Frame {binding.frame_id!r} does not reference expected port {binding.port_id!r}."
            )
        provider_dt = getattr(provider_port, "dt", None)
        if provider_dt is None or not math.isclose(
            float(provider_dt), binding.dt_seconds, rel_tol=0.0, abs_tol=0.0
        ):
            raise BraketCapabilityError(
                f"Frame {binding.frame_id!r} port dt does not match the captured snapshot."
            )
        if getattr(frame, "is_predefined", False) is not True:
            raise BraketCapabilityError(
                f"Frame {binding.frame_id!r} is not a predefined device frame."
            )

        cursor = cursors.get(channel, 0)
        if instruction.start < cursor:
            raise BraketCapabilityError(
                f"Instruction at sample {instruction.start} overlaps prior lowering on "
                f"{channel.kind.value}[{channel.index}]."
            )
        if instruction.start > cursor:
            sequence.delay(frame, (instruction.start - cursor) * binding.dt_seconds)
            cursor = instruction.start

        if isinstance(instruction, Play):
            provider_waveform = _provider_waveform(
                instruction.waveform,
                dt_seconds=binding.dt_seconds,
                identifier=f"qplanck_w{index}",
                sdk=sdk,
            )
            sequence.play(frame, provider_waveform)
        elif isinstance(instruction, Delay):
            sequence.delay(frame, instruction.duration * binding.dt_seconds)
        elif isinstance(instruction, ShiftPhase):
            sequence.shift_phase(frame, instruction.phase)
        elif isinstance(instruction, SetPhase):
            sequence.set_phase(frame, instruction.phase)
        elif isinstance(instruction, ShiftFrequency):
            sequence.shift_frequency(frame, instruction.frequency)
        elif isinstance(instruction, SetFrequency):
            sequence.set_frequency(frame, instruction.frequency)
        else:  # pragma: no cover - exhaustive while qplanck.pulse is unchanged
            raise BraketCapabilityError(
                f"Unsupported QPlanck instruction: {type(instruction).__name__}."
            )
        cursors[channel] = max(cursor, instruction.end)
    return sequence
