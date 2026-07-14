# Phase 0 Source Register

> Status: Research baseline  
> Evidence cut-off: 2026-07-14

This register is the canonical bibliography for Phase 0. Dates and versions are
the latest directly observed during the audit, not promises of currentness.
Primary specifications, official documentation, repositories, release notes, and
papers are preferred.

## Evidence method

- **Verified:** a source directly supports the adjacent claim.
- **Inference:** a QCore conclusion drawn from one or more verified sources.
- **Open Question:** evidence is absent, conflicting, or likely to change.
- Access date for all web sources: 2026-07-14.

## QCore baseline

| ID | Primary source | Scope |
|---|---|---|
| QC-01 | [`pyproject.toml`](../../pyproject.toml) | Distribution metadata, dependencies, Python support, tooling |
| QC-02 | [`src/qplanck`](../../src/qplanck) | Audited implementation at commit `2f2ed07` |
| QC-03 | [`tests`](../../tests) | Behavioral test baseline |
| QC-04 | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | Project license text |
| QC-05 | [Developer Certificate of Origin 1.1](https://developercertificate.org/) | DCO contribution model |
| QC-06 | [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) | Proposed version policy |

## Frameworks and runtimes

| ID | Primary source | Observed version/date and scope |
|---|---|---|
| QB-01 | [qBraid SDK overview](https://docs.qbraid.com/v2/sdk/user-guide/overview) | SDK v2 documentation; conversion graph and runtime model |
| QB-02 | [qBraid Lab overview](https://docs.qbraid.com/v2/lab/user-guide/overview) | Hosted lab environments and integrations |
| QB-03 | [qBraid environment CLI](https://docs.qbraid.com/cli/api-reference/qbraid_envs) | Environment lifecycle commands |
| QB-S1 | Supplied qBraid Dashboard screenshot, SHA-256 `e829745872daba27b4df20305dff9a5057b31603802190e4555d02223e271457` | Visible environments, CPU hours, jobs, and quick actions |
| QB-S2 | Supplied qBraid Explore screenshot, SHA-256 `6fcf8fdd8a219a5a4183f97100c8c154186a8c2a35a70ed99256ba4305c8fa9b` | Visible search, project cards, tags, and submission action |
| QK-01 | [Qiskit transpiler API](https://qiskit.qotlabs.org/docs/api/qiskit/transpiler) | DAG circuits, staged pass managers, plugins |
| QK-02 | [Qiskit Runtime primitives](https://quantum.cloud.ibm.com/docs/en/guides/qiskit-runtime-primitives) | Sampler, Estimator, and Executor runtime surfaces |
| QK-03 | [Qiskit Runtime execution modes](https://quantum.cloud.ibm.com/docs/en/guides/execution-modes) | Job, session, and batch modes |
| QK-04 | [Qiskit Runtime service API](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/runtime-service) | Backends, jobs, status, results, cancellation |
| QK-05 | [Qiskit Runtime release notes](https://quantum.cloud.ibm.com/docs/en/guides/latest-updates) | Time-sensitive runtime capabilities |
| AE-01 | [Qiskit Aer documentation](https://qiskit.github.io/qiskit-aer/) | Aer 0.17.1; simulator overview and license |
| AE-02 | [AerSimulator API](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html) | Simulation methods, CPU/GPU options |
| AE-03 | [Aer noise API](https://qiskit.github.io/qiskit-aer/apidocs/aer_noise.html) | Noise models and transformations |
| CQ-01 | [Cirq basics](https://quantumai.google/cirq/start/basics) | Circuit, moment, device, simulate/run model |
| CQ-02 | [Cirq simulation](https://quantumai.google/cirq/simulate) | Exact, noisy, sweep, and sampling workflows |
| CQ-03 | [Cirq devices](https://quantumai.google/cirq/hardware/devices) | Device validation and constraints |
| CQ-04 | [Google device specification](https://quantumai.google/cirq/google/specification) | Serializable device capability model |
| TK-01 | [TKET documentation](https://docs.quantinuum.com/tket/) | Circuit construction, compilation, mapping, execution |
| TK-02 | [pytket backend API](https://docs.quantinuum.com/tket/api-docs/backends.html) | Backend contracts and result capabilities |
| TK-03 | [pytket passes](https://docs.quantinuum.com/tket/api-docs/passes.html) | Predicates, compositional passes, mapping |
| TK-04 | [pytket backend guide](https://docs.quantinuum.com/tket/user-guide/manual/manual_backend.html) | Separate provider extension packages |
| PL-01 | [PennyLane architecture](https://docs.pennylane.ai/en/stable/development/guide/architecture.html) | QNodes, tapes, devices, differentiation |
| PL-02 | [PennyLane plugins](https://docs.pennylane.ai/en/stable/development/plugins.html) | Device and preprocessing extension model |
| CT-01 | [Catalyst architecture](https://docs.pennylane.ai/projects/catalyst/en/latest/dev/architecture.html) | JAX capture, MLIR, QIR, native runtime |
| CT-02 | [Catalyst dialects](https://docs.pennylane.ai/projects/catalyst/en/stable/dev/dialects.html) | Quantum-specific MLIR dialect stack |
| CT-03 | [Catalyst runtime](https://docs.pennylane.ai/projects/catalyst/en/latest/modules/runtime.html) | C++ QIR runtime and device interface |
| CU-01 | [CUDA-Q documentation](https://nvidia.github.io/cuda-quantum/latest/index.html) | Heterogeneous C++/Python platform |
| CU-02 | [CUDA-Q language specification](https://nvidia.github.io/cuda-quantum/latest/specification/cudaq.html) | Quantum kernels and types |
| CU-03 | [CUDA-Q compiler specifications](https://nvidia.github.io/cuda-quantum/latest/specification/index.html) | Quake/MLIR compilation architecture |
| CU-04 | [CUDA-Q backends](https://nvidia.github.io/cuda-quantum/latest/using/backends/backends.html) | Simulator and QPU targets |
| BR-01 | [Amazon Braket architecture](https://docs.aws.amazon.com/braket/latest/developerguide/braket-how-it-works.html) | Task, device, S3, and managed service flow |
| BR-02 | [Braket local simulators](https://docs.aws.amazon.com/braket/latest/developerguide/braket-send-to-local-simulator.html) | Local statevector/density-matrix execution |
| BR-03 | [Braket Hybrid Jobs](https://docs.aws.amazon.com/braket/latest/developerguide/braket-jobs.html) | Managed hybrid workload model |
| AZ-01 | [Azure Quantum overview](https://learn.microsoft.com/en-us/azure/quantum/overview-azure-quantum) | Cloud workspace and provider model |
| AZ-02 | [Azure Quantum jobs](https://learn.microsoft.com/en-us/azure/quantum/how-to-work-with-jobs) | Job lifecycle and result retrieval |
| AZ-03 | [Azure target profiles](https://learn.microsoft.com/en-us/azure/quantum/quantum-computing-target-profiles) | Capability profiles and QIR compatibility |
| QS-01 | [Modern QDK/Q# repository](https://github.com/microsoft/qsharp) | Rust/Wasm implementation and browser tooling |
| QS-02 | [Q# overview](https://learn.microsoft.com/en-us/azure/quantum/qsharp-overview) | Language and quantum program model |
| CL-01 | [Classiq documentation](https://docs.classiq.io/) | High-level modeling and synthesis platform |
| CL-02 | [Qmod language reference](https://docs.classiq.io/qmod-reference) | High-level Qmod modeling and synthesis language |
| CL-03 | [Classiq providers](https://docs.classiq.io/latest/sdk-reference/providers/) | Provider integrations |
| CL-04 | [Classiq 1.4.1 release notes](https://docs.classiq.io/latest/release-notes/1-4-1/) | Release dated 2026-03-04 |
| PU-01 | [Pulser sequence model](https://pulser.readthedocs.io/en/stable/sequence.html) | Register, device, channel, pulse, schedule |
| PU-02 | [Pulser repository](https://github.com/pasqal-io/Pulser) | v1.8.0 on 2026-05-04; Apache-2.0 |
| SF-01 | [Strawberry Fields circuits](https://strawberryfields.readthedocs.io/en/latest/introduction/circuits.html) | Photonic programs, engines, backend families |
| SF-02 | [Strawberry Fields backends](https://strawberryfields.readthedocs.io/en/latest/code/sf_backends.html) | Fock, Gaussian, Bosonic, TensorFlow backends |
| PJ-01 | [ProjectQ repository](https://github.com/ProjectQ-Framework/ProjectQ) | v0.8.0 on 2022-10-18; compiler-engine model |
| QT-01 | [QuTiP user guide](https://qutip.readthedocs.io/en/qutip-5.0.x/guide/guide-overview.html) | Open-system dynamics and numerical solvers |
| QT-02 | [QuTiP roadmap](https://qutip.readthedocs.io/en/latest/development/roadmap.html) | Project direction and architecture work |
| OF-01 | [OpenFermion introduction](https://quantumai.google/openfermion/tutorials/intro_to_openfermion) | Fermionic operators and qubit transforms |
| MT-01 | [Mitiq executor guide](https://mitiq.readthedocs.io/en/stable/guide/executors.html) | User-supplied executor abstraction |
| MT-02 | [Mitiq repository](https://github.com/unitaryfoundation/mitiq) | v1.0.0 on 2026-03-25; GPL-3.0 |
| ZX-01 | [PyZX quick introduction](https://pyzx.readthedocs.io/en/stable/quickintro.html) | Circuit and ZX graph representations |
| ZX-02 | [PyZX simplification](https://pyzx.readthedocs.io/en/stable/simplify.html) | Graph rewriting and circuit extraction |
| ZX-03 | [PyZX repository](https://github.com/zxcalc/pyzx) | v0.10.4 on 2026-07-01; Apache-2.0 |

## Languages, standards, and compiler infrastructure

| ID | Primary source | Scope |
|---|---|---|
| OQ-02 | [OpenQASM 2 repository branch](https://github.com/openqasm/openqasm/tree/OpenQASM2.x) | OpenQASM 2 grammar and specification history |
| OQ-03 | [OpenQASM 3 introduction](https://openqasm.com/versions/3.0/intro.html) | Language goals and execution-model boundary |
| OQ-04 | [OpenQASM 3 language specification](https://openqasm.com/versions/3.0/language/index.html) | Normative language semantics |
| OQ-05 | [OpenQASM 3 grammar](https://openqasm.com/versions/3.0/grammar/index.html) | Normative grammar |
| OP-01 | [OpenPulse grammar](https://openqasm.com/versions/3.0/language/openpulse.html) | Calibration and pulse-level grammar |
| QI-01 | [QIR specification](https://github.com/qir-alliance/qir-spec) | LLVM-based quantum IR and profiles |
| QI-02 | [QIR Alliance](https://www.qir-alliance.org/) | Governance and ecosystem |
| QI-03 | [QIR Adapter Tool](https://www.qir-alliance.org/qat/) | Profile adaptation and validation |
| QI-04 | [PyQIR](https://www.qir-alliance.org/pyqir/) | Python bindings for QIR construction and inspection |
| LL-01 | [LLVM language reference](https://llvm.org/docs/LangRef.html) | LLVM IR semantics |
| LL-02 | [LLVM new pass manager](https://llvm.org/docs/NewPassManager.html) | Analysis preservation and pass pipelines |
| ML-01 | [MLIR dialects](https://mlir.llvm.org/docs/Dialects/) | Extensible dialect model |
| ML-02 | [MLIR pass management](https://mlir.llvm.org/docs/PassManagement/) | Pass, analysis, instrumentation model |
| ML-03 | [MLIR dialect conversion](https://mlir.llvm.org/docs/DialectConversion/) | Multi-level lowering framework |
| ML-04 | [MLIR LLVM translation](https://mlir.llvm.org/docs/TargetLLVMIR/) | Lowering to LLVM IR |

## Simulators and control stacks

| ID | Primary source | Observed scope |
|---|---|---|
| SI-01 | [qsim overview](https://quantumai.google/qsim/overview) | High-performance statevector and hybrid simulation |
| SI-02 | [Qulacs overview](https://docs.qulacs.org/en/latest/intro/0_about.html) | C++/Python CPU/GPU circuit simulation; MIT |
| SI-03 | [QuEST documentation](https://quest-kit.github.io/QuEST/) | OpenMP/MPI/GPU statevector and density matrix |
| SI-04 | [Stim repository](https://github.com/quantumlib/Stim) | v1.16.0 on 2026-05-22; stabilizer/QEC simulation |
| DY-01 | [Qiskit Dynamics API](https://qiskit-community.github.io/qiskit-dynamics/apidocs/index.html) | Signals, models, solvers, pulse simulation |
| ZI-01 | [LabOne Q manual](https://docs.zhinst.com/labone_q_user_manual/core/index.html) | Experiment DSL, compiler, controller, results |
| ZI-02 | [LabOne Q introduction](https://docs.zhinst.com/labone_q_user_manual/getting_started/introduction.html) | Deterministic pulse scheduling model |
| QM-01 | [QUA overview](https://docs.quantum-machines.co/latest/docs/Introduction/qua_overview/) | Real-time pulse and classical-control language |
| QM-02 | [QUA feedback guide](https://docs.quantum-machines.co/latest/docs/Guides/feedback/) | Real-time feedback patterns |

## Browser and notebook environments

| ID | Primary source | Scope |
|---|---|---|
| JL-01 | [JupyterLab kernels and documents](https://jupyterlab.readthedocs.io/en/latest/user/documents_kernels.html) | Server-managed kernels and documents |
| JL-02 | [JupyterLite documentation](https://jupyterlite.readthedocs.io/en/stable/) | Static, in-browser Jupyter distribution |
| PY-01 | [Pyodide documentation](https://pyodide.org/en/stable/) | CPython and NumPy in WebAssembly |
| PY-02 | [Pyodide package loading](https://pyodide.org/en/stable/usage/loading-packages.html) | Browser package constraints and `micropip` |
| GH-01 | [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) | Static-site deployment model |
| FC-01 | [Firecracker documentation](https://firecracker-microvm.github.io/) | MicroVM isolation option for future hosted execution |
| K8-01 | [Kubernetes concepts](https://kubernetes.io/docs/concepts/) | Container orchestration option for future hosted execution |
| CF-01 | [Cloudflare Sandboxes](https://developers.cloudflare.com/sandbox/) | Managed isolated code execution option; future evaluation |

## Package-name evidence

- **Verified:** [`qcore` on PyPI](https://pypi.org/project/qcore/) was occupied by
  an unrelated distribution when checked on 2026-07-14.
- **Verified:** [`qplanck` on PyPI](https://pypi.org/project/qplanck/) returned no
  project page when checked on 2026-07-14.
- **Open Question:** Repeat both ownership checks immediately before every release;
  absence of a project page does not reserve a name.

## Known evidence gaps

- **Open Question:** Provider pricing, quotas, and exact service availability were
  intentionally excluded because they are volatile and not required for the local
  Phase 1 scope.
- **Open Question:** Comparative compiler and simulator performance remains
  unverified until QCore publishes pinned, correctness-checked benchmarks.
- **Open Question:** Commercial platform license terms require legal review before
  any code-level integration; documentation access is not redistribution permission.
