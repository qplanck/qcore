"""Explicit QPlanck-channel to predefined Braket-frame bindings."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from qplanck.pulse import Channel

from .errors import BraketCapabilityError, BraketSnapshotMismatchError
from .snapshot import BraketPulseSnapshot


def _channel_key(channel: Channel) -> tuple[str, int]:
    return (channel.kind.value, channel.index)


@dataclass(frozen=True)
class BraketChannelBinding:
    """One explicit QPlanck channel to predefined frame and port binding."""

    channel: Channel
    frame_id: str
    port_id: str
    dt_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.channel, Channel):
            raise BraketCapabilityError("Channel bindings require QPlanck Channel values.")
        if not isinstance(self.frame_id, str) or not self.frame_id.strip():
            raise BraketCapabilityError("Channel binding frame ID must be non-empty.")
        if not isinstance(self.port_id, str) or not self.port_id.strip():
            raise BraketCapabilityError("Channel binding port ID must be non-empty.")
        dt = float(self.dt_seconds)
        if not 0 < dt < float("inf"):
            raise BraketCapabilityError("Channel binding dt must be positive and finite.")
        object.__setattr__(self, "frame_id", self.frame_id.strip())
        object.__setattr__(self, "port_id", self.port_id.strip())
        object.__setattr__(self, "dt_seconds", dt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.to_dict(),
            "frame_id": self.frame_id,
            "port_id": self.port_id,
            "dt_seconds": self.dt_seconds,
        }


@dataclass(frozen=True)
class BraketChannelMap(Mapping[Channel, BraketChannelBinding]):
    """Immutable explicit channel bindings tied to one capability snapshot."""

    bindings: tuple[BraketChannelBinding, ...]
    snapshot_hash: str

    def __post_init__(self) -> None:
        bindings = tuple(sorted(self.bindings, key=lambda item: _channel_key(item.channel)))
        if not bindings:
            raise BraketCapabilityError("A Braket channel map must contain at least one binding.")
        channels = [binding.channel for binding in bindings]
        frames = [binding.frame_id for binding in bindings]
        ports = [binding.port_id for binding in bindings]
        if len(set(channels)) != len(channels):
            raise BraketCapabilityError("A QPlanck channel may be bound only once.")
        if len(set(frames)) != len(frames):
            raise BraketCapabilityError("A predefined Braket frame may be bound only once.")
        if len(set(ports)) != len(ports):
            raise BraketCapabilityError(
                "Each QPlanck channel must use a distinct Braket hardware port."
            )
        if len({binding.dt_seconds for binding in bindings}) != 1:
            raise BraketCapabilityError(
                "All mapped Braket ports must share one dt for the QPlanck sample timeline."
            )
        if not isinstance(self.snapshot_hash, str) or len(self.snapshot_hash) != 64:
            raise BraketCapabilityError("Channel map snapshot hash must be a SHA-256 digest.")
        object.__setattr__(self, "bindings", bindings)

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[Channel, str],
        *,
        snapshot: BraketPulseSnapshot,
    ) -> BraketChannelMap:
        if not isinstance(snapshot, BraketPulseSnapshot):
            raise BraketCapabilityError("Channel mapping requires a BraketPulseSnapshot.")
        frames = snapshot.frame_by_id
        ports = snapshot.port_by_id
        bindings = []
        for channel, frame_id in mapping.items():
            if not isinstance(channel, Channel) or not isinstance(frame_id, str):
                raise BraketCapabilityError(
                    "Channel mapping keys and values must be Channel/string."
                )
            if frame_id not in frames:
                raise BraketCapabilityError(
                    f"Frame {frame_id!r} is not predefined by snapshot {snapshot.snapshot_hash}."
                )
            frame = frames[frame_id]
            port = ports[frame.port_id]
            bindings.append(
                BraketChannelBinding(channel, frame.frame_id, port.port_id, port.dt_seconds)
            )
        result = cls(tuple(bindings), snapshot.snapshot_hash)
        result.validate_snapshot(snapshot)
        return result

    def validate_snapshot(self, snapshot: BraketPulseSnapshot) -> None:
        if self.snapshot_hash != snapshot.snapshot_hash:
            raise BraketSnapshotMismatchError(
                "Channel map was built for a different Braket pulse snapshot."
            )
        frames = snapshot.frame_by_id
        ports = snapshot.port_by_id
        for binding in self.bindings:
            frame = frames.get(binding.frame_id)
            port = ports.get(binding.port_id)
            if frame is None or port is None or frame.port_id != binding.port_id:
                raise BraketSnapshotMismatchError(
                    f"Channel binding for {binding.frame_id!r} is no longer available."
                )
            if port.dt_seconds != binding.dt_seconds:
                raise BraketSnapshotMismatchError(f"Port timing changed for {binding.port_id!r}.")

    def __getitem__(self, channel: Channel) -> BraketChannelBinding:
        for binding in self.bindings:
            if binding.channel == channel:
                return binding
        raise KeyError(channel)

    def __iter__(self) -> Iterator[Channel]:
        return (binding.channel for binding in self.bindings)

    def __len__(self) -> int:
        return len(self.bindings)

    @property
    def dt_seconds(self) -> float:
        """Shared provider sample period for the absolute QPlanck timeline."""

        return self.bindings[0].dt_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "bindings": [binding.to_dict() for binding in self.bindings],
        }
