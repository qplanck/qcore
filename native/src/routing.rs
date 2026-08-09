use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::types::{CircuitIr, Measurement, Operation, IR_SCHEMA_VERSION};

const LAYOUT_SCHEMA_VERSION: &str = "qplanck.layout.v0.1";
const ROUTING_TRACE_SCHEMA_VERSION: &str = "qplanck.routing.trace.v0.1";
const TARGET_SCHEMA_VERSION: &str = "qplanck.target.v0.1";
const TOPOLOGY_SCHEMA_VERSION: &str = "qplanck.topology.v0.1";

#[derive(Clone, Debug, Deserialize)]
pub struct Topology {
    schema_version: String,
    qubit_count: usize,
    #[serde(default)]
    directed: bool,
    #[serde(default)]
    edges: Vec<(usize, usize)>,
}

impl Topology {
    fn validate(&self) -> Result<(), String> {
        if self.schema_version != TOPOLOGY_SCHEMA_VERSION {
            return Err(format!(
                "Unsupported topology schema: {}.",
                self.schema_version
            ));
        }
        if self.qubit_count == 0 {
            return Err("Topology must contain at least one qubit.".to_owned());
        }
        let mut unique = BTreeSet::new();
        for &(left, right) in &self.edges {
            if left >= self.qubit_count || right >= self.qubit_count {
                return Err("Topology edge references a qubit outside the topology.".to_owned());
            }
            if left == right {
                return Err("Topology self-loops are not allowed.".to_owned());
            }
            let edge = if self.directed || left < right {
                (left, right)
            } else {
                (right, left)
            };
            if !unique.insert(edge) {
                continue;
            }
        }
        Ok(())
    }

    fn has_arc(&self, left: usize, right: usize) -> bool {
        if self.directed {
            self.edges.contains(&(left, right))
        } else {
            self.edges.contains(&(left.min(right), left.max(right)))
        }
    }

    fn has_weak_edge(&self, left: usize, right: usize) -> bool {
        self.has_arc(left, right) || (self.directed && self.has_arc(right, left))
    }

    fn neighbors(&self, qubit: usize) -> Vec<usize> {
        let mut result = BTreeSet::new();
        for &(left, right) in &self.edges {
            if left == qubit {
                result.insert(right);
            }
            if right == qubit {
                result.insert(left);
            }
        }
        result.into_iter().collect()
    }

    fn components(&self) -> Vec<Vec<usize>> {
        let mut remaining: BTreeSet<_> = (0..self.qubit_count).collect();
        let mut components = Vec::new();
        while let Some(&start) = remaining.first() {
            let mut queue = VecDeque::from([start]);
            let mut found = BTreeSet::from([start]);
            while let Some(current) = queue.pop_front() {
                for neighbor in self.neighbors(current) {
                    if found.insert(neighbor) {
                        queue.push_back(neighbor);
                    }
                }
            }
            for item in &found {
                remaining.remove(item);
            }
            components.push(found.into_iter().collect());
        }
        components
    }

    fn shortest_path(&self, source: usize, target: usize) -> Result<Vec<usize>, String> {
        if source >= self.qubit_count || target >= self.qubit_count {
            return Err("Topology path endpoint is out of range.".to_owned());
        }
        if source == target {
            return Ok(vec![source]);
        }
        let mut queue = VecDeque::from([source]);
        let mut previous = BTreeMap::from([(source, None)]);
        while let Some(current) = queue.pop_front() {
            for neighbor in self.neighbors(current) {
                if previous.contains_key(&neighbor) {
                    continue;
                }
                previous.insert(neighbor, Some(current));
                if neighbor == target {
                    let mut path = vec![target];
                    let mut cursor = target;
                    while let Some(Some(parent)) = previous.get(&cursor) {
                        path.push(*parent);
                        cursor = *parent;
                    }
                    path.reverse();
                    return Ok(path);
                }
                queue.push_back(neighbor);
            }
        }
        Err(format!(
            "No topology path connects physical qubits {source} and {target}."
        ))
    }

    fn distance(&self, source: usize, target: usize) -> Result<usize, String> {
        Ok(self.shortest_path(source, target)?.len() - 1)
    }

    fn diameter(&self) -> Result<usize, String> {
        let mut maximum = 0;
        for component in self.components() {
            for (index, source) in component.iter().enumerate() {
                for target in component.iter().skip(index + 1) {
                    maximum = maximum.max(self.distance(*source, *target)?);
                }
            }
        }
        Ok(maximum)
    }
}

#[derive(Clone, Debug, Deserialize)]
struct InstructionSupport {
    name: String,
    arity: usize,
    locations: Option<Vec<Vec<usize>>>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Target {
    schema_version: String,
    pub target_id: String,
    pub topology: Topology,
    instructions: Vec<InstructionSupport>,
    #[serde(flatten)]
    _other: BTreeMap<String, Value>,
}

impl Target {
    pub fn from_value(value: Value) -> Result<Self, String> {
        let target: Self = serde_json::from_value(value)
            .map_err(|error| format!("Invalid native target payload: {error}"))?;
        target.validate()?;
        Ok(target)
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema_version != TARGET_SCHEMA_VERSION {
            return Err(format!(
                "Unsupported target schema: {}.",
                self.schema_version
            ));
        }
        if self.target_id.trim().is_empty() {
            return Err("Target ID must be non-empty.".to_owned());
        }
        self.topology.validate()?;
        if self.instructions.is_empty() {
            return Err("Target must declare at least one instruction.".to_owned());
        }
        let mut names = BTreeSet::new();
        for instruction in &self.instructions {
            let expected = gate_arity(&instruction.name)
                .ok_or_else(|| format!("Unknown target instruction {:?}.", instruction.name))?;
            if instruction.arity != expected {
                return Err(format!(
                    "Instruction {:?} requires arity {expected}, not {}.",
                    instruction.name, instruction.arity
                ));
            }
            if !names.insert(instruction.name.as_str()) {
                return Err("Target instruction names must be unique.".to_owned());
            }
            if let Some(locations) = &instruction.locations {
                for location in locations {
                    if location.len() != instruction.arity
                        || location.iter().copied().collect::<BTreeSet<_>>().len() != location.len()
                        || location
                            .iter()
                            .any(|qubit| *qubit >= self.topology.qubit_count)
                    {
                        return Err(format!(
                            "Invalid physical location for instruction {:?}.",
                            instruction.name
                        ));
                    }
                }
            }
        }
        Ok(())
    }

    fn basis_gates(&self) -> BTreeSet<&str> {
        self.instructions
            .iter()
            .map(|instruction| instruction.name.as_str())
            .collect()
    }

    fn supports_operation(&self, operation: &Operation) -> bool {
        let Some(support) = self
            .instructions
            .iter()
            .find(|instruction| instruction.name == operation.name)
        else {
            return false;
        };
        if operation.qubits.len() != support.arity
            || operation
                .qubits
                .iter()
                .any(|qubit| *qubit >= self.topology.qubit_count)
        {
            return false;
        }
        if let Some(locations) = &support.locations {
            let mut location = operation.qubits.clone();
            if matches!(operation.name.as_str(), "cz" | "swap") {
                location.sort_unstable();
            }
            return locations.contains(&location);
        }
        if operation.qubits.len() == 1 {
            return true;
        }
        if operation.name == "cx" && self.topology.directed {
            return self
                .topology
                .has_arc(operation.qubits[0], operation.qubits[1]);
        }
        self.topology
            .has_weak_edge(operation.qubits[0], operation.qubits[1])
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Layout {
    #[serde(default = "layout_schema")]
    schema_version: String,
    pub logical_to_physical: Vec<usize>,
}

fn layout_schema() -> String {
    LAYOUT_SCHEMA_VERSION.to_owned()
}

impl Layout {
    fn new(values: Vec<usize>) -> Self {
        Self {
            schema_version: LAYOUT_SCHEMA_VERSION.to_owned(),
            logical_to_physical: values,
        }
    }

    fn identity(count: usize) -> Self {
        Self::new((0..count).collect())
    }

    fn validate(&self, logical_qubits: usize, physical_qubits: usize) -> Result<(), String> {
        if self.schema_version != LAYOUT_SCHEMA_VERSION {
            return Err(format!(
                "Unsupported layout schema: {}.",
                self.schema_version
            ));
        }
        if self.logical_to_physical.len() != logical_qubits {
            return Err(format!(
                "Layout maps {} logical qubits; the circuit requires {logical_qubits}.",
                self.logical_to_physical.len()
            ));
        }
        if self
            .logical_to_physical
            .iter()
            .copied()
            .collect::<BTreeSet<_>>()
            .len()
            != logical_qubits
        {
            return Err("Layout physical qubits must be unique.".to_owned());
        }
        if self
            .logical_to_physical
            .iter()
            .any(|physical| *physical >= physical_qubits)
        {
            return Err("Layout references a physical qubit outside the target.".to_owned());
        }
        Ok(())
    }

    fn swap_physical(&self, left: usize, right: usize) -> Self {
        Self::new(
            self.logical_to_physical
                .iter()
                .map(|physical| {
                    if *physical == left {
                        right
                    } else if *physical == right {
                        left
                    } else {
                        *physical
                    }
                })
                .collect(),
        )
    }
}

#[derive(Clone, Debug, Serialize)]
struct RoutingStep {
    index: usize,
    physical_edge: (usize, usize),
    trigger_source_indices: Vec<usize>,
    layout_before: Layout,
    layout_after: Layout,
    reason: &'static str,
}

#[derive(Clone, Debug, Serialize)]
struct RoutingTrial {
    trial: usize,
    seed: u64,
    initial_layout: Layout,
    final_layout: Layout,
    inserted_swaps: usize,
    routed_depth: usize,
    two_qubit_depth: usize,
    selected: bool,
    baseline: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct RoutingTrace {
    schema_version: &'static str,
    initial_layout: Layout,
    final_layout: Layout,
    steps: Vec<RoutingStep>,
    trials: Vec<RoutingTrial>,
    source_to_routed_indices: Vec<Vec<usize>>,
    routed_to_final_indices: Vec<Vec<usize>>,
    measurement_map: Vec<Value>,
}

impl RoutingTrace {
    pub fn inserted_swaps(&self) -> usize {
        self.steps.len()
    }
}

#[derive(Clone, Debug)]
struct TrialResult {
    trial: usize,
    seed: u64,
    initial_layout: Layout,
    final_layout: Layout,
    routed_ir: CircuitIr,
    steps: Vec<RoutingStep>,
    source_to_routed_indices: Vec<Vec<usize>>,
    inserted_swaps: usize,
    routed_depth: usize,
    two_qubit_depth: usize,
    baseline: bool,
    routed_hash: String,
}

pub struct RoutingOutput {
    pub routed_ir: CircuitIr,
    pub final_ir: CircuitIr,
    pub initial_layout: Layout,
    pub final_layout: Layout,
    pub trace: RoutingTrace,
}

pub struct RoutingOptions {
    pub initial_layout: Option<Layout>,
    pub routing_seed: u64,
    pub placement_trials: usize,
    pub max_inserted_swaps: Option<usize>,
}

pub fn route<F>(
    ir: &CircuitIr,
    target: &Target,
    options: RoutingOptions,
    target_hash: &str,
    mut hash_ir: F,
) -> Result<RoutingOutput, String>
where
    F: FnMut(&CircuitIr) -> Result<String, String>,
{
    if options.placement_trials == 0 {
        return Err("placement_trials must be a positive integer.".to_owned());
    }
    if ir.qubit_count > target.topology.qubit_count {
        return Err(format!(
            "Circuit width {} exceeds target width {}.",
            ir.qubit_count, target.topology.qubit_count
        ));
    }
    validate_routing_feasibility(ir, target)?;
    if let Some(layout) = &options.initial_layout {
        layout.validate(ir.qubit_count, target.topology.qubit_count)?;
    }

    let source_hash = hash_ir(ir)?;
    let greedy = options
        .initial_layout
        .clone()
        .map_or_else(|| interaction_greedy_layout(ir, target), Ok)?;
    let source_two_qubit_count = ir
        .operations
        .iter()
        .filter(|operation| operation.qubits.len() == 2)
        .count();
    let default_budget =
        64.max(8 * source_two_qubit_count.max(1) * target.topology.diameter()?.max(1));
    let swap_budget = options.max_inserted_swaps.unwrap_or(default_budget);
    let identity = Layout::identity(ir.qubit_count);
    let mut candidates = Vec::new();
    for trial in 0..options.placement_trials {
        let mut candidate = if let Some(layout) = &options.initial_layout {
            layout.clone()
        } else if trial == 0 {
            greedy.clone()
        } else if trial == 1 && layout_connects_components(&identity, ir, target) {
            identity.clone()
        } else {
            hashed_layout(
                ir,
                target,
                options.routing_seed,
                trial,
                &source_hash,
                target_hash,
            )?
        };
        if options.initial_layout.is_none() {
            candidate = refine_layout(
                ir,
                target,
                candidate,
                trial,
                options.routing_seed,
                default_budget,
                2,
            )?;
        }
        candidates.push(candidate);
    }

    let mut results = Vec::new();
    for (trial, candidate) in candidates.into_iter().enumerate() {
        let mut result = route_trial(
            ir,
            target,
            candidate,
            trial,
            options.routing_seed,
            swap_budget,
            false,
        )?;
        result.routed_hash = hash_ir(&result.routed_ir)?;
        results.push(result);
    }
    let mut baseline = route_trial(
        ir,
        target,
        greedy,
        options.placement_trials,
        options.routing_seed,
        swap_budget,
        true,
    )?;
    baseline.routed_hash = hash_ir(&baseline.routed_ir)?;
    results.push(baseline);

    let winner_index = (0..results.len())
        .min_by(|left, right| compare_trials(&results[*left], &results[*right]))
        .expect("a baseline trial is always present");
    let winner = results[winner_index].clone();
    let (final_ir, routed_to_final_indices) = lower_to_target_basis(&winner.routed_ir, target)?;
    let trials = results
        .iter()
        .enumerate()
        .map(|(index, result)| RoutingTrial {
            trial: result.trial,
            seed: result.seed,
            initial_layout: result.initial_layout.clone(),
            final_layout: result.final_layout.clone(),
            inserted_swaps: result.inserted_swaps,
            routed_depth: result.routed_depth,
            two_qubit_depth: result.two_qubit_depth,
            selected: index == winner_index,
            baseline: result.baseline,
        })
        .collect();
    let measurement_map = ir
        .measurements
        .iter()
        .map(|measurement| {
            json!({
                "logical_qubit": measurement.qubit,
                "physical_qubit": winner.final_layout.logical_to_physical[measurement.qubit],
                "classical_bit": measurement.cbit,
            })
        })
        .collect();
    let trace = RoutingTrace {
        schema_version: ROUTING_TRACE_SCHEMA_VERSION,
        initial_layout: winner.initial_layout.clone(),
        final_layout: winner.final_layout.clone(),
        steps: winner.steps,
        trials,
        source_to_routed_indices: winner.source_to_routed_indices,
        routed_to_final_indices,
        measurement_map,
    };
    Ok(RoutingOutput {
        routed_ir: winner.routed_ir,
        final_ir,
        initial_layout: winner.initial_layout,
        final_layout: winner.final_layout,
        trace,
    })
}

fn compare_trials(left: &TrialResult, right: &TrialResult) -> Ordering {
    (
        left.inserted_swaps,
        left.two_qubit_depth,
        left.routed_depth,
        &left.routed_hash,
        left.trial,
    )
        .cmp(&(
            right.inserted_swaps,
            right.two_qubit_depth,
            right.routed_depth,
            &right.routed_hash,
            right.trial,
        ))
}

fn gate_arity(name: &str) -> Option<usize> {
    match name {
        "h" | "x" | "y" | "z" | "s" | "t" | "rx" | "ry" | "rz" => Some(1),
        "cx" | "cz" | "swap" => Some(2),
        _ => None,
    }
}

fn operation(name: &str, qubits: Vec<usize>, metadata: BTreeMap<String, Value>) -> Operation {
    Operation {
        name: name.to_owned(),
        qubits,
        params: Vec::new(),
        metadata,
    }
}

fn validate_routing_feasibility(ir: &CircuitIr, target: &Target) -> Result<(), String> {
    component_assignment_indices(ir, &target.topology)?;

    let basis = target.basis_gates();
    for operation in &ir.operations {
        if operation.qubits.len() > 2 {
            return Err("The O2 router supports only one- and two-qubit operations.".to_owned());
        }
        if operation.qubits.len() == 1 && !basis.contains(operation.name.as_str()) {
            return Err(format!(
                "Target cannot exactly lower single-qubit gate {:?}.",
                operation.name
            ));
        }
        if operation.qubits.len() == 2 && !matches!(operation.name.as_str(), "cx" | "cz" | "swap") {
            return Err(format!(
                "Target cannot route unsupported gate {:?}.",
                operation.name
            ));
        }
    }
    for &(left, right) in &target.topology.edges {
        if !can_lower_swap(target, left, right) {
            return Err(format!(
                "Target basis cannot implement an exact SWAP on topology edge ({left}, {right})."
            ));
        }
    }
    Ok(())
}

fn logical_components(ir: &CircuitIr) -> Vec<Vec<usize>> {
    let mut neighbors: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); ir.qubit_count];
    for operation in &ir.operations {
        if operation.qubits.len() == 2 {
            let left = operation.qubits[0];
            let right = operation.qubits[1];
            neighbors[left].insert(right);
            neighbors[right].insert(left);
        }
    }
    let mut remaining: BTreeSet<_> = (0..ir.qubit_count).collect();
    let mut components = Vec::new();
    while let Some(&start) = remaining.first() {
        let mut pending = vec![start];
        let mut found = BTreeSet::from([start]);
        while let Some(current) = pending.pop() {
            for &neighbor in &neighbors[current] {
                if found.insert(neighbor) {
                    pending.push(neighbor);
                }
            }
        }
        for item in &found {
            remaining.remove(item);
        }
        components.push(found.into_iter().collect::<Vec<_>>());
    }
    components.sort_by_key(|component| {
        (
            std::cmp::Reverse(component.len()),
            component.first().copied().unwrap_or(0),
        )
    });
    components
}

fn component_assignment_indices(ir: &CircuitIr, topology: &Topology) -> Result<Vec<usize>, String> {
    let logical = logical_components(ir);
    let physical = topology.components();
    let mut remaining: Vec<_> = physical.iter().map(Vec::len).collect();
    let mut assignments = vec![usize::MAX; logical.len()];
    let mut failed = BTreeSet::new();

    fn assign(
        index: usize,
        logical: &[Vec<usize>],
        physical: &[Vec<usize>],
        remaining: &mut [usize],
        assignments: &mut [usize],
        failed: &mut BTreeSet<(usize, Vec<usize>)>,
    ) -> bool {
        if index == logical.len() {
            return true;
        }
        let state = (index, remaining.to_vec());
        if failed.contains(&state) {
            return false;
        }

        let required = logical[index].len();
        let mut candidates: Vec<_> = remaining
            .iter()
            .enumerate()
            .filter(|(_, capacity)| **capacity >= required)
            .map(|(position, capacity)| {
                (
                    position,
                    *capacity - required,
                    physical[position].first().copied().unwrap_or(usize::MAX),
                )
            })
            .collect();
        candidates.sort_by_key(|(_, surplus, first)| (*surplus, *first));
        let mut seen_capacities = BTreeSet::new();
        for (position, _, _) in candidates {
            let capacity = remaining[position];
            if !seen_capacities.insert(capacity) {
                continue;
            }
            remaining[position] -= required;
            assignments[index] = position;
            if assign(index + 1, logical, physical, remaining, assignments, failed) {
                return true;
            }
            assignments[index] = usize::MAX;
            remaining[position] = capacity;
        }

        failed.insert(state);
        false
    }

    if !assign(
        0,
        &logical,
        &physical,
        &mut remaining,
        &mut assignments,
        &mut failed,
    ) {
        return Err(
            "Logical interaction components cannot fit the target's disconnected topology."
                .to_owned(),
        );
    }
    Ok(assignments)
}

fn component_assignments(ir: &CircuitIr, topology: &Topology) -> Result<Vec<Vec<usize>>, String> {
    let physical = topology.components();
    component_assignment_indices(ir, topology).map(|indices| {
        indices
            .into_iter()
            .map(|physical_index| physical[physical_index].clone())
            .collect()
    })
}

fn interaction_weights(ir: &CircuitIr) -> BTreeMap<(usize, usize), usize> {
    let mut weights = BTreeMap::new();
    for operation in &ir.operations {
        if operation.qubits.len() == 2 {
            let edge = (
                operation.qubits[0].min(operation.qubits[1]),
                operation.qubits[0].max(operation.qubits[1]),
            );
            *weights.entry(edge).or_insert(0) += 1;
        }
    }
    weights
}

fn interaction_greedy_layout(ir: &CircuitIr, target: &Target) -> Result<Layout, String> {
    let logical_components = logical_components(ir);
    let assignments = component_assignments(ir, &target.topology)?;
    let weights = interaction_weights(ir);
    let mut mapped = BTreeMap::new();
    let mut used = BTreeSet::new();

    for (component_index, component) in logical_components.iter().enumerate() {
        let allowed: BTreeSet<_> = assignments[component_index]
            .iter()
            .copied()
            .filter(|physical| !used.contains(physical))
            .collect();
        if allowed.len() < component.len() {
            return Err(
                "Logical interaction components cannot fit the target's disconnected topology."
                    .to_owned(),
            );
        }

        let weighted_degree = |logical: usize| -> usize {
            weights
                .iter()
                .filter(|(edge, _)| edge.0 == logical || edge.1 == logical)
                .map(|(_, weight)| *weight)
                .sum()
        };
        let distinct_neighbors = |logical: usize| -> usize {
            weights
                .keys()
                .filter(|edge| edge.0 == logical || edge.1 == logical)
                .count()
        };
        let seed = *component
            .iter()
            .max_by_key(|logical| {
                (
                    weighted_degree(**logical),
                    distinct_neighbors(**logical),
                    std::cmp::Reverse(**logical),
                )
            })
            .expect("logical components are non-empty");
        let eccentricity = |physical: usize| -> Result<usize, String> {
            allowed
                .iter()
                .map(|other| target.topology.distance(physical, *other))
                .collect::<Result<Vec<_>, _>>()
                .map(|distances| distances.into_iter().max().unwrap_or(0))
        };
        let mut seed_candidates = Vec::new();
        for physical in &allowed {
            seed_candidates.push((
                eccentricity(*physical)?,
                std::cmp::Reverse(target.topology.neighbors(*physical).len()),
                *physical,
            ));
        }
        let seed_physical = seed_candidates
            .into_iter()
            .min()
            .expect("allowed placement vertices are non-empty")
            .2;
        mapped.insert(seed, seed_physical);
        used.insert(seed_physical);

        while component
            .iter()
            .any(|logical| !mapped.contains_key(logical))
        {
            let weight_to_mapped = |logical: usize| -> usize {
                mapped
                    .keys()
                    .map(|other| {
                        weights
                            .get(&(logical.min(*other), logical.max(*other)))
                            .copied()
                            .unwrap_or(0)
                    })
                    .sum()
            };
            let logical = *component
                .iter()
                .filter(|logical| !mapped.contains_key(logical))
                .max_by_key(|logical| {
                    (
                        weight_to_mapped(**logical),
                        weighted_degree(**logical),
                        std::cmp::Reverse(**logical),
                    )
                })
                .expect("an unmapped logical vertex exists");
            let physical_candidates: Vec<_> = allowed
                .iter()
                .copied()
                .filter(|physical| !used.contains(physical))
                .collect();
            let mut costs = Vec::new();
            for physical in physical_candidates {
                let mut distance_cost = 0;
                for (other, mapped_physical) in &mapped {
                    if component.contains(other) {
                        distance_cost += weights
                            .get(&(logical.min(*other), logical.max(*other)))
                            .copied()
                            .unwrap_or(0)
                            * target.topology.distance(physical, *mapped_physical)?;
                    }
                }
                costs.push((
                    distance_cost,
                    eccentricity(physical)?,
                    std::cmp::Reverse(target.topology.neighbors(physical).len()),
                    physical,
                ));
            }
            let selected = costs
                .into_iter()
                .min()
                .expect("a physical placement vertex exists")
                .3;
            mapped.insert(logical, selected);
            used.insert(selected);
        }
    }

    Ok(Layout::new(
        (0..ir.qubit_count)
            .map(|logical| mapped[&logical])
            .collect(),
    ))
}

fn hashed_layout(
    ir: &CircuitIr,
    target: &Target,
    seed: u64,
    trial: usize,
    source_hash: &str,
    target_hash: &str,
) -> Result<Layout, String> {
    let logical_components = logical_components(ir);
    let assignments = component_assignments(ir, &target.topology)?;
    let mut used = BTreeSet::new();
    let mut mapped = BTreeMap::new();
    for (component_index, component) in logical_components.into_iter().enumerate() {
        let allowed: BTreeSet<_> = assignments[component_index]
            .iter()
            .copied()
            .filter(|physical| !used.contains(physical))
            .collect();
        if allowed.len() < component.len() {
            return Err("Hashed placement could not embed a logical component.".to_owned());
        }
        let mut selected: Vec<_> = allowed.into_iter().collect();
        selected.sort_by_key(|physical| {
            (
                sha256_hex(format!(
                    "{seed}:{trial}:{target_hash}:{source_hash}:{physical}"
                )),
                *physical,
            )
        });
        selected.truncate(component.len());
        let mut logical_order = component;
        logical_order.sort_by_key(|logical| {
            (
                sha256_hex(format!("{seed}:{trial}:logical:{logical}")),
                *logical,
            )
        });
        for (logical, physical) in logical_order.into_iter().zip(selected) {
            mapped.insert(logical, physical);
            used.insert(physical);
        }
    }
    Ok(Layout::new(
        (0..ir.qubit_count)
            .map(|logical| mapped[&logical])
            .collect(),
    ))
}

#[allow(clippy::too_many_arguments)]
fn refine_layout(
    ir: &CircuitIr,
    target: &Target,
    initial_layout: Layout,
    trial: usize,
    seed: u64,
    swap_budget: usize,
    rounds: usize,
) -> Result<Layout, String> {
    let mut reverse_ir = ir.clone();
    reverse_ir.operations.reverse();
    reverse_ir.measurements.clear();
    let mut layout = initial_layout;
    for _ in 0..rounds {
        let forward = route_trial(ir, target, layout, trial, seed, swap_budget, false)?;
        let reverse = route_trial(
            &reverse_ir,
            target,
            forward.final_layout,
            trial,
            seed,
            swap_budget,
            false,
        )?;
        layout = reverse.final_layout;
    }
    Ok(layout)
}

fn sha256_hex(value: String) -> String {
    format!("{:x}", Sha256::digest(value.as_bytes()))
}

fn layout_connects_components(layout: &Layout, ir: &CircuitIr, target: &Target) -> bool {
    if layout
        .validate(ir.qubit_count, target.topology.qubit_count)
        .is_err()
    {
        return false;
    }
    ir.operations.iter().all(|operation| {
        operation.qubits.len() != 2
            || target
                .topology
                .shortest_path(
                    layout.logical_to_physical[operation.qubits[0]],
                    layout.logical_to_physical[operation.qubits[1]],
                )
                .is_ok()
    })
}

fn dependency_data(ir: &CircuitIr) -> (Vec<usize>, Vec<Vec<usize>>) {
    let mut predecessors: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); ir.operations.len()];
    let mut successors = vec![Vec::new(); ir.operations.len()];
    let mut last_on_qubit = BTreeMap::new();
    for (index, operation) in ir.operations.iter().enumerate() {
        for qubit in &operation.qubits {
            if let Some(predecessor) = last_on_qubit.get(qubit) {
                predecessors[index].insert(*predecessor);
            }
            last_on_qubit.insert(*qubit, index);
        }
    }
    for (target, values) in predecessors.iter().enumerate() {
        for source in values {
            successors[*source].push(target);
        }
    }
    (predecessors.iter().map(BTreeSet::len).collect(), successors)
}

fn route_trial(
    ir: &CircuitIr,
    target: &Target,
    initial_layout: Layout,
    trial: usize,
    seed: u64,
    swap_budget: usize,
    baseline: bool,
) -> Result<TrialResult, String> {
    initial_layout.validate(ir.qubit_count, target.topology.qubit_count)?;
    let (mut indegree, successors) = dependency_data(ir);
    let mut pending: BTreeSet<_> = (0..ir.operations.len()).collect();
    let mut layout = initial_layout.clone();
    let mut routed = Vec::new();
    let mut steps = Vec::new();
    let mut source_to_routed = vec![Vec::new(); ir.operations.len()];
    let mut no_progress_swaps = 0;
    let mut layouts_since_progress = BTreeSet::from([layout.logical_to_physical.clone()]);
    let release_threshold = 4.max(2 * target.topology.diameter()?.max(1));

    while !pending.is_empty() {
        let front: Vec<_> = pending
            .iter()
            .copied()
            .filter(|index| indegree[*index] == 0)
            .collect();
        let executable: Vec<_> = front
            .iter()
            .copied()
            .filter(|index| {
                let operation = &ir.operations[*index];
                operation.qubits.len() < 2
                    || target.topology.has_weak_edge(
                        layout.logical_to_physical[operation.qubits[0]],
                        layout.logical_to_physical[operation.qubits[1]],
                    )
            })
            .collect();
        if !executable.is_empty() {
            for source_index in executable {
                let source = &ir.operations[source_index];
                let mut mapped = source.clone();
                mapped.qubits = source
                    .qubits
                    .iter()
                    .map(|logical| layout.logical_to_physical[*logical])
                    .collect();
                source_to_routed[source_index].push(routed.len());
                routed.push(mapped);
                pending.remove(&source_index);
                for successor in &successors[source_index] {
                    indegree[*successor] -= 1;
                }
            }
            no_progress_swaps = 0;
            layouts_since_progress = BTreeSet::from([layout.logical_to_physical.clone()]);
            continue;
        }

        let blocked: Vec<_> = front
            .iter()
            .copied()
            .filter(|index| ir.operations[*index].qubits.len() == 2)
            .collect();
        if blocked.is_empty() {
            return Err("Routing dependency graph made no progress.".to_owned());
        }
        if steps.len() >= swap_budget {
            return Err(format!(
                "Routing exceeded the {swap_budget}-SWAP budget before completing."
            ));
        }

        let force_release = baseline || no_progress_swaps >= release_threshold;
        let (mut edge, mut reason) = if force_release {
            let source_index = blocked[0];
            let source = &ir.operations[source_index];
            let path = target.topology.shortest_path(
                layout.logical_to_physical[source.qubits[0]],
                layout.logical_to_physical[source.qubits[1]],
            )?;
            (
                (path[0].min(path[1]), path[0].max(path[1])),
                if baseline {
                    "canonical-baseline"
                } else {
                    "release-valve"
                },
            )
        } else {
            let mut candidates = BTreeSet::new();
            for source_index in &blocked {
                for logical in &ir.operations[*source_index].qubits {
                    let physical = layout.logical_to_physical[*logical];
                    for neighbor in target.topology.neighbors(physical) {
                        let edge = (physical.min(neighbor), physical.max(neighbor));
                        if can_lower_swap(target, edge.0, edge.1) {
                            candidates.insert(edge);
                        }
                    }
                }
            }
            if candidates.is_empty() {
                return Err(
                    "No exact SWAP candidate can advance the blocked front layer.".to_owned(),
                );
            }
            let front_set: BTreeSet<_> = front.iter().copied().collect();
            let lookahead: Vec<_> = pending
                .iter()
                .copied()
                .filter(|index| {
                    !front_set.contains(index) && ir.operations[*index].qubits.len() == 2
                })
                .take(20)
                .collect();
            let mut scores = Vec::new();
            for edge in candidates {
                let candidate_layout = layout.swap_physical(edge.0, edge.1);
                let mut front_distance = 0;
                for index in &blocked {
                    let operation = &ir.operations[*index];
                    front_distance += target.topology.distance(
                        candidate_layout.logical_to_physical[operation.qubits[0]],
                        candidate_layout.logical_to_physical[operation.qubits[1]],
                    )?;
                }
                let mut lookahead_distance = 0;
                for index in &lookahead {
                    let operation = &ir.operations[*index];
                    lookahead_distance += target.topology.distance(
                        candidate_layout.logical_to_physical[operation.qubits[0]],
                        candidate_layout.logical_to_physical[operation.qubits[1]],
                    )?;
                }
                let newly_executable = blocked
                    .iter()
                    .filter(|index| {
                        let operation = &ir.operations[**index];
                        target.topology.has_weak_edge(
                            candidate_layout.logical_to_physical[operation.qubits[0]],
                            candidate_layout.logical_to_physical[operation.qubits[1]],
                        )
                    })
                    .count();
                scores.push((
                    2 * front_distance + lookahead_distance,
                    std::cmp::Reverse(newly_executable),
                    edge,
                ));
            }
            (
                scores
                    .into_iter()
                    .min()
                    .expect("routing candidates are non-empty")
                    .2,
                "heuristic",
            )
        };

        let before = layout.clone();
        let mut after = before.swap_physical(edge.0, edge.1);
        if !baseline && layouts_since_progress.contains(&after.logical_to_physical) {
            let source = &ir.operations[blocked[0]];
            let path = target.topology.shortest_path(
                layout.logical_to_physical[source.qubits[0]],
                layout.logical_to_physical[source.qubits[1]],
            )?;
            edge = (path[0].min(path[1]), path[0].max(path[1]));
            after = before.swap_physical(edge.0, edge.1);
            reason = "release-valve";
        }

        let step = RoutingStep {
            index: steps.len(),
            physical_edge: edge,
            trigger_source_indices: blocked,
            layout_before: before,
            layout_after: after.clone(),
            reason,
        };
        let metadata = BTreeMap::from([
            (
                "qplanck.inserted".to_owned(),
                Value::String("routing".to_owned()),
            ),
            (
                "routing_step".to_owned(),
                Value::from(u64::try_from(step.index).map_err(|_| "routing step overflow")?),
            ),
        ]);
        routed.push(operation("swap", vec![edge.0, edge.1], metadata));
        steps.push(step);
        layout = after;
        no_progress_swaps += 1;
        layouts_since_progress.insert(layout.logical_to_physical.clone());
    }

    let measurements = ir
        .measurements
        .iter()
        .map(|measurement| Measurement {
            qubit: layout.logical_to_physical[measurement.qubit],
            cbit: measurement.cbit,
            metadata: measurement.metadata.clone(),
        })
        .collect();
    let routed_ir = CircuitIr {
        schema_version: IR_SCHEMA_VERSION.to_owned(),
        qubit_count: target.topology.qubit_count,
        operations: routed,
        measurements,
        metadata: ir.metadata.clone(),
    };
    let inserted_swaps = steps.len();
    let routed_depth = depth(&routed_ir.operations);
    let two_qubit_operations: Vec<_> = routed_ir
        .operations
        .iter()
        .filter(|operation| operation.qubits.len() == 2)
        .cloned()
        .collect();
    Ok(TrialResult {
        trial,
        seed,
        initial_layout,
        final_layout: layout,
        routed_ir,
        steps,
        source_to_routed_indices: source_to_routed,
        inserted_swaps,
        routed_depth,
        two_qubit_depth: depth(&two_qubit_operations),
        baseline,
        routed_hash: String::new(),
    })
}

fn depth(operations: &[Operation]) -> usize {
    let mut qubit_depth = BTreeMap::new();
    let mut maximum = 0;
    for operation in operations {
        let operation_depth = 1 + operation
            .qubits
            .iter()
            .map(|qubit| qubit_depth.get(qubit).copied().unwrap_or(0))
            .max()
            .unwrap_or(0);
        for qubit in &operation.qubits {
            qubit_depth.insert(*qubit, operation_depth);
        }
        maximum = maximum.max(operation_depth);
    }
    maximum
}

fn can_apply_h(target: &Target, qubit: usize) -> bool {
    target.supports_operation(&operation("h", vec![qubit], BTreeMap::new()))
}

fn can_lower_cx(target: &Target, control: usize, target_qubit: usize) -> bool {
    if target.supports_operation(&operation(
        "cx",
        vec![control, target_qubit],
        BTreeMap::new(),
    )) {
        return true;
    }
    if target.supports_operation(&operation(
        "cx",
        vec![target_qubit, control],
        BTreeMap::new(),
    )) && can_apply_h(target, control)
        && can_apply_h(target, target_qubit)
    {
        return true;
    }
    target.supports_operation(&operation(
        "cz",
        vec![control, target_qubit],
        BTreeMap::new(),
    )) && can_apply_h(target, target_qubit)
}

fn can_lower_swap(target: &Target, left: usize, right: usize) -> bool {
    target.supports_operation(&operation("swap", vec![left, right], BTreeMap::new()))
        || (can_lower_cx(target, left, right) && can_lower_cx(target, right, left))
}

fn lower_cx(
    target: &Target,
    control: usize,
    target_qubit: usize,
    metadata: &BTreeMap<String, Value>,
) -> Result<Vec<Operation>, String> {
    let direct = operation("cx", vec![control, target_qubit], metadata.clone());
    if target.supports_operation(&direct) {
        return Ok(vec![direct]);
    }
    let reverse = operation("cx", vec![target_qubit, control], metadata.clone());
    if target.supports_operation(&reverse)
        && can_apply_h(target, control)
        && can_apply_h(target, target_qubit)
    {
        return Ok(vec![
            operation("h", vec![control], metadata.clone()),
            operation("h", vec![target_qubit], metadata.clone()),
            reverse,
            operation("h", vec![control], metadata.clone()),
            operation("h", vec![target_qubit], metadata.clone()),
        ]);
    }
    let cz = operation("cz", vec![control, target_qubit], metadata.clone());
    if target.supports_operation(&cz) && can_apply_h(target, target_qubit) {
        return Ok(vec![
            operation("h", vec![target_qubit], metadata.clone()),
            cz,
            operation("h", vec![target_qubit], metadata.clone()),
        ]);
    }
    Err(format!(
        "Target cannot exactly lower CX({control}, {target_qubit})."
    ))
}

fn lower_operation(source: &Operation, target: &Target) -> Result<Vec<Operation>, String> {
    if target.supports_operation(source) {
        return Ok(vec![source.clone()]);
    }
    match source.name.as_str() {
        "cx" => lower_cx(target, source.qubits[0], source.qubits[1], &source.metadata),
        "cz" if can_apply_h(target, source.qubits[1]) => {
            let right = source.qubits[1];
            let mut lowered = vec![operation("h", vec![right], source.metadata.clone())];
            lowered.extend(lower_cx(target, source.qubits[0], right, &source.metadata)?);
            lowered.push(operation("h", vec![right], source.metadata.clone()));
            Ok(lowered)
        }
        "swap" => {
            let left = source.qubits[0];
            let right = source.qubits[1];
            let mut lowered = lower_cx(target, left, right, &source.metadata)?;
            lowered.extend(lower_cx(target, right, left, &source.metadata)?);
            lowered.extend(lower_cx(target, left, right, &source.metadata)?);
            Ok(lowered)
        }
        _ => Err(format!(
            "Target basis cannot exactly lower operation {:?} on {:?}.",
            source.name, source.qubits
        )),
    }
}

fn lower_to_target_basis(
    routed_ir: &CircuitIr,
    target: &Target,
) -> Result<(CircuitIr, Vec<Vec<usize>>), String> {
    let mut operations = Vec::new();
    let mut mapping = Vec::new();
    for source in &routed_ir.operations {
        let start = operations.len();
        operations.extend(lower_operation(source, target)?);
        mapping.push((start..operations.len()).collect());
    }
    for operation in &operations {
        if !target.supports_operation(operation) {
            return Err(format!(
                "Native lowering emitted nonconforming {:?}{:?}.",
                operation.name, operation.qubits
            ));
        }
    }
    Ok((
        CircuitIr {
            schema_version: IR_SCHEMA_VERSION.to_owned(),
            qubit_count: routed_ir.qubit_count,
            operations,
            measurements: routed_ir.measurements.clone(),
            metadata: routed_ir.metadata.clone(),
        },
        mapping,
    ))
}

#[cfg(test)]
mod tests {
    use super::{Layout, Topology};

    #[test]
    fn shortest_path_uses_canonical_weak_neighbors() {
        let topology = Topology {
            schema_version: "qplanck.topology.v0.1".to_owned(),
            qubit_count: 3,
            directed: true,
            edges: vec![(0, 1), (2, 1)],
        };
        assert_eq!(topology.shortest_path(0, 2).unwrap(), vec![0, 1, 2]);
    }

    #[test]
    fn physical_swap_only_moves_mapped_logicals() {
        assert_eq!(
            Layout::new(vec![2, 0]).swap_physical(0, 1),
            Layout::new(vec![2, 1])
        );
    }
}
