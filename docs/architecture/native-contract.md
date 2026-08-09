# Native Core Contract

QCore `0.3.0a1` exposes one Rust library with a required PyO3 CPython binding.
The contract version is `qplanck.core.contract.v1`; the
CPython extension ABI is `qplanck.native.abi.v1`.

## Frozen alpha operations

| Operation | Request schema | Response schema | Rust-owned behavior |
|---|---|---|---|
| Compile | `qplanck.native.compile.request.v1` | `qplanck.native.compile.response.v1` | Static validation, O0/O1 rewrites, O2 placement/routing/basis lowering, hashes, metrics, pass evidence |
| Lower QIR | `qplanck.native.qir.request.v1` | `qplanck.native.qir.response.v1` | QIR 2.0 Base Profile text, QIS checks, measurement/source maps |
| Simulate | `qplanck.native.simulate.request.v1` | `qplanck.native.simulate.response.v1` | State evolution, probabilities, explicit measurement mapping, frozen seeded sampling, traces, resource preflight |

Requests and responses are UTF-8 JSON bytes. Unknown schema versions, compile
options, gates, targets, or QIR capabilities fail closed. A missing or
ABI-incompatible extension never invokes a Python numerical/compiler fallback.

## Circuit and identity compatibility

- `qplanck.ir.v0.1` remains the only accepted circuit schema and the public
  source representation. Existing v0.1 fixtures remain readable.
- Canonical IR JSON uses recursively sorted object keys and frozen one-line JSON
  separators. SHA-256 content identities cover those canonical bytes.
- Build identity, architecture, operating system, and binding metadata are
  observational and do not participate in semantic IR or compiled-artifact
  content hashes.
- `Target` is immutable input to O2 and is linked by its canonical content hash.
  Source, routed, and final IR plus layout/measurement provenance remain
  distinct artifacts.
- A compiled QIR manifest links source IR, compiled artifact, compiler trace,
  routing trace, target, and an embedded origin-to-routed-to-final-to-QIS call
  map. Compiler-inserted SWAP calls retain their routing-step origin.
- `CircuitIR` is the conceptual source/HIR layer without a public rename. The
  routed physical representation is internal and does not establish a public
  MIR. A future LIR will be a versioned `ExecutableBundle` envelope carrying a
  QIR, provider-native, or pulse payload rather than treating one format as
  universal.

## Resource and failure contract

- Contract requests are limited to 32 MiB. Circuit IR JSON is limited to 16 MiB,
  65,536 qubits/classical bits, one million operations, and one million
  measurements before expensive work.
- Simulation checks statevector bytes, peak execution bytes, serialized-result
  bytes, and trace width before allocation. Python defaults are 256 MiB peak
  execution, 64 MiB result payload, and eight trace qubits.
- Sampling uses `qplanck.splitmix64-cdf.v1`; a missing seed resolves to the
  documented stable zero seed. Explicit seeds and measurement mappings are
  recorded in the experiment manifest.
- Invalid contracts map to public validation errors, budget failures map to
  `ResourceLimitError`, unsupported semantics map to
  `UnsupportedOperationError`, and panics/internal errors fail as
  `NativeCompilerError` without exposing a fallback path.

## Binding and release status

The PyO3 wheel is the only supported binding. WebAssembly and browser runtimes
are unsupported. Labs must use a remote supported CPython kernel or remain
pinned to the final pure-Python 0.2 artifact.

Any v1 behavior change requires golden fixture review. An incompatible wire
change requires a new request/response schema and compatibility policy; changing
only the Rust implementation version is insufficient.
