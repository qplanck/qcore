from __future__ import annotations

import math
import runpy
from pathlib import Path
from typing import Any

import pytest

from qplanck_braket import redacted_arn_identity


@pytest.fixture(scope="module")
def live_helpers() -> dict[str, Any]:
    script = Path(__file__).parents[1] / "scripts" / "live_smoke.py"
    return runpy.run_path(str(script), run_name="qplanck_braket_live_smoke")


@pytest.mark.parametrize("gate", ["rx", "ry"])
def test_parameterized_smoke_gate_uses_angle_then_qubit(
    live_helpers: dict[str, Any],
    gate: str,
) -> None:
    circuit, parameters = live_helpers["_program_for_gate"](gate)
    operation = circuit.operations[0]
    assert operation.name == gate
    assert operation.qubits == (0,)
    assert operation.params == (math.pi,)
    assert parameters == (math.pi,)


def test_live_evidence_redacts_account_and_full_arns(live_helpers: dict[str, Any]) -> None:
    account_canary = "112233445566"
    device_arn = (
        f"arn:aws:braket:us-west-1:{account_canary}:"
        "device/qpu/rigetti/Cepheus-canary"
    )
    task_arn = (
        f"arn:aws:braket:us-west-1:{account_canary}:"
        "quantum-task/task-canary"
    )
    evidence = live_helpers["_live_evidence"](
        device_arn=device_arn,
        task_arn=task_arn,
        status="succeeded",
        counts={"0": 10},
        target_hash="sha256:target-canary",
        pulse_snapshot_hash="sha256:pulse-canary",
        manifest_hash="sha256:manifest-canary",
    )
    serialized = str(evidence)
    assert evidence["device_identity"] == redacted_arn_identity(device_arn)
    assert evidence["task_identity"] == redacted_arn_identity(task_arn)
    assert account_canary not in serialized
    assert device_arn not in serialized
    assert task_arn not in serialized
    assert "s3://" not in serialized
