# Changelog

All notable user-facing changes are recorded here. QCore uses pre-release
semantic versions while public contracts are still evolving.

## 0.2.0a1 - Unreleased

### Added

- Deterministic graph-based reference compiler with O0/O1 pipelines, exact local
  rewrites, dependency depth, resource metrics, hashes, and pass provenance.
- QIR 2.0 Base Profile LLVM text exporter with QIS/resource capability checks,
  measurement mapping, and source-call manifest.
- Provider-neutral pulse schedule, target, waveform, channel, acquisition, and
  calibration library contracts with canonical JSON.
- `ConversionResult`, `LossReport`, and evidence-bearing OpenQASM, Qiskit, and QIR
  export methods.
- PEP 561 `py.typed` marker.
- Tested Python 3.14 support in addition to Python 3.11-3.13.
- Trusted-publishing workflow for TestPyPI rehearsals and GitHub-release PyPI
  publication.

### Corrected

- Seeded sampling now applies explicit qubit-to-classical-bit measurement
  mappings and reports the result-key convention.
- The NumPy statevector simulator checks its allocation against a configurable
  byte limit before allocating memory.
- Numeric IR parameters reject NaN and infinity.
- Distribution metadata uses SPDX licensing and the canonical GitHub project
  URLs.

### Capability limits

- The compiler remains pure Python and performs no placement, routing, SWAP
  insertion, target-basis synthesis, scheduling, or native acceleration.
- QIR support is export-only for the static Base Profile subset; no adaptive
  lowering, QIR import, bundled bitcode toolchain, runtime, or provider execution
  is included.
- Pulse support is QCore's local hardware-neutral schema, not OpenPulse source
  conformance or a provider hardware driver.
- No comparative performance claim is made without a published
  equivalent-semantics benchmark.
