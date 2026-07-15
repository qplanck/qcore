"""Provider-neutral pulse scheduling and calibration contracts.

This module defines QPlanck's own deterministic pulse representation.  It is a
safe interchange boundary for compiler passes, calibration stores, and future
provider adapters; it does not execute hardware programs.

The JSON emitted here is the ``qplanck.pulse.v0.1`` schema.  It is deliberately
not labelled as OpenPulse or OpenQASM calibration syntax: those standards and
provider dialects require a separate, capability-aware lowering step.  Keeping
that boundary explicit prevents a locally valid program from being mistaken for
a portable hardware program.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol, runtime_checkable

from qplanck.errors import QPlanckError

PULSE_SCHEMA_VERSION = "qplanck.pulse.v0.1"
CALIBRATION_SCHEMA_VERSION = "qplanck.calibrations.v0.1"


class PulseError(QPlanckError):
    """Raised when a pulse program, target, or calibration is invalid."""


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PulseError(f"{label} must be an integer.")
    if value < 0:
        raise PulseError(f"{label} must be non-negative.")
    return value


def _positive_int(value: object, *, label: str) -> int:
    result = _non_negative_int(value, label=label)
    if result == 0:
        raise PulseError(f"{label} must be positive.")
    return result


def _finite_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PulseError(f"{label} must be a real number.")
    result = float(value)
    if not math.isfinite(result):
        raise PulseError(f"{label} must be finite.")
    return 0.0 if result == 0.0 else result


def _bounded_complex(value: object, *, label: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, int | float | complex):
        raise PulseError(f"{label} must be a number.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise PulseError(f"{label} must be finite.")
    if abs(result) > 1.0:
        raise PulseError(f"{label} magnitude must not exceed 1.0.")
    real = 0.0 if result.real == 0.0 else result.real
    imag = 0.0 if result.imag == 0.0 else result.imag
    return complex(real, imag)


def _complex_to_dict(value: complex) -> dict[str, float]:
    return {"real": value.real, "imag": value.imag}


def _complex_from_dict(data: object, *, label: str) -> complex:
    if not isinstance(data, Mapping):
        raise PulseError(f"{label} must contain real and imag fields.")
    if "real" not in data or "imag" not in data:
        raise PulseError(f"{label} must contain real and imag fields.")
    real = _finite_float(data["real"], label=f"{label}.real")
    imag = _finite_float(data["imag"], label=f"{label}.imag")
    return _bounded_complex(complex(real, imag), label=label)


def _canonical_json(data: Mapping[str, Any], *, indent: int | None = None) -> str:
    if indent is None:
        return json.dumps(data, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return json.dumps(data, allow_nan=False, indent=indent, sort_keys=True)


class ChannelKind(StrEnum):
    """Hardware-neutral channel roles."""

    DRIVE = "drive"
    MEASURE = "measure"
    ACQUIRE = "acquire"
    CONTROL = "control"


class Channel(ABC):
    """Base class for immutable, typed pulse channel identifiers."""

    index: int

    @property
    @abstractmethod
    def kind(self) -> ChannelKind:
        """Return the semantic role of this channel."""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "index": self.index}


@dataclass(frozen=True)
class DriveChannel(Channel):
    """Qubit drive channel."""

    index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _non_negative_int(self.index, label="Channel index"))

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.DRIVE


@dataclass(frozen=True)
class MeasureChannel(Channel):
    """Measurement stimulus channel."""

    index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _non_negative_int(self.index, label="Channel index"))

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.MEASURE


@dataclass(frozen=True)
class AcquireChannel(Channel):
    """Measurement acquisition channel."""

    index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _non_negative_int(self.index, label="Channel index"))

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.ACQUIRE


@dataclass(frozen=True)
class ControlChannel(Channel):
    """Multi-qubit or auxiliary control channel."""

    index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _non_negative_int(self.index, label="Channel index"))

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.CONTROL


def channel_from_dict(data: Mapping[str, Any]) -> Channel:
    """Deserialize a typed channel identifier."""

    kind = data.get("kind")
    index = _non_negative_int(data.get("index"), label="Channel index")
    if kind == ChannelKind.DRIVE.value:
        return DriveChannel(index)
    if kind == ChannelKind.MEASURE.value:
        return MeasureChannel(index)
    if kind == ChannelKind.ACQUIRE.value:
        return AcquireChannel(index)
    if kind == ChannelKind.CONTROL.value:
        return ControlChannel(index)
    raise PulseError(f"Unsupported channel kind: {kind!r}.")


@runtime_checkable
class Waveform(Protocol):
    """Structural contract for bounded, finite pulse envelopes."""

    @property
    def duration(self) -> int:
        """Duration in target clock samples."""
        ...

    @property
    def max_abs_amplitude(self) -> float:
        """Maximum envelope magnitude."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible waveform payload."""
        ...


@dataclass(frozen=True)
class GaussianWaveform:
    """A Gaussian envelope sampled for ``duration`` target clock ticks."""

    duration: int
    sigma: float
    amplitude: complex = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_int(self.duration, label="Duration"))
        sigma = _finite_float(self.sigma, label="Gaussian sigma")
        if sigma <= 0:
            raise PulseError("Gaussian sigma must be positive.")
        object.__setattr__(self, "sigma", sigma)
        object.__setattr__(
            self,
            "amplitude",
            _bounded_complex(self.amplitude, label="Gaussian amplitude"),
        )

    @property
    def max_abs_amplitude(self) -> float:
        return abs(self.amplitude)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "gaussian",
            "duration": self.duration,
            "sigma": self.sigma,
            "amplitude": _complex_to_dict(self.amplitude),
        }


@dataclass(frozen=True)
class ConstantWaveform:
    """A constant complex envelope."""

    duration: int
    amplitude: complex

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_int(self.duration, label="Duration"))
        object.__setattr__(
            self,
            "amplitude",
            _bounded_complex(self.amplitude, label="Constant amplitude"),
        )

    @property
    def max_abs_amplitude(self) -> float:
        return abs(self.amplitude)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "constant",
            "duration": self.duration,
            "amplitude": _complex_to_dict(self.amplitude),
        }


@dataclass(frozen=True)
class SampledWaveform:
    """An explicit sequence of finite complex samples bounded by unit magnitude."""

    samples: tuple[complex, ...]

    def __post_init__(self) -> None:
        samples = tuple(
            _bounded_complex(sample, label=f"Waveform sample {index}")
            for index, sample in enumerate(self.samples)
        )
        if not samples:
            raise PulseError("A sampled waveform must contain at least one sample.")
        object.__setattr__(self, "samples", samples)

    @property
    def duration(self) -> int:
        return len(self.samples)

    @property
    def max_abs_amplitude(self) -> float:
        return max(abs(sample) for sample in self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "sampled",
            "samples": [_complex_to_dict(sample) for sample in self.samples],
        }


def waveform_from_dict(data: Mapping[str, Any]) -> Waveform:
    """Deserialize a waveform from the QPlanck pulse schema."""

    kind = data.get("kind")
    if kind == "gaussian":
        return GaussianWaveform(
            duration=_positive_int(data.get("duration"), label="Duration"),
            sigma=_finite_float(data.get("sigma"), label="Gaussian sigma"),
            amplitude=_complex_from_dict(data.get("amplitude"), label="Gaussian amplitude"),
        )
    if kind == "constant":
        return ConstantWaveform(
            duration=_positive_int(data.get("duration"), label="Duration"),
            amplitude=_complex_from_dict(data.get("amplitude"), label="Constant amplitude"),
        )
    if kind == "sampled":
        raw_samples = data.get("samples")
        if not isinstance(raw_samples, list):
            raise PulseError("Sampled waveform samples must be a list.")
        return SampledWaveform(
            tuple(
                _complex_from_dict(sample, label=f"Waveform sample {index}")
                for index, sample in enumerate(raw_samples)
            )
        )
    raise PulseError(f"Unsupported waveform kind: {kind!r}.")


def _validate_start(value: object) -> int:
    return _non_negative_int(value, label="Instruction start")


def _validate_output_channel(channel: object) -> Channel:
    if not isinstance(channel, DriveChannel | MeasureChannel | ControlChannel):
        raise PulseError("This instruction requires a drive, measure, or control channel.")
    return channel


class Instruction(ABC):
    """Base class for instructions placed on an absolute sample timeline."""

    start: int

    @property
    @abstractmethod
    def kind(self) -> str:
        """Serialized instruction discriminator."""

    @property
    @abstractmethod
    def channels(self) -> tuple[Channel, ...]:
        """Channels touched by this instruction."""

    @property
    @abstractmethod
    def duration(self) -> int:
        """Occupied duration, or zero for frame changes."""

    @property
    def end(self) -> int:
        return self.start + self.duration

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible instruction payload."""


@dataclass(frozen=True)
class Play(Instruction):
    """Play a waveform on an output channel."""

    start: int
    channel: Channel
    waveform: Waveform

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        object.__setattr__(self, "channel", _validate_output_channel(self.channel))
        if not isinstance(self.waveform, Waveform):
            raise PulseError("Play requires a Waveform.")

    @property
    def kind(self) -> str:
        return "play"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return self.waveform.duration

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "waveform": self.waveform.to_dict(),
        }


@dataclass(frozen=True)
class Delay(Instruction):
    """Reserve a channel for a duration without emitting a waveform."""

    start: int
    channel: Channel
    length: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        if not isinstance(self.channel, Channel):
            raise PulseError("Delay requires a pulse channel.")
        object.__setattr__(self, "length", _positive_int(self.length, label="Delay duration"))

    @property
    def kind(self) -> str:
        return "delay"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return self.length

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "duration": self.duration,
        }


@dataclass(frozen=True)
class ShiftPhase(Instruction):
    """Shift an output channel frame phase by radians."""

    start: int
    channel: Channel
    phase: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        object.__setattr__(self, "channel", _validate_output_channel(self.channel))
        object.__setattr__(self, "phase", _finite_float(self.phase, label="Phase"))

    @property
    def kind(self) -> str:
        return "shift_phase"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "phase": self.phase,
        }


@dataclass(frozen=True)
class SetPhase(Instruction):
    """Set an output channel frame phase in radians."""

    start: int
    channel: Channel
    phase: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        object.__setattr__(self, "channel", _validate_output_channel(self.channel))
        object.__setattr__(self, "phase", _finite_float(self.phase, label="Phase"))

    @property
    def kind(self) -> str:
        return "set_phase"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "phase": self.phase,
        }


@dataclass(frozen=True)
class ShiftFrequency(Instruction):
    """Shift an output channel frame frequency in hertz."""

    start: int
    channel: Channel
    frequency: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        object.__setattr__(self, "channel", _validate_output_channel(self.channel))
        object.__setattr__(
            self,
            "frequency",
            _finite_float(self.frequency, label="Frequency"),
        )

    @property
    def kind(self) -> str:
        return "shift_frequency"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "frequency": self.frequency,
        }


@dataclass(frozen=True)
class SetFrequency(Instruction):
    """Set an output channel frame frequency in hertz."""

    start: int
    channel: Channel
    frequency: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        object.__setattr__(self, "channel", _validate_output_channel(self.channel))
        object.__setattr__(
            self,
            "frequency",
            _finite_float(self.frequency, label="Frequency"),
        )

    @property
    def kind(self) -> str:
        return "set_frequency"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "frequency": self.frequency,
        }


@dataclass(frozen=True)
class Acquire(Instruction):
    """Acquire samples into an optional hardware-neutral memory slot."""

    start: int
    channel: AcquireChannel
    length: int
    memory_slot: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _validate_start(self.start))
        if not isinstance(self.channel, AcquireChannel):
            raise PulseError("Acquire requires an acquire channel.")
        object.__setattr__(
            self,
            "length",
            _positive_int(self.length, label="Acquisition duration"),
        )
        if self.memory_slot is not None:
            object.__setattr__(
                self,
                "memory_slot",
                _non_negative_int(self.memory_slot, label="Memory slot"),
            )

    @property
    def kind(self) -> str:
        return "acquire"

    @property
    def channels(self) -> tuple[Channel, ...]:
        return (self.channel,)

    @property
    def duration(self) -> int:
        return self.length

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "channel": self.channel.to_dict(),
            "duration": self.duration,
            "memory_slot": self.memory_slot,
        }


def instruction_from_dict(data: Mapping[str, Any]) -> Instruction:
    """Deserialize a scheduled instruction."""

    kind = data.get("kind")
    raw_channel = data.get("channel")
    if not isinstance(raw_channel, Mapping):
        raise PulseError("Instruction channel must be an object.")
    channel = channel_from_dict(raw_channel)
    start = _validate_start(data.get("start"))
    if kind == "play":
        raw_waveform = data.get("waveform")
        if not isinstance(raw_waveform, Mapping):
            raise PulseError("Play waveform must be an object.")
        return Play(start, channel, waveform_from_dict(raw_waveform))
    if kind == "delay":
        return Delay(start, channel, _positive_int(data.get("duration"), label="Delay duration"))
    if kind == "shift_phase":
        return ShiftPhase(start, channel, _finite_float(data.get("phase"), label="Phase"))
    if kind == "set_phase":
        return SetPhase(start, channel, _finite_float(data.get("phase"), label="Phase"))
    if kind == "shift_frequency":
        return ShiftFrequency(
            start,
            channel,
            _finite_float(data.get("frequency"), label="Frequency"),
        )
    if kind == "set_frequency":
        return SetFrequency(
            start,
            channel,
            _finite_float(data.get("frequency"), label="Frequency"),
        )
    if kind == "acquire":
        if not isinstance(channel, AcquireChannel):
            raise PulseError("Acquire requires an acquire channel.")
        raw_slot = data.get("memory_slot")
        memory_slot = None if raw_slot is None else _non_negative_int(raw_slot, label="Memory slot")
        return Acquire(
            start,
            channel,
            _positive_int(data.get("duration"), label="Acquisition duration"),
            memory_slot,
        )
    raise PulseError(f"Unsupported instruction kind: {kind!r}.")


def _channel_label(channel: Channel) -> str:
    return f"{channel.kind.value}[{channel.index}]"


@dataclass(frozen=True)
class PulseProgram:
    """An immutable, validated schedule on an absolute integer-sample timeline.

    Positive-duration instructions may not overlap on the same channel.  Frame
    changes are permitted at interval boundaries but not inside an active play,
    delay, or acquisition interval.
    """

    instructions: tuple[Instruction, ...] = ()
    name: str | None = None
    schema_version: str = PULSE_SCHEMA_VERSION

    SUPPORTED_SCHEMA: ClassVar[str] = PULSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PULSE_SCHEMA_VERSION:
            raise PulseError(f"Unsupported pulse schema version: {self.schema_version}.")
        if self.name is not None:
            name = self.name.strip()
            if not name:
                raise PulseError("Pulse program name must be non-empty when provided.")
            object.__setattr__(self, "name", name)

        instructions = tuple(self.instructions)
        if any(not isinstance(item, Instruction) for item in instructions):
            raise PulseError("PulseProgram instructions must be Instruction instances.")
        instructions = tuple(sorted(instructions, key=lambda item: item.start))
        object.__setattr__(self, "instructions", instructions)
        self._validate_timing()

    def _validate_timing(self) -> None:
        intervals: dict[Channel, list[Instruction]] = {}
        instants: dict[Channel, list[Instruction]] = {}
        for instruction in self.instructions:
            collection = intervals if instruction.duration else instants
            for channel in instruction.channels:
                collection.setdefault(channel, []).append(instruction)

        for channel, channel_intervals in intervals.items():
            ordered = sorted(channel_intervals, key=lambda item: (item.start, item.end))
            previous: Instruction | None = None
            for current in ordered:
                if previous is not None and current.start < previous.end:
                    raise PulseError(
                        f"Instructions overlap on {_channel_label(channel)}: "
                        f"[{previous.start}, {previous.end}) and "
                        f"[{current.start}, {current.end})."
                    )
                previous = current

            for instant in instants.get(channel, []):
                for occupied in ordered:
                    if occupied.start < instant.start < occupied.end:
                        raise PulseError(
                            f"Frame instruction at {instant.start} occurs inside an active "
                            f"interval on {_channel_label(channel)}."
                        )

    @property
    def duration(self) -> int:
        """Program duration in target clock samples."""

        return max((instruction.end for instruction in self.instructions), default=0)

    def with_instruction(self, instruction: Instruction) -> PulseProgram:
        """Return a new program containing ``instruction``."""

        return PulseProgram(
            instructions=(*self.instructions, instruction),
            name=self.name,
            schema_version=self.schema_version,
        )

    def play(self, start: int, channel: Channel, waveform: Waveform) -> PulseProgram:
        return self.with_instruction(Play(start, channel, waveform))

    def delay(self, start: int, channel: Channel, duration: int) -> PulseProgram:
        return self.with_instruction(Delay(start, channel, duration))

    def shift_phase(self, start: int, channel: Channel, phase: float) -> PulseProgram:
        return self.with_instruction(ShiftPhase(start, channel, phase))

    def set_phase(self, start: int, channel: Channel, phase: float) -> PulseProgram:
        return self.with_instruction(SetPhase(start, channel, phase))

    def shift_frequency(self, start: int, channel: Channel, frequency: float) -> PulseProgram:
        return self.with_instruction(ShiftFrequency(start, channel, frequency))

    def set_frequency(self, start: int, channel: Channel, frequency: float) -> PulseProgram:
        return self.with_instruction(SetFrequency(start, channel, frequency))

    def acquire(
        self,
        start: int,
        channel: AcquireChannel,
        duration: int,
        *,
        memory_slot: int | None = None,
    ) -> PulseProgram:
        return self.with_instruction(Acquire(start, channel, duration, memory_slot))

    def validate(self, target: PulseTarget) -> None:
        """Validate this schedule against target timing and channel constraints."""

        target.validate(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "instructions": [instruction.to_dict() for instruction in self.instructions],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize deterministically; compact output is canonical for this schema."""

        return _canonical_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PulseProgram:
        schema_version = data.get("schema_version", PULSE_SCHEMA_VERSION)
        if not isinstance(schema_version, str):
            raise PulseError("Pulse schema version must be a string.")
        raw_name = data.get("name")
        if raw_name is not None and not isinstance(raw_name, str):
            raise PulseError("Pulse program name must be a string or null.")
        raw_instructions = data.get("instructions", [])
        if not isinstance(raw_instructions, list):
            raise PulseError("Pulse program instructions must be a list.")
        instructions: list[Instruction] = []
        for item in raw_instructions:
            if not isinstance(item, Mapping):
                raise PulseError("Each pulse instruction must be an object.")
            instructions.append(instruction_from_dict(item))
        return cls(tuple(instructions), raw_name, schema_version)

    @classmethod
    def from_json(cls, text: str) -> PulseProgram:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PulseError("Invalid pulse program JSON.") from exc
        if not isinstance(data, Mapping):
            raise PulseError("Pulse program JSON must contain an object.")
        return cls.from_dict(data)


@dataclass(frozen=True)
class PulseTarget:
    """Minimal target constraints used before provider-specific lowering.

    ``dt_seconds`` records the target sample period when known.  All instruction
    times remain integer sample counts, avoiding floating-point timeline drift.
    """

    channels: frozenset[Channel]
    dt_seconds: float | None = None
    granularity: int = 1
    min_duration: int = 1
    pulse_alignment: int = 1
    acquire_alignment: int = 1
    max_program_duration: int | None = None
    max_amplitude: float = 1.0

    def __post_init__(self) -> None:
        channels = frozenset(self.channels)
        if not channels:
            raise PulseError("A pulse target must define at least one channel.")
        if any(not isinstance(channel, Channel) for channel in channels):
            raise PulseError("Pulse target channels must be Channel instances.")
        object.__setattr__(self, "channels", channels)

        if self.dt_seconds is not None:
            dt_seconds = _finite_float(self.dt_seconds, label="Target dt_seconds")
            if dt_seconds <= 0:
                raise PulseError("Target dt_seconds must be positive.")
            object.__setattr__(self, "dt_seconds", dt_seconds)

        for attribute, label in (
            ("granularity", "Target granularity"),
            ("min_duration", "Target minimum duration"),
            ("pulse_alignment", "Target pulse alignment"),
            ("acquire_alignment", "Target acquire alignment"),
        ):
            object.__setattr__(
                self,
                attribute,
                _positive_int(getattr(self, attribute), label=label),
            )
        if self.max_program_duration is not None:
            object.__setattr__(
                self,
                "max_program_duration",
                _positive_int(
                    self.max_program_duration,
                    label="Target maximum program duration",
                ),
            )
        max_amplitude = _finite_float(self.max_amplitude, label="Target maximum amplitude")
        if not 0 < max_amplitude <= 1.0:
            raise PulseError("Target maximum amplitude must be in the interval (0, 1].")
        object.__setattr__(self, "max_amplitude", max_amplitude)

    def validate(self, program: PulseProgram) -> None:
        if not isinstance(program, PulseProgram):
            raise PulseError("PulseTarget.validate() expects a PulseProgram.")
        if self.max_program_duration is not None and program.duration > self.max_program_duration:
            raise PulseError(
                f"Program duration {program.duration} exceeds target maximum "
                f"{self.max_program_duration}."
            )
        for instruction in program.instructions:
            for channel in instruction.channels:
                if channel not in self.channels:
                    raise PulseError(f"Target does not define {_channel_label(channel)}.")

            alignment = (
                self.acquire_alignment
                if isinstance(instruction.channels[0], AcquireChannel)
                else self.pulse_alignment
            )
            if instruction.start % alignment:
                raise PulseError(
                    f"{instruction.kind} start {instruction.start} is not aligned to {alignment}."
                )
            if instruction.duration:
                if instruction.duration < self.min_duration:
                    raise PulseError(
                        f"{instruction.kind} duration {instruction.duration} is below target "
                        f"minimum {self.min_duration}."
                    )
                if instruction.duration % self.granularity:
                    raise PulseError(
                        f"{instruction.kind} duration {instruction.duration} is not a multiple "
                        f"of target granularity {self.granularity}."
                    )
            if (
                isinstance(instruction, Play)
                and instruction.waveform.max_abs_amplitude > self.max_amplitude
            ):
                raise PulseError(
                    f"Waveform amplitude {instruction.waveform.max_abs_amplitude} exceeds "
                    f"target maximum {self.max_amplitude}."
                )

    def to_dict(self) -> dict[str, Any]:
        ordered_channels = sorted(
            self.channels,
            key=lambda channel: (channel.kind.value, channel.index),
        )
        return {
            "channels": [channel.to_dict() for channel in ordered_channels],
            "dt_seconds": self.dt_seconds,
            "granularity": self.granularity,
            "min_duration": self.min_duration,
            "pulse_alignment": self.pulse_alignment,
            "acquire_alignment": self.acquire_alignment,
            "max_program_duration": self.max_program_duration,
            "max_amplitude": self.max_amplitude,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PulseTarget:
        raw_channels = data.get("channels")
        if not isinstance(raw_channels, list):
            raise PulseError("Pulse target channels must be a list.")
        channels: list[Channel] = []
        for item in raw_channels:
            if not isinstance(item, Mapping):
                raise PulseError("Each target channel must be an object.")
            channels.append(channel_from_dict(item))
        return cls(
            channels=frozenset(channels),
            dt_seconds=data.get("dt_seconds"),
            granularity=_positive_int(data.get("granularity", 1), label="Target granularity"),
            min_duration=_positive_int(
                data.get("min_duration", 1),
                label="Target minimum duration",
            ),
            pulse_alignment=_positive_int(
                data.get("pulse_alignment", 1),
                label="Target pulse alignment",
            ),
            acquire_alignment=_positive_int(
                data.get("acquire_alignment", 1),
                label="Target acquire alignment",
            ),
            max_program_duration=data.get("max_program_duration"),
            max_amplitude=_finite_float(
                data.get("max_amplitude", 1.0),
                label="Target maximum amplitude",
            ),
        )


@dataclass(frozen=True)
class CalibrationKey:
    """Identity of a concrete gate calibration."""

    gate: str
    qubits: tuple[int, ...]
    parameters: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.gate, str):
            raise PulseError("Calibration gate must be a string.")
        gate = self.gate.strip().lower()
        if not gate:
            raise PulseError("Calibration gate must be non-empty.")
        qubits = tuple(_non_negative_int(qubit, label="Calibration qubit") for qubit in self.qubits)
        if not qubits:
            raise PulseError("A calibration must reference at least one qubit.")
        if len(set(qubits)) != len(qubits):
            raise PulseError("Calibration qubits must be distinct.")
        parameters = tuple(
            _finite_float(parameter, label="Calibration parameter") for parameter in self.parameters
        )
        object.__setattr__(self, "gate", gate)
        object.__setattr__(self, "qubits", qubits)
        object.__setattr__(self, "parameters", parameters)

    def _sort_key(self) -> tuple[str, tuple[int, ...], tuple[float, ...]]:
        return (self.gate, self.qubits, self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "qubits": list(self.qubits),
            "parameters": list(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CalibrationKey:
        gate = data.get("gate")
        if not isinstance(gate, str):
            raise PulseError("Calibration gate must be a string.")
        raw_qubits = data.get("qubits")
        raw_parameters = data.get("parameters", [])
        if not isinstance(raw_qubits, list) or not isinstance(raw_parameters, list):
            raise PulseError("Calibration qubits and parameters must be lists.")
        return cls(
            gate,
            tuple(_non_negative_int(item, label="Calibration qubit") for item in raw_qubits),
            tuple(_finite_float(item, label="Calibration parameter") for item in raw_parameters),
        )


@dataclass(frozen=True)
class CalibrationLibrary(Mapping[CalibrationKey, PulseProgram]):
    """An immutable mapping from gate signatures to pulse programs."""

    entries: tuple[tuple[CalibrationKey, PulseProgram], ...] = field(default_factory=tuple)
    schema_version: str = CALIBRATION_SCHEMA_VERSION

    SUPPORTED_SCHEMA: ClassVar[str] = CALIBRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_SCHEMA_VERSION:
            raise PulseError(f"Unsupported calibration schema version: {self.schema_version}.")
        entries = tuple(self.entries)
        seen: set[CalibrationKey] = set()
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise PulseError("Each calibration entry must be a (key, program) tuple.")
            key, program = entry
            if not isinstance(key, CalibrationKey) or not isinstance(program, PulseProgram):
                raise PulseError("Calibration entries require CalibrationKey and PulseProgram.")
            if key in seen:
                raise PulseError(f"Duplicate calibration for {key.gate!r} on {key.qubits}.")
            seen.add(key)
        entries = tuple(sorted(entries, key=lambda item: item[0]._sort_key()))
        object.__setattr__(self, "entries", entries)

    @classmethod
    def from_mapping(
        cls,
        calibrations: Mapping[CalibrationKey, PulseProgram],
    ) -> CalibrationLibrary:
        return cls(tuple(calibrations.items()))

    def __getitem__(self, key: CalibrationKey) -> PulseProgram:
        for candidate, program in self.entries:
            if candidate == key:
                return program
        raise KeyError(key)

    def __iter__(self) -> Iterator[CalibrationKey]:
        return (key for key, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def with_calibration(
        self,
        key: CalibrationKey,
        program: PulseProgram,
        *,
        replace: bool = False,
    ) -> CalibrationLibrary:
        """Return a new library containing a calibration.

        Existing keys are protected unless ``replace=True`` is explicit.
        """

        if not isinstance(key, CalibrationKey) or not isinstance(program, PulseProgram):
            raise PulseError("Calibration entries require CalibrationKey and PulseProgram.")
        if key in self and not replace:
            raise PulseError(f"Calibration for {key.gate!r} on {key.qubits} already exists.")
        retained = tuple(entry for entry in self.entries if entry[0] != key)
        return CalibrationLibrary((*retained, (key, program)), self.schema_version)

    def resolve(
        self,
        gate: str,
        qubits: tuple[int, ...],
        parameters: tuple[float, ...] = (),
    ) -> PulseProgram:
        """Resolve a concrete gate signature or raise ``KeyError``."""

        return self[CalibrationKey(gate, qubits, parameters)]

    def validate(self, target: PulseTarget) -> None:
        """Validate every calibration program against a pulse target."""

        for program in self.values():
            target.validate(program)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "calibrations": [
                {"key": key.to_dict(), "program": program.to_dict()}
                for key, program in self.entries
            ],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return _canonical_json(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CalibrationLibrary:
        schema_version = data.get("schema_version", CALIBRATION_SCHEMA_VERSION)
        if not isinstance(schema_version, str):
            raise PulseError("Calibration schema version must be a string.")
        raw_calibrations = data.get("calibrations", [])
        if not isinstance(raw_calibrations, list):
            raise PulseError("Calibrations must be a list.")
        entries: list[tuple[CalibrationKey, PulseProgram]] = []
        for item in raw_calibrations:
            if not isinstance(item, Mapping):
                raise PulseError("Each calibration must be an object.")
            raw_key = item.get("key")
            raw_program = item.get("program")
            if not isinstance(raw_key, Mapping) or not isinstance(raw_program, Mapping):
                raise PulseError("Calibration key and program must be objects.")
            entries.append((CalibrationKey.from_dict(raw_key), PulseProgram.from_dict(raw_program)))
        return cls(tuple(entries), schema_version)

    @classmethod
    def from_json(cls, text: str) -> CalibrationLibrary:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PulseError("Invalid calibration library JSON.") from exc
        if not isinstance(data, Mapping):
            raise PulseError("Calibration library JSON must contain an object.")
        return cls.from_dict(data)
