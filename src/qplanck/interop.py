"""Typed evidence for conversions at QCore interoperability boundaries.

Formats do not preserve the same information.  These contracts let adapters
state what was retained, omitted, or rejected instead of treating a successful
conversion as proof of a lossless round trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from qplanck.errors import InteropError

T = TypeVar("T")


class InteropIssueKind(StrEnum):
    """The effect an interoperability issue has on a conversion."""

    LOSS = "loss"
    WARNING = "warning"


@dataclass(frozen=True)
class InteropIssue:
    """One stable, machine-readable interoperability finding."""

    code: str
    kind: InteropIssueKind
    message: str
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.code.startswith("QCORE-INTEROP-"):
            raise ValueError("Interop issue codes must start with 'QCORE-INTEROP-'.")
        if not self.message:
            raise ValueError("Interop issue messages must be non-empty.")

    def to_dict(self) -> dict[str, str]:
        payload = {
            "code": self.code,
            "kind": self.kind.value,
            "message": self.message,
        }
        if self.path is not None:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class LossReport:
    """Deterministic semantic-fidelity report for one conversion."""

    source_format: str
    target_format: str
    preserved: tuple[str, ...] = ()
    issues: tuple[InteropIssue, ...] = ()
    schema_version: str = "qplanck.interop.loss.v0.1"

    def __post_init__(self) -> None:
        if not self.source_format or not self.target_format:
            raise ValueError("Source and target formats must be non-empty.")
        object.__setattr__(self, "preserved", tuple(sorted(set(self.preserved))))
        object.__setattr__(
            self,
            "issues",
            tuple(sorted(self.issues, key=lambda item: (item.path or "", item.code, item.message))),
        )

    @property
    def losses(self) -> tuple[InteropIssue, ...]:
        return tuple(issue for issue in self.issues if issue.kind is InteropIssueKind.LOSS)

    @property
    def warnings(self) -> tuple[InteropIssue, ...]:
        return tuple(issue for issue in self.issues if issue.kind is InteropIssueKind.WARNING)

    @property
    def is_lossless(self) -> bool:
        return not self.losses

    def require_lossless(self) -> None:
        """Raise when the conversion omitted semantic or provenance data."""

        if self.is_lossless:
            return
        codes = ", ".join(issue.code for issue in self.losses)
        raise InteropError(
            f"Conversion from {self.source_format} to {self.target_format} is lossy: {codes}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_format": self.source_format,
            "target_format": self.target_format,
            "lossless": self.is_lossless,
            "preserved": list(self.preserved),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(frozen=True)
class ConversionResult(Generic[T]):
    """A converted value paired with the evidence needed to assess fidelity."""

    value: T
    report: LossReport
