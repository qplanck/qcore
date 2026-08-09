use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::types::{canonical_ir_json, content_hash, parse_ir_json, CircuitIr, Operation};
use crate::{implementation_info_value, KernelError};

const REQUEST_SCHEMA: &str = "qplanck.native.simulate.request.v1";
const RESPONSE_SCHEMA: &str = "qplanck.native.simulate.response.v1";
const TRACE_SCHEMA: &str = "qplanck.trace.v0.1";
const DEFAULT_MAX_RESULT_BYTES: u64 = 64 * 1024 * 1024;
const REQUEST_OVERHEAD_BYTES: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum SimulationMode {
    Run,
    Statevector,
    Probabilities,
}

#[derive(Debug, Deserialize)]
struct SimulationRequest {
    schema_version: String,
    ir_json: String,
    mode: SimulationMode,
    #[serde(default)]
    shots: Option<usize>,
    #[serde(default)]
    seed: Option<u64>,
    #[serde(default)]
    trace: bool,
    max_statevector_bytes: u64,
    #[serde(default)]
    max_result_bytes: Option<u64>,
    max_trace_qubits: usize,
}

#[derive(Clone, Copy, Debug, Default)]
struct Complex64 {
    real: f64,
    imag: f64,
}

impl Complex64 {
    const ONE: Self = Self {
        real: 1.0,
        imag: 0.0,
    };

    const fn new(real: f64, imag: f64) -> Self {
        Self { real, imag }
    }

    fn add(self, other: Self) -> Self {
        Self::new(self.real + other.real, self.imag + other.imag)
    }

    fn mul(self, other: Self) -> Self {
        Self::new(
            self.real * other.real - self.imag * other.imag,
            self.real * other.imag + self.imag * other.real,
        )
    }

    fn probability(self) -> f64 {
        let value = self.real.mul_add(self.real, self.imag * self.imag);
        if value.abs() < f64::EPSILON {
            0.0
        } else if (value - 1.0).abs() < 8.0 * f64::EPSILON {
            1.0
        } else {
            value.clamp(0.0, 1.0)
        }
    }
}

#[derive(Clone, Debug, Serialize)]
struct ComplexValue {
    real: f64,
    imag: f64,
}

impl From<Complex64> for ComplexValue {
    fn from(value: Complex64) -> Self {
        Self {
            real: value.real,
            imag: value.imag,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
struct TraceStep {
    index: usize,
    operation: Option<Operation>,
    statevector: Vec<ComplexValue>,
    probabilities: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecutionTrace {
    schema_version: &'static str,
    circuit: CircuitIr,
    metadata: BTreeMap<String, Value>,
    steps: Vec<TraceStep>,
}

#[derive(Serialize)]
struct SimulationResponse {
    schema_version: &'static str,
    implementation: Value,
    mode: SimulationMode,
    ir_hash: String,
    statevector_bytes: u64,
    peak_execution_bytes: u64,
    estimated_result_bytes: u64,
    counts: BTreeMap<String, usize>,
    measurements: Vec<String>,
    probabilities: BTreeMap<String, f64>,
    statevector: Option<Vec<ComplexValue>>,
    trace: Option<ExecutionTrace>,
    metadata: BTreeMap<String, Value>,
}

pub fn simulate(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    if request.len() > crate::types::MAX_IR_JSON_BYTES + REQUEST_OVERHEAD_BYTES {
        return Err(KernelError::Resource(format!(
            "Native simulation request is {} bytes, exceeding the frozen alpha request limit.",
            request.len()
        )));
    }
    let request: SimulationRequest = serde_json::from_slice(request)?;
    if request.schema_version != REQUEST_SCHEMA {
        return Err(KernelError::Invalid(format!(
            "Unsupported native simulation request schema: {}.",
            request.schema_version
        )));
    }
    if request.max_statevector_bytes == 0 {
        return Err(KernelError::Invalid(
            "max_statevector_bytes must be positive.".to_owned(),
        ));
    }
    if request.max_result_bytes == Some(0) {
        return Err(KernelError::Invalid(
            "max_result_bytes must be positive when provided.".to_owned(),
        ));
    }

    let ir = parse_ir_json(&request.ir_json).map_err(KernelError::Invalid)?;
    if request.trace && ir.qubit_count > request.max_trace_qubits {
        return Err(KernelError::Unsupported(format!(
            "Trace JSON supports at most {} qubits for this request; increase max_trace_qubits only if the payload size is acceptable.",
            request.max_trace_qubits
        )));
    }

    let state_count = 1_u64
        .checked_shl(
            u32::try_from(ir.qubit_count)
                .map_err(|_| KernelError::Resource("Circuit width is too large.".to_owned()))?,
        )
        .ok_or_else(|| KernelError::Resource("Circuit width is too large.".to_owned()))?;
    let statevector_bytes = state_count
        .checked_mul(16)
        .ok_or_else(|| KernelError::Resource("Statevector size overflowed.".to_owned()))?;
    if statevector_bytes > request.max_statevector_bytes {
        return Err(KernelError::Resource(format!(
            "Statevector requires {statevector_bytes} bytes, exceeding the configured {}-byte limit.",
            request.max_statevector_bytes
        )));
    }

    let sample_width = ir
        .measurements
        .iter()
        .map(|measurement| measurement.cbit.saturating_add(1))
        .max()
        .unwrap_or(ir.qubit_count);
    let estimated_result_bytes = estimate_result_bytes(
        state_count,
        ir.qubit_count,
        request.shots.unwrap_or(0),
        sample_width,
        request
            .trace
            .then_some(ir.operations.len().saturating_add(1)),
        matches!(request.mode, SimulationMode::Statevector),
    )?;
    let result_limit = request.max_result_bytes.unwrap_or(DEFAULT_MAX_RESULT_BYTES);
    if estimated_result_bytes > result_limit {
        return Err(KernelError::Resource(format!(
            "Estimated result requires {estimated_result_bytes} bytes, exceeding the configured {result_limit}-byte limit."
        )));
    }
    let peak_execution_bytes = statevector_bytes
        .checked_add(estimated_result_bytes)
        .ok_or_else(|| KernelError::Resource("Peak execution memory overflowed.".to_owned()))?;
    if peak_execution_bytes > request.max_statevector_bytes {
        return Err(KernelError::Resource(format!(
            "Estimated peak execution memory requires {peak_execution_bytes} bytes, exceeding the configured {}-byte limit.",
            request.max_statevector_bytes
        )));
    }

    let state_len = usize::try_from(state_count)
        .map_err(|_| KernelError::Resource("Statevector does not fit this platform.".to_owned()))?;
    let mut state = vec![Complex64::default(); state_len];
    state[0] = Complex64::ONE;
    let mut trace_steps = request
        .trace
        .then(|| vec![trace_step(0, None, &state, ir.qubit_count)]);
    for (index, operation) in ir.operations.iter().enumerate() {
        apply_operation(&mut state, operation)?;
        if let Some(steps) = &mut trace_steps {
            steps.push(trace_step(
                index + 1,
                Some(operation.clone()),
                &state,
                ir.qubit_count,
            ));
        }
    }

    let probabilities = probability_map(&state, ir.qubit_count);
    let (measurements, counts) = if matches!(request.mode, SimulationMode::Run) {
        sample_measurements(
            &probabilities,
            &ir,
            request.shots.unwrap_or(0),
            request.seed.unwrap_or(0),
        )
    } else {
        (Vec::new(), BTreeMap::new())
    };
    let canonical_ir = canonical_ir_json(&ir).map_err(KernelError::Internal)?;
    let mut metadata = BTreeMap::new();
    metadata.insert("endianness".to_owned(), Value::String("little".to_owned()));
    metadata.insert(
        "sampling_algorithm".to_owned(),
        Value::String("qplanck.splitmix64-cdf.v1".to_owned()),
    );
    metadata.insert(
        "seed".to_owned(),
        request.seed.map_or(Value::Null, Value::from),
    );
    metadata.insert(
        "shots".to_owned(),
        request.shots.map_or(Value::Null, Value::from),
    );
    let trace = trace_steps.map(|steps| {
        let mut trace_metadata = BTreeMap::new();
        trace_metadata.insert(
            "backend".to_owned(),
            Value::String("rust-statevector".to_owned()),
        );
        trace_metadata.insert("endianness".to_owned(), Value::String("little".to_owned()));
        ExecutionTrace {
            schema_version: TRACE_SCHEMA,
            circuit: ir.clone(),
            metadata: trace_metadata,
            steps,
        }
    });
    let statevector = matches!(request.mode, SimulationMode::Statevector)
        .then(|| state.into_iter().map(ComplexValue::from).collect());
    let response = SimulationResponse {
        schema_version: RESPONSE_SCHEMA,
        implementation: serde_json::to_value(implementation_info_value())
            .map_err(|error| KernelError::Internal(error.to_string()))?,
        mode: request.mode,
        ir_hash: content_hash(&canonical_ir),
        statevector_bytes,
        peak_execution_bytes,
        estimated_result_bytes,
        counts,
        measurements,
        probabilities,
        statevector,
        trace,
        metadata,
    };
    serde_json::to_vec(&response).map_err(KernelError::from)
}

fn estimate_result_bytes(
    state_count: u64,
    qubits: usize,
    shots: usize,
    sample_width: usize,
    trace_steps: Option<usize>,
    include_statevector: bool,
) -> Result<u64, KernelError> {
    let states = u128::from(state_count);
    let probability_bytes = states
        .checked_mul((qubits as u128).saturating_add(32))
        .ok_or_else(|| KernelError::Resource("Result size overflowed.".to_owned()))?;
    let statevector_bytes = if include_statevector {
        states.saturating_mul(40)
    } else {
        0
    };
    let measurement_bytes =
        (shots as u128).saturating_mul((sample_width as u128).saturating_add(8));
    let trace_bytes = trace_steps
        .map(|steps| {
            (steps as u128)
                .saturating_mul(states.saturating_mul((qubits as u128).saturating_add(72)))
        })
        .unwrap_or(0);
    let total = probability_bytes
        .saturating_add(statevector_bytes)
        .saturating_add(measurement_bytes)
        .saturating_add(trace_bytes);
    u64::try_from(total).map_err(|_| KernelError::Resource("Result size overflowed.".to_owned()))
}

fn trace_step(
    index: usize,
    operation: Option<Operation>,
    state: &[Complex64],
    qubit_count: usize,
) -> TraceStep {
    TraceStep {
        index,
        operation,
        statevector: state.iter().copied().map(ComplexValue::from).collect(),
        probabilities: probability_map(state, qubit_count),
    }
}

fn probability_map(state: &[Complex64], qubit_count: usize) -> BTreeMap<String, f64> {
    state
        .iter()
        .enumerate()
        .map(|(index, amplitude)| (basis_key(index, qubit_count), amplitude.probability()))
        .collect()
}

fn basis_key(index: usize, width: usize) -> String {
    (0..width)
        .rev()
        .map(|bit| if index & (1 << bit) == 0 { '0' } else { '1' })
        .collect()
}

fn sample_measurements(
    probabilities: &BTreeMap<String, f64>,
    ir: &CircuitIr,
    shots: usize,
    seed: u64,
) -> (Vec<String>, BTreeMap<String, usize>) {
    if shots == 0 {
        return (Vec::new(), BTreeMap::new());
    }
    let ordered_probabilities: Vec<f64> = (0..probabilities.len())
        .map(|index| probabilities[&basis_key(index, ir.qubit_count)])
        .collect();
    let mut cumulative = Vec::with_capacity(ordered_probabilities.len());
    let mut total = 0.0;
    for probability in ordered_probabilities {
        total += probability;
        cumulative.push(total);
    }
    if let Some(last) = cumulative.last_mut() {
        *last = 1.0;
    }

    let mut generator = SplitMix64::new(seed);
    let mut measurements = Vec::with_capacity(shots);
    let mut counts = BTreeMap::new();
    for _ in 0..shots {
        let draw = generator.next_f64();
        let basis = cumulative.partition_point(|boundary| *boundary <= draw);
        let key = measurement_key(basis.min(cumulative.len() - 1), ir);
        *counts.entry(key.clone()).or_insert(0) += 1;
        measurements.push(key);
    }
    (measurements, counts)
}

fn measurement_key(basis: usize, ir: &CircuitIr) -> String {
    if ir.measurements.is_empty() {
        return basis_key(basis, ir.qubit_count);
    }
    let width = ir
        .measurements
        .iter()
        .map(|measurement| measurement.cbit.saturating_add(1))
        .max()
        .unwrap_or(0);
    let mut bits = vec!['0'; width];
    for measurement in &ir.measurements {
        bits[measurement.cbit] = if basis & (1 << measurement.qubit) == 0 {
            '0'
        } else {
            '1'
        };
    }
    bits.into_iter().rev().collect()
}

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    const fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E3779B97F4A7C15);
        let mut value = self.state;
        value = (value ^ (value >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94D049BB133111EB);
        value ^ (value >> 31)
    }

    fn next_f64(&mut self) -> f64 {
        ((self.next_u64() >> 11) as f64) * (1.0 / ((1_u64 << 53) as f64))
    }
}

fn apply_operation(state: &mut [Complex64], operation: &Operation) -> Result<(), KernelError> {
    match operation.name.as_str() {
        "h" => {
            let scale = std::f64::consts::FRAC_1_SQRT_2;
            apply_single(
                state,
                operation.qubits[0],
                [
                    [Complex64::new(scale, 0.0), Complex64::new(scale, 0.0)],
                    [Complex64::new(scale, 0.0), Complex64::new(-scale, 0.0)],
                ],
            );
        }
        "x" => apply_single(
            state,
            operation.qubits[0],
            [
                [Complex64::default(), Complex64::ONE],
                [Complex64::ONE, Complex64::default()],
            ],
        ),
        "y" => apply_single(
            state,
            operation.qubits[0],
            [
                [Complex64::default(), Complex64::new(0.0, -1.0)],
                [Complex64::new(0.0, 1.0), Complex64::default()],
            ],
        ),
        "z" => apply_diagonal(
            state,
            operation.qubits[0],
            Complex64::ONE,
            Complex64::new(-1.0, 0.0),
        ),
        "s" => apply_diagonal(
            state,
            operation.qubits[0],
            Complex64::ONE,
            Complex64::new(0.0, 1.0),
        ),
        "t" => {
            let scale = std::f64::consts::FRAC_1_SQRT_2;
            apply_diagonal(
                state,
                operation.qubits[0],
                Complex64::ONE,
                Complex64::new(scale, scale),
            );
        }
        "rx" => {
            let half = parameter(operation)? / 2.0;
            let cosine = half.cos();
            let sine = half.sin();
            apply_single(
                state,
                operation.qubits[0],
                [
                    [Complex64::new(cosine, 0.0), Complex64::new(0.0, -sine)],
                    [Complex64::new(0.0, -sine), Complex64::new(cosine, 0.0)],
                ],
            );
        }
        "ry" => {
            let half = parameter(operation)? / 2.0;
            let cosine = half.cos();
            let sine = half.sin();
            apply_single(
                state,
                operation.qubits[0],
                [
                    [Complex64::new(cosine, 0.0), Complex64::new(-sine, 0.0)],
                    [Complex64::new(sine, 0.0), Complex64::new(cosine, 0.0)],
                ],
            );
        }
        "rz" => {
            let half = parameter(operation)? / 2.0;
            apply_diagonal(
                state,
                operation.qubits[0],
                Complex64::new(half.cos(), -half.sin()),
                Complex64::new(half.cos(), half.sin()),
            );
        }
        "cx" => apply_controlled_x(state, operation.qubits[0], operation.qubits[1]),
        "cz" => apply_controlled_z(state, operation.qubits[0], operation.qubits[1]),
        "swap" => apply_swap(state, operation.qubits[0], operation.qubits[1]),
        unsupported => {
            return Err(KernelError::Unsupported(format!(
                "Unsupported operation '{unsupported}'."
            )));
        }
    }
    Ok(())
}

fn parameter(operation: &Operation) -> Result<f64, KernelError> {
    operation
        .params
        .first()
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            KernelError::Invalid(format!(
                "Operation '{}' requires a finite numeric parameter.",
                operation.name
            ))
        })
}

fn apply_single(state: &mut [Complex64], target: usize, matrix: [[Complex64; 2]; 2]) {
    let mask = 1 << target;
    for zero_index in 0..state.len() {
        if zero_index & mask != 0 {
            continue;
        }
        let one_index = zero_index | mask;
        let zero = state[zero_index];
        let one = state[one_index];
        state[zero_index] = matrix[0][0].mul(zero).add(matrix[0][1].mul(one));
        state[one_index] = matrix[1][0].mul(zero).add(matrix[1][1].mul(one));
    }
}

fn apply_diagonal(
    state: &mut [Complex64],
    target: usize,
    zero_factor: Complex64,
    one_factor: Complex64,
) {
    let mask = 1 << target;
    for (index, amplitude) in state.iter_mut().enumerate() {
        *amplitude = if index & mask == 0 {
            zero_factor.mul(*amplitude)
        } else {
            one_factor.mul(*amplitude)
        };
    }
}

fn apply_controlled_x(state: &mut [Complex64], control: usize, target: usize) {
    let control_mask = 1 << control;
    let target_mask = 1 << target;
    for index in 0..state.len() {
        if index & control_mask != 0 && index & target_mask == 0 {
            state.swap(index, index | target_mask);
        }
    }
}

fn apply_controlled_z(state: &mut [Complex64], control: usize, target: usize) {
    let mask = (1 << control) | (1 << target);
    for (index, amplitude) in state.iter_mut().enumerate() {
        if index & mask == mask {
            amplitude.real = -amplitude.real;
            amplitude.imag = -amplitude.imag;
        }
    }
}

fn apply_swap(state: &mut [Complex64], left: usize, right: usize) {
    let left_mask = 1 << left;
    let right_mask = 1 << right;
    for index in 0..state.len() {
        let left_value = index & left_mask != 0;
        let right_value = index & right_mask != 0;
        if left_value != right_value {
            let partner = index ^ left_mask ^ right_mask;
            if index < partner {
                state.swap(index, partner);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{basis_key, measurement_key, CircuitIr, SplitMix64};
    use crate::types::Measurement;
    use std::collections::BTreeMap;

    fn splitmix_sequence(seed: u64, length: usize) -> Vec<u64> {
        let mut generator = SplitMix64::new(seed);
        (0..length).map(|_| generator.next_u64()).collect()
    }

    #[test]
    fn basis_keys_are_big_endian_views_of_little_endian_indices() {
        assert_eq!(basis_key(5, 3), "101");
    }

    #[test]
    fn classical_measurement_mapping_is_explicit() {
        let ir = CircuitIr {
            schema_version: "qplanck.ir.v0.1".to_owned(),
            qubit_count: 3,
            operations: Vec::new(),
            measurements: vec![
                Measurement {
                    qubit: 0,
                    cbit: 2,
                    metadata: BTreeMap::new(),
                },
                Measurement {
                    qubit: 1,
                    cbit: 0,
                    metadata: BTreeMap::new(),
                },
            ],
            metadata: BTreeMap::new(),
        };
        assert_eq!(measurement_key(1, &ir), "100");
    }

    #[test]
    fn splitmix64_is_frozen() {
        assert_eq!(
            splitmix_sequence(0, 2),
            vec![0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4]
        );
    }
}
