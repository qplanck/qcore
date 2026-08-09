from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from qplanck import Circuit, ResourceLimitError, RunResult, Simulator
from qplanck.backends import FakeClock, LocalSimulator, MockBackend
from qplanck.compiler import CompileOptions
from qplanck.pulse import CalibrationLibrary
from qplanck.runtime import (
    Backend,
    BackendError,
    CalibratedCircuit,
    Diagnostic,
    ExecutionOptions,
    ExperimentManifest,
    ExternalArtifactRef,
    JobCancelledError,
    JobFailedError,
    JobStatus,
    JobTimeoutError,
    validate_job_transition,
)
from qplanck.targets import Target, Topology


def test_execution_options_are_canonical_immutable_and_round_trip() -> None:
    options = ExecutionOptions(
        shots=100,
        seed=7,
        trace="summary",
        timeout_seconds=2,
        max_memory_bytes=1024,
        max_result_bytes=2048,
        backend_options={"vendor.mode": "test"},
    )

    restored = ExecutionOptions.from_dict(options.to_dict())

    assert restored == options
    assert restored.content_hash == options.content_hash
    with pytest.raises(TypeError):
        options.backend_options["vendor.mode"] = "changed"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        options.shots = 2  # type: ignore[misc]

    nested = ExecutionOptions(backend_options={"vendor.config": {"items": [1, 2]}})
    with pytest.raises(TypeError):
        nested.backend_options["vendor.config"]["items"] = []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"shots": -1}, "non-negative"),
        ({"shots": True}, "non-negative"),
        ({"trace": "verbose"}, "off.*summary.*full"),
        ({"timeout_seconds": 0}, "positive"),
        ({"backend_options": {"mode": "fast"}}, "namespace"),
        ({"backend_options": {"vendor.api_token": "secret"}}, "secret-bearing"),
        ({"backend_options": {"vendor.value": float("nan")}}, "finite JSON"),
    ],
)
def test_execution_options_reject_ambiguous_or_unsafe_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ExecutionOptions(**kwargs)  # type: ignore[arg-type]


def test_job_transition_contract_rejects_regression() -> None:
    validate_job_transition(JobStatus.CREATED, JobStatus.QUEUED)
    validate_job_transition(JobStatus.CANCEL_REQUESTED, JobStatus.SUCCEEDED)

    with pytest.raises(ValueError, match="succeeded -> running"):
        validate_job_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING)


def test_manifest_round_trip_hash_redaction_and_tamper_detection() -> None:
    manifest = ExperimentManifest(
        source={"circuit_hash": "sha256:source", "path": "/Users/example/source.json"},
        compilation={"compiled_hash": "sha256:compiled"},
        target={"target_hash": "sha256:target"},
        execution={
            "backend_id": "provider.backend",
            "options": {"provider.token": "must-not-appear"},
        },
        environment={"python": "3.13", "workspace": "/tmp/private/project"},
        result={"result_hash": "sha256:result"},
    )

    payload = manifest.to_json()
    restored = ExperimentManifest.from_json(payload)

    assert restored.content_hash == manifest.content_hash
    assert "must-not-appear" not in payload
    assert "/Users/example" not in payload
    assert restored.execution["options"] == {"provider.token": "[REDACTED]"}

    data = manifest.to_dict()
    data["result"]["result_hash"] = "sha256:tampered"
    with pytest.raises(ValueError, match="integrity hash"):
        ExperimentManifest.from_dict(data)


def test_run_result_is_immutable_serializable_and_preserves_trace_alias() -> None:
    diagnostic = Diagnostic("PROVIDER_NOTE", "Provider normalized the result.", "info")
    artifact = ExternalArtifactRef("arn:aws:braket:task/example", media_type="application/json")
    result = RunResult(
        counts={"0": 2},
        probabilities={"0": 1.0},
        measurements=["0", "0"],
        metadata={"backend_id": "test"},
        diagnostics=(diagnostic,),
        raw_result=artifact,
    )

    restored = RunResult.from_json(result.to_json())

    assert restored.to_dict() == result.to_dict()
    assert restored.trace is restored.execution_trace
    assert result.measurements == ["0", "0"]
    with pytest.raises(TypeError):
        result.measurements.append("1")
    with pytest.raises(TypeError):
        result.counts["1"] = 1  # type: ignore[index]


def test_local_simulator_supports_runtime_options_manifest_and_async_parity() -> None:
    circuit = Circuit(2).h(0).cx(0, 1).measure_all()
    backend = LocalSimulator()
    options = ExecutionOptions(shots=32, seed=19, trace="full")

    direct = backend.run(circuit, options=options)
    submitted = backend.submit(circuit, options=options)
    async_result = submitted.result(timeout=0)

    assert isinstance(backend, Backend)
    assert backend.target.target_id == backend.backend_id
    assert submitted.status() is JobStatus.SUCCEEDED
    assert submitted.cancel() is False
    assert direct.counts == async_result.counts
    assert direct.measurements == async_result.measurements
    assert direct.execution_trace is not None
    assert direct.manifest is not None
    assert direct.manifest.execution["options"] == options.to_dict()
    assert direct.manifest.execution["implicit_measure_all"] is False
    assert direct.manifest.execution["started_at"]
    assert direct.manifest.execution["completed_at"]


def test_simulator_remains_a_local_simulator_compatibility_facade() -> None:
    simulator = Simulator()

    assert isinstance(simulator, LocalSimulator)
    assert simulator.run(Circuit(1).x(0), shots=2, seed=1).counts == {"1": 2}


def test_local_simulator_executes_routed_compiled_circuit_and_records_exact_target() -> None:
    source = Circuit(3).x(0).cx(0, 2).measure_all()
    target = Target.testing(3, topology=Topology.line(3), target_id="testing.line-3")
    compiled = source.compile(CompileOptions(optimization_level=2), target=target)

    result = LocalSimulator().run(compiled, shots=4, seed=1)

    assert result.counts == {"101": 4}
    assert result.manifest is not None
    assert result.manifest.target["target_id"] == "testing.line-3"
    assert result.manifest.compilation["target_hash"] == target.content_hash


def test_local_simulator_rejects_conflicting_or_unsupported_options() -> None:
    backend = LocalSimulator()

    with pytest.raises(ValueError, match="either options or direct"):
        backend.run(Circuit(1), options=ExecutionOptions(shots=1), shots=1)
    with pytest.raises(BackendError, match="does not support backend options"):
        backend.run(
            Circuit(1),
            options=ExecutionOptions(backend_options={"vendor.mode": "remote"}),
        )
    with pytest.raises(ResourceLimitError, match="peak execution memory"):
        backend.run(
            Circuit(1),
            options=ExecutionOptions(shots=10, max_memory_bytes=100),
        )


def test_mock_backend_lifecycle_timeout_and_repeated_result() -> None:
    fixture = RunResult.testing(counts={"00": 5, "11": 5})
    clock = FakeClock()
    backend = MockBackend.scenario(
        target=Target.testing(2),
        states=(JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED),
        transition_delays=(1.0, 2.0, 3.0),
        result=fixture,
        clock=clock,
    )
    job = backend.submit(Circuit(2), options=ExecutionOptions(shots=10))

    with pytest.raises(JobTimeoutError):
        job.result(timeout=5.9)
    assert clock.monotonic() == 0.0
    assert job.status() is JobStatus.QUEUED
    assert job.status() is JobStatus.RUNNING
    result = job.result(timeout=3.0)

    assert result is job.result()
    assert result.counts == fixture.counts
    assert result.manifest is not None
    assert result.manifest.execution["job_id"] == job.id
    assert clock.monotonic() == 6.0


def test_mock_job_cancellation_before_and_during_execution() -> None:
    backend = MockBackend.scenario(
        target=Target.testing(1),
        states=(JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED),
        result=RunResult.testing(counts={"0": 1}),
    )
    created = backend.submit(Circuit(1))

    assert created.cancel() is True
    assert created.status() is JobStatus.CANCELLED
    assert created.cancel() is False
    with pytest.raises(JobCancelledError):
        created.result()

    running = backend.submit(Circuit(1))
    assert running.status() is JobStatus.QUEUED
    assert running.status() is JobStatus.RUNNING
    assert running.cancel() is True
    assert running.status() is JobStatus.CANCELLED


def test_mock_failure_is_stable() -> None:
    backend = MockBackend.scenario(
        target=Target.testing(1),
        states=(JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED),
        failure_message="synthetic provider failure",
    )
    job = backend.submit(Circuit(1))

    for _ in range(2):
        with pytest.raises(JobFailedError, match="synthetic provider failure"):
            job.result()
    assert job.status() is JobStatus.FAILED


class _CompiledFixture:
    def __init__(self, target: Target):
        self.target = target

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": "testing", "target": self.target.to_dict()}


def test_calibrated_circuit_binds_target_and_pulse_snapshot_hashes() -> None:
    target = Target.testing(1)
    calibrated = CalibratedCircuit(
        compiled_circuit=_CompiledFixture(target),  # type: ignore[arg-type]
        calibrations=CalibrationLibrary(),
        target_hash=target.content_hash,
        pulse_snapshot_hash="sha256:pulse-snapshot",
    )

    assert calibrated.to_dict()["target_hash"] == target.content_hash
    assert calibrated.content_hash.startswith("sha256:")
    with pytest.raises(ValueError, match="does not match"):
        CalibratedCircuit(
            compiled_circuit=_CompiledFixture(target),  # type: ignore[arg-type]
            calibrations=CalibrationLibrary(),
            target_hash="sha256:different",
            pulse_snapshot_hash="sha256:pulse-snapshot",
        )
