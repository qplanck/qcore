# Changelog

All notable user-facing changes are recorded here. QCore uses pre-release
semantic versions while public contracts are still evolving.

## 0.3.0a1 - Unreleased

### Added

- Required Maturin/PyO3 Rust graph compiler with deterministic O0/O1 pipelines,
  exact local rewrites, dependency depth, metrics, hashes, and provenance.
- Deterministic O2 placement, topology routing, compiler-inserted SWAP evidence,
  exact target-basis lowering, layout tracking, and measurement remapping.
- Versioned topology, target, layout, and routing artifacts.
- Semantic `swap` support across circuits, simulation, QASM, Qiskit conversion,
  native optimization, and QIR lowering.
- QIR 2.0 Base Profile LLVM text exporter with QIS/resource capability checks,
  measurement mapping, and source-call manifest.
- Provider-neutral pulse schedule, target, waveform, channel, acquisition, and
  calibration library contracts with canonical JSON.
- Provider-neutral backend, job, status, execution options, experiment manifest,
  local simulator, mock backend, and calibrated-circuit contracts.
- Required Rust statevector evolution, explicit measurement mapping, frozen
  SplitMix64 sampling, trace generation, and peak-memory/result preflight.
- Versioned Rust contract entry points behind the required CPython extension
  for compile, QIR lowering, and bounded simulation.
- Separate experimental `qplanck-braket 0.1.0a1` adapter with immutable device
  snapshots, explicit channel maps, offline pulse lowering, and task wrappers.
- Offline adaptive-planning research kernel with versioned `Program`, `Objective`,
  candidate, `Plan`, metrics, explanation, and secret-free manifest contracts;
  deterministic native portfolios; optional multi-level Qiskit strategies; and
  offline IBM BackendV2-like target normalization.
- Versioned planner vertical-slice benchmark artifacts and a master-specification
  conformance matrix that keeps the complete v0.1 go/no-go decision gated.
- `ConversionResult`, `LossReport`, and evidence-bearing OpenQASM, Qiskit, and QIR
  export methods.
- PEP 561 `py.typed` marker.
- Tested Python 3.14 support in addition to Python 3.11-3.13.
- Maturin wheel/sdist release checks and trusted-publishing workflows for
  TestPyPI rehearsals and GitHub-release PyPI publication.

### Corrected

- Seeded sampling now applies explicit qubit-to-classical-bit measurement
  mappings and reports the result-key convention.
- The statevector simulator checks peak execution and serialized-result budgets
  before allocating the Rust statevector or materializing result payloads.
- Numeric IR parameters reject NaN and infinity.
- Distribution metadata uses SPDX licensing and the canonical GitHub project
  URLs.

### Capability limits

- The Python distribution requires a native CPython extension; Pyodide, PyPy,
  free-threaded Python, exported WebAssembly bindings, and source installs
  without Rust are unsupported. The Python-independent core target is
  build-checked but has no JavaScript/npm surface.
- QIR support is export-only for the static Base Profile subset; no adaptive
  lowering, QIR import, bundled bitcode toolchain, runtime, or provider execution
  is included.
- Pulse support is QCore's hardware-neutral schema, not universal OpenPulse
  conformance. Braket `Acquire` and provider-independent pulse execution remain
  outside the supported adapter subset.
- No Braket hardware-execution claim is made until the protected, single-task
  live smoke succeeds.
- No comparative performance claim is made without a published
  equivalent-semantics benchmark.
- The single synthetic planner fixture is narrow offline research evidence, not
  the complete QCore v0.1 gate. Fair equal-budget baselines, a held-out corpus,
  replay/correctness floors, statistical reporting, and independent review are
  still required.

## 0.2.0a1

The final pure-Python alpha line. It remains the compatibility option for
browser/Pyodide experiments and does not contain native routing or provider
execution.
