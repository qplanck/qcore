from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FakePort:
    id: str
    dt: float


@dataclass(frozen=True)
class FakeFrame:
    id: str
    port: FakePort
    is_predefined: bool = True


class FakeWaveform:
    def __init__(self, kind: str, **kwargs: Any) -> None:
        self.kind = kind
        self.kwargs = kwargs


class FakePulseSequence:
    def __init__(self) -> None:
        self.operations: list[tuple[str, str, tuple[Any, ...]]] = []

    def delay(self, frame: FakeFrame, duration: float) -> FakePulseSequence:
        self.operations.append(("delay", frame.id, (duration,)))
        return self

    def play(self, frame: FakeFrame, waveform: FakeWaveform) -> FakePulseSequence:
        self.operations.append(("play", frame.id, (waveform,)))
        return self

    def shift_phase(self, frame: FakeFrame, phase: float) -> FakePulseSequence:
        self.operations.append(("shift_phase", frame.id, (phase,)))
        return self

    def set_phase(self, frame: FakeFrame, phase: float) -> FakePulseSequence:
        self.operations.append(("set_phase", frame.id, (phase,)))
        return self

    def shift_frequency(self, frame: FakeFrame, frequency: float) -> FakePulseSequence:
        self.operations.append(("shift_frequency", frame.id, (frequency,)))
        return self

    def set_frequency(self, frame: FakeFrame, frequency: float) -> FakePulseSequence:
        self.operations.append(("set_frequency", frame.id, (frequency,)))
        return self


def arbitrary_waveform(*, amplitudes: list[complex], id: str) -> FakeWaveform:
    return FakeWaveform("arbitrary", amplitudes=amplitudes, id=id)


def constant_waveform(*, length: float, iq: complex, id: str) -> FakeWaveform:
    return FakeWaveform("constant", length=length, iq=iq, id=id)


def gaussian_waveform(
    *,
    length: float,
    sigma: float,
    amplitude: float,
    zero_at_edges: bool,
    id: str,
) -> FakeWaveform:
    return FakeWaveform(
        "gaussian",
        length=length,
        sigma=sigma,
        amplitude=amplitude,
        zero_at_edges=zero_at_edges,
        id=id,
    )
