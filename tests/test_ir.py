import json
import math
from dataclasses import FrozenInstanceError

import pytest

from qplanck import CircuitIR, MeasurementSpec, Operation, Parameter
from qplanck.errors import CircuitError


def test_ir_serializes_deterministically_and_round_trips() -> None:
    ir = CircuitIR(
        qubit_count=2,
        operations=(Operation("H", (0,), metadata={"b": 2, "a": 1}),),
        measurements=(MeasurementSpec(0, 0),),
        metadata={"name": "demo"},
    )

    assert ir.to_json() == ir.to_json()
    payload = json.loads(ir.to_json())
    assert payload["schema_version"] == "qplanck.ir.v0.1"
    assert payload["operations"][0]["name"] == "h"
    assert list(payload["operations"][0]["metadata"]) == ["a", "b"]

    restored = CircuitIR.from_json(ir.to_json())
    assert restored.to_dict() == ir.to_dict()


def test_ir_dataclasses_are_frozen_and_metadata_is_read_only() -> None:
    operation = Operation("h", (0,), metadata={"owner": "test"})

    with pytest.raises(FrozenInstanceError):
        operation.name = "x"  # type: ignore[misc]
    with pytest.raises(TypeError):
        operation.metadata["owner"] = "other"  # type: ignore[index]


def test_parameter_round_trip() -> None:
    parameter = Parameter("theta", 0.25)
    assert Parameter.from_dict(parameter.to_dict()) == parameter


def test_ir_rejects_out_of_range_qubits() -> None:
    with pytest.raises(CircuitError):
        CircuitIR(1, operations=(Operation("h", (1,)),))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_ir_rejects_non_finite_numeric_values(value: float) -> None:
    with pytest.raises(CircuitError, match="finite"):
        Operation("rx", (0,), (value,))
    with pytest.raises(CircuitError, match="finite"):
        Parameter("theta", value)
