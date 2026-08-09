import json
from pathlib import Path

from qplanck import CircuitIR
from qplanck._native import CORE_CONTRACT_VERSION, compile_ir, implementation_info, simulate_ir

FIXTURE = Path(__file__).parents[1] / "native" / "contract-fixtures" / "bell-v1.json"


def test_frozen_bell_contract_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ir = CircuitIR.from_dict(fixture["ir"])

    compiled = compile_ir(ir.to_json(), fixture["compile"]["options"])
    simulated = simulate_ir(
        ir.to_json(),
        mode="run",
        shots=fixture["simulate"]["shots"],
        seed=fixture["simulate"]["seed"],
        trace=False,
        max_statevector_bytes=1024 * 1024,
        max_result_bytes=1024 * 1024,
        max_trace_qubits=8,
    )

    assert implementation_info()["core_contract_version"] == CORE_CONTRACT_VERSION
    assert compiled["pipeline_id"] == fixture["compile"]["pipeline_id"]
    assert compiled["input_ir_hash"] == fixture["compile"]["input_ir_hash"]
    assert compiled["output_ir_hash"] == fixture["compile"]["output_ir_hash"]
    assert [event["pass"]["id"] for event in compiled["events"]] == fixture["compile"]["pass_ids"]
    for key, expected in fixture["simulate"].items():
        if key not in {"shots", "seed"}:
            assert simulated[key] == expected
