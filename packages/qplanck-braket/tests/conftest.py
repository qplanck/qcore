from __future__ import annotations

import json
from pathlib import Path

import pytest

from qplanck_braket import BraketPulseSnapshot


@pytest.fixture
def capabilities() -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "rigetti_pulse_capabilities.json"
    return json.loads(path.read_text())


@pytest.fixture
def snapshot(capabilities: dict[str, object]) -> BraketPulseSnapshot:
    return BraketPulseSnapshot.from_capabilities(
        "arn:aws:braket:us-west-1::device/qpu/rigetti/Cepheus-1-108Q",
        capabilities,
        calibration_digest="0" * 64,
        captured_at="2026-07-14T00:00:00+00:00",
    )
