"""Strict, provider-free replay of saved QCore planning decisions.

Replay verifies a saved planning artifact, requires the caller to provide the
exact compiler-strategy portfolio recorded by that artifact, and reruns the
planner using only the saved Program, Target snapshots, and Objective.  It
does not discover providers, credentials, or remote jobs.

Wall-clock timestamps and compilation latency are observational evidence in
the planning model.  They are intentionally absent from candidate, Plan, and
Manifest semantic hashes, so they cannot make an otherwise identical replay
fail.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import platform
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from qplanck.planning import (
    MANIFEST_SCHEMA_VERSION,
    CandidatePlan,
    CompilerStrategy,
    Plan,
    PlanningError,
    PlanningManifest,
    plan,
)

REPLAY_MISMATCH_SCHEMA_VERSION = "qcore.replay-mismatch.v0.1"
REPLAY_REPORT_SCHEMA_VERSION = "qcore.replay-report.v0.1"

_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_SECRET_KEY = re.compile(
    r"(?:^|_)(?:passwords?|passwd|secrets?|tokens?|credentials?|auth|authorization|"
    r"bearer|cookies?|api_keys?|access_keys?|session_keys?|private_keys?|"
    r"connection_strings?|dsn)(?:$|_)",
    re.IGNORECASE,
)

_JsonScalar = str | bool | int | float | None
_JsonValue = _JsonScalar | tuple["_JsonValue", ...] | Mapping[str, "_JsonValue"]
_Descriptor = tuple[str, str, str]


class ReplayError(ValueError):
    """Raised when a replay cannot safely begin."""


@dataclass(frozen=True)
class ReplayMismatch:
    """One deterministic or environment difference found during replay."""

    category: str
    subject: str
    expected: _JsonValue
    actual: _JsonValue
    message: str
    schema_version: str = REPLAY_MISMATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_MISMATCH_SCHEMA_VERSION:
            raise ValueError(f"Unsupported ReplayMismatch schema: {self.schema_version}.")
        for label in ("category", "subject", "message"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"ReplayMismatch {label} must be a non-empty string.")
            object.__setattr__(self, label, value.strip())
        object.__setattr__(self, "expected", _freeze_json(self.expected))
        object.__setattr__(self, "actual", _freeze_json(self.actual))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "category": self.category,
            "subject": self.subject,
            "expected": _thaw_json(self.expected),
            "actual": _thaw_json(self.actual),
            "message": self.message,
        }


@dataclass(frozen=True)
class ReplayReport:
    """Immutable result of one completed offline planning replay."""

    saved_plan_hash: str
    replayed_plan_hash: str | None
    saved_manifest_hash: str
    replayed_manifest_hash: str | None
    saved_selected_candidate_id: str
    replayed_selected_candidate_id: str | None
    saved_candidate_count: int
    replayed_candidate_count: int
    matched_candidate_count: int
    mismatches: tuple[ReplayMismatch, ...]
    environment_mismatches: tuple[ReplayMismatch, ...]
    schema_version: str = REPLAY_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_REPORT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported ReplayReport schema: {self.schema_version}.")
        for label in ("saved_plan_hash", "saved_manifest_hash"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise ValueError(f"ReplayReport {label} must be a SHA-256 identity.")
        for label in ("replayed_plan_hash", "replayed_manifest_hash"):
            value = getattr(self, label)
            if value is not None and not value.startswith("sha256:"):
                raise ValueError(f"ReplayReport {label} must be a SHA-256 identity or None.")
        if not self.saved_selected_candidate_id.startswith("sha256:"):
            raise ValueError("saved_selected_candidate_id must be a SHA-256 identity.")
        if (
            self.replayed_selected_candidate_id is not None
            and not self.replayed_selected_candidate_id.startswith("sha256:")
        ):
            raise ValueError("replayed_selected_candidate_id must be a SHA-256 identity or None.")
        for label in (
            "saved_candidate_count",
            "replayed_candidate_count",
            "matched_candidate_count",
        ):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"ReplayReport {label} must be a non-negative integer.")
        if self.matched_candidate_count > min(
            self.saved_candidate_count, self.replayed_candidate_count
        ):
            raise ValueError("matched_candidate_count cannot exceed either candidate count.")
        if any(not isinstance(item, ReplayMismatch) for item in self.mismatches):
            raise TypeError("ReplayReport mismatches must contain ReplayMismatch objects.")
        if any(not isinstance(item, ReplayMismatch) for item in self.environment_mismatches):
            raise TypeError(
                "ReplayReport environment_mismatches must contain ReplayMismatch objects."
            )
        object.__setattr__(self, "mismatches", tuple(self.mismatches))
        object.__setattr__(self, "environment_mismatches", tuple(self.environment_mismatches))

    @property
    def passed(self) -> bool:
        """Whether all required semantic replay comparisons passed."""

        return not self.mismatches

    @property
    def environment_compatible(self) -> bool:
        """Whether the saved and replay environments are exactly compatible."""

        return not self.environment_mismatches

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "passed": self.passed,
            "environment_compatible": self.environment_compatible,
            "saved_plan_hash": self.saved_plan_hash,
            "replayed_plan_hash": self.replayed_plan_hash,
            "saved_manifest_hash": self.saved_manifest_hash,
            "replayed_manifest_hash": self.replayed_manifest_hash,
            "saved_selected_candidate_id": self.saved_selected_candidate_id,
            "replayed_selected_candidate_id": self.replayed_selected_candidate_id,
            "saved_candidate_count": self.saved_candidate_count,
            "replayed_candidate_count": self.replayed_candidate_count,
            "matched_candidate_count": self.matched_candidate_count,
            "mismatches": [item.to_dict() for item in self.mismatches],
            "environment_mismatches": [item.to_dict() for item in self.environment_mismatches],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


def replay(
    source: Plan | PlanningManifest | str | Path,
    *,
    strategies: Sequence[CompilerStrategy],
) -> ReplayReport:
    """Re-execute and compare one planning decision without provider access.

    ``source`` may be a validated :class:`Plan`, a
    :class:`PlanningManifest`, canonical manifest JSON, or a path to canonical
    manifest JSON.  Serialized input is accepted only when every canonical
    field and integrity hash is present and valid.

    The supplied strategies must cover the saved unique descriptors exactly by
    strategy ID, version, and canonical options.  Missing, duplicate, changed,
    or extra descriptors raise :class:`ReplayError` before any strategy runs.
    """

    saved = _load_manifest(source)
    resolved_strategies = tuple(strategies)
    _verify_strategy_coverage(saved, resolved_strategies)

    replayed: Plan | None
    actual_candidates: tuple[CandidatePlan, ...]
    try:
        replayed = plan(
            saved.program,
            targets=saved.targets,
            strategies=resolved_strategies,
            objective=saved.objective,
        )
        actual_candidates = replayed.candidates
    except PlanningError as error:
        # A portfolio that no longer produces any valid candidate is itself
        # replay evidence.  Preserve its candidate dispositions and report the
        # absent selection/Plan/Manifest rather than hiding the drift.
        replayed = None
        actual_candidates = error.candidates
    except (TypeError, ValueError) as error:
        raise ReplayError(f"Offline planning replay could not be executed: {error}") from error

    replayed_manifest = None if replayed is None else replayed.manifest
    mismatches, matched = _compare_candidates(saved.candidates, actual_candidates)

    actual_selected = None if replayed is None else replayed.selected_candidate_id
    actual_plan_hash = None if replayed is None else replayed.plan_hash
    actual_manifest_hash = None if replayed_manifest is None else replayed_manifest.manifest_hash
    _compare_value(
        mismatches,
        category="selection",
        subject="selected_candidate_id",
        expected=saved.selected_candidate_id,
        actual=actual_selected,
        message="The selected candidate changed during replay.",
    )
    _compare_value(
        mismatches,
        category="plan_hash",
        subject="plan",
        expected=saved.selected_plan_hash,
        actual=actual_plan_hash,
        message="The deterministic Plan hash changed during replay.",
    )
    _compare_value(
        mismatches,
        category="manifest_hash",
        subject="manifest",
        expected=saved.manifest_hash,
        actual=actual_manifest_hash,
        message="The deterministic Manifest hash changed during replay.",
    )

    replay_environment = (
        _current_environment() if replayed_manifest is None else dict(replayed_manifest.environment)
    )
    environment_mismatches = _compare_environment(dict(saved.environment), replay_environment)
    return ReplayReport(
        saved_plan_hash=saved.selected_plan_hash,
        replayed_plan_hash=actual_plan_hash,
        saved_manifest_hash=saved.manifest_hash,
        replayed_manifest_hash=actual_manifest_hash,
        saved_selected_candidate_id=saved.selected_candidate_id,
        replayed_selected_candidate_id=actual_selected,
        saved_candidate_count=len(saved.candidates),
        replayed_candidate_count=len(actual_candidates),
        matched_candidate_count=matched,
        mismatches=tuple(mismatches),
        environment_mismatches=environment_mismatches,
    )


def _load_manifest(source: Plan | PlanningManifest | str | Path) -> PlanningManifest:
    if isinstance(source, Plan):
        try:
            verified_plan = Plan.from_json(source.to_json(include_observations=True))
            return PlanningManifest.from_json(
                verified_plan.manifest.to_json(include_observations=True)
            )
        except (TypeError, ValueError) as error:
            raise ReplayError(f"Saved Plan failed integrity validation: {error}") from error
    if isinstance(source, PlanningManifest):
        try:
            return PlanningManifest.from_json(source.to_json(include_observations=True))
        except (TypeError, ValueError) as error:
            raise ReplayError(f"Saved Manifest failed integrity validation: {error}") from error
    if not isinstance(source, str | Path):
        raise TypeError("source must be a Plan, PlanningManifest, manifest JSON, or path.")

    text = _read_manifest_text(source)
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ReplayError("Saved Manifest is not valid JSON.") from error
    if not isinstance(raw, dict):
        raise ReplayError("Saved Manifest JSON must contain one object.")
    _assert_secret_free(raw)
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ReplayError(
            "Saved Manifest schema is missing or unsupported; replay requires "
            f"{MANIFEST_SCHEMA_VERSION}."
        )
    if "manifest_hash" not in raw:
        raise ReplayError("Saved Manifest must include manifest_hash for replay.")
    try:
        manifest = PlanningManifest.from_dict(raw)
    except (KeyError, TypeError, ValueError) as error:
        raise ReplayError(f"Saved Manifest failed integrity validation: {error}") from error

    include_observations = "observations" in raw
    normalized = manifest.to_dict(include_observations=include_observations)
    if _canonical_json(raw) != _canonical_json(normalized):
        raise ReplayError(
            "Saved Manifest is not the exact canonical schema; unknown, missing, or "
            "unverified fields are forbidden during replay."
        )
    return manifest


def _read_manifest_text(source: str | Path) -> str:
    if isinstance(source, Path):
        path = source
    elif source.lstrip().startswith(("{", "[")):
        encoded_size = len(source.encode("utf-8"))
        if encoded_size > _MAX_MANIFEST_BYTES:
            raise ReplayError("Saved Manifest exceeds the replay size limit.")
        return source
    else:
        path = Path(source)
    try:
        size = path.stat().st_size
        if size > _MAX_MANIFEST_BYTES:
            raise ReplayError("Saved Manifest exceeds the replay size limit.")
        return path.read_text(encoding="utf-8")
    except ReplayError:
        raise
    except (OSError, UnicodeError) as error:
        raise ReplayError("Saved Manifest path could not be read as UTF-8 JSON.") from error


def _verify_strategy_coverage(
    saved: PlanningManifest,
    strategies: tuple[CompilerStrategy, ...],
) -> None:
    saved_descriptors = {_candidate_descriptor(candidate) for candidate in saved.candidates}
    if not saved_descriptors:
        raise ReplayError("Saved Manifest contains no compiler-strategy descriptors.")
    if not strategies:
        raise ReplayError("Replay requires the saved compiler-strategy portfolio.")

    supplied: list[_Descriptor] = []
    for strategy in strategies:
        if not isinstance(strategy, CompilerStrategy):
            raise ReplayError("Every replay strategy must satisfy CompilerStrategy.")
        try:
            options = _thaw_json(_freeze_json(strategy.options))
            descriptor = (
                _non_empty(strategy.strategy_id, label="strategy_id"),
                _non_empty(strategy.strategy_version, label="strategy_version"),
                _canonical_json(options),
            )
            _assert_secret_free(options)
        except (TypeError, ValueError) as error:
            raise ReplayError(f"Replay strategy descriptor is invalid: {error}") from error
        supplied.append(descriptor)

    supplied_set = set(supplied)
    if len(supplied_set) != len(supplied):
        raise ReplayError(
            "Replay strategy descriptors are ambiguous; duplicate ID/version/options "
            "descriptors are forbidden."
        )
    if supplied_set != saved_descriptors:
        missing = saved_descriptors - supplied_set
        extra = supplied_set - saved_descriptors
        details = []
        if missing:
            details.append(f"missing={len(missing)}")
        if extra:
            details.append(f"extra_or_changed={len(extra)}")
        raise ReplayError(
            "Replay strategies do not exactly cover the saved ID/version/options "
            f"descriptors ({', '.join(details)})."
        )


def _candidate_descriptor(candidate: CandidatePlan) -> _Descriptor:
    return (
        candidate.strategy_id,
        candidate.strategy_version,
        _canonical_json(_thaw_json(candidate.strategy_options)),
    )


def _compare_candidates(
    saved_candidates: tuple[CandidatePlan, ...],
    actual_candidates: tuple[CandidatePlan, ...],
) -> tuple[list[ReplayMismatch], int]:
    mismatches: list[ReplayMismatch] = []
    saved_by_id = {item.candidate_id: item for item in saved_candidates}
    actual_by_id = {item.candidate_id: item for item in actual_candidates}
    matched = 0
    for candidate_id in sorted(set(saved_by_id) | set(actual_by_id)):
        expected = saved_by_id.get(candidate_id)
        actual = actual_by_id.get(candidate_id)
        if expected is None:
            mismatches.append(
                ReplayMismatch(
                    category="candidate_id",
                    subject=candidate_id,
                    expected=None,
                    actual=candidate_id,
                    message="Replay produced an unexpected candidate ID.",
                )
            )
            continue
        if actual is None:
            mismatches.append(
                ReplayMismatch(
                    category="candidate_id",
                    subject=candidate_id,
                    expected=candidate_id,
                    actual=None,
                    message="Replay did not reproduce a saved candidate ID.",
                )
            )
            continue

        before = len(mismatches)
        _compare_value(
            mismatches,
            category="candidate_hash",
            subject=candidate_id,
            expected=expected.candidate_hash,
            actual=actual.candidate_hash,
            message="Candidate evidence hash changed during replay.",
        )
        _compare_value(
            mismatches,
            category="candidate_disposition",
            subject=candidate_id,
            expected=expected.disposition.value,
            actual=actual.disposition.value,
            message="Candidate disposition changed during replay.",
        )
        _compare_value(
            mismatches,
            category="candidate_artifact_hash",
            subject=candidate_id,
            expected=expected.artifact_hash,
            actual=actual.artifact_hash,
            message="Candidate artifact hash changed during replay.",
        )
        if len(mismatches) == before:
            matched += 1
    return mismatches, matched


def _compare_value(
    mismatches: list[ReplayMismatch],
    *,
    category: str,
    subject: str,
    expected: _JsonValue,
    actual: _JsonValue,
    message: str,
) -> None:
    if expected != actual:
        mismatches.append(
            ReplayMismatch(
                category=category,
                subject=subject,
                expected=expected,
                actual=actual,
                message=message,
            )
        )


def _compare_environment(
    saved: Mapping[str, Any], actual: Mapping[str, Any]
) -> tuple[ReplayMismatch, ...]:
    differences: list[ReplayMismatch] = []
    for key in sorted(set(saved) | set(actual)):
        expected_value = _freeze_json(saved.get(key))
        actual_value = _freeze_json(actual.get(key))
        if expected_value != actual_value:
            differences.append(
                ReplayMismatch(
                    category="environment",
                    subject=f"environment.{key}",
                    expected=expected_value,
                    actual=actual_value,
                    message="Saved and replay environment values differ.",
                )
            )
    return tuple(differences)


def _current_environment() -> dict[str, str]:
    try:
        package_version = importlib.metadata.version("qplanck")
    except importlib.metadata.PackageNotFoundError:
        package_version = "unknown-source-tree"
    return {
        "qplanck_version": package_version,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "operating_system": platform.system(),
        "machine": platform.machine(),
    }


def _non_empty(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise TypeError("Replay artifacts must contain finite JSON values.") from error


def _freeze_json(value: Any) -> _JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in sorted(value.items())}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Replay artifact floats must be finite.")
        return value
    raise TypeError("Replay artifacts must contain JSON values, not provider SDK objects.")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_json(item) for item in value]
    return value


def _assert_secret_free(value: object, *, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            if path == "manifest" and key == "secrets_recorded" and item is False:
                # This canonical, negative policy marker is part of every
                # PlanningManifest.  Any other value is rejected below or by
                # the exact canonical round-trip check.
                continue
            normalized_key = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
            normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized_key)
            normalized_key = re.sub(r"[^A-Za-z0-9]+", "_", normalized_key).strip("_")
            if _SECRET_KEY.search(normalized_key.lower()):
                raise ReplayError(f"Secret-bearing field {path}.{key} is forbidden.")
            _assert_secret_free(item, path=f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _assert_secret_free(item, path=f"{path}[{index}]")
    elif not (value is None or isinstance(value, str | bool | int | float)):
        raise ReplayError(f"Provider SDK object is forbidden at {path}.")
    try:
        _canonical_json(_thaw_json(value))
    except TypeError as error:
        raise ReplayError(str(error)) from error


__all__ = [
    "REPLAY_MISMATCH_SCHEMA_VERSION",
    "REPLAY_REPORT_SCHEMA_VERSION",
    "ReplayError",
    "ReplayMismatch",
    "ReplayReport",
    "replay",
]
