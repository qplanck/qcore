"""Built-in local and deterministic mock backend implementations."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qplanck.results import RunResult
from qplanck.runtime import (
    ExecutionOptions,
    ExperimentManifest,
    JobCancelledError,
    JobFailedError,
    JobStatus,
    JobTimeoutError,
    validate_job_transition,
)
from qplanck.simulator import LocalSimulator
from qplanck.targets import Target


@dataclass
class FakeClock:
    """Explicit deterministic clock used by mock jobs; it never sleeps."""

    current: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.current) or self.current < 0.0:
            raise ValueError("FakeClock current time must be finite and non-negative.")
        self.current = float(self.current)

    def monotonic(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0.0:
            raise ValueError("FakeClock advance must be finite and non-negative.")
        self.current += float(seconds)


class CompletedJob:
    """An immutable, already-succeeded local job handle."""

    def __init__(self, job_id: str, result: RunResult):
        normalized_id = job_id.strip()
        if not normalized_id:
            raise ValueError("Job ID must be non-empty.")
        if not isinstance(result, RunResult):
            raise TypeError("CompletedJob result must be a RunResult.")
        self._id = normalized_id
        self._result = result

    @property
    def id(self) -> str:
        return self._id

    def status(self) -> JobStatus:
        return JobStatus.SUCCEEDED

    def cancel(self) -> bool:
        return False

    def result(self, *, timeout: float | None = None) -> RunResult:
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(float(timeout))
            or timeout < 0.0
        ):
            raise ValueError("timeout must be a finite, non-negative number or None.")
        return self._result


class MockJob:
    """Deterministic scripted job with no thread, sleep, or network dependency."""

    def __init__(
        self,
        job_id: str,
        *,
        states: tuple[JobStatus, ...],
        delays: tuple[float, ...],
        result: RunResult | None,
        failure_message: str,
        cancellation_accepted: bool,
        cancel_outcome: JobStatus,
        clock: FakeClock,
    ) -> None:
        self._id = job_id
        self._remaining = list(zip(states, delays, strict=True))
        self._current = JobStatus.CREATED
        self._result = result
        self._failure_message = failure_message
        self._cancellation_accepted = cancellation_accepted
        self._cancel_outcome = cancel_outcome
        self._clock = clock
        self._lock = threading.RLock()

    @property
    def id(self) -> str:
        return self._id

    @property
    def provider_detail(self) -> dict[str, Any]:
        return {"mock_time": self._clock.monotonic()}

    def _advance_one(self) -> JobStatus:
        if not self._remaining:
            return self._current
        following, delay = self._remaining.pop(0)
        validate_job_transition(self._current, following)
        self._clock.advance(delay)
        self._current = following
        return self._current

    def status(self) -> JobStatus:
        with self._lock:
            if not self._current.terminal:
                self._advance_one()
            return self._current

    def cancel(self) -> bool:
        with self._lock:
            if self._current.terminal or self._current is JobStatus.CANCEL_REQUESTED:
                return False
            if not self._cancellation_accepted:
                return False
            if self._current in {JobStatus.CREATED, JobStatus.QUEUED}:
                validate_job_transition(self._current, JobStatus.CANCELLED)
                self._current = JobStatus.CANCELLED
                self._remaining.clear()
                return True
            validate_job_transition(self._current, JobStatus.CANCEL_REQUESTED)
            self._current = JobStatus.CANCEL_REQUESTED
            self._remaining = [(self._cancel_outcome, 0.0)]
            return True

    def result(self, *, timeout: float | None = None) -> RunResult:
        with self._lock:
            if timeout is not None:
                if (
                    isinstance(timeout, bool)
                    or not isinstance(timeout, int | float)
                    or not math.isfinite(float(timeout))
                    or timeout < 0.0
                ):
                    raise ValueError("timeout must be a finite, non-negative number or None.")
                remaining_delay = sum(delay for _, delay in self._remaining)
                if not self._current.terminal and remaining_delay > float(timeout):
                    raise JobTimeoutError(
                        f"Job {self.id} did not finish within {float(timeout):g} seconds."
                    )
            while not self._current.terminal and self._remaining:
                self._advance_one()
            if self._current is JobStatus.SUCCEEDED:
                if self._result is None:  # pragma: no cover - scenario construction prevents this
                    raise JobFailedError(f"Job {self.id} succeeded without a result fixture.")
                return self._result
            if self._current is JobStatus.CANCELLED:
                raise JobCancelledError(f"Job {self.id} was cancelled.")
            if self._current is JobStatus.FAILED:
                raise JobFailedError(self._failure_message)
            raise JobFailedError(
                f"Job {self.id} ended in non-terminal state {self._current.value}."
            )


class MockBackend:
    """Declarative backend for lifecycle, provider-adapter, and client tests."""

    def __init__(
        self,
        *,
        target: Target,
        states: Sequence[JobStatus],
        result: RunResult | None,
        transition_delays: Sequence[float] | None = None,
        failure_message: str = "Mock job failed.",
        cancellation_accepted: bool = True,
        cancel_outcome: JobStatus = JobStatus.CANCELLED,
        backend_id: str = "qplanck.mock",
        clock: FakeClock | None = None,
    ) -> None:
        if not isinstance(target, Target):
            raise TypeError("MockBackend target must be a Target.")
        normalized_id = backend_id.strip()
        if not normalized_id:
            raise ValueError("MockBackend backend_id must be non-empty.")
        normalized_states = tuple(JobStatus(state) for state in states)
        if normalized_states and normalized_states[0] is JobStatus.CREATED:
            normalized_states = normalized_states[1:]
        if not normalized_states:
            raise ValueError("MockBackend requires at least one post-created state.")
        current = JobStatus.CREATED
        for following in normalized_states:
            validate_job_transition(current, following)
            current = following
        if not current.terminal:
            raise ValueError("MockBackend state script must end in a terminal state.")
        if current is JobStatus.SUCCEEDED and result is None:
            raise ValueError("A succeeded mock scenario requires a result fixture.")
        if current is not JobStatus.SUCCEEDED and result is not None:
            raise ValueError("Only a succeeded mock scenario may contain a result fixture.")
        if not failure_message.strip():
            raise ValueError("failure_message must be non-empty.")
        if cancel_outcome not in {
            JobStatus.CANCELLED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }:
            raise ValueError("cancel_outcome must be cancelled, succeeded, or failed.")
        if cancel_outcome is JobStatus.SUCCEEDED and result is None:
            raise ValueError("A succeeded cancel_outcome requires a result fixture.")
        raw_delays = (
            (0.0,) * len(normalized_states) if transition_delays is None else transition_delays
        )
        if len(raw_delays) != len(normalized_states):
            raise ValueError("transition_delays must align one-to-one with states.")
        normalized_delays = tuple(float(value) for value in raw_delays)
        if any(not math.isfinite(value) or value < 0.0 for value in normalized_delays):
            raise ValueError("Mock transition delays must be finite and non-negative.")

        self._target = target
        self._states = normalized_states
        self._result = result
        self._delays = normalized_delays
        self._failure_message = failure_message.strip()
        self._cancellation_accepted = bool(cancellation_accepted)
        self._cancel_outcome = cancel_outcome
        self._backend_id = normalized_id
        self._clock = clock or FakeClock()
        self._submission_count = 0

    @classmethod
    def scenario(
        cls,
        *,
        target: Target,
        states: Sequence[JobStatus],
        result: RunResult | None = None,
        transition_delays: Sequence[float] | None = None,
        failure_message: str = "Mock job failed.",
        cancellation_accepted: bool = True,
        cancel_outcome: JobStatus = JobStatus.CANCELLED,
        backend_id: str = "qplanck.mock",
        clock: FakeClock | None = None,
    ) -> MockBackend:
        return cls(
            target=target,
            states=states,
            result=result,
            transition_delays=transition_delays,
            failure_message=failure_message,
            cancellation_accepted=cancellation_accepted,
            cancel_outcome=cancel_outcome,
            backend_id=backend_id,
            clock=clock,
        )

    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def backend_version(self) -> str:
        return "1"

    @property
    def target(self) -> Target:
        return self._target

    def submit(self, program: Any, *, options: ExecutionOptions | None = None) -> MockJob:
        resolved = options or ExecutionOptions()
        if not isinstance(resolved, ExecutionOptions):
            raise TypeError("options must be an ExecutionOptions instance or None.")
        self._submission_count += 1
        job_id = f"mock-{self._submission_count:08d}"
        fixture = self._result
        if fixture is not None:
            fixture = _with_mock_manifest(
                fixture,
                program=program,
                target=self.target,
                options=resolved,
                backend_id=self.backend_id,
                backend_version=self.backend_version,
                job_id=job_id,
            )
        return MockJob(
            job_id,
            states=self._states,
            delays=self._delays,
            result=fixture,
            failure_message=self._failure_message,
            cancellation_accepted=self._cancellation_accepted,
            cancel_outcome=self._cancel_outcome,
            clock=self._clock,
        )

    def run(self, program: Any, *, options: ExecutionOptions | None = None) -> RunResult:
        resolved = options or ExecutionOptions()
        job = self.submit(program, options=resolved)
        return job.result(timeout=resolved.timeout_seconds)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _program_sections(program: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    source_ir = getattr(program, "source_ir", None)
    if source_ir is None:
        source_ir = getattr(program, "ir", None)
    source_to_dict = getattr(source_ir, "to_dict", None)
    source_dict = source_to_dict() if callable(source_to_dict) else {}
    compiled = hasattr(program, "source_ir") and hasattr(program, "to_dict")
    compiled_dict = None
    to_dict = getattr(program, "to_dict", None)
    if compiled and callable(to_dict):
        compiled_dict = to_dict()
    source = {
        "circuit_hash": _canonical_hash(source_dict) if source_dict else None,
        "schema_version": source_dict.get("schema_version") if source_dict else None,
    }
    compilation = {
        "compiled": compiled,
        "compiled_hash": _canonical_hash(compiled_dict) if compiled_dict is not None else None,
    }
    return source, compilation


def _with_mock_manifest(
    fixture: RunResult,
    *,
    program: Any,
    target: Target,
    options: ExecutionOptions,
    backend_id: str,
    backend_version: str,
    job_id: str,
) -> RunResult:
    source, compilation = _program_sections(program)
    compilation["target_hash"] = target.content_hash
    metadata = {**fixture.metadata, "backend_id": backend_id}
    preliminary = RunResult(
        counts=fixture.counts,
        probabilities=fixture.probabilities,
        measurements=fixture.measurements,
        metadata=metadata,
        diagnostics=fixture.diagnostics,
        execution_trace=fixture.execution_trace,
        raw_result=fixture.raw_result,
    )
    manifest = ExperimentManifest(
        source=source,
        compilation=compilation,
        target={"target_id": target.target_id, "target_hash": target.content_hash},
        execution={
            "backend_id": backend_id,
            "backend_version": backend_version,
            "job_id": job_id,
            "options": options.to_dict(),
            "seed_handling": "fixture",
        },
        result={
            "result_hash": preliminary.content_hash,
            "accepted_shots": options.shots,
            "returned_shots": sum(preliminary.counts.values()),
            "numeric_tolerance_profile": "fixture",
        },
        diagnostics=preliminary.diagnostics,
    )
    return RunResult(
        counts=preliminary.counts,
        probabilities=preliminary.probabilities,
        measurements=preliminary.measurements,
        metadata=preliminary.metadata,
        diagnostics=preliminary.diagnostics,
        execution_trace=preliminary.execution_trace,
        manifest=manifest,
        raw_result=preliminary.raw_result,
    )


__all__ = [
    "CompletedJob",
    "FakeClock",
    "LocalSimulator",
    "MockBackend",
    "MockJob",
]
