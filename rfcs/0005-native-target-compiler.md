# RFC 0005: Required Native Target Compiler

- Status: **Accepted**
- Date: 2026-07-14
- Decision owner: QPlanck maintainer
- Supersedes: RFC 0002's native-code deferral only

## Summary

QCore 0.3 makes a Rust compiler and QIR kernel mandatory. The public SDK remains
Python, while validation, graph construction, exact local optimization,
placement, routing, target-basis lowering, bounded statevector simulation,
resource analysis, provenance, hashes, and QIR Base Profile emission execute in
Rust. PyO3 provides the required CPython binding over versioned byte contracts.

This decision does not rename the `qplanck` distribution or implementation
namespace. The repository and collision decisions in RFC 0002 remain in force.

## Native boundary

`qplanck` is a mixed Maturin package containing `qplanck._qplanck_native`.
Python calls the extension through versioned canonical JSON byte requests. Public
Python dataclasses reconstruct the native response and remain the stable user
contract. Missing or ABI-incompatible native code fails closed with
`NativeCompilerError`; production never falls back to the Python oracle.

The Python O0/O1 compiler and deterministic router remain test-only reference
implementations. They are retained to support differential correctness testing
and transparent algorithm review, not execution fallback.

## Target and routing contract

- `Topology` is an immutable directed or undirected physical graph.
- `Target` records topology, per-location instructions, explicit limits, provider
  identity, and snapshot identity under a canonical content hash.
- `Layout` is a complete injective logical-to-physical map.
- O2 performs O1 exact optimization, deterministic multi-trial placement and
  routing, abstract SWAP insertion, then exact target-basis lowering.
- Compiler-inserted SWAP changes the virtual layout. A user-authored SWAP is a
  semantic operation and does not alter compiler bookkeeping.
- Terminal measurements retain their classical bits and are moved to the final
  physical locations.
- `CompiledCircuit` records source, routed, and final IR; initial/final layouts;
  target identity; structural metrics; native implementation identity; and
  pass/routing provenance.

Deterministic ordering, SHA-256-derived trials, integer heuristic scores,
canonical tie-breaking, a shortest-path release valve, and an explicit SWAP
budget prevent platform- or CPU-count-dependent artifacts.

## QIR boundary

The native QIR kernel emits QIR 2.0 Base Profile LLVM text for the supported
static gate set. SWAP lowers to three CNOT calls with one source origin. A QIR
manifest links the module to compiler, target, routing, measurement, and source
map artifacts. QIR import, adaptive profiles, dynamic resource management, and
arbitrary target QIS remain deferred.

## Compatibility and packaging

The native requirement intentionally ends universal `py3-none-any` and Pyodide
support. Supported wheels are CPython 3.11-3.14 on tested 64-bit Linux, macOS,
and Windows targets. Source builds require the pinned Rust toolchain.
Free-threaded CPython, PyPy, GraalPy, and Windows ARM64 remain unsupported.

WebAssembly and browser runtimes are unsupported. Labs must use a remote
supported CPython kernel or remain pinned to the final pure-Python 0.2 artifact.

## Evidence gates

Native publication requires zero reference-semantic drift, at least 2x median
speedup at 100,000 operations, at least 1.5x geometric-mean speedup over the
10,000/100,000-operation workloads, no small-case regression above 10%, and peak
RSS no greater than 1.25x the reference.

A named competitive win is independent of feature acceptance. It requires a
published pinned corpus where the runtime ratio is below 0.8, added two-qubit
gate ratio is at most 1.05, the 95% bootstrap interval excludes parity, and the
competitor has no correctness or timeout advantage. Otherwise QCore publishes
neutral results.

## Consequences

- Maintainers own Rust, PyO3, Maturin, cross-platform wheels, security review,
  and differential tests.
- Native implementation identity is observational and excluded from semantic IR
  hashes.
- A feature-complete compiler does not imply a blanket performance claim.
