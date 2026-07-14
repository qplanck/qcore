# Quantum Software Ecosystem Audit

> Status: Phase 0 research baseline  
> Evidence cut-off: 2026-07-14

## Method and scope

**Verified:** This audit covers every framework, standard, simulator, runtime,
control stack, and browser-lab model named in the QCore master prompt. Primary
sources are indexed in the [source register](source-register.md). A snapshot date
means the official documentation or repository was inspected on that date; it
does not imply a release was made that day.

**Inference:** The comparison asks what QCore should learn, integrate, defer, or
avoid. It is not a feature-count ranking. Performance is not compared because no
common pinned benchmark and correctness protocol has yet been run.

## SDKs, compilers, and runtimes

Each row's ecosystem description is **Verified**. The final QCore implication is
an **Inference** unless marked otherwise.

| System | Version/date, stack, license | Purpose and architecture | Strengths | Limitations relevant to QCore | QCore implication |
|---|---|---|---|---|---|
| [qBraid SDK](https://docs.qbraid.com/v2/sdk/user-guide/overview) | SDK v2 docs; Python; Apache-2.0; accessed 2026-07-14 | Vendor-neutral program conversion uses a directed graph; runtime abstractions cover providers, devices, jobs, and results. | Broad interoperability and a coherent provider-facing SDK. | Conversion breadth and provider maintenance are large continuing commitments; transformation explainability is not its primary product wedge. | Integrate selected formats; do not recreate its conversion graph or provider catalogue. |
| [qBraid Lab](https://docs.qbraid.com/v2/lab/user-guide/overview) | Current docs; managed web platform; accessed 2026-07-14 | Browser IDE with preconfigured environments, notebooks, terminals, Git integration, and compute/QPU access. | Low setup cost and a substantial hosted workflow. | Hosted environments require operations, isolation, quotas, support, and cost control. | Start with a static local-in-browser lab, not managed containers. |
| [Qiskit](https://qiskit.qotlabs.org/docs/api/qiskit/transpiler) | Installed adapter baseline 2.5.0; Python/Rust components; Apache-2.0 | `QuantumCircuit` lowers through staged pass managers over `DAGCircuit`; stages and plugins support target-aware translation, routing, optimization, and scheduling. | Mature circuit model, hardware-aware compiler, extensive IBM ecosystem. | Large API surface and IBM-shaped workflows raise integration and compatibility cost. | Keep a narrow adapter; learn from staged passes and target models; do not copy the surface wholesale. |
| [Qiskit Runtime](https://quantum.cloud.ibm.com/docs/en/guides/qiskit-runtime-primitives) | Service docs accessed 2026-07-14; proprietary cloud service with open client components | Sampler/Estimator primitives and job, batch, and session execution modes normalize IBM hardware workflows. | Production job lifecycle, resilience options, and workload-oriented primitives. | Cloud semantics, account policy, and provider evolution are outside a local core contract. | Model jobs and capabilities generically; defer the IBM adapter and preserve provider-specific options. |
| [Qiskit Aer](https://qiskit.github.io/qiskit-aer/) | 0.17.1 docs; C++/Python; Apache-2.0 | High-performance simulation supports statevector, density matrix, stabilizer, matrix-product-state, unitary, superoperator, noise, MPI, and GPU modes. | Broad simulation and noise coverage with optimized native kernels. | Heavy native/GPU distribution and many method-specific semantics. | Use as an optional differential-test and external backend; keep QCore's NumPy engine as the small reference oracle. |
| [Cirq](https://quantumai.google/cirq/start/basics) | Current docs; Python; Apache-2.0; accessed 2026-07-14 | Circuits are ordered moments of operations; devices validate supported operations; `simulate` exposes state while `run` samples measurements. | Clear near-term hardware abstractions, protocols, sweeps, and testable simulator split. | Its abstractions and provider support are Google-ecosystem shaped; exact simulation scales exponentially. | Adopt the explicit simulate/run distinction and capability validation; provide a selective adapter. |
| [Cirq Google](https://quantumai.google/cirq/google/specification) | Current docs; Python/protobuf; Apache-2.0; accessed 2026-07-14 | Serializable device specifications describe gate sets, targets, and validation constraints for Google processors. | Concrete example of machine-readable target capabilities. | A provider schema is not a universal backend contract. | Inform `Target`, while retaining escape hatches and provider namespaces. |
| [TKET / pytket](https://docs.quantinuum.com/tket/) | Current docs; C++ core/Python API; Apache-2.0; accessed 2026-07-14 | Predicate-driven, compositional compilation passes transform circuits; provider backends live in separate extension packages. | Strong compilation, routing, rebasing, and disciplined adapter separation. | Advanced internals and extension ecosystem create a steep compatibility surface. | Emulate pass contracts and out-of-core providers; consider an adapter rather than reimplementing mature synthesis. |
| [PennyLane](https://docs.pennylane.ai/en/stable/development/guide/architecture.html) | Stable docs; Python; Apache-2.0; accessed 2026-07-14 | QNodes capture quantum tapes, preprocess through transforms, execute on device plugins, and integrate with autodiff frameworks. | Differentiable hybrid programming and broad device/plugin ecosystem. | Differentiation and ML framework integration add semantics QCore does not need for its first wedge. | Defer native autodiff; support future interchange at circuit/observable boundaries. |
| [Catalyst](https://docs.pennylane.ai/projects/catalyst/en/latest/dev/architecture.html) | Development docs around 0.16; Python/C++/MLIR; Apache-2.0; accessed 2026-07-14 | JAX capture lowers through quantum MLIR dialects to LLVM/QIR and a native runtime, including structured control flow. | Concrete multi-level compiler, ahead-of-time compilation, and pluginable dialect pipeline. | Experimental status and MLIR infrastructure are disproportionate for static-circuit Phase 1. | Treat as evidence that MLIR becomes useful with kernels and control flow; defer a QCore dialect. |
| [CUDA-Q](https://nvidia.github.io/cuda-quantum/latest/index.html) | Current docs; C++/Python/MLIR; Apache-2.0; accessed 2026-07-14 | Quantum kernels compile through the Quake MLIR dialect to heterogeneous CPU, GPU, simulator, and QPU targets. | Integrated kernel language, native compilation, and accelerated backends. | Hardware and GPU breadth require native toolchains and substantial platform support. | Consider a future QIR or adapter boundary; do not compete on GPU kernels in Phase 1. |
| [Amazon Braket SDK](https://docs.aws.amazon.com/braket/latest/developerguide/braket-how-it-works.html) | Service docs accessed 2026-07-14; Python SDK Apache-2.0; managed AWS service | Quantum tasks target local simulators, managed simulators, or QPUs; results and task metadata use AWS services such as S3. Hybrid Jobs manage classical/quantum workloads. | Unified AWS job model and multiple providers behind one service. | Requires AWS identity, storage, service semantics, and cost management. | Defer adapter; use its task metadata and local/managed distinction as runtime design input. |
| [Azure Quantum](https://learn.microsoft.com/en-us/azure/quantum/overview-azure-quantum) | Service docs accessed 2026-07-14; managed Azure service | Workspaces expose provider targets, jobs, results, and QIR target profiles. | Multiple providers and explicit capability profiles. | Workspace, identity, region, and provider constraints belong outside core. | Keep Azure integration in a separately versioned adapter. |
| [Microsoft QDK and Q#](https://github.com/microsoft/qsharp) | Modern repository observed 2026-07-14; Rust/Wasm/TypeScript interfaces; MIT | Q# is a purpose-built quantum language; the modern QDK includes compiler, simulator, resource estimator, notebooks, and browser-capable Wasm. | Language-level quantum semantics, resource estimation, and browser deployment. | Adopting another source language or runtime would dilute QCore's initial circuit wedge. | Learn from Wasm delivery and diagnostics; consider QIR exchange rather than Q# reimplementation. |
| [Classiq](https://docs.classiq.io/) | 1.4.1 release dated 2026-03-04; Python/Qmod with commercial services; platform terms apply | High-level functional models and constraints are synthesized into target circuits, then executed through provider integrations. | Raises abstraction above gates and applies constraint-driven synthesis. | Synthesis service and platform are not an open local compiler foundation; exact licensing varies by component/service. | Do not pursue high-level synthesis initially; keep the future programming model open to generated circuits. |
| [Pulser](https://github.com/pasqal-io/Pulser) | 1.8.0, 2026-05-04; Python; Apache-2.0 | Neutral-atom experiments bind registers to devices and schedule pulses on constrained channels; simulation is an extension using QuTiP. | Device-faithful analog and pulse-level model. | Not a gate-circuit general-purpose runtime; device physics and timing are specialized. | Keep pulse and analog programs outside CircuitIR; integrate later through a distinct program type. |
| [Strawberry Fields](https://strawberryfields.readthedocs.io/en/latest/introduction/circuits.html) | Latest docs accessed 2026-07-14; Python; Apache-2.0 | Photonic continuous-variable programs execute through Fock, Gaussian, Bosonic, and TensorFlow backends. | Rich photonic model and backend specialization. | Qubit circuit assumptions do not preserve continuous-variable semantics; cloud service availability has changed. | Do not force photonics into the initial qubit IR; add a future program-kind boundary before any adapter. |
| [ProjectQ](https://github.com/ProjectQ-Framework/ProjectQ) | 0.8.0, 2022-10-18; Python/C++; Apache-2.0 | A `MainEngine` sends commands through compiler engines to simulators or provider backends. | Historically clear streaming compiler-engine pipeline and resource estimation. | Latest listed release is old relative to this audit; provider integrations may not reflect current APIs. | Study the command pipeline, but do not choose it as a primary dependency. |
| [QuTiP](https://qutip.readthedocs.io/en/qutip-5.0.x/guide/guide-overview.html) | 5.0.x guide plus current roadmap; Python/Cython; BSD-3-Clause | Numerical framework for closed and open quantum-system dynamics, master equations, stochastic solvers, and control. | Mature physics solvers beyond gate circuits. | Different abstraction, numerical workload, and result model from circuit execution. | Integrate for future Hamiltonian/pulse simulation; do not recreate its solvers. |
| [OpenFermion](https://quantumai.google/openfermion/tutorials/intro_to_openfermion) | Current docs; Python; Apache-2.0; accessed 2026-07-14 | Represents fermionic/qubit operators and transforms them through Jordan-Wigner, Bravyi-Kitaev, and related mappings. | Established quantum-chemistry operator tooling. | Not a circuit compiler/runtime and carries domain-specific dependencies. | Prefer adapter-compatible observables over native chemistry tooling in early phases. |
| [Mitiq](https://github.com/unitaryfoundation/mitiq) | 1.0.0, 2026-03-25; Python; GPL-3.0 | Error-mitigation functions transform circuits and invoke user-supplied executors across supported frontends. | Backend-agnostic executor pattern and broad mitigation techniques. | GPL-3.0 compatibility and technique-specific statistical assumptions need legal/technical review. | Learn from executor injection; defer integration and avoid copying mitigation algorithms into core. |
| [PyZX](https://github.com/zxcalc/pyzx) | 0.10.4, 2026-07-01; Python; Apache-2.0 | Circuits convert to ZX graphs, simplify through rewrite rules, and extract optimized circuits. | Explainable algebraic rewriting, equivalence workflows, and visualization. | Extraction and supported fragments have constraints; it is not a complete hardware runtime. | Strong candidate for an optional optimization/teaching plugin with provenance around every conversion. |

## Standards and compiler infrastructure

| Standard or project | Version/date and license | Verified role | Principal boundary | QCore decision |
|---|---|---|---|---|
| [OpenQASM 2](https://github.com/openqasm/openqasm/tree/OpenQASM2.x) | 2.x specification; Apache-2.0 repository; accessed 2026-07-14 | Assembly-like circuit interchange widely supported by established SDKs. | Limited classical types/control compared with OpenQASM 3. | Import for compatibility when demand is demonstrated; export only when lossless for the selected subset. |
| [OpenQASM 3](https://openqasm.com/versions/3.0/language/index.html) | 3.0 specification; CC BY 4.0 text; accessed 2026-07-14 | Imperative quantum/classical language with timing, calibration hooks, subroutines, loops, and feed-forward. The specification does not define a complete execution environment. | A language AST alone does not provide QCore provenance, runtime metadata, or stable in-memory contracts. | Use as the primary exchange language, not as QCore's sole internal IR. |
| [QIR](https://github.com/qir-alliance/qir-spec) | Alliance specification; LLVM ecosystem licensing; accessed 2026-07-14 | Quantum programs represented in LLVM IR with profiles that constrain runtime calls and capabilities. | Low-level representation is not ergonomic for circuit editing or source-level trace visualization. | Future lowering target after dynamic control or external runtime demand exists. |
| [LLVM IR](https://llvm.org/docs/LangRef.html) | Current language reference; Apache-2.0 with LLVM exceptions | Typed low-level compiler IR with mature optimization and code-generation infrastructure. | Circuit topology and quantum source provenance require additional conventions. | Consume through QIR/tooling if needed; do not lower static circuits to LLVM in Phase 1. |
| [MLIR](https://mlir.llvm.org/docs/Dialects/) | Current docs; Apache-2.0 with LLVM exceptions | Extensible dialects, pass management, analysis preservation, and progressive lowering. | Adds native build, dialect design, verification, and long-term compatibility obligations. | Defer until structured control flow or multi-level lowering produces measurable need. |
| [Catalyst quantum dialects](https://docs.pennylane.ai/projects/catalyst/en/stable/dev/dialects.html) | Docs accessed 2026-07-14 | Multi-dialect lowering for hybrid quantum programs. | Coupled to Catalyst/JAX/PennyLane semantics. | Reference design, not a dependency. |
| [CUDA-Q Quake](https://nvidia.github.io/cuda-quantum/latest/specification/index.html) | Docs accessed 2026-07-14 | MLIR quantum kernel representation and lowering stack. | Coupled to CUDA-Q's kernel/runtime architecture. | Future interop research only. |

**Inference:** A small, versioned custom CircuitIR is justified because QCore needs
stable source mapping, validation, trace identities, and transformation provenance
before it needs full language semantics. The custom layer must remain narrow and
must not claim to be a new ecosystem standard.

## Simulator landscape

| Simulator | Snapshot | Verified model and strengths | Verified limitations | QCore use |
|---|---|---|---|---|
| QCore NumPy reference | Commit `2f2ed07`; NumPy `complex128`; Apache-2.0 | Exact little-endian statevector for a small gate subset, seeded sampling, per-operation traces. | Exponential memory; no noise, density matrix, dynamic control, acceleration, or hard run-size limit. | Retain as deterministic oracle and teaching engine; add resource guards. |
| [Aer](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html) | 0.17.1 docs | Multiple exact/approximate methods, noise, CPU/GPU, MPI. | Native packaging and method-dependent behavior. | Optional backend and differential oracle. |
| [Cirq Simulator](https://quantumai.google/cirq/simulate) | Docs accessed 2026-07-14 | Exact/noisy simulation, parameter sweeps, state inspection, sampling. | Statevector scale is exponential; behavior is Cirq-model specific. | Adapter and differential testing. |
| [qsim](https://quantumai.google/qsim/overview) | Docs accessed 2026-07-14; C++/Python; Apache-2.0 | High-performance statevector and distributed/hybrid simulation integrated with Cirq. | Native build and large-state resource demands. | External performance backend, not core. |
| [Qulacs](https://docs.qulacs.org/en/latest/intro/0_about.html) | Docs accessed 2026-07-14; C++/Python; MIT | Fast CPU/GPU statevector, noisy and parametric circuits. | Separate circuit/noise semantics and native distribution. | Candidate adapter after backend contracts stabilize. |
| [QuEST](https://quest-kit.github.io/QuEST/) | Docs accessed 2026-07-14; C/C++; MIT | Statevector/density matrices with OpenMP, MPI, CUDA, HIP, and cuQuantum options. | Lower-level API and deployment complexity. | Benchmark/reference adapter for large simulation, later. |
| [Stim](https://github.com/quantumlib/Stim) | 1.16.0, 2026-05-22; C++/Python; Apache-2.0 | Extremely fast stabilizer and detector-error-model workflows for QEC. | Non-Clifford general simulation is intentionally unsupported. | Future specialized `StabilizerSimulator`; never hide its capability boundary. |
| [Strawberry Fields backends](https://strawberryfields.readthedocs.io/en/latest/code/sf_backends.html) | Docs accessed 2026-07-14 | Photonic Fock/Gaussian/Bosonic/TensorFlow methods. | Continuous-variable program semantics differ from qubit circuits. | Future separate program-kind adapter. |
| [QuTiP](https://qutip.readthedocs.io/en/qutip-5.0.x/guide/guide-overview.html) | 5.0.x guide | Open-system, Hamiltonian, stochastic, and control solvers. | Not a gate-circuit sampler. | External physics/pulse solver later. |
| [CUDA-Q backends](https://nvidia.github.io/cuda-quantum/latest/using/backends/backends.html) | Docs accessed 2026-07-14 | Heterogeneous simulator and QPU targets, including GPU acceleration. | Toolchain and runtime complexity. | Future adapter if user evidence justifies it. |

**Decision:** Phase 1 builds no new simulator algorithm. It hardens the NumPy
reference engine and defines a backend contract suitable for external simulators.

## Pulse-level and control software

| System | Snapshot | Verified architecture | Boundary and QCore implication |
|---|---|---|---|
| [OpenPulse](https://openqasm.com/versions/3.0/language/openpulse.html) | OpenQASM 3 grammar accessed 2026-07-14 | Grammar for frames, ports, waveforms, and calibrations embedded in the OpenQASM family. | Exchange syntax does not supply hardware calibration ownership or a control runtime; defer. |
| [Qiskit Dynamics](https://qiskit-community.github.io/qiskit-dynamics/apidocs/index.html) | 0.6.0 docs accessed 2026-07-14 | Signals, Hamiltonian/Lindblad models, solvers, and pulse simulation. | Specialized numerical stack; integrate rather than rebuild if pulse research becomes a priority. |
| [Pulser](https://pulser.readthedocs.io/en/stable/sequence.html) | 1.8.0 | Device-constrained neutral-atom pulse scheduling. | Evidence for a distinct pulse/analog program type, not extensions on `Operation`. |
| [LabOne Q](https://docs.zhinst.com/labone_q_user_manual/getting_started/introduction.html) | Docs accessed 2026-07-14; commercial hardware stack | Experiment DSL compiles logical signals and sections into deterministic controller schedules, with result and pulse-sheet inspection. | Calibration and controller semantics are vendor-specific; future adapter only. |
| [QUA](https://docs.quantum-machines.co/latest/docs/Introduction/qua_overview/) | Docs accessed 2026-07-14; commercial control stack | High-level pulse language with exact timing, acquisition, processing, and real-time classical feedback. | Reinforces that pulse runtime requirements differ from circuit-job APIs; future adapter only. |

## Cloud execution models

| Model | Verified examples | Strength | Cost/risk | QCore position |
|---|---|---|---|---|
| Provider primitive service | [Qiskit Runtime](https://quantum.cloud.ibm.com/docs/en/guides/execution-modes) | Domain-specific sampling/estimation with sessions and resilience. | Provider-specific semantics and account lifecycle. | Adapter after local runtime stabilizes. |
| Multi-provider managed service | [Braket](https://docs.aws.amazon.com/braket/latest/developerguide/braket-submit-tasks-to-braket.html), [Azure Quantum](https://learn.microsoft.com/en-us/azure/quantum/how-to-submit-jobs) | One cloud identity and job model over several targets. | Cloud storage, identity, quotas, cost, and regional constraints. | Preserve generic job concepts but avoid credential code in core. |
| SDK conversion plus runtime graph | [qBraid SDK](https://docs.qbraid.com/v2/sdk/user-guide/overview) | Broad format/provider reach. | Continuing adapter and normalization burden. | Do not compete in Phase 1. |
| Local backend | QCore prototype, Aer, Cirq, Braket local simulator | Fast feedback, deterministic testing, no credentials. | No real queue/calibration behavior. | Primary Phase 1 execution mode. |
| Mock backend | Common contract-testing pattern; QCore design | Deterministic lifecycle and error testing. | Cannot establish hardware correctness. | Required Phase 1 backend. |

## Browser labs and notebook environments

| Model | Snapshot | Verified architecture | Strengths | Limitations | QCore implication |
|---|---|---|---|---|---|
| [qBraid Lab](https://docs.qbraid.com/v2/lab/user-guide/overview) | Docs and supplied screenshots, 2026-07-14 | Managed browser IDE launches selectable environments and connects notebooks, terminals, compute, and QPUs. | Rich zero-local-setup workflow. | Requires hosted operations and account/resource management. | Product reference, not a UI or infrastructure template to clone. |
| [JupyterLab](https://jupyterlab.readthedocs.io/en/latest/user/documents_kernels.html) | Current docs | Browser client talks to server-managed kernels and documents. | Full Python ecosystem and extensible desktop-like workspace. | A hosted deployment must isolate kernels, storage, terminals, and networks. | Use later if server-side packages become necessary. |
| [JupyterLite](https://jupyterlite.readthedocs.io/en/stable/) + [Pyodide](https://pyodide.org/en/stable/) | Stable docs accessed 2026-07-14 | Static assets run notebooks and CPython/Wasm in the browser, commonly in Web Workers, without an application server. | Lowest operations cost; easy static hosting; NumPy available. | Wasm/package compatibility, browser memory, threading, filesystem, and network constraints. | **Decision:** first Labs architecture and feasibility target. |
| Remote containers | Jupyter/server container pattern | Full native package compatibility and persistent kernels. | Flexible environment and toolchain. | Image supply chain, tenant isolation, scheduling, idle cleanup, storage, and cost. | Defer until browser-only constraints block validated use cases. |
| MicroVM/sandbox workers | [Firecracker](https://firecracker-microvm.github.io/), [Cloudflare Sandboxes](https://developers.cloudflare.com/sandbox/) | Isolated ephemeral compute with stronger boundaries than in-process execution. | Potential path for untrusted workloads. | Platform coupling, orchestration, observability, and cost. | Research only after a hosted-lab product gate. |
| Hybrid browser/remote | Browser local kernel plus opt-in remote execution | Low-friction local lessons with escape hatch for native workloads. | Evolves without replacing the client. | Two execution semantics and reproducibility environments to support. | Likely long-term Labs model, but not Phase 1. |

## Cross-cutting conclusions

- **Verified:** Mature ecosystems separate provider adapters from core contracts in
  several successful designs, notably pytket extensions and PennyLane devices.
- **Inference:** QCore should make target capabilities extensible rather than
  compressing all providers into a lowest-common-denominator boolean matrix.
- **Verified:** LLVM/MLIR ecosystems require explicit pass, analysis, verification,
  and lowering infrastructure; Catalyst and CUDA-Q demonstrate the payoff for
  structured kernels and heterogeneous targets.
- **Inference:** QCore's static-circuit Phase 1 cannot justify that infrastructure.
- **Verified:** Simulator methods have different valid input domains and numerical
  semantics; Stim, QuTiP, and Strawberry Fields are not interchangeable
  statevector accelerators.
- **Inference:** Backend capability negotiation must reject incompatible programs
  early and visibly.
- **Open Question:** Which external simulator should become the first official
  adapter must be decided from user demand, package reliability, license review,
  and published contract benchmarks.
