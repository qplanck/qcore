use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::{json, Number, Value};

use crate::routing::{self, Layout, RoutingOptions, RoutingTrace, Target};
use crate::types::{canonical_ir_json, content_hash, parse_ir_json, CircuitIr, Operation};
use crate::{implementation_info_value, KernelError};

const REQUEST_SCHEMA: &str = "qplanck.native.compile.request.v1";
const RESPONSE_SCHEMA: &str = "qplanck.native.compile.response.v1";

#[derive(Debug, Deserialize)]
struct CompileRequest {
    schema_version: String,
    ir_json: String,
    options: CompileOptions,
    #[serde(default)]
    target: Option<Value>,
    #[serde(default)]
    target_hash: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CompileOptions {
    optimization_level: u8,
    #[serde(default)]
    angle_tolerance: f64,
    #[serde(default)]
    initial_layout: Option<Layout>,
    #[serde(default)]
    routing_seed: u64,
    #[serde(default = "default_placement_trials")]
    placement_trials: usize,
    #[serde(default)]
    max_inserted_swaps: Option<usize>,
    #[serde(flatten)]
    unknown_options: BTreeMap<String, Value>,
}

const fn default_placement_trials() -> usize {
    4
}

#[derive(Clone, Debug, Serialize)]
struct DependencyGraph {
    operation_count: usize,
    edges: Vec<(usize, usize)>,
}

#[derive(Clone, Debug, Serialize)]
struct ResourceMetrics {
    qubit_count: usize,
    operation_count: usize,
    measurement_count: usize,
    depth: usize,
    single_qubit_gate_count: usize,
    two_qubit_gate_count: usize,
    gate_counts: BTreeMap<String, usize>,
}

#[derive(Clone, Debug, Serialize)]
struct Rewrite {
    rule: &'static str,
    source_indices: Vec<usize>,
    before: Vec<Operation>,
    after: Vec<Operation>,
}

#[derive(Clone, Debug)]
struct TrackedOperation {
    operation: Operation,
    source_indices: Vec<usize>,
    rotation_terms: Vec<f64>,
}

#[derive(Serialize)]
struct CompileResponse {
    schema_version: &'static str,
    implementation: Value,
    compiled_ir: CircuitIr,
    source_graph: DependencyGraph,
    compiled_graph: DependencyGraph,
    before_metrics: ResourceMetrics,
    after_metrics: ResourceMetrics,
    routed_metrics: Option<ResourceMetrics>,
    routed_ir: Option<CircuitIr>,
    initial_layout: Option<Layout>,
    final_layout: Option<Layout>,
    routing_trace: Option<RoutingTrace>,
    target_hash: Option<String>,
    pipeline_id: String,
    input_ir_hash: String,
    output_ir_hash: String,
    events: Vec<Value>,
}

pub fn compile(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    let request: CompileRequest = serde_json::from_slice(request)?;
    if request.schema_version != REQUEST_SCHEMA {
        return Err(KernelError::Invalid(format!(
            "Unsupported native compile request schema: {}.",
            request.schema_version
        )));
    }
    if !request.options.angle_tolerance.is_finite() || request.options.angle_tolerance < 0.0 {
        return Err(KernelError::Invalid(
            "angle_tolerance must be a finite, non-negative number.".to_owned(),
        ));
    }
    if request.options.optimization_level > 2 {
        return Err(KernelError::Invalid(
            "optimization_level must be 0, 1, or 2.".to_owned(),
        ));
    }
    if !request.options.unknown_options.is_empty() {
        let names = request
            .options
            .unknown_options
            .keys()
            .cloned()
            .collect::<Vec<_>>()
            .join(", ");
        return Err(KernelError::Invalid(format!(
            "Unknown native compile option(s): {names}."
        )));
    }
    if request.options.optimization_level < 2
        && (request.options.initial_layout.is_some()
            || request.options.routing_seed != 0
            || request.options.placement_trials != default_placement_trials()
            || request.options.max_inserted_swaps.is_some()
            || request.target.is_some())
    {
        return Err(KernelError::Invalid(
            "Routing target/options are valid only at optimization level 2.".to_owned(),
        ));
    }

    let source_ir = parse_ir_json(&request.ir_json).map_err(KernelError::Invalid)?;

    let source_graph = dependency_graph(&source_ir);
    let before_metrics = resource_metrics(&source_ir, &source_graph);
    let source_ir_json = canonical_ir_json(&source_ir).map_err(KernelError::Internal)?;
    let input_ir_hash = content_hash(&source_ir_json);
    let mut events = vec![validation_event(&input_ir_hash, &before_metrics)];

    let (optimized_ir, rewrites) = if request.options.optimization_level >= 1 {
        optimize_local(&source_ir, request.options.angle_tolerance)?
    } else {
        (source_ir.clone(), Vec::new())
    };
    let optimized_ir_json = canonical_ir_json(&optimized_ir).map_err(KernelError::Internal)?;
    let optimized_ir_hash = content_hash(&optimized_ir_json);
    let optimized_graph = dependency_graph(&optimized_ir);
    let optimized_metrics = resource_metrics(&optimized_ir, &optimized_graph);

    if request.options.optimization_level >= 1 {
        events.push(optimization_event(
            &input_ir_hash,
            &optimized_ir_hash,
            &before_metrics,
            &optimized_metrics,
            rewrites,
        ));
    }

    let mut routed_ir = None;
    let mut routed_metrics = None;
    let mut initial_layout = None;
    let mut final_layout = None;
    let mut routing_trace = None;
    let mut target_hash = None;
    let compiled_ir = if request.options.optimization_level == 2 {
        let target_value = request.target.ok_or_else(|| {
            KernelError::Invalid("Optimization level 2 requires a target.".to_owned())
        })?;
        let resolved_target_hash = request.target_hash.unwrap_or_else(|| {
            let serialized = serde_json::to_string(&target_value).unwrap_or_default();
            content_hash(&serialized)
        });
        if !resolved_target_hash.starts_with("sha256:") {
            return Err(KernelError::Invalid(
                "target_hash must be a SHA-256 content identity.".to_owned(),
            ));
        }
        let target = Target::from_value(target_value).map_err(KernelError::Invalid)?;
        let route_output = routing::route(
            &optimized_ir,
            &target,
            RoutingOptions {
                initial_layout: request.options.initial_layout,
                routing_seed: request.options.routing_seed,
                placement_trials: request.options.placement_trials,
                max_inserted_swaps: request.options.max_inserted_swaps,
            },
            &resolved_target_hash,
            |ir| canonical_ir_json(ir).map(|serialized| content_hash(&serialized)),
        )
        .map_err(KernelError::Invalid)?;
        let routed_graph = dependency_graph(&route_output.routed_ir);
        let route_metrics = resource_metrics(&route_output.routed_ir, &routed_graph);
        let routed_json =
            canonical_ir_json(&route_output.routed_ir).map_err(KernelError::Internal)?;
        let routed_hash = content_hash(&routed_json);
        let final_graph = dependency_graph(&route_output.final_ir);
        let final_metrics = resource_metrics(&route_output.final_ir, &final_graph);
        let final_json =
            canonical_ir_json(&route_output.final_ir).map_err(KernelError::Internal)?;
        let final_hash = content_hash(&final_json);
        events.push(routing_event(
            events.len(),
            &optimized_ir_hash,
            &routed_hash,
            &optimized_metrics,
            &route_metrics,
            route_output.trace.inserted_swaps(),
            &resolved_target_hash,
        ));
        events.push(lowering_event(
            events.len(),
            &routed_hash,
            &final_hash,
            &route_metrics,
            &final_metrics,
            &resolved_target_hash,
        ));
        routed_ir = Some(route_output.routed_ir);
        routed_metrics = Some(route_metrics);
        initial_layout = Some(route_output.initial_layout);
        final_layout = Some(route_output.final_layout);
        routing_trace = Some(route_output.trace);
        target_hash = Some(resolved_target_hash);
        route_output.final_ir
    } else {
        optimized_ir
    };
    let compiled_ir_json = canonical_ir_json(&compiled_ir).map_err(KernelError::Internal)?;
    let output_ir_hash = content_hash(&compiled_ir_json);
    let compiled_graph = dependency_graph(&compiled_ir);
    let after_metrics = resource_metrics(&compiled_ir, &compiled_graph);
    events.push(resource_event(
        events.len(),
        &output_ir_hash,
        &after_metrics,
    ));

    let response = CompileResponse {
        schema_version: RESPONSE_SCHEMA,
        implementation: serde_json::to_value(implementation_info_value())
            .map_err(|error| KernelError::Internal(error.to_string()))?,
        compiled_ir,
        source_graph,
        compiled_graph,
        before_metrics,
        after_metrics,
        routed_metrics,
        routed_ir,
        initial_layout,
        final_layout,
        routing_trace,
        target_hash,
        pipeline_id: format!("qplanck.default-o{}.v1", request.options.optimization_level),
        input_ir_hash,
        output_ir_hash,
        events,
    };
    serde_json::to_vec(&response).map_err(KernelError::from)
}

fn dependency_graph(ir: &CircuitIr) -> DependencyGraph {
    let mut last_on_qubit = vec![None; ir.qubit_count];
    let mut edges = BTreeSet::new();
    for (index, operation) in ir.operations.iter().enumerate() {
        for qubit in &operation.qubits {
            if let Some(predecessor) = last_on_qubit[*qubit] {
                edges.insert((predecessor, index));
            }
        }
        for qubit in &operation.qubits {
            last_on_qubit[*qubit] = Some(index);
        }
    }
    DependencyGraph {
        operation_count: ir.operations.len(),
        edges: edges.into_iter().collect(),
    }
}

fn resource_metrics(ir: &CircuitIr, graph: &DependencyGraph) -> ResourceMetrics {
    let mut predecessors: Vec<Vec<usize>> = vec![Vec::new(); graph.operation_count];
    for (source, target) in &graph.edges {
        predecessors[*target].push(*source);
    }
    let mut depths = vec![0; graph.operation_count];
    for node in 0..graph.operation_count {
        let predecessor_depth = predecessors[node]
            .iter()
            .map(|predecessor| depths[*predecessor])
            .max()
            .unwrap_or(0);
        depths[node] = predecessor_depth + 1;
    }

    let mut gate_counts = BTreeMap::new();
    for operation in &ir.operations {
        *gate_counts.entry(operation.name.clone()).or_insert(0) += 1;
    }
    ResourceMetrics {
        qubit_count: ir.qubit_count,
        operation_count: ir.operations.len(),
        measurement_count: ir.measurements.len(),
        depth: depths.into_iter().max().unwrap_or(0),
        single_qubit_gate_count: ir
            .operations
            .iter()
            .filter(|operation| operation.qubits.len() == 1)
            .count(),
        two_qubit_gate_count: ir
            .operations
            .iter()
            .filter(|operation| operation.qubits.len() == 2)
            .count(),
        gate_counts,
    }
}

fn optimize_local(
    ir: &CircuitIr,
    angle_tolerance: f64,
) -> Result<(CircuitIr, Vec<Rewrite>), KernelError> {
    let mut live_operations: Vec<Option<TrackedOperation>> = Vec::new();
    let mut qubit_history: Vec<Vec<usize>> = vec![Vec::new(); ir.qubit_count];
    let mut rewrites = Vec::new();

    for (source_index, operation) in ir.operations.iter().enumerate() {
        let slot = candidate_slot(operation, &qubit_history);
        let candidate = slot.and_then(|slot| live_operations[slot].clone());
        if let (Some(slot), Some(candidate)) = (slot, candidate) {
            if same_rewrite_boundary(&candidate.operation, operation) {
                let mut source_indices = candidate.source_indices.clone();
                source_indices.push(source_index);
                if is_self_inverse(&operation.name) {
                    rewrites.push(Rewrite {
                        rule: "self-inverse-adjacent",
                        source_indices,
                        before: vec![candidate.operation.clone(), operation.clone()],
                        after: Vec::new(),
                    });
                    remove_slot(slot, &candidate, &mut live_operations, &mut qubit_history)?;
                    continue;
                }

                if is_rotation(&operation.name) {
                    let current_angle = parameter(operation, source_index)?;
                    let mut terms = candidate.rotation_terms.clone();
                    terms.push(current_angle);
                    if let Some(merged_angle) = faithful_sum(&terms) {
                        if merged_angle.abs() <= angle_tolerance {
                            rewrites.push(Rewrite {
                                rule: "remove-near-zero-rotation",
                                source_indices,
                                before: vec![candidate.operation.clone(), operation.clone()],
                                after: Vec::new(),
                            });
                            remove_slot(
                                slot,
                                &candidate,
                                &mut live_operations,
                                &mut qubit_history,
                            )?;
                            continue;
                        }

                        let mut merged = operation.clone();
                        let number = Number::from_f64(merged_angle).ok_or_else(|| {
                            KernelError::Internal(
                                "A finite rotation sum could not be represented as JSON."
                                    .to_owned(),
                            )
                        })?;
                        merged.params = vec![Value::Number(number)];
                        rewrites.push(Rewrite {
                            rule: "merge-adjacent-rotation",
                            source_indices: source_indices.clone(),
                            before: vec![candidate.operation, operation.clone()],
                            after: vec![merged.clone()],
                        });
                        live_operations[slot] = Some(TrackedOperation {
                            operation: merged,
                            source_indices,
                            rotation_terms: terms,
                        });
                        continue;
                    }
                }
            }
        }

        let rotation_terms = if is_rotation(&operation.name) {
            vec![parameter(operation, source_index)?]
        } else {
            Vec::new()
        };
        let slot = live_operations.len();
        live_operations.push(Some(TrackedOperation {
            operation: operation.clone(),
            source_indices: vec![source_index],
            rotation_terms,
        }));
        for qubit in &operation.qubits {
            qubit_history[*qubit].push(slot);
        }
    }

    let mut optimized = ir.clone();
    optimized.operations = live_operations
        .into_iter()
        .flatten()
        .map(|tracked| tracked.operation)
        .collect();
    Ok((optimized, rewrites))
}

fn candidate_slot(operation: &Operation, qubit_history: &[Vec<usize>]) -> Option<usize> {
    let mut slots = operation
        .qubits
        .iter()
        .map(|qubit| qubit_history[*qubit].last().copied());
    let first = slots.next()??;
    slots.all(|slot| slot == Some(first)).then_some(first)
}

fn same_rewrite_boundary(left: &Operation, right: &Operation) -> bool {
    left.name == right.name && left.qubits == right.qubits && left.metadata == right.metadata
}

fn remove_slot(
    slot: usize,
    tracked: &TrackedOperation,
    live_operations: &mut [Option<TrackedOperation>],
    qubit_history: &mut [Vec<usize>],
) -> Result<(), KernelError> {
    for qubit in &tracked.operation.qubits {
        if qubit_history[*qubit].pop() != Some(slot) {
            return Err(KernelError::Internal(
                "Compiler dependency history is inconsistent.".to_owned(),
            ));
        }
    }
    live_operations[slot] = None;
    Ok(())
}

fn parameter(operation: &Operation, index: usize) -> Result<f64, KernelError> {
    operation
        .params
        .first()
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            KernelError::Invalid(format!(
                "Compiler requires finite numeric gate parameters; operation {index} ('{}') is invalid.",
                operation.name
            ))
        })
}

fn is_self_inverse(name: &str) -> bool {
    matches!(name, "h" | "x" | "y" | "z" | "cx" | "cz" | "swap")
}

fn is_rotation(name: &str) -> bool {
    matches!(name, "rx" | "ry" | "rz")
}

// This is the Shewchuk-style partials algorithm used by CPython's math.fsum.
// Returning None matches the reference compiler's policy for an overflowing
// intermediate sum: preserve the operations instead of introducing infinity.
fn faithful_sum(values: &[f64]) -> Option<f64> {
    let mut partials: Vec<f64> = Vec::new();
    for &value in values {
        let mut x = value;
        let xsave = x;
        let mut index = 0;
        for partial_index in 0..partials.len() {
            let mut y = partials[partial_index];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                partials[index] = lo;
                index += 1;
            }
            x = hi;
        }
        partials.truncate(index);
        if !x.is_finite() {
            if xsave.is_finite() {
                return None;
            }
            return Some(x);
        }
        partials.push(x);
    }

    let mut hi = 0.0;
    let mut lo = 0.0;
    let mut index = partials.len();
    while index > 0 {
        index -= 1;
        let x = hi;
        let y = partials[index];
        hi = x + y;
        let yr = hi - x;
        lo = y - yr;
        if lo != 0.0 {
            break;
        }
    }
    if index > 0 {
        let next = partials[index - 1];
        if (lo < 0.0 && next < 0.0) || (lo > 0.0 && next > 0.0) {
            let y = lo * 2.0;
            let x = hi + y;
            let yr = x - hi;
            if y == yr {
                hi = x;
            }
        }
    }
    Some(hi)
}

fn pass_info(id: &'static str, requires: &[&str], provides: &[&str], preserves: &[&str]) -> Value {
    json!({
        "id": id,
        "version": "1",
        "requires": requires,
        "provides": provides,
        "preserves": preserves,
        "deterministic": true,
    })
}

fn validation_event(hash: &str, metrics: &ResourceMetrics) -> Value {
    json!({
        "index": 0,
        "pass": pass_info(
            "validate.static",
            &[],
            &["static-validity/v1"],
            &["circuit-ir"],
        ),
        "input_ir_hash": hash,
        "output_ir_hash": hash,
        "changed": false,
        "metrics_before": metrics,
        "metrics_after": metrics,
        "rewrites": [],
        "message": "Static gate, parameter, qubit, schema, and measurement validation passed.",
    })
}

fn optimization_event(
    input_hash: &str,
    output_hash: &str,
    before: &ResourceMetrics,
    after: &ResourceMetrics,
    rewrites: Vec<Rewrite>,
) -> Value {
    let message = format!("Applied {} conservative local rewrite(s).", rewrites.len());
    json!({
        "index": 1,
        "pass": pass_info(
            "opt.local-exact",
            &["static-validity/v1"],
            &["local-rewrite-provenance/v1"],
            &["qubit-count", "measurements", "circuit-metadata"],
        ),
        "input_ir_hash": input_hash,
        "output_ir_hash": output_hash,
        "changed": output_hash != input_hash,
        "metrics_before": before,
        "metrics_after": after,
        "rewrites": rewrites,
        "message": message,
    })
}

fn routing_event(
    index: usize,
    input_hash: &str,
    output_hash: &str,
    before: &ResourceMetrics,
    after: &ResourceMetrics,
    inserted_swaps: usize,
    target_hash: &str,
) -> Value {
    json!({
        "index": index,
        "pass": pass_info(
            "route.target-deterministic",
            &["static-validity/v1", "local-rewrite-provenance/v1"],
            &["physical-layout/v1", "routing-provenance/v1"],
            &["logical-semantics", "classical-bit-mapping"],
        ),
        "input_ir_hash": input_hash,
        "output_ir_hash": output_hash,
        "changed": output_hash != input_hash,
        "metrics_before": before,
        "metrics_after": after,
        "rewrites": [],
        "message": format!(
            "Routed to target {target_hash} with {inserted_swaps} inserted SWAP(s)."
        ),
    })
}

fn lowering_event(
    index: usize,
    input_hash: &str,
    output_hash: &str,
    before: &ResourceMetrics,
    after: &ResourceMetrics,
    target_hash: &str,
) -> Value {
    json!({
        "index": index,
        "pass": pass_info(
            "lower.target-basis-exact",
            &["physical-layout/v1"],
            &["target-conformance/v1"],
            &["logical-semantics", "classical-bit-mapping"],
        ),
        "input_ir_hash": input_hash,
        "output_ir_hash": output_hash,
        "changed": output_hash != input_hash,
        "metrics_before": before,
        "metrics_after": after,
        "rewrites": [],
        "message": format!("Lowered routed operations exactly into target {target_hash}."),
    })
}

fn resource_event(index: usize, hash: &str, metrics: &ResourceMetrics) -> Value {
    json!({
        "index": index,
        "pass": pass_info(
            "analyze.resources",
            &["static-validity/v1"],
            &["structure.resources/v1"],
            &["circuit-ir"],
        ),
        "input_ir_hash": hash,
        "output_ir_hash": hash,
        "changed": false,
        "metrics_before": metrics,
        "metrics_after": metrics,
        "rewrites": [],
        "message": "Collected deterministic gate counts and dependency depth.",
    })
}

#[cfg(test)]
mod tests {
    use super::faithful_sum;

    #[test]
    fn faithful_sum_cancels_without_losing_the_small_term() {
        assert_eq!(faithful_sum(&[1.0e100, 1.0, -1.0e100]), Some(1.0));
    }

    #[test]
    fn faithful_sum_refuses_overflow() {
        assert_eq!(faithful_sum(&[f64::MAX, f64::MAX]), None);
    }
}
