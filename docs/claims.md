# Verified Claims and Release Gates

This page is rendered from the policy represented by `docs/claims.json`. A code
path may exist before its public claim is allowed. Documentation and release
review must use the wording and evidence state below.

| Capability | Current evidence state | Allowed public wording / gate |
|---|---|---|
| Offline planner vertical slice | Offline verified | QCore has an offline, explainable planning research-kernel vertical slice. One versioned synthetic fixture showed an improvement under its declared proxy; a separate public 15-pair development cohort passed 255 declared exact-small candidate checks and 45 offline compiler-reexecution replays, with mixed results against the stronger same-attempt Qiskit baseline. Neither result is the master-specification v0.1 gate. |
| Master-spec v0.1 Go decision | Gated | No product-level v0.1 Go claim until fair equal-budget baselines, a locked held-out cohort, correctness and replay floors, complete reporting, falsification tests, and independent review pass. |
| Required Rust compiler/QIR kernel | Implementation in progress | Claim only after native differential, speed, wheel, and release checks pass. |
| Target-aware routing | Implementation in progress | Claim only after routing invariants and native parity pass. |
| Braket pulse lowering | Offline verified | QCore may describe the supported lowering subset and fixture evidence. |
| Braket hardware execution | Gated | No execution claim until the protected paid smoke succeeds. |
| Competitive performance | Gated | No named win until the published statistical and quality thresholds pass. |
| Browser/Pyodide | Unsupported in 0.3 | QCore does not support Pyodide or WebAssembly and has no JavaScript binding, npm artifact, or browser runtime. |

Prohibited release wording includes unqualified statements that QCore “beats
Qiskit”, “beats all quantum SDKs”, provides universal QIR, or executes arbitrary
provider-neutral pulse acquisition. The narrow planner fixture must not be
described as the complete v0.1 go/no-go experiment.
