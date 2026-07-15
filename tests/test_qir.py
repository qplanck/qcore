import math

import pytest

from qplanck import Circuit
from qplanck.ir import CircuitIR, MeasurementSpec, Operation, Parameter
from qplanck.qir import (
    QIRCapabilities,
    QIRExportError,
    QIRProfile,
    dumps,
    export_qir,
    export_qir_with_report,
    validate_capabilities,
)


def test_base_profile_export_is_deterministic_and_complete() -> None:
    circuit = Circuit(2).h(0).rx(math.pi / 2, 1).cx(0, 1).measure(1, 3).measure(0, 1)

    module = export_qir(circuit)

    assert module.text == dumps(circuit)
    assert module.text == export_qir(circuit).text
    assert module.profile is QIRProfile.BASE
    assert module.manifest.qir_version == "2.0"
    assert module.manifest.required_num_qubits == 2
    assert module.manifest.required_num_results == 2
    assert module.manifest.required_qis == ("cnot", "h", "mz", "rx")

    text = module.text
    assert "define i64 @qplanck_main() #0" in text
    assert "call void @__quantum__rt__initialize(ptr null)" in text
    assert "call void @__quantum__qis__h__body(ptr null)" in text
    assert (
        "call void @__quantum__qis__rx__body"
        "(double 0x3FF921FB54442D18, ptr inttoptr (i64 1 to ptr))"
    ) in text
    assert ("call void @__quantum__qis__cnot__body(ptr null, ptr inttoptr (i64 1 to ptr))") in text
    assert ("call void @__quantum__qis__mz__body(ptr null, ptr writeonly null)") in text
    assert (
        "call void @__quantum__qis__mz__body"
        "(ptr inttoptr (i64 1 to ptr), ptr writeonly inttoptr (i64 1 to ptr))"
    ) in text
    assert "call void @__quantum__rt__tuple_record_output(i64 2, ptr @qplanck_label_0)" in text
    assert '"qir_profiles"="base_profile"' in text
    assert '"output_labeling_schema"="qplanck.cbit.v1"' in text
    assert '"required_num_qubits"="2"' in text
    assert '"required_num_results"="2"' in text
    assert "declare void @__quantum__qis__mz__body(ptr, ptr writeonly) #1" in text
    assert 'attributes #1 = { "irreversible" }' in text
    assert '!0 = !{i32 1, !"qir_major_version", i32 2}' in text
    assert '!1 = !{i32 7, !"qir_minor_version", i32 0}' in text
    assert '!2 = !{i32 1, !"dynamic_qubit_management", i1 false}' in text
    assert '!3 = !{i32 1, !"dynamic_result_management", i1 false}' in text


def test_manifest_preserves_classical_mapping_and_operation_provenance() -> None:
    circuit = Circuit(2).x(1).measure(1, 7).measure(0, 2)

    manifest = export_qir(circuit, entry_point="mapped_main").manifest

    assert [item.classical_bit for item in manifest.measurement_map] == [2, 7]
    assert [item.result_id for item in manifest.measurement_map] == [0, 1]
    assert [item.source_index for item in manifest.measurement_map] == [1, 0]
    assert manifest.source_map[0].source_operation == "x"
    assert manifest.source_map[0].qir_function == "__quantum__qis__x__body"
    assert manifest.source_map[1].source_index == 1
    assert manifest.source_map[1].classical_bit == 2
    assert manifest.source_map[2].source_index == 0
    assert manifest.source_map[2].classical_bit == 7
    assert manifest.to_dict()["entry_point"] == "mapped_main"
    assert manifest.to_dict()["measurement_map"][0]["label"] == "qplanck.cbit.2"


def test_export_covers_the_entire_static_qcore_gate_subset() -> None:
    circuit = (
        Circuit(2)
        .h(0)
        .x(0)
        .y(0)
        .z(0)
        .s(0)
        .t(0)
        .rx(0.1, 0)
        .ry(0.2, 0)
        .rz(0.3, 0)
        .cx(0, 1)
        .cz(0, 1)
        .measure_all()
    )

    module = export_qir(circuit)

    assert module.manifest.required_qis == (
        "cnot",
        "cz",
        "h",
        "mz",
        "rx",
        "ry",
        "rz",
        "s",
        "t",
        "x",
        "y",
        "z",
    )
    for qis_name in module.manifest.required_qis:
        assert f"@__quantum__qis__{qis_name}__body" in module.text


def test_capability_validation_rejects_missing_qis_and_resource_limits() -> None:
    circuit = Circuit(2).h(0).cx(0, 1).measure_all()
    missing_cnot = QIRCapabilities(supported_qis=frozenset({"h", "mz"}))

    with pytest.raises(QIRExportError, match="missing required instruction.*cnot"):
        validate_capabilities(circuit, missing_cnot)

    one_qubit = QIRCapabilities(max_qubits=1)
    with pytest.raises(QIRExportError, match="requires 2 qubits"):
        export_qir(circuit, capabilities=one_qubit)

    one_result = QIRCapabilities(max_results=1)
    with pytest.raises(QIRExportError, match="requires 2 results"):
        export_qir(circuit, capabilities=one_result)


@pytest.mark.parametrize(
    ("ir", "message"),
    [
        (
            CircuitIR(
                2,
                operations=(Operation("swap", (0, 1)),),
                measurements=(MeasurementSpec(0, 0),),
            ),
            "unsupported gate 'swap'",
        ),
        (
            CircuitIR(
                1,
                operations=(Operation("rx", (0,), (Parameter("theta"),)),),
                measurements=(MeasurementSpec(0, 0),),
            ),
            "symbolic parameter",
        ),
        (
            CircuitIR(
                1,
                measurements=(MeasurementSpec(0, 0), MeasurementSpec(0, 1)),
            ),
            "reuses qubit 0",
        ),
        (
            CircuitIR(
                2,
                measurements=(MeasurementSpec(0, 0), MeasurementSpec(1, 0)),
            ),
            "reuses classical bit 0",
        ),
    ],
)
def test_export_rejects_unsupported_or_ambiguous_ir(ir: CircuitIR, message: str) -> None:
    with pytest.raises(QIRExportError, match=message):
        export_qir(ir)


def test_export_rejects_invalid_entry_point_and_profile() -> None:
    circuit = Circuit(1).measure_all()

    with pytest.raises(QIRExportError, match="Invalid LLVM entry-point"):
        export_qir(circuit, entry_point="not valid")

    with pytest.raises(QIRExportError, match="Unsupported QIR profile"):
        export_qir(circuit, profile="adaptive_profile")


def test_measurement_free_circuit_has_zero_static_results() -> None:
    module = export_qir(Circuit(1).z(0))

    assert module.manifest.required_num_results == 0
    assert module.manifest.required_qis == ("z",)
    assert '"required_num_results"="0"' in module.text
    assert "@qplanck_label_" not in module.text
    assert "__quantum__qis__mz__body" not in module.text
    assert "__quantum__rt__result_record_output" not in module.text


def test_qir_export_reports_metadata_loss_and_semantic_preservation() -> None:
    circuit = Circuit(1, name="not-encoded-in-qir").h(0).measure_all()

    exported = export_qir_with_report(circuit)

    assert exported.value.text == export_qir(circuit).text
    assert not exported.report.is_lossless
    assert exported.report.losses[0].code == "QCORE-INTEROP-CIRCUIT-METADATA-DROPPED"
    assert "source operation mapping" in exported.report.preserved


def test_generated_module_verifies_with_official_pyqir() -> None:
    pyqir = pytest.importorskip("pyqir")
    circuit = Circuit(2).h(0).rx(0.25, 1).cx(0, 1).measure_all()

    module = pyqir.Module.from_ir(pyqir.Context(), export_qir(circuit).text)

    assert module.verify() is None
