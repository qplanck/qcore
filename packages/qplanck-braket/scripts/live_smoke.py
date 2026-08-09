"""Protected one-task Amazon Braket pulse smoke.

This script is intentionally unusable without an exact confirmation string, an
ambient AWS identity, an online Rigetti Cepheus QPU, and an already-configured
per-device Braket spending limit no greater than USD 10. It creates at most one
10-shot quantum task and never retries submission.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qplanck import CalibratedCircuit, Circuit, CompileOptions, ExecutionOptions, compile_circuit
from qplanck.pulse import (
    CalibrationKey,
    CalibrationLibrary,
    DriveChannel,
    GaussianWaveform,
    PulseProgram,
)
from qplanck.targets import Layout

from qplanck_braket import (
    BraketChannelMap,
    BraketPulseBackend,
    BraketPulseDevice,
    redacted_arn_identity,
)

CONFIRMATION = "I_UNDERSTAND_THIS_RUNS_ONE_PAID_BRAKET_QPU_TASK"
MAX_ALLOWED_COST = Decimal("10.00")
SHOTS = 10


def _decimal(value: str, *, label: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SystemExit(f"{label} must be a decimal amount.") from exc
    if not result.is_finite() or result <= 0:
        raise SystemExit(f"{label} must be positive and finite.")
    return result


def _active_spending_limit(
    client: Any,
    *,
    device_arn: str,
    max_cost: Decimal,
    estimated_cost: Decimal,
) -> dict[str, Any]:
    response = client.search_spending_limits(
        filters=[{"name": "deviceArn", "operator": "EQUAL", "values": [device_arn]}]
    )
    limits = response.get("spendingLimits", [])
    now = datetime.now(UTC)
    active = []
    for item in limits:
        period = item.get("timePeriod") or {}
        starts = period.get("startAt")
        ends = period.get("endAt")
        if starts is not None and starts.astimezone(UTC) > now:
            continue
        if ends is not None and ends.astimezone(UTC) < now:
            continue
        active.append(item)
    if len(active) != 1:
        raise SystemExit("Exactly one active per-device Amazon Braket spending limit is required.")
    selected = active[0]
    limit = _decimal(str(selected["spendingLimit"]), label="AWS spending limit")
    queued = Decimal(str(selected.get("queuedSpend", "0")))
    total = Decimal(str(selected.get("totalSpend", "0")))
    if limit > max_cost or limit > MAX_ALLOWED_COST:
        raise SystemExit(
            f"AWS spending limit is ${limit}; this smoke requires a limit no greater than "
            f"${min(max_cost, MAX_ALLOWED_COST)}."
        )
    remaining = limit - queued - total
    if remaining < estimated_cost:
        raise SystemExit(
            f"Remaining Braket spending limit ${remaining} is below the supplied conservative "
            f"estimate ${estimated_cost}."
        )
    return {
        "limit_usd": str(limit),
        "queued_usd": str(queued),
        "total_usd": str(total),
        "remaining_usd": str(remaining),
    }


def _select_drive(device: BraketPulseDevice) -> tuple[int, str, str]:
    ports = device.snapshot.port_by_id
    candidates = []
    for frame in device.snapshot.frames:
        port = ports[frame.port_id]
        if len(frame.qubits) != 1 or port.direction != "tx":
            continue
        associated = frame.associated_gate.lower() if frame.associated_gate else None
        candidates.append((frame, associated))
    if not candidates:
        raise SystemExit("Device capabilities expose no single-qubit transmit frame.")

    single_qubit_basis = [name for name in ("rx", "x", "ry") if name in device.target.basis_gates]
    if not single_qubit_basis:
        raise SystemExit("Device target exposes no supported single-qubit calibration gate.")
    for preferred_gate in single_qubit_basis:
        matching = sorted(
            (frame for frame, associated in candidates if associated == preferred_gate),
            key=lambda frame: (frame.qubits, frame.frame_id),
        )
        if matching:
            frame = matching[0]
            return frame.qubits[0], frame.frame_id, preferred_gate
    frame = sorted((item[0] for item in candidates), key=lambda item: (item.qubits, item.frame_id))[
        0
    ]
    return frame.qubits[0], frame.frame_id, single_qubit_basis[0]


def _program_for_gate(gate: str) -> tuple[Circuit, tuple[float, ...]]:
    circuit = Circuit(1)
    if gate == "x":
        circuit.x(0)
        parameters: tuple[float, ...] = ()
    elif gate == "rx":
        circuit.rx(math.pi, 0)
        parameters = (math.pi,)
    elif gate == "ry":
        circuit.ry(math.pi, 0)
        parameters = (math.pi,)
    else:  # pragma: no cover - guarded by capability selection
        raise SystemExit(f"Unsupported smoke calibration gate: {gate}.")
    circuit.measure(0, 0)
    return circuit, parameters


def _pulse_shape(device: BraketPulseDevice, frame_id: str) -> tuple[int, float, float]:
    frame = device.snapshot.frame_by_id[frame_id]
    port = device.snapshot.port_by_id[frame.port_id]
    validation = dict(device.snapshot.validation_parameters)
    minimum_seconds = float(validation.get("MIN_PULSE_LENGTH", 0.0) or 0.0)
    maximum_seconds = float(validation.get("MAX_PULSE_LENGTH", float("inf")) or float("inf"))
    duration = max(40, math.ceil(minimum_seconds / port.dt_seconds))
    if duration * port.dt_seconds > maximum_seconds:
        raise SystemExit("Capability-selected Gaussian duration exceeds device pulse maximum.")
    maximum_amplitude = float(validation.get("MAX_AMPLITUDE", 1.0) or 1.0)
    amplitude = min(0.2, maximum_amplitude / 2)
    if amplitude <= 0:
        raise SystemExit("Device capabilities do not permit a positive pulse amplitude.")
    return duration, duration / 4, amplitude


def _live_evidence(
    *,
    device_arn: str,
    task_arn: str,
    status: str,
    counts: Mapping[str, int],
    target_hash: str,
    pulse_snapshot_hash: str,
    manifest_hash: str | None,
) -> dict[str, Any]:
    """Build the only persisted live-smoke artifact, with unusable ARN identities."""

    return {
        "schema_version": "qplanck.braket.live-smoke.v0.1",
        "device_identity": redacted_arn_identity(device_arn),
        "task_identity": redacted_arn_identity(task_arn),
        "status": status,
        "shots": SHOTS,
        "counts": dict(counts),
        "target_hash": target_hash,
        "pulse_snapshot_hash": pulse_snapshot_hash,
        "manifest_hash": manifest_hash,
        "claim": "provider execution smoke only; no hardware-fidelity claim",
    }


def main() -> int:
    try:
        import boto3
        from braket.aws import AwsDevice
    except ImportError as exc:  # pragma: no cover - protected workflow installs dependencies
        raise SystemExit("The protected smoke requires boto3 and amazon-braket-sdk.") from exc

    parser = argparse.ArgumentParser()
    parser.add_argument("--device-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--estimated-cost-usd", required=True)
    parser.add_argument("--max-cost-usd", default="10.00")
    parser.add_argument("--output", type=Path, default=Path("braket-live-result.json"))
    args = parser.parse_args()

    if args.confirmation != CONFIRMATION:
        raise SystemExit(f"Refusing paid execution: confirmation must equal {CONFIRMATION!r}.")
    max_cost = _decimal(args.max_cost_usd, label="Maximum cost")
    estimated_cost = _decimal(args.estimated_cost_usd, label="Estimated task cost")
    if max_cost > MAX_ALLOWED_COST or estimated_cost > max_cost:
        raise SystemExit("Cost inputs exceed the approved USD 10 ceiling.")
    arn_region = args.device_arn.split(":")[3]
    if arn_region != args.region:
        raise SystemExit("AWS region must match the Braket device ARN region.")
    if "/qpu/rigetti/Cepheus-" not in args.device_arn:
        raise SystemExit("This protected smoke is restricted to a Rigetti Cepheus QPU ARN.")

    session = boto3.Session(region_name=args.region)
    session.client("sts").get_caller_identity()  # IAM/ambient-credential preflight; not serialized.
    results_uri = os.environ.get("AMZN_BRAKET_TASK_RESULTS_S3_URI", "")
    parsed_results = urlparse(results_uri)
    if (
        parsed_results.scheme != "s3"
        or not parsed_results.netloc
        or not parsed_results.path.strip("/")
    ):
        raise SystemExit(
            "AMZN_BRAKET_TASK_RESULTS_S3_URI must identify an existing bucket and non-empty prefix."
        )
    session.client("s3").head_bucket(Bucket=parsed_results.netloc)
    braket_client = session.client("braket")
    spending = _active_spending_limit(
        braket_client,
        device_arn=args.device_arn,
        max_cost=max_cost,
        estimated_cost=estimated_cost,
    )

    aws_device = AwsDevice(args.device_arn)
    if aws_device.status != "ONLINE" or aws_device.provider_name != "Rigetti":
        raise SystemExit("Capability-selected Rigetti device must be ONLINE before submission.")
    device = BraketPulseDevice.from_aws_device(aws_device, refresh_calibrations=True)
    physical_qubit, frame_id, gate = _select_drive(device)
    circuit, parameters = _program_for_gate(gate)
    compiled = compile_circuit(
        circuit,
        CompileOptions(
            optimization_level=2,
            initial_layout=Layout((physical_qubit,)),
        ),
        target=device.target,
    )
    channel = DriveChannel(0)
    channel_map = BraketChannelMap.from_mapping(
        {channel: frame_id},
        snapshot=device.snapshot,
    )
    duration, sigma, amplitude = _pulse_shape(device, frame_id)
    pulse_program = PulseProgram(name="qplanck-braket-protected-smoke").play(
        0,
        channel,
        GaussianWaveform(duration, sigma, amplitude),
    )
    calibrations = CalibrationLibrary.from_mapping(
        {CalibrationKey(gate, (physical_qubit,), parameters): pulse_program}
    )
    calibrated = CalibratedCircuit(
        compiled,
        calibrations,
        device.target_hash,
        device.snapshot.snapshot_hash,
    )
    options = ExecutionOptions(shots=SHOTS, timeout_seconds=18_000.0)
    backend = BraketPulseBackend(device, channel_map, default_shots=SHOTS)
    preflight = backend.preflight(calibrated, options=options)
    print(json.dumps({"preflight": preflight.to_dict(), "spending": spending}, sort_keys=True))

    # This is the sole CreateQuantumTask path. BraketPulseBackend never retries it.
    job = backend.submit(calibrated, options=options)
    result = job.result(timeout=options.timeout_seconds)
    evidence = _live_evidence(
        device_arn=device.arn,
        task_arn=job.id,
        status=job.status().value,
        counts=result.counts,
        target_hash=device.target_hash,
        pulse_snapshot_hash=device.snapshot.snapshot_hash,
        manifest_hash=result.manifest.content_hash if result.manifest else None,
    )
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
