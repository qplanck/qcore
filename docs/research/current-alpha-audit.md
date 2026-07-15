# Current Alpha Audit

**Historical note:** this source audit describes the Phase 0 implementation
baseline, not the current `0.2.0a1` tree. See the
[SDK standards contract](../sdk-standards.md) for the implemented compiler, QIR,
pulse, and loss-report boundaries.

> Baseline: commit `2f2ed07`  
> Audit date: 2026-07-14  
> Production code changes in Phase 0: none

## Reproduced baseline

**Verified:** An isolated Python 3.13 environment was created in
`/tmp/qcore-phase0-venv` and installed with `.[dev,qiskit]`. The resolved key
versions were Python 3.13.12, NumPy 2.4.6, Qiskit 2.5.0, pytest 9.1.1, Ruff
0.15.21, and mypy 2.3.0.

| Check | Result |
|---|---|
| `ruff check .` | Passed |
| `ruff format --check .` | Passed; 19 files already formatted |
| `mypy src/qplanck` | Passed; 11 source files |
| `pytest --cov` | Passed; 25 tests, 80% total line coverage |
| Optional Qiskit tests | Passed; 2 tests executed |

**Verified:** The only pre-existing untracked worktree item was `.coverage 2`.
This audit did not modify or remove it.

## Architecture at the baseline

**Verified:** The distribution, import namespace, and CLI are all `qplanck`; QCore
is the product brand. The package requires Python 3.11+ and NumPy, with Qiskit as
an optional extra. The implemented path is:

```text
Circuit builder -> frozen CircuitIR -> NumPy simulator -> RunResult/ExecutionTrace
        |                  |
        +-> ASCII          +-> deterministic JSON
        +-> OpenQASM 3 subset
        +-> Qiskit subset
```

**Verified:** Internal basis indexing is little-endian and public bit strings use
`q[n-1]...q[0]`. Gates after a terminal measurement are rejected. Traces default
to at most eight qubits.

## Public API disposition

The table classifies every symbol exported by `qplanck.__all__` and every current
public command. `Retain` means preserve through v0.x; `Evolve` means extend behind
compatible behavior; `Deprecate` requires a future RFC and warning period;
`Investigate` blocks a stable semantic promise.

| Public surface | Current contract | Disposition | Reason / next action |
|---|---|---|---|
| `Circuit` | Mutable fluent builder over immutable `CircuitIR` | **Retain** | It is approachable and already anchors all interop. Add `compile()` compatibly after RFC acceptance. |
| `Circuit.h/x/y/z/s/t/rx/ry/rz/cx/cz` | Numeric static gate subset | **Retain** | Stable teaching/reference subset; test gate semantics against independent matrices. |
| `Circuit.measure/measure_all` | Terminal measurement declarations | **Investigate** | Clarify classical-bit mapping, duplicate mapping, partial measurement, and whether sampling requires declared measurements. |
| `Circuit.add` | Adds validated `Operation` | **Retain** | Necessary low-level extension point; future diagnostics should identify operation/source. |
| `Circuit.draw` | ASCII only | **Evolve** | Preserve ASCII; move future renderers to plugins. |
| `Circuit.trace` | Returns last execution trace attached to this instance | **Evolve** | Keep behavior but separate `CompilationTrace` from `ExecutionTrace`. |
| `Circuit.to/from_json` | CircuitIR JSON round trip | **Retain** | Add formal schema validation and migration policy before calling it stable. |
| `Circuit.to/from_qasm3` | Hand-parsed v0.1 subset | **Retain** | Preserve subset; add input limits and clearer unsupported-syntax diagnostics. |
| `Circuit.to/from_qiskit` | Optional subset adapter | **Retain** | Keep optional and version-tested; provider behavior stays out of core. |
| `Circuit.copy`, properties | Copy and immutable tuple views | **Retain** | Straightforward compatibility surface. |
| `CircuitIR` | Frozen dataclass with schema version and JSON | **Evolve** | Add node IDs, source spans, provenance references, feature declarations, and migration hooks. |
| `Operation` | Frozen name/qubits/params/metadata node | **Evolve** | Add stable operation identity and typed attributes without making a universal instruction bag. |
| `MeasurementSpec` | Qubit-to-classical-bit mapping | **Investigate** | Runtime currently does not project counts through this mapping. Define semantics before Phase 1. |
| `Parameter` | Named immutable parameter serializes in IR | **Investigate** | Circuit builders and simulator intentionally require numeric parameters; decide bind-time model in Phase 2. |
| `Simulator` | `statevector` facade with `run`, `statevector`, `probabilities` | **Retain** | Preserve throughout v0.x as a compatibility wrapper over future `LocalSimulator`. |
| `RunResult` | Counts, probabilities, samples, metadata, optional trace | **Evolve** | Add typed experiment identity and diagnostics while retaining fields. |
| `StatevectorResult` | Tuple of complex amplitudes plus metadata | **Retain** | Define normalization/tolerance and serialization contract. |
| `ProbabilityResult` | Basis-key mapping plus metadata | **Retain** | Preserve ordering convention and numerical tolerance. |
| `ExecutionTrace` | Circuit, state snapshots, probabilities, metadata | **Evolve** | Version separately, add resource estimates and stable operation IDs; keep payload guard. |
| `gates` and `H/X/Y/Z/S/T/RX/RY/RZ/CX/CZ` | Constructors returning `Operation` | **Retain** | Useful typed low-level API; document parameter order consistently. |
| Error classes | `QPlanckError`, `CircuitError`, `UnsupportedOperationError`, `QASMError`, `InteropError` | **Evolve** | Keep inheritance; add stable diagnostic code, path/span, context, and remediation fields. |
| `qplanck doctor` | Version/dependency/smoke trace output | **Evolve** | Add distribution ownership detection before a future `qcore` facade and machine-readable mode. |
| `qplanck draw` | Draw IR JSON or QASM file | **Retain** | Preserve; add explicit format/error diagnostics later. |
| `qplanck trace` | Emit execution trace JSON | **Retain** | Preserve; add manifest linkage and atomic output handling. |

**Decision:** No current public API is marked for immediate deprecation.

## Behavioral findings and risks

| Severity | Evidence | Classification | Phase 1 action |
|---|---|---|---|
| High | `Simulator.run` samples the entire statevector and formats every qubit; it does not apply `MeasurementSpec` classical mappings. | **Verified** semantic gap | Specify measurement/result semantics and add conformance tests before runtime extraction. |
| High | State allocation is `2 ** qubit_count` complex128 values; non-trace runs have no qubit or memory budget. | **Verified** denial-of-service risk | Estimate bytes before allocation and enforce configurable execution limits. |
| Medium | Trace protection defaults to eight qubits, but callers can raise the limit without a byte estimate. | **Verified** payload risk | Use explicit trace budget and truncation/rejection diagnostics. |
| Medium | IR dataclasses are frozen, but nested values inside metadata are not recursively immutable or schema-validated. | **Verified** contract risk | Restrict metadata to validated JSON values and deep-freeze canonical structures. |
| Medium | The QASM subset parser splits statements and evaluates a restricted Python AST for numeric expressions. | **Verified** parser boundary | Add byte/token/depth limits, fuzz tests, and a published grammar subset; evaluate an official parser adapter. |
| Medium | `shots=0` is accepted and returns empty counts/samples. | **Verified** ambiguous edge case | Decide and document whether zero shots is a valid dry run. |
| Medium | Qiskit numeric parameter conversion and external API shape depend on optional versions wider than the tested floor. | **Verified** compatibility risk | Establish tested version ranges and wrap conversion failures in coded diagnostics. |
| Low | Golden behavior is asserted in tests but committed external fixture files are absent. | **Verified** test-structure gap | Add canonical schema fixtures once schemas are accepted. |
| Low | Package metadata defines an empty `qasm` extra. | **Verified** packaging ambiguity | Remove or populate only in a future packaging RFC; no Phase 0 change. |

## Testing gaps

- **Verified:** Existing tests cover IR round trips and immutability, circuit
  validation, basic gates, Bell/GHZ/rotations, sampling reproducibility, trace
  limits, QASM/Qiskit subsets, CLI smoke tests, and examples.
- **Open Question:** Differential tests have not yet established all gate matrices,
  qubit ordering, or randomized circuit equivalence against two independent
  implementations.
- **Open Question:** No fuzzing currently covers malformed QASM/JSON, extreme
  nesting, NaN/infinite values, or oversized circuits.
- **Open Question:** No benchmark baseline records parsing, construction,
  compilation, simulation, memory, or serialization costs.
- **Open Question:** Windows/macOS/Linux CI exists, but this audit reproduced the
  baseline only on the local macOS host.

## Audit conclusion

**Inference:** The alpha is a coherent vertical slice, not disposable scaffolding.
Phase 1 should preserve its public experience while inserting explicit compiler,
runtime, diagnostic, and manifest contracts beneath it. The measurement and
resource-limit findings are release blockers for any claim of stable execution
semantics.
