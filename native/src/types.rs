use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const IR_SCHEMA_VERSION: &str = "qplanck.ir.v0.1";
pub const MAX_IR_JSON_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_QUBITS: usize = 65_536;
pub const MAX_CLASSICAL_BITS: usize = 65_536;
pub const MAX_OPERATIONS: usize = 1_000_000;
pub const MAX_MEASUREMENTS: usize = 1_000_000;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CircuitIr {
    pub schema_version: String,
    pub qubit_count: usize,
    #[serde(default)]
    pub operations: Vec<Operation>,
    #[serde(default)]
    pub measurements: Vec<Measurement>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Operation {
    pub name: String,
    pub qubits: Vec<usize>,
    #[serde(default)]
    pub params: Vec<Value>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Measurement {
    pub qubit: usize,
    pub cbit: usize,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

pub fn validate_static_ir(ir: &CircuitIr) -> Result<(), String> {
    if ir.schema_version != IR_SCHEMA_VERSION {
        return Err(format!(
            "Unsupported IR schema version: {}.",
            ir.schema_version
        ));
    }
    if ir.qubit_count == 0 {
        return Err("Circuit must contain at least one qubit.".to_owned());
    }
    if ir.qubit_count > MAX_QUBITS {
        return Err(format!(
            "Circuit contains {} qubits, exceeding the frozen alpha limit of {MAX_QUBITS}.",
            ir.qubit_count
        ));
    }
    if ir.operations.len() > MAX_OPERATIONS {
        return Err(format!(
            "Circuit contains {} operations, exceeding the frozen alpha limit of {MAX_OPERATIONS}.",
            ir.operations.len()
        ));
    }
    if ir.measurements.len() > MAX_MEASUREMENTS {
        return Err(format!(
            "Circuit contains {} measurements, exceeding the frozen alpha limit of {MAX_MEASUREMENTS}.",
            ir.measurements.len()
        ));
    }

    for (index, operation) in ir.operations.iter().enumerate() {
        let (qubits, params) = match operation.name.as_str() {
            "h" | "x" | "y" | "z" | "s" | "t" => (1, 0),
            "rx" | "ry" | "rz" => (1, 1),
            "cx" | "cz" | "swap" => (2, 0),
            unsupported => {
                return Err(format!("Unsupported operation '{unsupported}'."));
            }
        };
        if operation.qubits.len() != qubits {
            return Err(format!(
                "Gate '{}' expects {qubits} qubit(s), got {}.",
                operation.name,
                operation.qubits.len()
            ));
        }
        if operation.params.len() != params {
            return Err(format!(
                "Gate '{}' expects {params} parameter(s), got {}.",
                operation.name,
                operation.params.len()
            ));
        }
        if operation
            .qubits
            .iter()
            .any(|qubit| *qubit >= ir.qubit_count)
        {
            return Err(format!(
                "Gate '{}' references a qubit outside this circuit.",
                operation.name
            ));
        }
        if matches!(operation.name.as_str(), "cx" | "cz" | "swap")
            && operation.qubits[0] == operation.qubits[1]
        {
            return Err(format!(
                "Gate '{}' requires distinct qubits.",
                operation.name
            ));
        }
        for parameter in &operation.params {
            if parameter.as_f64().is_none_or(|value| !value.is_finite()) {
                return Err(format!(
                    "Compiler requires finite numeric gate parameters; operation {index} ('{}') is invalid.",
                    operation.name
                ));
            }
        }
    }

    let mut measured_qubits = std::collections::BTreeSet::new();
    let mut measured_cbits = std::collections::BTreeSet::new();
    for measurement in &ir.measurements {
        if measurement.qubit >= ir.qubit_count {
            return Err("Measurement references a qubit outside this circuit.".to_owned());
        }
        if !measured_qubits.insert(measurement.qubit) {
            return Err(format!(
                "Qubit {} has already been measured.",
                measurement.qubit
            ));
        }
        if !measured_cbits.insert(measurement.cbit) {
            return Err(format!(
                "Classical bit {} is already assigned.",
                measurement.cbit
            ));
        }
        if measurement.cbit >= MAX_CLASSICAL_BITS {
            return Err(format!(
                "Classical bit {} exceeds the frozen alpha limit of {MAX_CLASSICAL_BITS}.",
                measurement.cbit
            ));
        }
    }
    Ok(())
}

pub fn parse_ir_json(ir_json: &str) -> Result<CircuitIr, String> {
    if ir_json.len() > MAX_IR_JSON_BYTES {
        return Err(format!(
            "Circuit IR JSON is {} bytes, exceeding the frozen alpha limit of {MAX_IR_JSON_BYTES}.",
            ir_json.len()
        ));
    }
    let ir: CircuitIr = serde_json::from_str(ir_json)
        .map_err(|error| format!("Invalid CircuitIR JSON: {error}"))?;
    validate_static_ir(&ir)?;
    Ok(ir)
}

pub fn canonical_ir_json(ir: &CircuitIr) -> Result<String, String> {
    let value = serde_json::to_value(ir)
        .map_err(|error| format!("Could not serialize CircuitIR: {error}"))?;
    let mut output = String::new();
    write_canonical_value(&value, &mut output)?;
    Ok(output)
}

fn write_canonical_value(value: &Value, output: &mut String) -> Result<(), String> {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Value::Number(value) => output.push_str(&python_number(value)),
        Value::String(value) => write_python_string(value, output),
        Value::Array(values) => {
            output.push('[');
            for (index, item) in values.iter().enumerate() {
                if index > 0 {
                    output.push_str(", ");
                }
                write_canonical_value(item, output)?;
            }
            output.push(']');
        }
        Value::Object(values) => {
            output.push('{');
            let mut keys: Vec<_> = values.keys().collect();
            keys.sort();
            for (index, key) in keys.into_iter().enumerate() {
                if index > 0 {
                    output.push_str(", ");
                }
                write_python_string(key, output);
                output.push_str(": ");
                write_canonical_value(&values[key], output)?;
            }
            output.push('}');
        }
    }
    Ok(())
}

fn python_number(value: &serde_json::Number) -> String {
    let raw = value.to_string();
    if !value.is_f64() {
        return raw;
    }
    if let Some((mantissa, exponent)) = raw.split_once(['e', 'E']) {
        let exponent_value = exponent.parse::<i32>().unwrap_or(0);
        return format!("{mantissa}e{exponent_value:+03}");
    }

    let (sign, unsigned) = raw
        .strip_prefix('-')
        .map_or(("", raw.as_str()), |value| ("-", value));
    let (integer, fraction) = unsigned.split_once('.').unwrap_or((unsigned, ""));
    let exponent = if let Some(position) = integer.find(|character| character != '0') {
        i32::try_from(integer.len() - position - 1).unwrap_or(i32::MAX)
    } else if let Some(position) = fraction.find(|character| character != '0') {
        -i32::try_from(position).unwrap_or(i32::MAX) - 1
    } else {
        return raw;
    };
    if (-4..16).contains(&exponent) {
        return raw;
    }

    let joined = format!("{integer}{fraction}");
    let digits = joined.trim_start_matches('0').trim_end_matches('0');
    let mut characters = digits.chars();
    let first = characters.next().unwrap_or('0');
    let remainder: String = characters.collect();
    let mantissa = if remainder.is_empty() {
        first.to_string()
    } else {
        format!("{first}.{remainder}")
    };
    format!("{sign}{mantissa}e{exponent:+03}")
}

fn write_python_string(value: &str, output: &mut String) {
    output.push('"');
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\u{0008}' => output.push_str("\\b"),
            '\u{000c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character < '\u{0020}' || !character.is_ascii() => {
                let mut units = [0_u16; 2];
                for unit in character.encode_utf16(&mut units) {
                    output.push_str(&format!("\\u{unit:04x}"));
                }
            }
            character => output.push(character),
        }
    }
    output.push('"');
}

pub fn content_hash(payload: &str) -> String {
    let digest = Sha256::digest(payload.as_bytes());
    format!("sha256:{digest:x}")
}

#[cfg(test)]
mod tests {
    use super::{canonical_ir_json, CircuitIr, Operation};
    use serde_json::Value;
    use std::collections::BTreeMap;

    #[test]
    fn canonical_ir_json_sorts_keys_and_freezes_spacing() {
        let ir = CircuitIr {
            schema_version: "qplanck.ir.v0.1".to_owned(),
            qubit_count: 1,
            operations: Vec::new(),
            measurements: Vec::new(),
            metadata: BTreeMap::from([("name".to_owned(), "alpha".into())]),
        };
        assert_eq!(
            canonical_ir_json(&ir).unwrap(),
            r#"{"measurements": [], "metadata": {"name": "alpha"}, "operations": [], "qubit_count": 1, "schema_version": "qplanck.ir.v0.1"}"#
        );
    }

    #[test]
    fn canonical_ir_json_matches_python_float_and_unicode_spelling() {
        let ir = CircuitIr {
            schema_version: "qplanck.ir.v0.1".to_owned(),
            qubit_count: 1,
            operations: vec![Operation {
                name: "rx".to_owned(),
                qubits: vec![0],
                params: vec![Value::from(1.0e-7)],
                metadata: BTreeMap::new(),
            }],
            measurements: Vec::new(),
            metadata: BTreeMap::from([("name".to_owned(), Value::String("café".to_owned()))]),
        };
        let json = canonical_ir_json(&ir).unwrap();
        assert!(json.contains("\"params\": [1e-07]"));
        assert!(json.contains("\"name\": \"caf\\u00e9\""));
    }

    #[test]
    fn canonical_ir_json_uses_python_scientific_notation_threshold() {
        let ir = CircuitIr {
            schema_version: "qplanck.ir.v0.1".to_owned(),
            qubit_count: 1,
            operations: vec![Operation {
                name: "rx".to_owned(),
                qubits: vec![0],
                params: vec![Value::from(1.234_567_890_123_45e-5)],
                metadata: BTreeMap::new(),
            }],
            measurements: Vec::new(),
            metadata: BTreeMap::new(),
        };
        assert!(canonical_ir_json(&ir)
            .unwrap()
            .contains("\"params\": [1.23456789012345e-05]"));
    }
}
