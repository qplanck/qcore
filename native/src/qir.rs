use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::types::{CircuitIr, Operation, IR_SCHEMA_VERSION, MAX_IR_JSON_BYTES};
use crate::{implementation_info_value, KernelError};

const REQUEST_SCHEMA: &str = "qplanck.native.qir.request.v1";
const RESPONSE_SCHEMA: &str = "qplanck.native.qir.response.v1";
const OUTPUT_LABELING_SCHEMA: &str = "qplanck.cbit.v1";

#[derive(Debug, Deserialize)]
struct QirRequest {
    schema_version: String,
    ir_json: String,
    profile: String,
    supported_qis: BTreeSet<String>,
    #[serde(default)]
    max_qubits: Option<usize>,
    #[serde(default)]
    max_results: Option<usize>,
    entry_point: String,
}

#[derive(Clone, Debug, Serialize)]
struct MeasurementMap {
    source_index: usize,
    qubit: usize,
    classical_bit: usize,
    result_id: usize,
    output_index: usize,
    label: String,
}

#[derive(Clone, Debug, Serialize)]
struct SourceMapEntry {
    qis_call_index: usize,
    block: &'static str,
    source_kind: &'static str,
    source_index: usize,
    source_operation: String,
    qir_function: String,
    qubits: Vec<usize>,
    result_id: Option<usize>,
    classical_bit: Option<usize>,
}

#[derive(Debug)]
struct GateCall {
    qis_name: &'static str,
    operation_name: String,
    qubits: Vec<usize>,
    parameter: Option<f64>,
}

#[derive(Serialize)]
struct QirResponse {
    schema_version: &'static str,
    implementation: Value,
    text: String,
    profile: String,
    required_num_qubits: usize,
    required_num_results: usize,
    required_qis: Vec<String>,
    measurement_map: Vec<MeasurementMap>,
    source_map: Vec<SourceMapEntry>,
}

pub fn lower(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    let request: QirRequest = serde_json::from_slice(request)?;
    if request.schema_version != REQUEST_SCHEMA {
        return Err(KernelError::Invalid(format!(
            "Unsupported native QIR request schema: {}.",
            request.schema_version
        )));
    }
    if request.profile != "base_profile" {
        return Err(KernelError::Invalid(format!(
            "QIR profile '{}' is not implemented.",
            request.profile
        )));
    }
    if !valid_entry_point(&request.entry_point) {
        return Err(KernelError::Invalid(format!(
            "Invalid LLVM entry-point identifier {:?}; use an unquoted identifier.",
            request.entry_point
        )));
    }

    if request.ir_json.len() > MAX_IR_JSON_BYTES {
        return Err(KernelError::Invalid(format!(
            "Circuit IR JSON is {} bytes, exceeding the frozen alpha limit of {MAX_IR_JSON_BYTES}.",
            request.ir_json.len()
        )));
    }
    let ir: CircuitIr = serde_json::from_str(&request.ir_json)
        .map_err(|error| KernelError::Invalid(format!("Invalid CircuitIR JSON: {error}")))?;
    if ir.schema_version != IR_SCHEMA_VERSION {
        return Err(KernelError::Invalid(format!(
            "Unsupported QCore IR schema version: {}.",
            ir.schema_version
        )));
    }
    if ir.qubit_count == 0 {
        return Err(KernelError::Invalid(
            "Circuit must contain at least one qubit.".to_owned(),
        ));
    }

    let mut calls_by_operation = Vec::with_capacity(ir.operations.len());
    let mut required_qis = BTreeSet::new();
    for (source_index, operation) in ir.operations.iter().enumerate() {
        let calls = gate_calls(operation, source_index, ir.qubit_count)?;
        required_qis.extend(calls.iter().map(|call| call.qis_name.to_owned()));
        calls_by_operation.push(calls);
    }

    let mut seen_qubits = BTreeSet::new();
    let mut seen_cbits = BTreeSet::new();
    let mut indexed_measurements = Vec::with_capacity(ir.measurements.len());
    for (source_index, measurement) in ir.measurements.iter().enumerate() {
        if measurement.qubit >= ir.qubit_count {
            return Err(KernelError::Invalid(format!(
                "Measurement {source_index} references qubit {} outside the circuit.",
                measurement.qubit
            )));
        }
        if !seen_qubits.insert(measurement.qubit) {
            return Err(KernelError::Invalid(format!(
                "Measurement {source_index} reuses qubit {}; the Base Profile forbids using a qubit after an irreversible call.",
                measurement.qubit
            )));
        }
        if !seen_cbits.insert(measurement.cbit) {
            return Err(KernelError::Invalid(format!(
                "Measurement {source_index} reuses classical bit {}.",
                measurement.cbit
            )));
        }
        indexed_measurements.push((source_index, measurement));
    }
    indexed_measurements.sort_by_key(|(_, measurement)| measurement.cbit);
    let measurements: Vec<MeasurementMap> = indexed_measurements
        .into_iter()
        .enumerate()
        .map(|(result_id, (source_index, measurement))| MeasurementMap {
            source_index,
            qubit: measurement.qubit,
            classical_bit: measurement.cbit,
            result_id,
            output_index: result_id,
            label: format!("qplanck.cbit.{}", measurement.cbit),
        })
        .collect();
    if !measurements.is_empty() {
        required_qis.insert("mz".to_owned());
    }

    let missing: Vec<_> = required_qis
        .difference(&request.supported_qis)
        .cloned()
        .collect();
    if !missing.is_empty() {
        return Err(KernelError::Invalid(format!(
            "Target QIS is missing required instruction(s): {}.",
            missing.join(", ")
        )));
    }
    if request
        .max_qubits
        .is_some_and(|limit| ir.qubit_count > limit)
    {
        return Err(KernelError::Invalid(format!(
            "Circuit requires {} qubits, but the target limit is {}.",
            ir.qubit_count,
            request.max_qubits.expect("checked above")
        )));
    }
    if request
        .max_results
        .is_some_and(|limit| measurements.len() > limit)
    {
        return Err(KernelError::Invalid(format!(
            "Circuit requires {} results, but the target limit is {}.",
            measurements.len(),
            request.max_results.expect("checked above")
        )));
    }

    let required_qis: Vec<_> = required_qis.into_iter().collect();
    let (text, source_map) = emit_module(
        &ir,
        &calls_by_operation,
        &measurements,
        &required_qis,
        &request.entry_point,
        &request.profile,
    );
    let response = QirResponse {
        schema_version: RESPONSE_SCHEMA,
        implementation: serde_json::to_value(implementation_info_value())
            .map_err(|error| KernelError::Internal(error.to_string()))?,
        text,
        profile: request.profile,
        required_num_qubits: ir.qubit_count,
        required_num_results: measurements.len(),
        required_qis,
        measurement_map: measurements,
        source_map,
    };
    serde_json::to_vec(&response).map_err(KernelError::from)
}

fn gate_calls(
    operation: &Operation,
    source_index: usize,
    qubit_count: usize,
) -> Result<Vec<GateCall>, KernelError> {
    let (qis_name, qubits, params) = match operation.name.as_str() {
        "h" | "x" | "y" | "z" | "s" | "t" => (operation.name.as_str(), 1, 0),
        "rx" | "ry" | "rz" => (operation.name.as_str(), 1, 1),
        "cx" => ("cnot", 2, 0),
        "cz" => ("cz", 2, 0),
        "swap" => ("cnot", 2, 0),
        unsupported => {
            return Err(KernelError::Invalid(format!(
                "Operation {source_index} uses unsupported gate '{unsupported}' for QIR export."
            )));
        }
    };
    if operation.qubits.len() != qubits {
        return Err(KernelError::Invalid(format!(
            "Operation {source_index} ('{}') expects {qubits} qubit(s), got {}.",
            operation.name,
            operation.qubits.len()
        )));
    }
    if operation.params.len() != params {
        return Err(KernelError::Invalid(format!(
            "Operation {source_index} ('{}') expects {params} parameter(s), got {}.",
            operation.name,
            operation.params.len()
        )));
    }
    if operation.qubits.iter().any(|qubit| *qubit >= qubit_count) {
        return Err(KernelError::Invalid(format!(
            "Operation {source_index} ('{}') references a qubit outside the circuit.",
            operation.name
        )));
    }
    if matches!(operation.name.as_str(), "cx" | "cz" | "swap")
        && operation.qubits[0] == operation.qubits[1]
    {
        return Err(KernelError::Invalid(format!(
            "Operation {source_index} ('{}') requires distinct qubits.",
            operation.name
        )));
    }
    let parameter = if params == 1 {
        let raw = &operation.params[0];
        let value = raw.as_f64().ok_or_else(|| {
            KernelError::Invalid(format!(
                "Operation {source_index} ('{}') has a symbolic parameter; Base Profile export requires numeric constants.",
                operation.name
            ))
        })?;
        if !value.is_finite() {
            return Err(KernelError::Invalid(format!(
                "Operation {source_index} ('{}') has a non-finite parameter.",
                operation.name
            )));
        }
        Some(value)
    } else {
        None
    };

    if operation.name == "swap" {
        let left = operation.qubits[0];
        let right = operation.qubits[1];
        return Ok(vec![
            GateCall {
                qis_name: "cnot",
                operation_name: operation.name.clone(),
                qubits: vec![left, right],
                parameter: None,
            },
            GateCall {
                qis_name: "cnot",
                operation_name: operation.name.clone(),
                qubits: vec![right, left],
                parameter: None,
            },
            GateCall {
                qis_name: "cnot",
                operation_name: operation.name.clone(),
                qubits: vec![left, right],
                parameter: None,
            },
        ]);
    }
    Ok(vec![GateCall {
        qis_name: match qis_name {
            "h" => "h",
            "x" => "x",
            "y" => "y",
            "z" => "z",
            "s" => "s",
            "t" => "t",
            "rx" => "rx",
            "ry" => "ry",
            "rz" => "rz",
            "cnot" => "cnot",
            "cz" => "cz",
            _ => unreachable!("gate table is exhaustive"),
        },
        operation_name: operation.name.clone(),
        qubits: operation.qubits.clone(),
        parameter,
    }])
}

fn emit_module(
    ir: &CircuitIr,
    calls_by_operation: &[Vec<GateCall>],
    measurements: &[MeasurementMap],
    required_qis: &[String],
    entry_point: &str,
    profile: &str,
) -> (String, Vec<SourceMapEntry>) {
    let mut labels = Vec::new();
    if !measurements.is_empty() {
        labels.push("qplanck.results".to_owned());
        labels.extend(measurements.iter().map(|item| item.label.clone()));
    }
    let mut lines = vec![
        "; ModuleID = 'qplanck'".to_owned(),
        "source_filename = \"qplanck\"".to_owned(),
        String::new(),
    ];
    for (index, label) in labels.iter().enumerate() {
        lines.push(format!(
            "@qplanck_label_{index} = internal constant [{} x i8] c\"{label}\\00\"",
            label.len() + 1
        ));
    }
    if !labels.is_empty() {
        lines.push(String::new());
    }
    lines.extend([
        format!("define i64 @{entry_point}() #0 {{"),
        "entry:".to_owned(),
        "  call void @__quantum__rt__initialize(ptr null)".to_owned(),
        "  br label %body".to_owned(),
        String::new(),
        "body:".to_owned(),
    ]);

    let mut source_map = Vec::new();
    for (source_index, calls) in calls_by_operation.iter().enumerate() {
        for call in calls {
            let symbol = qis_symbol(call.qis_name);
            let args = if let Some(parameter) = call.parameter {
                format!(
                    "double {}, ptr {}",
                    double_literal(parameter),
                    pointer(call.qubits[0])
                )
            } else {
                call.qubits
                    .iter()
                    .map(|qubit| format!("ptr {}", pointer(*qubit)))
                    .collect::<Vec<_>>()
                    .join(", ")
            };
            lines.push(format!("  call void @{symbol}({args})"));
            source_map.push(SourceMapEntry {
                qis_call_index: source_map.len(),
                block: "body",
                source_kind: "operation",
                source_index,
                source_operation: call.operation_name.clone(),
                qir_function: symbol,
                qubits: call.qubits.clone(),
                result_id: None,
                classical_bit: None,
            });
        }
    }

    lines.extend([
        "  br label %measurements".to_owned(),
        String::new(),
        "measurements:".to_owned(),
    ]);
    for measurement in measurements {
        let symbol = qis_symbol("mz");
        lines.push(format!(
            "  call void @{symbol}(ptr {}, ptr writeonly {})",
            pointer(measurement.qubit),
            pointer(measurement.result_id)
        ));
        source_map.push(SourceMapEntry {
            qis_call_index: source_map.len(),
            block: "measurements",
            source_kind: "measurement",
            source_index: measurement.source_index,
            source_operation: "measure".to_owned(),
            qir_function: symbol,
            qubits: vec![measurement.qubit],
            result_id: Some(measurement.result_id),
            classical_bit: Some(measurement.classical_bit),
        });
    }

    lines.extend([
        "  br label %output".to_owned(),
        String::new(),
        "output:".to_owned(),
    ]);
    if !measurements.is_empty() {
        lines.push(format!(
            "  call void @__quantum__rt__tuple_record_output(i64 {}, ptr @qplanck_label_0)",
            measurements.len()
        ));
        for (index, measurement) in measurements.iter().enumerate() {
            lines.push(format!(
                "  call void @__quantum__rt__result_record_output(ptr {}, ptr @qplanck_label_{})",
                pointer(measurement.result_id),
                index + 1
            ));
        }
    }
    lines.extend(["  ret i64 0".to_owned(), "}".to_owned(), String::new()]);

    for name in required_qis {
        lines.push(qis_declaration(name));
    }
    if !required_qis.is_empty() {
        lines.push(String::new());
    }
    lines.push("declare void @__quantum__rt__initialize(ptr)".to_owned());
    if !measurements.is_empty() {
        lines.extend([
            "declare void @__quantum__rt__tuple_record_output(i64, ptr)".to_owned(),
            "declare void @__quantum__rt__result_record_output(ptr, ptr)".to_owned(),
        ]);
    }
    lines.push(String::new());

    lines.push(format!(
        "attributes #0 = {{ \"entry_point\" \"qir_profiles\"=\"{profile}\" \"output_labeling_schema\"=\"{OUTPUT_LABELING_SCHEMA}\" \"required_num_qubits\"=\"{}\" \"required_num_results\"=\"{}\" }}",
        ir.qubit_count,
        measurements.len()
    ));
    if !measurements.is_empty() {
        lines.push("attributes #1 = { \"irreversible\" }".to_owned());
    }
    lines.extend([
        String::new(),
        "!llvm.module.flags = !{!0, !1, !2, !3}".to_owned(),
        String::new(),
        "!0 = !{i32 1, !\"qir_major_version\", i32 2}".to_owned(),
        "!1 = !{i32 7, !\"qir_minor_version\", i32 0}".to_owned(),
        "!2 = !{i32 1, !\"dynamic_qubit_management\", i1 false}".to_owned(),
        "!3 = !{i32 1, !\"dynamic_result_management\", i1 false}".to_owned(),
        String::new(),
    ]);
    (lines.join("\n"), source_map)
}

fn valid_entry_point(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !(first.is_ascii_alphabetic() || first == '_') {
        return false;
    }
    chars.all(|character| {
        character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | '$' | '-')
    })
}

fn qis_symbol(name: &str) -> String {
    format!("__quantum__qis__{name}__body")
}

fn qis_declaration(name: &str) -> String {
    let symbol = qis_symbol(name);
    match name {
        "rx" | "ry" | "rz" => format!("declare void @{symbol}(double, ptr)"),
        "cnot" | "cz" => format!("declare void @{symbol}(ptr, ptr)"),
        "mz" => format!("declare void @{symbol}(ptr, ptr writeonly) #1"),
        _ => format!("declare void @{symbol}(ptr)"),
    }
}

fn pointer(index: usize) -> String {
    if index == 0 {
        "null".to_owned()
    } else {
        format!("inttoptr (i64 {index} to ptr)")
    }
}

fn double_literal(value: f64) -> String {
    format!("0x{:016X}", value.to_bits())
}

#[cfg(test)]
mod tests {
    use super::{double_literal, valid_entry_point};

    #[test]
    fn llvm_double_is_exact() {
        assert_eq!(
            double_literal(std::f64::consts::FRAC_PI_2),
            "0x3FF921FB54442D18"
        );
    }

    #[test]
    fn entry_point_uses_unquoted_llvm_identifier_subset() {
        assert!(valid_entry_point("qplanck.main-$1"));
        assert!(!valid_entry_point("1main"));
        assert!(!valid_entry_point("not valid"));
    }
}
