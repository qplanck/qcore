# QCore Master Specification

**Founder-readable product thesis, software specification, v0.1 definition, and build roadmap**

| Document field | Value |
|---|---|
| Status | Working master specification; implementation guide, not proof that the thesis is true |
| Version | 0.1-draft |
| Date | 9 August 2026 |
| Primary audience | QPlanck founder, early engineers, quantum/compiler advisers, research collaborators, and investors conducting technical diligence |
| Product | QCore |
| Organisation | QPlanck / QPlanck Labs |

> **QCore takes a quantum program, understands what the user wants, evaluates available ways of running it, and returns the best execution plan it found—together with the evidence and artifacts needed to inspect, run, and reproduce that decision.**

That is the whole product thesis in one sentence. Everything in this report exists to make that sentence precise, buildable, measurable, and falsifiable.

---

## How to read this report

This report deliberately has two levels:

- The **founder explanation** gives the mental model and explains why a component exists.
- The **engineering contract** states what the software must do and how success will be judged.

The most important discipline is to keep vision and evidence separate:

- **Vision:** QCore could become a neutral execution intelligence layer across quantum and classical hardware.
- **Current hypothesis:** a portfolio of compilers plus target-aware, objective-aware planning can produce measurably better and more reproducible execution choices than a user selecting one default toolchain manually.
- **First proof required:** QCore v0.1 must demonstrate that advantage on controlled benchmarks. Until then, QCore is a promising thesis, not an industry standard.

The conceptual sequence is:

```text
WHY QCORE EXISTS
        ↓
THE PROBLEM
        ↓
THE QCORE THESIS
        ↓
CORE ABSTRACTIONS
        ↓
SOFTWARE ARCHITECTURE
        ↓
QCORE v0.1
        ↓
BENCHMARK
        ↓
PROVE / DISPROVE THE THESIS
        ↓
PLANNER + RUNTIME
        ↓
NATIVE COMPILER
        ↓
HYBRID CPU/GPU/QPU ORCHESTRATION
        ↓
FAULT-TOLERANT + QEC SUPPORT
```

## Contents

| Part | Purpose |
|---|---|
| I. First principles | SDK, compiler, IR, runtime, provider/backend, Target, Planner, and execution layer |
| II. Product thesis | why QCore exists; adaptive performance portability; what QCore is and is not |
| III. Ecosystem | honest comparison with the major frameworks, compilers, runtimes, IRs, and QEC stacks |
| IV. Product model | Program, Target, Objective, Plan, Execution, Result, and Artifact |
| V. Architecture | Rust core, Python/PyO3, compiler layer, adapters, planner, runtime, and provenance |
| VI. v0.1 specification | exact input, IBM Target, compiler portfolio, metrics, ranking, API, and acceptance contract |
| VII. Repository | proposed packages, dependency rules, and tests |
| VIII. Build phases | research kernel through planner, runtime, native compiler, Cloud, hybrid, and fault tolerance |
| IX. Evidence | success metrics, benchmark protocol, falsification tests, and go/no-go gates |
| X. Business model | QCore OSS, QCore Cloud, and QPlanck Labs |
| XI. Team | expertise, human review, and what Codex can and cannot own |
| XII. Founder roadmap | concepts to learn in sequence with practical checkpoints |
| XIII. Anti-goals | explicit boundaries and a scope-admission test |
| XIV. Risks and decisions | kill conditions, locked decisions, and open questions |
| XV. Final statement | precise founder, technical, and v0.1 definitions |

---

## Executive decision

QCore should **not** begin as another general-purpose quantum programming framework. Qiskit, Cirq, PennyLane, TKET, CUDA-Q, qBraid, Braket, BQSKit, Classiq, MQT, and others already provide sophisticated pieces of the stack.

QCore should begin as a **research kernel for explainable execution planning**:

1. Accept a program the researcher already has, initially from Qiskit or OpenQASM.
2. capture an immutable snapshot of an IBM target;
3. compile the same program through a controlled portfolio of Qiskit, TKET, BQSKit, and small QCore-native experimental pipelines;
4. validate each candidate against the same target and semantic checks;
5. evaluate every candidate with the same independent metrics;
6. select a plan according to an explicit objective;
7. explain why it won; and
8. preserve every input, version, seed, target snapshot, candidate, score, and output as reproducible artifacts.

The v0.1 question is therefore not:

> Can QPlanck build a universal quantum operating system?

It is:

> **Does portfolio-based, target-aware planning produce a repeatable execution advantage large enough to justify building QCore?**

If the answer is no, the team should narrow, pivot, or stop. If the answer is yes, the planner becomes the wedge from which the runtime, native compiler, cloud product, and later fault-tolerant capabilities can grow.

---

# Part I — First principles

## 1. A quantum program does not run directly

A quantum circuit written by a researcher is usually an **abstract intention**, not a sequence a physical quantum processor can execute unchanged.

Suppose a researcher writes:

```python
qc.h(0)
qc.cx(0, 4)
qc.measure_all()
```

Before a machine can run it, software may need to decide:

- whether the program is valid;
- what the operations mean;
- which physical qubits should represent logical qubits `0` and `4`;
- how to handle the fact that those physical qubits may not be connected;
- how to express `H` and `CX` using the device's native operations;
- which equivalent circuit has fewer noisy two-qubit operations;
- how to schedule the operations under timing constraints;
- which device, provider, and job interface to use;
- how many shots to request;
- how to retrieve and interpret the result; and
- how to record the conditions so the experiment can be understood later.

The program is therefore only the start of a decision pipeline:

```text
COMPUTE INTENT
    ↓
PROGRAM REPRESENTATION
    ↓
ANALYSIS AND TRANSFORMATION
    ↓
TARGET-SPECIFIC COMPILATION
    ↓
PLAN SELECTION
    ↓
SUBMISSION AND EXECUTION
    ↓
RESULTS AND PROVENANCE
```

QCore's proposed product boundary is the decision and evidence layer across this pipeline.

## 2. The essential vocabulary

### 2.1 SDK — the interface developers install and use

**SDK** means *software development kit*. It is a packaged set of APIs, types, documentation, examples, and tools that lets developers build with a system.

An SDK might expose:

```python
import qcore

program = qcore.Program.from_qiskit(circuit)
plan = qcore.plan(program, objective="min_estimated_error")
result = qcore.run(plan)
```

The SDK is not the whole system. It is the **doorway** into the system.

Founder analogy: the Google Maps app is an interface. The map data, traffic ingestion, route search, ranking, and navigation infrastructure behind it are the deeper system. In the same way, `qcore.plan()` should be simple even if the work behind it is complex.

**QCore implication:** Python should be the easiest doorway because quantum researchers commonly work in Python. Rust, compiler infrastructure, adapters, and provenance sit behind that doorway.

### 2.2 Compiler — software that transforms a valid program

A compiler turns a program from one form into another while preserving the behaviour that matters.

For quantum circuits, compilation can include:

- simplifying gates;
- decomposing high-level operations;
- synthesising equivalent subcircuits;
- assigning logical qubits to physical qubits, called **placement** or **layout**;
- inserting operations needed to move quantum state through limited connectivity, called **routing**;
- converting operations into a target's native gate set, called **lowering** or **rebasing**; and
- scheduling operations under timing constraints.

There is rarely one universally best compiled circuit. One candidate may have lower depth, another fewer two-qubit gates, and another a better mapping onto low-error physical qubits. Compilation is therefore partly an optimisation/search problem.

**QCore implication:** v0.1 should not attempt to replace mature compilers. It should run a portfolio of them, compare their outputs fairly, and learn where selection adds value.

### 2.3 IR — the compiler's internal language

**IR** means *intermediate representation*. It is the structured form a compiler uses to represent and reason about a program between the user's source format and the target's executable format.

An IR is more than a file syntax. A useful IR defines:

- operations and their types;
- qubits, classical values, parameters, and measurements;
- ordering, data flow, and control flow;
- regions, functions, or reusable blocks;
- invariants that valid programs must satisfy;
- metadata and source locations; and
- rules for transformation and verification.

Founder analogy: English and French recipes can both be converted into a kitchen's structured order tickets. The ticket is not another meal; it is a consistent internal form the kitchen can validate, schedule, and execute.

**QCore implication:** QCore needs a canonical representation, but inventing a grand universal quantum IR in v0.1 would be premature. Start with the smallest typed circuit representation needed for the experiment, preserve lossless source artifacts, and design an explicit path to MLIR/QIR/OpenQASM interoperability.

### 2.4 Runtime — software that manages work while or after it executes

A **runtime** manages the operational life of a program after a plan has been chosen. It may:

- prepare a provider request;
- submit a job;
- track state;
- retry safe failures;
- enforce timeouts and cancellation;
- retrieve results;
- map provider-specific output into a stable result model; and
- attach execution metadata and artifacts.

A compiler answers, “What executable program should we produce?” A runtime answers, “How do we cause this plan to run reliably and track what happened?”

**QCore implication:** planning and running must be separable. A researcher must be able to inspect and approve a `Plan` before `run()` incurs cost or submits anything externally.

### 2.5 Provider and backend — who supplies access, and what accepts the job

A **provider** is the organisation or service integration through which compute resources are discovered and accessed—for example, an IBM Quantum account or an AWS Braket account.

A **backend** is a provider-specific handle to something that can accept work, such as a QPU, simulator, or managed execution service.

The words are overloaded across existing SDKs, so QCore must make its own distinction explicit:

```text
Provider = access and service boundary
Backend  = provider-specific execution endpoint
Target   = immutable compilation-relevant snapshot used for reasoning
```

### 2.6 Target — the machine model the compiler plans against

A **Target** is QCore's normalized, time-stamped description of the constraints and capabilities relevant to compilation and execution.

It can include:

- target identity and provider;
- number and kind of qubits;
- supported operations;
- operation-to-qubit availability;
- connectivity/topology;
- gate durations and errors when available;
- readout errors;
- timing and measurement constraints;
- dynamic-circuit capabilities;
- queue, price, and availability observations; and
- source, acquisition time, and validity information.

The Target is not the live device itself. It is a **snapshot of what QCore believed about the device when it planned**.

This distinction matters because quantum hardware calibrations and availability can change. A plan produced against yesterday's calibration must not silently claim to describe today's machine.

### 2.7 Planner — the system that decides how

The **Planner** combines:

```text
Program + eligible Targets + Objective + search budget
```

and returns:

```text
Plan + ranked alternatives + explanation + evidence
```

The planner does not need machine learning in v0.1. A deterministic policy that generates candidate recipes, runs compilers, rejects invalid outputs, calculates comparable metrics, finds a Pareto frontier, and applies transparent ranking is more valuable than an opaque “AI optimiser.”

The honest claim is:

> QCore returns the best feasible plan it found within the declared target set, compiler portfolio, objective, and search budget.

It must not claim a mathematically global optimum unless it can prove one.

### 2.8 Execution layer — the boundary that turns a plan into a tracked experiment

The **execution layer** is the combined system between a selected plan and the provider: credential-safe submission, job-state management, cancellation, result retrieval, normalization, and provenance.

It is broader than a single provider adapter and narrower than the entire QCore platform.

```text
Plan
  ↓
QCore execution state machine
  ↓
Provider adapter
  ↓
Provider job / backend
  ↓
Raw provider result
  ↓
Normalized Result + immutable Artifacts
```

---

# Part II — The product thesis

## 3. Why QCore exists

Quantum software has several simultaneous forms of fragmentation:

1. **Program fragmentation:** researchers use different circuit and algorithm frameworks.
2. **Compiler fragmentation:** different compilers and pass pipelines perform better on different circuit structures and targets.
3. **Hardware fragmentation:** modalities expose different native gates, topology, timing, noise, and execution constraints.
4. **Provider fragmentation:** job APIs, credentials, queues, pricing, and result formats differ.
5. **Objective fragmentation:** “best” can mean fidelity, cost, latency, depth, research reproducibility, or a constrained mixture.
6. **Temporal fragmentation:** a target's calibration and availability can change between planning and execution.
7. **Evidence fragmentation:** the exact inputs, versions, seeds, mappings, and target data behind a result are often difficult to compare consistently.

Existing tools solve substantial parts of these problems. QCore only deserves to exist if a useful decision boundary remains between them.

That proposed boundary is:

> **Translate compute intent into an explainable, reproducible, high-quality execution plan across a changing portfolio of compilers and targets.**

## 4. The QCore thesis

The thesis has four parts:

### 4.1 Keep the user's existing framework

QCore should not require researchers to rewrite working programs in a new QCore language. The adoption path should be:

```python
program = qcore.Program.from_qiskit(existing_circuit)
```

Later frontends may accept Cirq, PennyLane, CUDA-Q/QIR, Qualtran, and other representations. QCore wins underneath existing workflows, not by demanding their replacement.

### 4.2 Treat compilation as a portfolio, not a single pipeline

No one compiler, pass order, seed, or layout strategy is guaranteed to dominate every workload. QCore should generate a bounded set of candidates using existing and QCore-native techniques, then compare them under a common evaluator.

The first product advantage is therefore not “we invented every compiler pass.” It is:

> **We systematically search, compare, select, and explain.**

### 4.3 Make the objective explicit

There is no useful definition of “best” without an objective and constraints.

Examples:

```python
Objective.min_estimated_error()

Objective(
    minimize=["estimated_error", "two_qubit_gates"],
    constraints={"max_depth": 800, "max_cost_gbp": 10.0},
)
```

The objective must be serializable and included in provenance. Silent or undocumented ranking preferences are unacceptable.

### 4.4 Preserve the decision, not only the winning circuit

The durable QCore product is not merely a compiled circuit. It is a decision record:

- what program was received;
- which target snapshot was used;
- which candidates were tried;
- which versions, configurations, seeds, and budgets were used;
- which candidates failed and why;
- how every candidate scored;
- why the selected candidate won; and
- what actually happened during execution.

This evidence is necessary for scientific reproducibility, debugging, enterprise audit, and later learning systems.

## 5. Defining concept: adaptive performance portability

QCore's defining concept is **adaptive performance portability**.

The phrase is easiest to understand as four levels:

| Level | Meaning | Example |
|---|---|---|
| Compatibility | The program can be represented or accepted. | A Qiskit circuit imports without error. |
| Portability | The same program can target more than one backend. | It compiles for two QPUs. |
| Performance portability | It remains competitively efficient across targets without hand-rewriting the program. | QCore finds circuits close to or better than strong target-specific baselines. |
| **Adaptive performance portability** | Planning changes when the program, target snapshot, objective, or budget changes—and records why. | A new calibration causes QCore to choose a different layout and explain the expected benefit. |

### 5.1 Formal statement

Let:

- `P` be a program;
- `T` be a set of eligible target snapshots;
- `O` be an objective with hard constraints and ordered preferences;
- `B` be a finite planning budget; and
- `Π(P, T, B)` be the set of feasible candidate plans QCore discovers within that budget.

QCore selects:

```text
π* = argmin according to O over feasible π in Π(P, T, B)
```

It must also return `Π`'s evaluated candidates, the policy used, and the evidence supporting `π*`.

The phrase “best plan” always means **best discovered under these declared conditions**, not omniscient global optimality.

### 5.2 What makes it adaptive

The output may legitimately change when any of these change:

- calibration data;
- available physical qubits or operations;
- target availability or queue;
- price;
- compiler version;
- candidate seed set;
- planning time budget;
- user objective;
- program parameters that affect compilation; or
- runtime capabilities such as mid-circuit measurement.

Adaptation is only trustworthy when QCore can show which input changed and why the new decision followed.

### 5.3 The falsifiable claim

For defined benchmark strata and equal resource budgets, a QCore portfolio planner should:

1. beat each constituent tool's single default pipeline on a meaningful share of workloads;
2. rarely produce a materially worse selected candidate than the best candidate it evaluated;
3. add acceptable planning overhead relative to the quality gain; and
4. reproduce the same decision from saved artifacts and deterministic settings.

If portfolio selection does not create material uplift over strong baselines, adaptive performance portability is not yet a product wedge.

## 6. What QCore is

QCore is intended to become:

- a vendor-neutral **execution planning layer**;
- a typed **program and target model**;
- a **compiler portfolio orchestrator**;
- an **objective and constraint engine**;
- an explainable **candidate evaluator and ranker**;
- a provider-neutral **runtime contract**;
- a content-addressed **artifact and provenance system**;
- a high-performance **Rust core** with an ergonomic Python SDK; and
- later, a native compiler and hybrid CPU/GPU/QPU orchestration system.

## 7. What QCore is not

QCore is not:

- a quantum computer or control system;
- a promise that one API erases real hardware differences;
- a new quantum algorithm library in v0.1;
- a replacement for Qiskit, Cirq, PennyLane, TKET, BQSKit, CUDA-Q, or QIR;
- a universal quantum IR standard by declaration;
- an AI system in v0.1;
- a simulator project;
- a billing marketplace;
- a notebook/IDE product—that is a possible QPlanck Labs surface;
- a guarantee of true hardware fidelity from calibration metadata;
- an error-correction decoder; or
- an excuse to build a huge platform before the planner thesis is proven.

---

# Part III — Where QCore sits in the ecosystem

## 8. The honest competitive position

Many projects already claim portability, hardware abstraction, compilation, or hybrid execution. Vendor neutrality alone is not differentiation. A Python wrapper around several providers is not differentiation. A new circuit class is not differentiation.

QCore's proposed differentiation is the combination of:

1. a **portfolio** of compiler strategies rather than a single preferred pipeline;
2. a first-class, serializable **Objective**;
3. time-stamped, normalized **Target snapshots**;
4. independent, comparable candidate evaluation;
5. explainable **Plan selection**;
6. immutable artifacts and end-to-end **provenance**; and
7. eventual feedback from predicted versus observed execution outcomes.

Even that combination is a hypothesis. qBraid, TKET, Qiskit, CUDA-Q, Classiq, Braket, or another platform could extend into the same boundary. QCore must earn its position through superior evidence, ergonomics, and execution outcomes.

## 9. Comparison by project

### 9.1 Qiskit

**What it is:** a mature quantum SDK with circuit construction, a powerful pass-based transpiler, a rich `Target` model, simulation integrations, and IBM Quantum execution services. Qiskit's `Target` is explicitly designed to communicate backend constraints to the compiler; IBM also offers heuristic and AI-powered routing and synthesis passes. See the [Qiskit Target documentation](https://quantum.cloud.ibm.com/docs/en/api/qiskit/2.3/qiskit.transpiler.Target) and [AI-powered transpiler passes](https://quantum.cloud.ibm.com/docs/en/guides/ai-transpiler-passes).

**Important correction:** Qiskit is strongly connected to IBM's ecosystem, but its SDK and transpiler are extensible and should not be described as technically IBM-only.

**Relationship to QCore:** Qiskit is QCore v0.1's primary frontend, target source, baseline, and one compiler engine.

**Proposed distinction:** QCore sits above individual Qiskit pass managers and compares Qiskit candidates with other compiler portfolios using an explicit objective and common provenance model.

**Competitive risk:** Qiskit is already highly optimised and has strong benchmarking results. If QCore cannot add value over well-tuned Qiskit plus multi-seed transpilation, the v0.1 thesis fails.

### 9.2 Cirq

**What it is:** Google's Python framework for constructing, transforming, simulating, and executing circuits, with explicit device constraints and strong support for hardware-aware circuit work. Cirq `Device` objects validate operations and connectivity; see [Cirq devices](https://quantumai.google/cirq/hardware/devices).

**Relationship to QCore:** future frontend and export adapter, particularly for Google-style circuit/device workflows.

**Proposed distinction:** QCore is not another circuit authoring model. It would consume Cirq programs, evaluate multiple execution paths, and return a plan and evidence.

### 9.3 PennyLane

**What it is:** a cross-platform framework focused on differentiable quantum programming, quantum machine learning, quantum chemistry, hybrid workflows, and device plugins. Its core strength is treating quantum computations as differentiable components connected to classical ML systems; see the [PennyLane architecture](https://docs.pennylane.ai/en/stable/development/guide/architecture.html).

**Relationship to QCore:** later frontend/runtime integration for circuits or captured workflows.

**Proposed distinction:** QCore does not replace gradient transforms, QNodes, optimizers, or QML abstractions. It may optimise the execution beneath them.

**Hard requirement:** any integration must preserve parameter binding, differentiation method, shot semantics, and batching. A circuit conversion that silently breaks gradients is not portability.

### 9.4 TKET / pytket

**What it is:** Quantinuum's platform-agnostic toolkit with composable compiler passes, predicates, placement/routing, rebasing, optimisation, and unified backend interfaces. Its documentation explicitly frames compilation as satisfying target constraints while optimising circuit quality; see the [pytket compilation guide](https://docs.quantinuum.com/tket/user-guide/manual/manual_compiler.html) and [backend model](https://docs.quantinuum.com/tket/user-guide/manual/manual_backend.html).

**Relationship to QCore:** a first-class v0.1 compiler engine and a strong baseline.

**Proposed distinction:** TKET primarily provides a compiler/toolkit and portable backend model. QCore's wedge would be deciding when a TKET pipeline is preferable to Qiskit, BQSKit, or QCore-native candidates for a declared objective, and preserving that decision.

**Competitive risk:** TKET is one of the closest architectural neighbours. QCore must not merely reproduce its pass system or backend abstraction.

### 9.5 CUDA-Q

**What it is:** NVIDIA's C++ and Python programming model and toolchain for heterogeneous CPU, GPU, and QPU systems, including simulation, hardware backends, asynchronous execution, MLIR-based compiler infrastructure, and hybrid workloads. See the [CUDA-Q overview](https://nvidia.github.io/cuda-quantum/latest/index.html).

**Relationship to QCore:** future input/lowering/runtime integration and an essential benchmark for the hybrid roadmap.

**Proposed distinction:** CUDA-Q owns a heterogeneous programming and execution model closely tied to NVIDIA's accelerated computing strengths. QCore would focus on neutral, objective-aware plan selection and cross-toolchain evidence rather than attempting to outbuild CUDA-Q's GPU/HPC runtime.

**Competitive risk:** “CPU + GPU + QPU” is not unique positioning. QCore should enter this phase only after proving the planner and runtime layers.

### 9.6 qBraid

**What it is:** a platform-agnostic Python runtime framework with provider/device/job/result abstractions and a graph-based transpiler connecting multiple program types. See the [qBraid SDK overview](https://docs.qbraid.com/v2/sdk/user-guide/overview).

**Relationship to QCore:** direct product-level comparator and potential integration partner.

**Proposed distinction:** QCore must go beyond program conversion and provider lifecycle management by demonstrating better plan search, comparable independent scoring, explicit objectives, explainable selection, and rigorous provenance.

**Competitive risk:** qBraid overlaps heavily with the portability/runtime story. If users only need conversion and multi-provider submission, QCore has no reason to exist.

### 9.7 QIR

**What it is:** Quantum Intermediate Representation, embedded in LLVM IR and designed for interoperability in hybrid quantum-classical compiler systems. See the [QIR Alliance explanation](https://www.qir-alliance.org/qir-book/concepts/what-is-qir.html).

**Relationship to QCore:** a strategic interoperability and lowering target, not a competitor to replace.

**Proposed distinction:** QIR specifies a compiler-level representation and conventions. It does not by itself choose providers, search compiler portfolios, rank candidates against user objectives, submit jobs, or preserve QCore-style decision provenance.

### 9.8 OpenQASM

**What it is:** an imperative language and interchange representation for quantum programs. OpenQASM 3 includes classical control, timing concepts, and calibration constructs, while deliberately not defining the execution environment that accepts a program. See the [OpenQASM 3 specification](https://openqasm.com/versions/3.0/index.html) and [scope](https://openqasm.com/intro.html).

**Relationship to QCore:** required import/export format and artifact format.

**Proposed distinction:** OpenQASM describes a program. QCore decides how to compile and execute it under an objective. QCore must not confuse supporting a subset of OpenQASM with implementing the whole language.

### 9.9 BQSKit

**What it is:** the Berkeley Quantum Synthesis Toolkit, a portable compiler framework with its own circuit IR, machine model, compiler workflows, and numerical synthesis algorithms. See the [BQSKit overview](https://bqskit.readthedocs.io/en/latest/) and [compiler infrastructure](https://bqskit.readthedocs.io/en/latest/source/compiler.html).

**Relationship to QCore:** a v0.1 compiler engine, especially for synthesis of suitable unitary regions, plus a strong research baseline.

**Proposed distinction:** QCore decides when and where BQSKit's techniques are worth their potentially higher compilation cost and compares the result with other candidates under a shared evaluator.

**Constraint:** BQSKit should not be forced over measurements, unsupported control flow, or circuits outside sensible synthesis limits. Adapters must identify suitable regions and fail explicitly.

### 9.10 Classiq

**What it is:** a high-level quantum modelling and synthesis platform. Users express functional intent and constraints in Qmod, and the platform synthesises hardware-aware gate-level implementations; see the [Classiq documentation](https://docs.classiq.io/).

**Relationship to QCore:** future high-level source or artifact integration and a comparator for intent-to-implementation workflows.

**Proposed distinction:** Classiq starts above the gate-level circuit and focuses on synthesising algorithms from high-level models. QCore v0.1 starts from an existing circuit and selects among compilation/execution plans. The long-term scopes could overlap, so QCore should avoid vague “intent-based compilation” claims until it supports them.

### 9.11 Amazon Braket

**What it is:** AWS's managed quantum computing service and open-source SDK for accessing multiple QPUs and simulators, with managed Hybrid Jobs for quantum-classical workloads. See the [Amazon Braket overview](https://aws.amazon.com/documentation-overview/braket/) and [Hybrid Jobs documentation](https://docs.aws.amazon.com/braket/latest/developerguide/braket-jobs.html).

**Relationship to QCore:** future provider adapter and managed execution substrate.

**Proposed distinction:** Braket provides AWS-mediated access and job infrastructure. QCore would remain provider-neutral, plan across toolchains/targets, and may choose Braket as one execution route.

**Competitive risk:** QCore Cloud must offer execution intelligence, reproducibility, or enterprise policy beyond a thinner multi-provider console.

### 9.12 MQT and MQSS

**What they are:** the Munich Quantum Toolkit is an open-source family of design-automation and quantum software tools. It is part of the broader Munich Quantum Software Stack ecosystem for modular hybrid quantum-classical computing. See the [MQT overview](https://mqt.readthedocs.io/) and [MQSS interfaces](https://munich-quantum-software-stack.github.io/MQSS-Interfaces/).

**Relationship to QCore:** research neighbour, benchmark source, verification/mapping inspiration, and possible future interoperability layer.

**Proposed distinction:** QCore is a focused product thesis around objective-aware portfolio planning and provenance, while MQT/MQSS span a broader academic and ecosystem stack. QCore should reuse and benchmark against relevant MQT components rather than recreate them.

### 9.13 Qualtran

**What it is:** Google's framework and algorithm library for expressing, analysing, decomposing, and resource-estimating fault-tolerant quantum algorithms using `Bloq` abstractions. See [Google's Qualtran overview](https://quantumai.google/qualtran).

**Relationship to QCore:** future fault-tolerant frontend and resource-estimation integration.

**Proposed distinction:** Qualtran reasons about algorithms and fault-tolerant resource costs at a higher level. Future QCore could turn those programs and resource models into architecture-specific execution plans; it should not rebuild Qualtran's library.

### 9.14 Stim

**What it is:** a very fast stabilizer-circuit simulation and analysis tool, particularly useful for quantum error-correction circuits. See the [Stim repository and documentation](https://github.com/quantumlib/Stim).

**Relationship to QCore:** future specialised simulator/verification adapter for Clifford and QEC workloads.

**Proposed distinction:** Stim is deliberately specialised. QCore would orchestrate or consume it where applicable, not compete as a general simulator.

### 9.15 Riverlane / Deltaflow / Deltakit

**What they are:** Riverlane's products focus on quantum error correction, including real-time decoding/orchestration infrastructure and the Deltakit SDK for QEC circuit generation, simulation, decoding, and noise-analysis workflows. See the [Deltakit documentation](https://deltakit-docs.riverlane.com/en/stable/) and [Deltaflow product sheet](https://www.riverlane.com/assets/docs/Deltaflow_2_Product_Sheet_Stack_Sep_2025.pdf).

**Relationship to QCore:** later fault-tolerant/QEC integration boundary and specialist partner category.

**Proposed distinction:** Riverlane operates much closer to real-time QEC data and control. QCore should not claim to provide a decoder or real-time QEC stack. Its possible future role is higher-level logical planning, resource policy, and orchestration across compatible QEC stacks.

## 10. Competitive summary

| Category | Strong existing owners | QCore's proposed role |
|---|---|---|
| Circuit authoring and algorithms | Qiskit, Cirq, PennyLane, Classiq, Qualtran | Accept existing programs; do not force a new source language |
| Circuit compilation and synthesis | Qiskit, TKET, BQSKit, MQT, Classiq | Orchestrate a portfolio first; build native passes only where evidence shows a gap |
| Interchange / compiler IR | OpenQASM, QIR, MLIR-based stacks | Interoperate; do not declare a new universal standard |
| Multi-provider runtime/access | qBraid, Braket, TKET extensions, vendor SDKs | Add objective-aware planning, provenance, and policy; use adapters |
| Hybrid CPU/GPU/QPU | CUDA-Q, Braket Hybrid Jobs, PennyLane/Catalyst, MQSS | Later orchestration phase after core thesis is proven |
| Fault-tolerant algorithms and QEC | Qualtran, Stim, Riverlane, specialised research stacks | Later integration and logical planning; never pretend v0.1 solves QEC |

The moat, if QCore earns one, is not a static list of integrations. It is a trusted loop:

```text
program + objective + target state
        ↓
candidate decisions
        ↓
predicted outcomes
        ↓
real execution outcomes
        ↓
better validated policies and models
```

That loop must be built with consent, privacy, scientific validity, and careful separation between prediction and observation.

---

# Part IV — The QCore product model

## 11. Seven core abstractions

The entire system should be understandable through seven stable objects:

```text
Program + Target + Objective
             ↓
            Plan
             ↓
          Execution
             ↓
            Result

Every stage reads or creates immutable Artifacts.
```

These objects are not merely convenient Python classes. They are the contracts that allow the SDK, Rust engine, compiler adapters, provider adapters, cloud services, and provenance store to evolve without collapsing into provider-specific code.

### 11.1 `Program` — what computation is intended?

`Program` is QCore's normalized handle for a computation and its semantics.

Minimum fields:

```text
Program
├── program_id                    content-derived stable identifier
├── source_kind                   qiskit | openqasm2 | openqasm3_subset | ...
├── source_version
├── source_artifact_id            lossless original input
├── canonical_ir_artifact_id      QCore-normalized representation
├── semantics_profile             static-circuit-v1, later dynamic/hybrid profiles
├── qubits / classical_bits
├── parameters and binding state
├── required_capabilities
├── measurements and output schema
├── source locations / labels
└── user metadata                 names and tags, never executable policy
```

Required invariants:

- A Program is immutable. A transformation creates a new artifact and lineage edge.
- Import either preserves semantics or returns a structured unsupported/error result.
- Source artifacts are always retained so a lossy canonical conversion cannot become the only record.
- Parameterized and bound programs are distinguishable.
- Measurement ordering and classical-bit mapping are explicit.
- Credentials, provider tokens, and secrets never appear in a Program.

Founder mental model: the Program says **what** should be computed. It does not decide where or how.

### 11.2 `Target` — what can a particular execution destination do now?

`Target` is an immutable compilation-relevant snapshot.

Minimum fields:

```text
Target
├── target_id                     stable logical target identity
├── snapshot_id                   digest of this exact snapshot
├── provider_id / backend_id
├── acquired_at / source timestamps
├── schema_version
├── modality                      simulator, superconducting, trapped-ion, etc.
├── qubit count and identifiers
├── operations by valid qubit tuples
├── topology / connectivity
├── instruction errors and durations, with units and timestamps
├── readout properties
├── coherence data when available
├── timing / measurement constraints
├── supported control-flow capabilities
├── execution limits
├── availability / queue observation
├── pricing observation
└── missing-data and freshness indicators
```

Required invariants:

- Unknown data is represented as unknown, not as zero.
- Every measured/calibrated value carries a source and, when available, a timestamp.
- Units are explicit and machine-readable.
- The exact operation-to-qubit map is preserved; a simplified coupling graph must not erase richer target constraints.
- A snapshot is never silently refreshed in place.
- A planner may mark a Plan stale if the live target has materially changed, but it does not rewrite the old Plan.

IBM's current backend model exposes a Qiskit `Target`, operation availability, durations, properties, and historical target access; this is the source model for v0.1 ingestion. See the [IBMBackend API](https://quantum.cloud.ibm.com/docs/api/qiskit-ibm-runtime/ibm-backend).

Founder mental model: the Target is a **dated map of the roads**, not the road network itself.

### 11.3 `Objective` — what does “better” mean?

`Objective` is a serializable statement of hard constraints and preferences.

Minimum fields:

```text
Objective
├── objective_id
├── hard_constraints              must be satisfied
├── ordered_metrics or weights    how feasible plans are ranked
├── risk policy                   treatment of missing/uncertain estimates
├── tie-break policy
├── metric definitions + versions
└── human-readable intent
```

Examples:

```python
Objective(
    name="min_estimated_error",
    constraints={"max_compile_seconds": 120},
    ranking=[
        "estimated_error_proxy",
        "two_qubit_gate_count",
        "depth",
        "swap_count",
    ],
)
```

```python
Objective(
    name="bounded_experiment",
    constraints={
        "max_cost_gbp": 10.0,
        "max_queue_minutes": 30,
        "requires_dynamic_circuits": True,
    },
    ranking=["estimated_error_proxy", "estimated_total_latency"],
)
```

Required invariants:

- Hard constraints are evaluated before soft preferences.
- Every metric has a versioned definition.
- Missing values follow a declared policy: reject, penalise, or allow with warning.
- A friendly alias such as `highest_fidelity` must map to an explicit versioned objective. It must not imply measured fidelity when only a proxy exists.

Founder mental model: the Objective defines **what winning means**.

### 11.4 `Plan` — QCore's inspectable decision

`Plan` is the central QCore product. It is an immutable, executable decision record.

Minimum fields:

```text
Plan
├── plan_id
├── program_id
├── objective_id
├── target_snapshot_id
├── planner_policy + version
├── search budget and actual resource use
├── selected_candidate_id
├── compiler recipe, versions, options, and seeds
├── logical-to-physical mapping
├── executable_artifact_id
├── predicted metrics and uncertainty/missingness
├── feasibility validation
├── ranked alternatives / Pareto frontier
├── explanation and reason codes
├── created_at
└── freshness / expiry policy
```

A good plan explanation looks like:

```text
Selected: tket.default.o2.seed_7
Target snapshot: ibm_example@2026-08-09T11:20:00Z

Why selected:
- lowest estimated-error proxy among 18 valid candidates;
- 12 fewer two-qubit operations than the Qiskit level-3 baseline;
- depth 4.1% higher than the shallowest candidate, accepted because the
  objective ranks estimated error before depth;
- no hard constraints violated.

Runner-up:
- qiskit.sabre.o3.seed_3;
- estimated-error proxy +0.008;
- depth -17.

Warnings:
- target readout calibration was 5h 12m old at planning time;
- estimated error is an independence-model proxy, not measured fidelity.
```

Required invariants:

- `plan()` never submits a paid or remote job.
- The selected executable validates against the referenced Target snapshot.
- Every reason can be traced to a metric, constraint, policy, or warning.
- Failed candidates remain visible as summaries with structured failure reasons.
- Plans reference immutable artifacts; they do not contain mutable provider objects.

Founder mental model: the Plan says **how QCore proposes to do it and why**.

### 11.5 `Execution` — what is happening to the approved plan?

`Execution` is a stateful operational record created only when a plan is submitted.

State machine:

```text
CREATED
  ↓
VALIDATING
  ↓
SUBMITTING ───────────────→ FAILED_PRE_SUBMISSION
  ↓
QUEUED ──→ RUNNING ──→ SUCCEEDED
  │           │
  ├───────────┴──────────→ FAILED_PROVIDER
  └──────────────────────→ CANCEL_REQUESTED → CANCELLED | COMPLETED_LATE
```

Minimum fields:

```text
Execution
├── execution_id
├── plan_id
├── provider / backend reference
├── idempotency key
├── provider job identifier
├── state + state transition history
├── submission options             shots, resilience settings, etc.
├── timestamps
├── retry attempts and reasons
├── cost observations
├── logs/events artifact ids
└── raw result artifact id
```

Required invariants:

- Submission requires an explicit call or approval boundary.
- Retries are idempotent where the provider supports it; QCore must not accidentally pay for duplicate jobs.
- Provider state and QCore state are both retained when they differ.
- Credentials are resolved at execution time from secure configuration and never serialized into artifacts.
- Cancellation is best-effort and never misreported as guaranteed.

Founder mental model: the Execution says **what is happening now**.

### 11.6 `Result` — what did QCore receive and how should it be interpreted?

`Result` is the normalized scientific/operational output linked to the original raw provider response.

Minimum fields:

```text
Result
├── result_id
├── execution_id / plan_id
├── output kind                    counts, quasi-distribution, expectation, samples...
├── normalized data
├── logical output mapping
├── shots and successful shots
├── provider metadata
├── observed timing and cost
├── mitigation/post-processing lineage
├── raw_result_artifact_id
└── warnings / quality notes
```

Required invariants:

- Raw output is retained alongside normalized output.
- QCore never labels a mitigated or quasi-probability distribution as raw counts.
- Bit ordering and logical/physical mappings are explicit.
- Post-processing creates new artifacts with lineage; it does not overwrite the original result.
- Predictions in the Plan and observations in the Result remain distinct fields.

Founder mental model: the Result says **what came back**.

### 11.7 `Artifact` — the immutable evidence behind every object

`Artifact` is a content-addressed blob or structured manifest.

Examples:

- original Qiskit QPY or serialized input;
- OpenQASM source;
- canonical QCore IR;
- target snapshot;
- compiler recipe;
- compiled candidate;
- metric report;
- equivalence/validation report;
- plan explanation;
- provider request and response;
- logs and benchmark environment manifest.

Minimum fields:

```text
Artifact
├── artifact_id                    digest, e.g. sha256:...
├── media_type / schema_id
├── byte_size
├── created_at
├── producer component + version
├── parent artifact ids
├── content location
├── integrity status
├── sensitivity classification
└── retention policy
```

Required invariants:

- Content is immutable; changed content gets a new identifier.
- Hashes are calculated over canonical bytes where a canonical format exists.
- Schema and producer versions are recorded.
- Sensitive artifacts can be encrypted/access-controlled without changing scientific lineage.
- No secrets are ever valid artifact content.

Founder mental model: Artifacts are **the receipts**.

## 12. Minimal founder-facing API

The public API should reveal the mental model rather than the internal complexity:

```python
import qcore

program = qcore.Program.from_qiskit(circuit)
target = qcore.ibm.snapshot("ibm_backend_name")

plan = qcore.plan(
    program,
    targets=[target],
    objective=qcore.Objective.min_estimated_error(),
    budget=qcore.PlanningBudget(seconds=120, max_candidates=32),
)

plan.explain()
plan.export("plan.json")

# A separate, explicit external action:
execution = qcore.run(plan, shots=4_000)
result = execution.wait()
```

Design rules:

- The simple path is five concepts: import, snapshot, plan, explain, run.
- Advanced configuration is available but not required for ordinary use.
- No hidden external execution occurs during import or planning.
- Every public method returns stable QCore types, not unwrapped provider objects.
- The API uses precise names such as `estimated_error_proxy`; documentation may explain friendlier aliases.

---

# Part V — Software architecture

## 13. Architecture at a glance

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         USER SURFACES                               │
│  Python SDK  │  CLI  │  notebooks  │  later: service/API          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ typed Python API
                    ┌──────────▼──────────┐
                    │   PyO3 boundary    │
                    └──────────┬──────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         RUST QCORE CORE                             │
│ models │ validation │ planner policy │ metrics │ ranking │ lineage │
│ artifact manifests │ deterministic IDs │ native experimental passes│
└───────────────┬───────────────────────┬───────────────────────┬─────┘
                │                       │                       │
       candidate recipes        target snapshots        execution contract
                │                       │                       │
┌───────────────▼────────────┐ ┌────────▼─────────┐ ┌──────────▼──────────┐
│ COMPILER ADAPTER WORKERS   │ │ PROVIDER ADAPTERS│ │ RUNTIME / JOB STATE│
│ Qiskit │ TKET │ BQSKit     │ │ IBM first       │ │ submit/track/result│
│ later: CUDA-Q/MQT/etc.     │ │ later: others   │ │ retries/cancel     │
└───────────────┬────────────┘ └────────┬─────────┘ └──────────┬──────────┘
                └───────────────────────┼───────────────────────┘
                                        │
                             ┌──────────▼──────────┐
                             │ ARTIFACT/PROVENANCE│
                             │ local CAS first;   │
                             │ cloud object store │
                             │ and metadata later │
                             └─────────────────────┘

Compiler evolution path:
QCore circuit IR → MLIR-compatible dialect/lowering → QIR/LLVM/provider forms
```

## 14. Responsibility by layer

### 14.1 Python API

Python owns:

- founder/researcher-facing ergonomics;
- conversion from live Python objects such as `qiskit.QuantumCircuit`;
- optional dependency discovery;
- notebooks, examples, and plotting;
- compiler adapter packages that depend on Python ecosystems;
- IBM SDK integration in v0.1; and
- translating Python exceptions into stable QCore error types.

Python must not become a second source of truth for ranking, IDs, metric definitions, or provenance rules.

### 14.2 PyO3 boundary

PyO3 provides a thin, typed interface between Python and Rust.

It should:

- expose stable Rust-owned models to Python;
- convert bulk data efficiently;
- release the Python GIL around Rust-heavy work where safe;
- map Rust error enums into a documented Python hierarchy; and
- avoid Python callbacks deep inside Rust planning loops.

It should not:

- leak raw Rust lifetimes or internal graph structures;
- embed every external Python compiler in the Rust process; or
- create circular control where Rust calls Python, which calls Rust, unpredictably.

### 14.3 Rust core

Rust owns the invariants that must remain fast, deterministic, and reliable:

- core models and schema versions;
- canonical identifiers and hashing;
- typed circuit/region representation for supported semantics;
- validation and target-compatibility checks;
- planner policy and candidate recipe generation;
- common metric calculation;
- Pareto analysis and ranking;
- explanation reason codes;
- artifact manifests and lineage;
- runtime state machine contracts; and
- carefully selected QCore-native analysis/transform passes.

Rust is chosen for performance, memory safety, concurrency, packaging into native libraries/services, and stronger control over long-lived infrastructure. Rust does not remove the need for quantum/compiler expertise.

### 14.4 QCore IR and compiler layer

The IR needs several abstraction levels over time:

```text
Source-preserving representation
        ↓
High-level quantum/classical regions
        ↓
Gate-level canonical circuit IR
        ↓
Placed/routed target IR
        ↓
Scheduled/executable provider form
```

For v0.1, implement only the gate-level static-circuit subset required for fair candidate evaluation, with explicit measurements and mappings. Preserve unsupported source programs without pretending they were imported.

Each IR operation should have:

- an operation name and versioned semantics;
- typed quantum/classical operands and results;
- parameters with units/types;
- source location and lineage;
- attributes separated from execution secrets; and
- verifier rules.

The transformation contract is:

```text
input IR + pass configuration + seed
    → output IR + change summary + validation report
```

### 14.5 MLIR/LLVM/QIR compatibility strategy

[MLIR](https://mlir.llvm.org/) is designed as reusable, extensible compiler infrastructure for multiple abstraction levels and heterogeneous hardware. QIR is embedded in LLVM IR for hybrid quantum-classical interoperability. They are important strategic foundations, but they should not become a v0.1 dependency tax before the product hypothesis is tested.

Use a staged approach:

**From day one:**

- define typed operations, regions, verifiers, pass preconditions/postconditions, and deterministic textual/structured serialization in ways that map cleanly to MLIR concepts;
- keep control flow and quantum/classical data flow explicit;
- treat OpenQASM and QIR as interoperability forms, not the only canonical model; and
- document every loss during import/export.

**After the research kernel passes its gate:**

- prototype a QCore MLIR dialect or adopt/extend a credible existing quantum dialect;
- lower high-level QCore operations through placed/routed forms;
- integrate MLIR pass/diagnostic infrastructure where it creates measured engineering value; and
- implement tested lowering to QIR/LLVM conventions for compatible hybrid execution systems.

**Do not:**

- rewrite LLVM in Rust;
- invent an incompatible “universal” dialect without ecosystem review;
- force simple v0.1 candidate comparison through a large compiler stack; or
- claim QIR compatibility until round-trip/lowering tests exist.

### 14.6 Compiler adapter workers

Mature compiler SDKs have large, sometimes conflicting Python dependency graphs. QCore should isolate them behind versioned adapters.

Adapter contract:

```text
CompilerRequest
├── program artifact
├── target snapshot
├── recipe id + options
├── seed
├── timeout/resource limit
└── requested output profile

CompilerResponse
├── status
├── output artifact
├── logical/physical mapping
├── compiler-native metadata
├── logs artifact
├── wall/CPU time and peak memory
└── structured failure
```

v0.1 may run adapters locally for simplicity, but the protocol must allow separate processes or containers. Isolation provides:

- dependency reproducibility;
- timeouts and resource limits;
- crash containment;
- exact environment manifests; and
- later distributed candidate compilation.

All candidates must be converted into a common evaluation form. QCore must not compare a compiler's self-reported metric with another compiler's differently defined metric.

### 14.7 Planner

The planner has six steps:

1. **Capability filtering:** remove targets and recipes that cannot represent required semantics.
2. **Candidate generation:** create bounded `(target, compiler recipe, options, seed)` combinations.
3. **Materialisation:** execute compiler adapters under explicit budgets.
4. **Validation:** reject candidates that fail semantic, structural, or target checks.
5. **Evaluation and ranking:** calculate common metrics, identify non-dominated candidates, apply the Objective, and run deterministic tie-breakers.
6. **Explanation:** create a Plan plus alternatives, warnings, and evidence.

Planner policy must be versioned independently from the SDK. The same saved policy and inputs should reproduce the same candidate set unless an adapter is explicitly non-deterministic, in which case that limitation is recorded.

### 14.8 Provider adapters

Provider adapters have two deliberately separate faces:

```text
Discovery face: list backends, capture target snapshots, observe queue/price
Execution face: validate payload, submit, poll, cancel, retrieve raw result
```

A provider adapter must declare capabilities rather than relying on name-based assumptions.

Required capabilities include, as applicable:

- supported program/payload types;
- static versus dynamic circuits;
- shots and batching limits;
- parameterized execution;
- result types;
- cancellation support;
- historical target/calibration access;
- queue and price availability; and
- idempotency/retry semantics.

### 14.9 Runtime

The runtime owns operational reliability, not compilation quality.

Responsibilities:

- revalidate target/plan freshness policy before submission;
- require explicit user action for external execution;
- bind secure credentials at the last responsible moment;
- create an idempotency key and execution record;
- submit via the provider adapter;
- persist every state transition;
- use bounded, policy-safe retries;
- retrieve raw results before normalization; and
- attach observed cost/timing without overwriting predicted values.

Planning must remain useful without the runtime. Users should be able to benchmark and export plans entirely offline with saved Target snapshots.

### 14.10 Provenance and storage

Use a local content-addressed store for v0.1:

```text
.qcore/
├── objects/sha256/ab/cdef...      immutable bytes
├── manifests/                    typed artifact manifests
├── runs/                         plan/execution indexes
└── cache/                        explicitly disposable derived cache
```

The object store and the cache are not the same. A benchmark must not depend on a cache entry that can disappear without preserving its source artifacts.

Later QCore Cloud can map the same contract to object storage plus a relational metadata/index service. Local and cloud artifact IDs should remain portable where content is identical.

## 15. Cross-cutting engineering principles

### 15.1 Semantics before optimisation

A shallower wrong circuit is a failure. Semantic preservation and correct output mapping outrank every optimisation metric.

### 15.2 Missingness is data

Unknown calibration, queue, price, or duration values must remain unknown. Never convert absence into a favourable zero.

### 15.3 Predictions are not observations

An error model estimates. Hardware execution observes. Store and label them separately.

### 15.4 Determinism by default

Seeds, versions, environment manifests, target snapshots, and candidate ordering are captured. Non-determinism is opt-in or explicitly reported.

### 15.5 Explain every selection

If the planner cannot explain a choice with metrics and policy, it is not ready to automate expensive scientific execution.

### 15.6 Capability negotiation over vendor conditionals

Core logic should ask “does this target support mid-circuit measurement?” rather than “is this an IBM backend?” Provider-specific knowledge stays in adapters.

### 15.7 Stable schemas, replaceable algorithms

Objects and provenance contracts should evolve carefully. Compiler passes, ranking policies, and estimators should remain replaceable and versioned.

### 15.8 Local-first research, cloud-ready contracts

v0.1 should run locally and offline with saved targets. Its object and adapter contracts should permit later services without requiring a premature distributed system.

### 15.9 Safe external actions

Compilation and planning are local/read-only with respect to providers. Submission, spending, sharing data, or changing provider state requires explicit action and policy checks.

### 15.10 Evidence over architecture theatre

No component is justified merely because LLVM, Rust, AI, agents, GPUs, or “operating systems” sound strategic. Each phase must produce measured user or technical value.

---

# Part VI — QCore v0.1 specification

## 16. v0.1 mission

**QCore v0.1 is a local-first, IBM-targeted research kernel that tests whether an explainable compiler-portfolio planner can select better target-compatible circuits than strong single-tool defaults.**

It is intentionally not the full QCore vision.

### 16.1 Primary research question

For supported static circuits, a fixed IBM Target snapshot, and equal declared planning budgets:

> Does generating and independently evaluating candidates from Qiskit, TKET, BQSKit, and small QCore-native experimental pipelines produce a selected candidate with a material advantage in estimated error, two-qubit gate count, circuit depth, or routing overhead—often enough to justify the added complexity and latency?

### 16.2 Primary user story

```text
As a quantum researcher with a Qiskit or OpenQASM circuit,
I want QCore to compare credible compilation strategies for a saved IBM target,
so I can inspect a strong candidate, see why it was selected,
and reproduce the decision without manually tuning several compilers.
```

### 16.3 v0.1 deliverable

A researcher can run:

```python
program = qcore.load("workload.qasm")
target = qcore.ibm.snapshot("ibm_backend_name")

plan = qcore.plan(
    program,
    targets=[target],
    objective="min_estimated_error_v1",
    budget={"seconds": 120, "max_candidates": 32},
)

print(plan.explain())
plan.save("plan.qcore.json")
```

and receive:

- the selected compiled circuit;
- a ranked candidate table;
- common metrics;
- validation confidence;
- exact compiler recipes, versions, seeds, and resource use;
- the immutable IBM Target snapshot;
- warnings about missing or stale data; and
- all artifacts required to replay the planning decision.

### 16.4 v0.1 non-goal

Remote IBM submission is **not required to pass v0.1**. A small, opt-in IBM executor may be added after the planning gate, but planning quality and reproducibility must be proven independently of provider spending and queue behaviour.

## 17. Supported program contract

### 17.1 Qiskit input

Required:

- `qiskit.QuantumCircuit` input through the Python SDK;
- QPY or another versioned, loss-aware serialized source artifact;
- named quantum and classical registers;
- standard one- and two-qubit unitary gates;
- gate parameters bound to numeric values before planning;
- barriers, with an explicit preserve/remove policy;
- terminal measurements; and
- custom composite gates only when they contain a definition QCore can safely decompose.

Compile-only mode may accept a unitary circuit with no measurements.

Not supported in the v0.1 semantic profile:

- mid-circuit measurement or reset;
- classical conditions or dynamic control flow;
- loops, branches, subroutine recursion, or real-time feed-forward;
- pulse programs or calibration definitions;
- delay/timing intent that must be preserved semantically;
- symbolic parameters not bound before planning;
- arbitrary noise channels;
- opaque custom operations without definitions; and
- circuits requiring more qubits than the chosen Target.

Unsupported input returns a structured error containing the operation, source location if available, required capability, and the semantic profile that rejected it. QCore must never silently drop an unsupported operation.

### 17.2 OpenQASM input

Required:

- OpenQASM 2 static-circuit input used by standard benchmark suites;
- a documented OpenQASM 3 **subset** covering declarations, supported gate invocations, numeric parameters, and terminal measurement; and
- lossless storage of the original text artifact.

Explicitly outside the OpenQASM 3 subset:

- runtime classical arithmetic and control flow;
- loops and complex subroutines;
- timing boxes, delays with required semantics, and stretch values;
- `defcal`, OpenPulse, waveform, frame, and port constructs;
- extern functions;
- mid-circuit measurement/feed-forward; and
- implementation-defined pragmas unless an adapter explicitly supports them.

OpenQASM 3 supports much more than a static circuit; the parser must not advertise “OpenQASM 3 support” without the word **subset** until conformance expands.

### 17.3 Canonical v0.1 semantics

The v0.1 canonical representation contains:

- qubits and classical bits;
- ordered/partially ordered gate operations;
- numeric parameters;
- barriers as policy-bearing annotations;
- terminal measurements;
- source locations;
- logical output mapping; and
- transformation lineage.

Each import produces:

```text
source artifact
    ↓ parse/import report
canonical Program artifact
    ↓ semantic-profile validation
validated Program or structured rejection
```

## 18. IBM Target ingestion

### 18.1 Source

The IBM adapter obtains a backend through the supported `qiskit-ibm-runtime` service API and captures the Qiskit `BackendV2`/`Target` information available at that time.

It must save two artifacts:

1. a source-faithful IBM/Qiskit snapshot sufficient for later debugging; and
2. a normalized QCore Target manifest used by the planner.

### 18.2 Required normalized fields

- backend/provider identity and reported version;
- acquisition timestamp and calibration/source timestamps;
- number and identity of qubits;
- operation names and exact valid qubit tuples;
- operation parameters relevant to validation;
- topology derived without discarding operation-specific directionality;
- gate error and duration per operation/qubit tuple when available;
- readout error per qubit when available;
- qubit properties such as T1/T2 only when supplied and correctly unit-normalized;
- timing constraints and `dt` when available;
- measurement constraints when available;
- supported dynamic-circuit feature flags, even though v0.1 input does not use them;
- operational status and pending-job observation as separate, time-sensitive fields; and
- a complete missing-data map.

### 18.3 Freshness policy

The snapshot stores age; it does not decide truth. v0.1 defines:

- `fresh`: acquired within a user-configurable planning window;
- `stale_allowed`: older than the window but explicitly permitted for offline benchmarking; and
- `stale_rejected`: disallowed by the Objective or execution policy.

Offline benchmarks must use saved snapshots so every compiler sees exactly the same target. Live target refresh during a candidate portfolio run is forbidden because it would make the comparison unfair.

### 18.4 Test targets

The repository must contain small, license-compatible synthetic target fixtures representing:

- line topology;
- heavy-hex-like sparse topology;
- all-to-all topology;
- asymmetric errors;
- missing duration/error fields; and
- faulty/unavailable qubits or edges.

Continuous integration uses fixtures and never requires live IBM credentials.

## 19. Compiler portfolio

### 19.1 Candidate recipe model

Every candidate is generated from a versioned recipe:

```text
CandidateRecipe
├── recipe_id
├── adapter_id + adapter version
├── compiler package versions
├── pass/pipeline configuration
├── target snapshot id
├── seed policy
├── semantic preconditions
├── timeout and resource budget
└── expected output profile
```

Recipes are data, not scattered conditional code. A benchmark report can therefore state exactly what “Qiskit baseline” or “TKET candidate” meant.

### 19.2 Qiskit candidates

Required initial recipes:

- preset pass manager optimisation level 0 as a feasibility/control baseline;
- levels 1, 2, and 3;
- a documented set of layout/routing methods where supported;
- multiple deterministic transpiler seeds for stochastic pipelines; and
- optionally, IBM AI-powered passes as a separately labelled recipe family when installed and their beta/version status is recorded.

Rules:

- Use the same saved Target data for every recipe.
- Keep Qiskit's final layout and classical-bit mapping.
- Capture a post-routing/pre-final-decomposition artifact when needed to count explicit routing operations.
- Treat the strongest sensible Qiskit configuration—not only defaults—as a go/no-go baseline.

### 19.3 TKET candidates

Required initial recipes:

- target-constraint satisfaction with optimisation levels/pipelines equivalent to ordinary recommended use;
- at least one stronger optimisation pipeline using documented TKET passes where applicable;
- deterministic placement/routing configuration where possible; and
- conversion artifacts on both sides of the TKET boundary.

Rules:

- Rebase to the same IBM Target operation set used for Qiskit evaluation.
- Preserve TKET's initial/final maps.
- Validate output independently in QCore; `Backend.valid_circuit` or predicates are useful but not the sole evaluator.

### 19.4 BQSKit candidates

Required initial recipes:

- a standard BQSKit compile workflow against a QCore-derived `MachineModel`; and
- one bounded synthesis/optimisation recipe for eligible unitary regions.

Rules:

- Apply only when semantic and size preconditions are satisfied.
- Separate terminal measurements before eligible unitary-region compilation and restore them with verified mapping.
- Use strict timeouts because numerical synthesis can be expensive.
- Record approximation thresholds and synthesis distance metrics.
- Never compare an approximate candidate as semantically exact; approximation becomes a hard constraint or declared objective dimension.

### 19.5 QCore-native experimental candidates

v0.1 may implement a small pass engine and conservative transformations such as:

- identity removal;
- adjacent inverse cancellation;
- numeric rotation normalization and safe rotation merging;
- redundant barrier cleanup under an explicit policy;
- local commutation/cancellation rules reviewed for the supported gate set; and
- a simple topology-aware layout/routing heuristic used only as an experimental baseline.

Native passes must have:

- precise preconditions;
- property-based and example tests;
- semantic verification on generated small circuits;
- deterministic behaviour under a saved seed;
- transformation statistics; and
- explicit `experimental` labels.

v0.1 should not attempt a novel general-purpose synthesis engine, an ML planner, or a full replacement for SABRE/TKET/BQSKit.

### 19.6 Portfolio budget

Planning is bounded by:

- maximum wall-clock time;
- maximum candidate count;
- per-adapter timeout;
- seed count;
- optional CPU/memory limits; and
- optional quality target for early stopping.

The planner records both requested and actual resource use. A candidate terminated by budget is `timed_out`, not “worse.”

For fair benchmarks, compare:

1. **default-budget baselines** reflecting normal user behaviour; and
2. **equal-budget strong baselines** given comparable time/seed resources to QCore.

QCore must not claim an advantage obtained solely by spending 100 times more compilation time than the baseline.

## 20. Candidate validation

Validation is layered because arbitrary quantum-program equivalence is difficult and large state-vector comparisons are expensive.

### 20.1 Layer A — schema and adapter validation

- response schema is valid;
- artifact hashes match;
- compiler completed without truncated output;
- mapping metadata is present; and
- output parses into the supported QCore representation.

### 20.2 Layer B — target compatibility

- every operation exists on the referenced Target for its exact qubit tuple;
- qubit indices are in range and not marked unavailable by the snapshot policy;
- topology/directionality constraints are satisfied;
- required measurement/timing predicates hold; and
- no unsupported abstract gate remains.

### 20.3 Layer C — semantic verification

Verification levels are recorded, never blurred:

| Level | Method | Intended use |
|---|---|---|
| `exact_small` | Compare unitaries/state vectors up to global phase after accounting for qubit permutation; terminal measurements checked separately. | Small supported circuits. |
| `randomized_medium` | Test multiple deterministic random input states or observable samples, with declared numeric tolerance. | Medium unitary regions where exact matrices are too costly. |
| `structural_large` | Target checks, mapping checks, pass invariants, compiler-native checks, and any available transformation certificates. | Large circuits; lower confidence. |
| `unverified` | No adequate semantic method. | Never eligible for automatic selection by default. |

The benchmark report must stratify results by verification level. Strong product claims should rest on `exact_small` and carefully designed `randomized_medium` cohorts, not only structurally valid large circuits.

### 20.4 Measurement and mapping validation

Terminal measurements are removed when comparing the unitary body, then restored and checked against:

- logical-to-physical layout;
- physical-to-logical final permutation;
- classical register/bit order; and
- provider result ordering.

Many apparently “equivalent” circuits produce misinterpreted results because the final mapping is lost. QCore treats mapping as part of semantics.

## 21. Common metric definitions

Every compiler candidate is evaluated by QCore's own versioned metric implementation after normalization to the same target basis/profile.

### 21.1 `depth_v1`

The minimum number of operation layers under QCore's documented dependency model, after target lowering. Report separately:

- `quantum_depth`;
- `two_qubit_depth`; and
- `duration_critical_path` when reliable instruction durations exist.

Do not compare one compiler's pre-routing depth with another's post-routing depth.

### 21.2 `two_qubit_gate_count_v1`

Count all two-qubit target operations after final target lowering. Also report counts by gate type and physical edge.

This metric is important because two-qubit operations are often noisier, but it is not identical to fidelity.

### 21.3 `swap_count_v1`

Count explicit logical routing SWAP actions at the post-routing, pre-final-decomposition stage.

Problems and policy:

- A compiler may absorb a SWAP into a final permutation or decompose it immediately.
- Different native gates make “one SWAP” an uneven cost.
- If the adapter cannot recover a comparable routing-stage count, the value is `unknown`, not zero.

Therefore also report:

- routing-added two-qubit operations relative to the unrouted/rebased body where measurable; and
- final mapping permutation.

The default objective does not reward a candidate merely because its SWAP count is unknown.

### 21.4 `estimated_error_proxy_v1`

Use one common, transparent independent-error proxy over the final physical operations. A minimal form is:

```text
log_success_proxy = Σ log(1 - operation_error_i)
                  + Σ log(1 - readout_error_j)

estimated_error_proxy = 1 - exp(log_success_proxy)
```

Rules:

- Use the Target's error value for the exact operation and qubit tuple.
- Include only final measured qubits in the readout term.
- Record which terms were missing.
- Reject, penalise, or fall back according to the Objective's missing-data policy.
- Never call this value “circuit fidelity” without the word **estimated** and the model version.

Known limitations:

- assumes independent errors;
- ignores coherent error accumulation, crosstalk, drift, leakage, and much context dependence;
- calibration error values may not predict application performance;
- omits decoherence unless a later separately versioned duration model is used; and
- is not a substitute for real-hardware application-level validation.

### 21.5 Operational metrics

Track but do not mix silently into circuit quality:

- compiler wall time;
- CPU time;
- peak memory;
- timeout/failure rate;
- cache status;
- artifact size; and
- planner total latency.

## 22. Ranking and selection

### 22.1 Selection pipeline

```text
all materialized candidates
        ↓
schema + semantic + target validation
        ↓
hard Objective constraints
        ↓
metric completeness / missing-data policy
        ↓
Pareto frontier
        ↓
objective-specific ordering
        ↓
deterministic tie-break
        ↓
selected Plan
```

A candidate is **Pareto dominated** when another valid candidate is no worse on every active quality metric and strictly better on at least one. Dominated candidates remain in provenance but normally do not win.

### 22.2 Default objective

`min_estimated_error_v1` uses lexicographic ordering:

1. minimise `estimated_error_proxy_v1`;
2. minimise `two_qubit_gate_count_v1`;
3. minimise `depth_v1`;
4. minimise `swap_count_v1` when comparable; and
5. minimise compiler wall time as the final quality-neutral tie-break.

This is deliberately transparent. It avoids hiding arbitrary trade-offs inside one magic score.

### 22.3 Optional balanced objective

`balanced_nisq_v1` may calculate a weighted normalized regret across error proxy, two-qubit gates, depth, and comparable routing overhead. The Plan must expose:

- metric values before normalization;
- normalization method and candidate range;
- weights;
- sensitivity analysis showing whether a modest weight change changes the winner; and
- correlation warnings, because estimated error and two-qubit count are not independent.

Weighted scoring is never the only view; the Pareto frontier and raw metrics remain available.

### 22.4 Deterministic tie-breaking

If active metrics are equal within documented tolerances, choose by:

1. higher semantic-verification confidence;
2. fewer missing target properties;
3. lower compilation resource use; and
4. stable lexical candidate ID.

### 22.5 Explainability contract

Every Plan explanation contains:

- a one-sentence selection reason;
- hard constraints and their pass/fail status;
- selected metrics;
- comparison with the default Qiskit baseline and runner-up;
- Pareto-front membership;
- compiler recipe and seed;
- target snapshot age and missing data;
- semantic-verification level;
- approximation information;
- budget/timeouts and candidates not completed; and
- model limitations, particularly for error estimation.

## 23. Required artifacts and outputs

One planning run must create at least:

```text
planning-run/
├── program.source.*
├── program.canonical.qcore.json
├── import-report.json
├── target.source.*
├── target.qcore.json
├── objective.json
├── planning-budget.json
├── environment-lock.json
├── candidates/
│   └── <candidate-id>/
│       ├── recipe.json
│       ├── compiler-input.*
│       ├── compiler-output.*
│       ├── mapping.json
│       ├── validation.json
│       ├── metrics.json
│       └── logs.*
├── pareto-front.json
├── ranking.json
├── plan.qcore.json
└── explanation.md
```

The physical layout may be content-addressed rather than directory-based, but the logical manifest must expose this structure.

## 24. CLI and API surface

Required CLI workflows:

```bash
qcore target snapshot ibm <backend> --output target.qcore.json
qcore inspect program workload.qasm
qcore plan workload.qasm --target target.qcore.json --objective min_estimated_error_v1
qcore explain <plan-id>
qcore candidates <plan-id>
qcore replay <plan-id> --offline
qcore benchmark benchmarks/smoke.yaml
```

Required Python surfaces:

```python
qcore.Program.from_qiskit(...)
qcore.Program.from_openqasm(...)
qcore.ibm.snapshot(...)
qcore.Target.load(...)
qcore.Objective(...)
qcore.PlanningBudget(...)
qcore.plan(...)
qcore.Plan.load(...)
qcore.replay(...)
```

`qcore.run()` is excluded from the v0.1 acceptance gate or shipped as an experimental, separately enabled subphase after safe IBM submission tests.

## 25. Error model

Errors must be typed and actionable:

```text
QCoreError
├── ImportError
│   ├── UnsupportedOperation
│   ├── UnsupportedControlFlow
│   └── ParseError
├── TargetError
│   ├── SnapshotUnavailable
│   ├── IncompleteTarget
│   └── StaleTarget
├── CompilerAdapterError
│   ├── DependencyUnavailable
│   ├── TimedOut
│   ├── Crashed
│   └── InvalidAdapterResponse
├── ValidationError
│   ├── SemanticMismatch
│   ├── TargetViolation
│   └── OutputMappingInvalid
├── PlanningError
│   ├── NoFeasibleCandidates
│   ├── BudgetExhausted
│   └── ObjectiveUnsatisfied
└── ArtifactError
    ├── IntegrityFailure
    ├── SchemaUnsupported
    └── MissingArtifact
```

The user-facing error includes what failed, the affected candidate/operation, what QCore tried, and a safe next action. Raw adapter traces are retained in logs but not dumped as the only explanation.

## 26. v0.1 non-functional requirements

### Reproducibility

- Same saved inputs, locked adapter environments, recipes, and seeds produce the same candidate set and selection within documented numeric determinism limits.
- An offline replay requires no provider account.

### Safety

- `plan()` performs no remote submission.
- IBM credentials are never written to logs or artifacts.
- External compiler workers have bounded timeouts.

### Integrity

- Every artifact is hash-verified when read.
- Schema migration is explicit and tested.
- Selected candidates must pass target validation and a permitted semantic-verification level.

### Performance

- Core parsing, metrics, and ranking overhead is reported separately from external compiler time.
- The planner respects its wall-time/candidate budget within a documented shutdown tolerance.
- Large candidate artifacts are streamed or referenced rather than repeatedly copied across PyO3.

### Usability

- A founder/researcher can understand `explanation.md` without reading compiler source code.
- Installation clearly distinguishes the core package from optional compiler/provider extras.
- Missing optional compilers reduce the portfolio with a warning; they do not corrupt the run.

### Compatibility

- The release publishes an exact supported matrix for Python, Rust, Qiskit, pytket, BQSKit, and IBM Runtime versions.
- Each adapter has contract tests against that matrix.

## 27. v0.1 completion criteria

v0.1 is complete only when all are true:

1. Qiskit and supported OpenQASM inputs import with loss/unsupported-feature reports.
2. An IBM Target can be captured, normalized, saved, reloaded, and hash-verified.
3. Qiskit, TKET, BQSKit, and at least one QCore-native experimental recipe can produce candidates on eligible tests.
4. Candidate target validation uses one shared evaluator.
5. Tiered semantic checks detect deliberately injected wrong mappings and wrong transformations.
6. Depth, two-qubit count, comparable SWAP/routing overhead, and estimated-error proxy have versioned definitions and golden tests.
7. The planner applies constraints, Pareto analysis, ranking, and deterministic ties correctly.
8. Every Plan explains its decision relative to the Qiskit baseline and runner-up.
9. A saved plan can be replayed offline from immutable artifacts.
10. The benchmark harness produces machine-readable data and a founder-readable report.
11. No test or ordinary planning path requires live execution credentials.
12. The falsification/go-no-go experiment in Part IX has been run and independently reviewed.

---

# Part VII — Repository specification

## 28. Proposed repository layout

The repository should make product boundaries visible. It should not be organised as one large `qcore` package containing compiler, cloud, provider, and experiment code with hidden dependencies.

```text
qcore/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── Cargo.toml                         Rust workspace
├── Cargo.lock
├── rust-toolchain.toml
├── pyproject.toml                     Python package/workspace configuration
│
├── crates/
│   ├── qcore-model/                   Program, Target, Objective, Plan, etc.
│   ├── qcore-ir/                      supported typed circuit IR + verifier
│   ├── qcore-target/                  target normalization and capability model
│   ├── qcore-metrics/                 versioned common metric implementations
│   ├── qcore-planner/                 recipes, Pareto analysis, ranking, explanation
│   ├── qcore-artifacts/               hashing, manifests, local content store
│   ├── qcore-provenance/              lineage and environment manifests
│   ├── qcore-runtime-contract/        state model; no provider SDK dependency
│   ├── qcore-native-passes/           explicitly experimental native transforms
│   └── qcore-python/                  thin PyO3 bindings
│
├── python/
│   └── qcore/
│       ├── __init__.py
│       ├── api/                       friendly Python API
│       ├── cli/                       command-line surface
│       ├── io/                        Qiskit/OpenQASM import-export
│       ├── adapters/
│       │   ├── protocol/              request/response types and harness
│       │   ├── compilers/
│       │   │   ├── qiskit/
│       │   │   ├── tket/
│       │   │   └── bqskit/
│       │   └── providers/
│       │       └── ibm/
│       ├── explain/                   text/tables/plots from Rust reason codes
│       └── _native.*                  built extension
│
├── schemas/
│   ├── program/
│   ├── target/
│   ├── objective/
│   ├── plan/
│   ├── execution/
│   ├── result/
│   └── artifact/
│
├── recipes/
│   ├── qiskit/
│   ├── tket/
│   ├── bqskit/
│   └── qcore_native/
│
├── benchmarks/
│   ├── README.md
│   ├── manifests/                    frozen benchmark definitions
│   ├── runners/                      orchestration only
│   ├── analysis/                     statistical/report code
│   ├── baselines/                    exact baseline recipes
│   └── reports/                      versioned generated results, not hand-edited claims
│
├── fixtures/
│   ├── programs/
│   ├── targets/
│   ├── adapter_responses/
│   └── corrupt_artifacts/            integrity/error tests
│
├── tests/
│   ├── rust/
│   ├── python/
│   ├── contracts/                    cross-language/adapter contracts
│   ├── golden/                       stable metrics and explanations
│   ├── property/                     generated circuit/pass invariants
│   ├── integration/                  optional compiler extras
│   └── end_to_end/                   offline planning and replay
│
├── docs/
│   ├── concepts/
│   ├── specification/
│   ├── decisions/                    architecture decision records (ADRs)
│   ├── adapters/
│   ├── metrics/
│   └── tutorials/
│
├── examples/
│   ├── 01_import_qiskit.py
│   ├── 02_snapshot_ibm_target.py
│   ├── 03_plan_offline.py
│   └── 04_explain_and_replay.py
│
└── tools/                             developer utilities; never runtime dependencies
```

## 29. Dependency rules

1. Core Rust crates do not import Python/provider SDKs.
2. `qcore-model` depends on no compiler adapter.
3. `qcore-metrics` evaluates normalized QCore models, not live Qiskit/TKET objects.
4. `qcore-planner` sees adapter capabilities and responses through contracts.
5. Provider adapters cannot mutate planner policy.
6. Compiler adapters cannot select their own winner.
7. The Python API may depend on the native binding; native Rust never depends on friendly Python presentation code.
8. Benchmark analysis is not imported by production SDK code.
9. Cloud-specific code, when it exists, lives outside or above the reusable OSS core.
10. Experimental code is feature-gated and labelled; it does not silently become a default.

## 30. Package strategy

Suggested installation layers:

```text
qcore-core                Rust engine + minimal Python SDK
qcore[qiskit]             Qiskit import/compiler support
qcore[tket]               TKET adapter
qcore[bqskit]             BQSKit adapter
qcore[ibm]                IBM target/provider adapter
qcore[portfolio]          supported v0.1 compiler portfolio
```

Exact package names can change, but optional dependencies must be explicit. A user who only wants offline plan inspection should not install every provider SDK.

## 31. Test architecture

The minimum test pyramid is:

- **Unit tests:** model invariants, hashing, metric formulas, ranking, errors.
- **Golden tests:** canonical serialization, known target metrics, explanation text structures.
- **Property tests:** generated small circuits for pass preservation and mapping round trips.
- **Contract tests:** every adapter responds to the same request/response rules.
- **Differential tests:** compare import/export and metrics against trusted libraries where appropriate.
- **Integration tests:** real optional compiler packages in pinned environments.
- **Offline end-to-end tests:** source → candidates → plan → replay using fixtures.
- **Credentialed smoke tests:** manually/securely triggered target ingestion; never required for normal pull requests.

Any live-hardware test must be separately budgeted, rate-limited, and explicitly approved.

---

# Part VIII — Evidence-gated build phases

The roadmap is ordered by uncertainty, not by how impressive a feature sounds. No later phase starts merely because the preceding code exists; it starts when the preceding evidence gate passes.

## 32. Phase 0 — Problem discovery and baseline map

**Question:** Is execution-planning pain real and important to users?

Deliverables:

- interview quantum researchers, compiler engineers, hardware teams, and application developers;
- map existing workflows and where manual compiler/target decisions occur;
- reproduce strong Qiskit, TKET, BQSKit, qBraid, and relevant MQT/Benchpress baselines;
- define benchmark strata and preregister go/no-go thresholds; and
- recruit independent quantum/compiler advisers.

Gate to proceed:

- repeated evidence of the problem from multiple user groups;
- at least five credible design partners willing to review results or try the kernel;
- baselines successfully reproduced; and
- advisers agree the v0.1 question is technically meaningful.

Stop/pivot signal:

- users do not make or care about these decisions;
- defaults are already consistently sufficient;
- or the problem is primarily access/pricing rather than compilation/planning.

## 33. Phase 1 — Correct research kernel

**Question:** Can QCore represent inputs/targets and compare compiler outputs without corrupting semantics?

Deliverables:

- supported Qiskit/OpenQASM import;
- canonical static-circuit representation;
- IBM Target snapshot ingestion;
- isolated Qiskit/TKET/BQSKit adapters;
- common metrics;
- tiered semantic/target validation; and
- artifact/provenance foundation.

Gate to proceed:

- zero unexplained semantic mismatches on the verified acceptance suite;
- deliberate mapping and gate corruption is detected;
- target/metric golden tests pass; and
- offline replay reproduces all kernel artifacts.

Stop/pivot signal:

- conversion loss or dependency fragility makes fair comparison unreliable;
- or the team cannot define a trustworthy common evaluator.

## 34. Phase 2 — Explainable planner (QCore v0.1)

**Question:** Does portfolio selection create material technical advantage?

Deliverables:

- Objective and PlanningBudget;
- recipe/seed portfolio generation;
- Pareto/ranking engine;
- Plan and explanation;
- benchmark harness and independent report; and
- founder-friendly Python/CLI workflow.

Gate to proceed:

- predeclared portfolio-uplift threshold passes on held-out benchmarks;
- no correctness regression;
- advantage survives equal-budget strong baselines;
- planning overhead is acceptable for the target workflow; and
- external reviewers can reproduce the report.

Stop/pivot signal:

- multi-seed Qiskit or one strong compiler matches the portfolio almost everywhere;
- improvements are tiny, cherry-picked, or too slow;
- or selection is driven by an error proxy that lacks hardware relevance.

## 35. Phase 3 — Runtime and real-outcome validation

**Question:** Do plans submit reliably, and do predicted rankings relate to real execution outcomes?

Deliverables:

- explicit IBM execution workflow;
- runtime state machine, idempotency, retries, cancellation, and raw results;
- predicted-versus-observed analysis;
- target freshness revalidation;
- cost controls and execution budgets;
- result normalization and end-to-end provenance; and
- second provider only after IBM reliability.

Gate to proceed:

- no duplicate paid submissions in fault-injection tests;
- execution/result lineage is complete;
- selected plans improve a preregistered application-level outcome on repeated hardware experiments, not only static proxies;
- failure recovery is reliable; and
- one additional provider can be integrated through the same contracts without core rewrites.

Stop/pivot signal:

- calibration-based rankings do not correlate usefully with observed outcomes;
- provider differences cannot fit a coherent capability model;
- or operational cost exceeds user value.

## 36. Phase 4 — QCore-native compiler and MLIR layer

**Question:** Is there a specific compiler capability QCore can own better than the portfolio alone?

This phase begins only after benchmark evidence identifies recurring gaps, such as a workload family, target modality, routing objective, or cross-region optimisation existing engines handle poorly.

Deliverables:

- research-backed native passes aimed at identified gaps;
- pass precondition/postcondition and verification framework;
- MLIR dialect/adoption decision based on a prototype;
- lowering to QIR/LLVM-compatible forms where needed;
- target-aware cost models calibrated against results; and
- upstream contributions to existing ecosystems when they are the better home.

Gate to proceed:

- native passes beat portfolio baselines on held-out applicable workloads;
- correctness has independent expert review;
- MLIR adds measurable reuse/interoperability or engineering velocity; and
- maintenance cost is justified by adoption or performance.

Stop/pivot signal:

- the “native” advantage disappears outside training benchmarks;
- existing projects accept equivalent upstream improvements;
- or QCore becomes an expensive compiler reimplementation without planner differentiation.

## 37. Phase 5 — QCore Cloud and QPlanck Labs integration

**Question:** Will teams pay for managed execution intelligence and collaboration?

Deliverables:

- managed, isolated compiler workers;
- team artifact/provenance workspace;
- target/calibration history;
- policy-controlled multi-provider execution;
- queues, quotas, budgets, audit logs, RBAC/SSO where justified;
- private adapters and organisation policies; and
- QPlanck Labs experience consuming public QCore APIs.

Gate to proceed:

- repeated workloads justify managed infrastructure;
- design partners show willingness to pay;
- unit economics for planning/execution are credible;
- security review passes; and
- OSS users retain a genuinely useful local product.

Stop/pivot signal:

- users want only the local library;
- managed compilation has no recurring value;
- or cloud costs/data obligations overwhelm the business.

## 38. Phase 6 — Hybrid CPU/GPU/QPU orchestration

**Question:** Can QCore optimise an entire heterogeneous workflow, not only a circuit?

Deliverables:

- a workflow graph with typed classical and quantum nodes;
- data placement and serialization contracts;
- latency/cost/resource objectives across CPU, GPU, simulator, and QPU;
- asynchronous and iterative execution;
- integration with CUDA-Q, Braket Hybrid Jobs, HPC schedulers, or other credible substrates rather than unnecessary replacement; and
- observability across the whole workflow.

Gate to proceed:

- real application workloads show material end-to-end advantage;
- orchestration overhead is smaller than saved latency/cost;
- failure semantics are understandable; and
- the product is not merely a thin workflow engine with quantum branding.

Stop/pivot signal:

- users prefer existing heterogeneous runtimes;
- QPU time is not the bottleneck QCore can improve;
- or workflow portability destroys access to target-specific performance.

## 39. Phase 7 — Fault-tolerant and QEC-aware QCore

**Question:** Can QCore plan useful logical computations across fault-tolerant architectures and QEC stacks?

Deliverables:

- logical operations, error budgets, code parameters, magic-state/resource models, and factory constraints in the Target/Objectives;
- Qualtran or equivalent fault-tolerant program/resource integration;
- QIR/other logical execution lowering where appropriate;
- QEC experiment/simulator adapters such as Stim/Deltakit where scientifically valid;
- boundaries to real-time decoding/control systems such as Riverlane's stack; and
- architecture-specific space-time-resource planning.

Gate to proceed:

- fault-tolerant/QEC specialists co-own the specification;
- resource estimates are validated against accepted literature/tools;
- partner hardware/QEC teams confirm the abstractions are useful;
- and QCore offers a specific planning advantage instead of generic future-proofing.

Stop/pivot signal:

- the abstraction hides decisive architecture details;
- estimates cannot be validated;
- or the field standardises on a layer QCore should simply support.

## 40. Roadmap rule

The roadmap is not cumulative permission to build everything. A later phase may be skipped, partnered, or abandoned. QCore can be a successful planner/provenance product without becoming a full compiler, cloud, hybrid runtime, or QEC stack.

---

# Part IX — Success metrics, benchmarks, falsification, and gates

## 41. What “number-one SDK” should mean

“Number one” is not an engineering specification. It becomes useful only when translated into evidence.

QCore should not define leadership as:

- most Python methods;
- most logos on an integrations page;
- most GitHub stars alone;
- fastest on one hand-selected circuit;
- lowest estimated error under its own private metric; or
- a claim that every program should be rewritten in QCore.

A defensible long-term definition is:

> **For important quantum workloads, researchers choose to pass their existing programs through QCore because it reliably gives them a better-understood, high-quality, reproducible execution plan.**

That requires four classes of evidence:

| Evidence class | Question |
|---|---|
| Correctness | Does QCore preserve the intended computation and mapping? |
| Technical advantage | Does planning produce better candidates under fair budgets? |
| User value | Do real users adopt and trust the workflow? |
| Commercial value | Will teams pay for managed/reliable capabilities? |

## 42. North-star and supporting metrics

### 42.1 v0.1 north-star metric

**Material portfolio uplift rate:** the proportion of eligible held-out workloads on which the QCore-selected plan improves the primary Objective metric by at least a preregistered threshold versus the strongest equal-budget single-tool baseline, while preserving correctness and hard constraints.

This metric asks whether the portfolio/planner adds value rather than whether one included compiler is good.

### 42.2 Technical metrics

- semantic mismatch escape rate;
- target-invalid candidate escape rate;
- eligible workload coverage;
- valid-candidate yield by adapter;
- material portfolio uplift rate;
- win/tie/loss rate against each baseline;
- improvement magnitude on wins and regressions;
- selection regret versus the best evaluated candidate;
- planner latency and resource use;
- timeout/crash rate;
- offline replay success; and
- deterministic selection rate.

### 42.3 Product metrics after external users exist

- time to first successful Plan;
- percentage of users who inspect an explanation;
- percentage who choose the recommended plan versus an alternative;
- repeat planning users and retained projects;
- workload volume by program/target family;
- target/compiler coverage requested by users;
- reproduction/export usage;
- plan-to-execution conversion; and
- support incidents caused by wrong conversion, mapping, or provider state.

### 42.4 Commercial metrics after Cloud exists

- active organisations with recurring workloads;
- paid planning/execution volume;
- gross margin by workload class;
- enterprise pilots converting to paid use;
- expansion by seats, workloads, or integrations;
- support/SLA burden; and
- revenue concentration by provider or one research partner.

Do not optimize commercial metrics before correctness and technical value exist.

## 43. Benchmark sources

Use several sources because every suite has biases:

- [MQT Bench](https://mqt.readthedocs.io/projects/bench/en/latest/) for configurable, multi-level quantum software benchmarks;
- [QASMBench](https://github.com/pnnl/QASMBench) for low-level OpenQASM circuits across application domains and sizes;
- [SupermarQ](https://arxiv.org/abs/2202.11045) for scalable, application-oriented circuits and workload feature coverage;
- [Benchpress](https://research.ibm.com/publications/benchmarking-the-performance-of-quantum-computing-software-for-quantum-circuit-creation-manipulation-and-compilation) for multi-SDK creation/manipulation/compilation methodology; and
- QCore-generated adversarial/property circuits designed to expose mapping, routing, parameter, and conversion errors.

No suite is neutral by magic. Benchpress is valuable and open, but Qiskit/IBM participation in its design should be disclosed; QCore's own suite has even more obvious QCore-author bias. Use external suites, publish manifests, and invite independent reruns.

## 44. Benchmark strata

Results must be stratified rather than averaged into one flattering number.

### 44.1 By verification feasibility

- **small:** exact semantic verification feasible;
- **medium:** deterministic randomized verification feasible;
- **large:** structural/compiler-invariant verification only, reported separately.

### 44.2 By program family

- Clifford/stabilizer-heavy;
- arithmetic and reversible logic;
- QFT/phase-estimation components;
- chemistry/VQE ansätze;
- QAOA/graph circuits;
- random or hardware-efficient circuits;
- state preparation;
- error-correction-inspired static circuits where supported; and
- synthetic topology stress tests.

### 44.3 By structure

- qubit width;
- original depth;
- two-qubit density;
- interaction-graph degree and mismatch with target topology;
- parameter count/binding profile;
- amount of reusable/synthesizable local structure; and
- measurement profile.

### 44.4 By target condition

- symmetric versus highly asymmetric gate errors;
- sparse versus dense connectivity;
- complete versus missing calibration fields;
- calibration snapshots from different times; and
- synthetic targets for modality/topology controls.

## 45. Fair baseline design

For each eligible workload and saved Target, run:

1. Qiskit standard recommended/default pipeline;
2. Qiskit strong multi-seed/equal-budget pipeline;
3. TKET recommended and strong applicable pipelines;
4. BQSKit standard/eligible bounded pipeline;
5. each QCore-native experimental recipe;
6. QCore portfolio selection over the allowed candidates; and
7. ablations: QCore without each compiler family, without calibration scoring, and with simplified ranking.

The most important comparison is not “QCore versus Qiskit level 0.” It is:

> QCore portfolio versus the strongest credible single-family workflow given comparable time, seeds, target information, and validation.

### 45.1 Equal inputs

- same original Program artifact;
- same bound parameters;
- same target snapshot;
- same allowed approximation tolerance;
- same barrier/measurement policy;
- same final target operation profile; and
- same semantic-verification policy.

### 45.2 Equal or reported resources

Compilation budgets can be compared in two modes:

- **equal wall-time/candidate budget** for the central scientific claim; and
- **ordinary default workflow** to estimate practical user convenience.

Always report CPU model, core count, memory, operating system, Python/Rust/compiler versions, process isolation, warm/cold cache, and parallelism.

### 45.3 Train/validation/held-out separation

- Use a development cohort to implement and debug.
- Freeze objectives/recipes and proposed gates.
- Use a validation cohort to tune documented defaults.
- Report final claims on a held-out cohort not used to design native passes or weights.
- Add newly encountered workloads to the next benchmark version, not retroactively to the held-out set.

## 46. Metric formulas for the experiment

Let `b(w)` be the strongest single-tool baseline value on workload `w` for the primary minimization metric, and `q(w)` the QCore-selected value.

### 46.1 Relative improvement

```text
relative_improvement(w) = (b(w) - q(w)) / b(w)
```

Report absolute differences too; percentages can exaggerate small baselines.

### 46.2 Material win

A material win requires:

- semantic and target validation pass;
- every hard Objective constraint pass; and
- relative improvement at or above the preregistered threshold, such as 5%, or an application-specific absolute threshold.

### 46.3 Selection regret

Let `o(w)` be the best candidate QCore actually evaluated under the same Objective. Then:

```text
selection_regret(w) = q(w) - o(w)
```

For lexicographic objectives, calculate regret per ordered metric and explain constraint/tolerance effects. Regret should normally be zero; non-zero regret exposes ranking, missing-data, or implementation problems.

### 46.4 Portfolio contribution

Report which compiler family wins and the marginal uplift of adding each family. If Qiskit wins 99.9% of workloads, maintaining three additional engines may not be justified even if the portfolio technically works.

## 47. Statistical reporting

- Publish every eligible workload result, not only aggregates.
- Report median, interquartile range, p90/p95, and win/tie/loss counts.
- Use paired comparisons because every tool sees the same workload/target pair.
- Bootstrap confidence intervals across workload pairs, stratified by family where possible.
- Treat multiple seeds as repeated search attempts, not independent scientific workloads.
- Report timeouts and crashes as outcomes, not silently removed rows.
- Separate exploratory analysis from preregistered tests.
- Have an external adviser review the manifest and analysis before headline claims.

## 48. Proposed v0.1 go threshold

These are **proposed thresholds to ratify before running the held-out benchmark**, not claims that QCore has met them:

### Correctness floor — mandatory

- zero known semantic mismatches among selected `exact_small` candidates;
- zero target-invalid selected candidates;
- 100% detection of the curated corruption/mapping fault suite;
- 100% offline replay on the locked reference environment; and
- every selection has complete recipe, target, objective, metric, and explanation artifacts.

Any unexplained selected-circuit correctness failure is a stop-the-line event.

### Portfolio-value threshold

- at least 25% of eligible held-out workload/target pairs show a ≥5% material improvement on the primary metric versus ordinary recommended baselines;
- at least 10% show a ≥5% improvement versus the strongest equal-budget single-tool baseline;
- median improvement among material wins is at least 5%;
- no selected plan is materially worse than an included feasible baseline on the primary lexicographic metric due to ranking error; and
- at least two compiler families each win a meaningful workload stratum, or the report recommends removing low-value families.

### Practicality threshold

- at least 95% of eligible workloads return a valid plan within the declared default budget on the reference machine;
- adapter crash/uncaught-error rate below 1% on the held-out suite;
- QCore core overhead, excluding compiler work, below 10% of total median planning time; and
- explanation generation and artifact preservation add no material correctness ambiguity.

Thresholds may be changed before the held-out run with a written reason. Changing them after seeing held-out results invalidates a clean go claim.

## 49. Falsification tests

The team should actively try to prove QCore unnecessary.

### F1 — Multi-seed incumbent test

Give Qiskit strong target-aware recipes and the same search budget. If it matches the whole portfolio, QCore should consider becoming a Qiskit extension, provenance tool, or narrower product.

### F2 — Best-single-compiler test

Choose the best compiler family per workload category using training data, then test held-out data. If a simple category-to-compiler rule matches QCore, a complex planner may not be needed.

### F3 — Metric validity test

Perturb or replace the estimated-error proxy. If plan choices are unstable under tiny reasonable model changes, QCore must expose uncertainty and avoid automatic claims.

### F4 — Real-hardware concordance test

In Phase 3, execute controlled top-ranked and lower-ranked candidates using randomized/interleaved order where practical. If the proxy ranking has no reproducible relationship to application-level outcomes, do not market “higher fidelity.”

### F5 — Conversion tax test

Measure bugs, unsupported features, compile latency, and loss caused by moving among frameworks. If interoperability cost exceeds portfolio benefit, reduce formats/engines.

### F6 — Search-cost test

Compare quality uplift with compilation resource cost. If small gains require excessive time, memory, or cloud compute, the default planner must prune or the commercial case fails.

### F7 — Reproducibility test

Replay after dependency upgrades and on a second reference environment. If plans cannot be reproduced, strengthen environment isolation or narrow the claim to artifact replay rather than recompilation.

### F8 — Incumbent feature test

Re-evaluate Qiskit, TKET, qBraid, CUDA-Q, MQT, and other relevant projects at every major roadmap gate. If an incumbent now provides the same value better, integrate, contribute, differentiate narrowly, or stop duplicating it.

### F9 — User indifference test

Give users the selected circuit and explanation. If they consistently prefer their existing default, do not infer value from benchmark uplift alone.

## 50. Go / pivot / no-go decision table

| Outcome | Evidence | Decision |
|---|---|---|
| **Go** | Correctness floor passes; portfolio beats strong equal-budget baselines on preregistered strata; design partners value explanations/replay. | Build the runtime and real-outcome validation phase. |
| **Narrow** | One engine or one workload family creates almost all value. | Productise that narrow planner/pass/integration; remove unjustified scope. |
| **Provenance pivot** | Selection uplift is weak, but reproducibility/target snapshots solve a real user problem. | Focus on experiment lineage and execution records. |
| **Framework extension** | Existing Qiskit/TKET workflows match quality; QCore mainly adds orchestration. | Build as an extension or contribute upstream. |
| **Research continue** | Signals are promising but sample/verification is insufficient. | Extend the controlled experiment; do not start Cloud/runtime expansion. |
| **No-go** | Correctness cannot be trusted, uplift disappears under fair baselines, or users are indifferent. | Stop broad QCore platform investment and preserve learnings. |

## 51. Hardware-validation cautions

Real-hardware experiments are necessary later and easy to misinterpret:

- calibration drifts between jobs;
- queue delays separate compared candidates in time;
- finite shots create statistical noise;
- the appropriate application-level success metric differs by workload;
- error mitigation can change output semantics and cost; and
- provider-reported gate errors are not independent circuit-fidelity guarantees.

Use interleaved/randomized execution order, repeated batches, saved calibration snapshots, identical shot budgets, raw-result preservation, and workload-appropriate output metrics. Report uncertainty. Never convert one successful device run into a universal compiler claim.

---

# Part X — Open-source and commercial strategy

## 52. Product family

```text
                         QPLANCK
                            │
            ┌───────────────┴───────────────┐
            │                               │
       QCORE OSS                       QCORE CLOUD
  local engine + SDK              managed execution intelligence
            │                               │
            └───────────────┬───────────────┘
                            │
                     QPLANCK LABS
             workspace / experiments / AI / teams
```

The boundaries are:

- **QCore OSS is the engine developers can use independently.**
- **QCore Cloud operates that engine at scale and adds team, policy, reliability, and managed data services.**
- **QPlanck Labs is a user environment built on public QCore contracts.**

QCore must remain usable without QPlanck Labs. Otherwise it is not credible open infrastructure.

## 53. QCore OSS

Recommended open-source scope:

- core Program/Target/Objective/Plan/Execution/Result/Artifact schemas;
- local Rust engine and Python SDK;
- supported Qiskit/OpenQASM frontends;
- public compiler and provider adapter contracts;
- IBM target adapter and other community adapters where licensing permits;
- local planner and transparent objectives;
- metric definitions and benchmark harness;
- local content-addressed artifacts/provenance;
- CLI, examples, and documentation; and
- QCore-native passes the company can openly validate and maintain.

The OSS product must solve a complete local problem. It must not be a non-functional client that requires QCore Cloud to plan one circuit.

### 53.1 Why open source is strategically appropriate

- Researchers need to inspect compilation and metric behaviour.
- Reproducibility is stronger when formats and evaluators are public.
- Hardware and software vendors are more likely to integrate a neutral public contract.
- Contributors can add targets, compiler adapters, and benchmark workloads.
- Public benchmarks create technical credibility.
- Adoption beneath existing SDKs requires low friction and trust.

### 53.2 Recommended licence posture

An Apache-2.0-style permissive licence is a strong default candidate because it supports academic and commercial adoption and includes an express patent licence. This is a product recommendation, not legal advice.

Before release:

- conduct a dependency and transitive-licence audit;
- decide DCO versus contributor licence agreement with counsel;
- publish a trademark policy for “QCore” and “QPlanck”;
- document whether benchmark fixtures can be redistributed;
- keep optional proprietary-provider SDKs out of the core distribution when required; and
- obtain legal advice on patent, export-control, data, and third-party API terms.

## 54. QCore Cloud

Cloud should sell operational value that is difficult or costly to reproduce, not access to obscured core algorithms.

Potential paid capabilities:

- distributed/parallel compiler portfolio execution;
- managed, pinned compiler environments;
- calibration and Target history;
- multi-provider credentials vault and policy-controlled execution;
- team projects, shared artifacts, comments, and approvals;
- organisation objectives and compliance policies;
- budgets, quotas, cost/queue optimisation, and alerts;
- scheduled/repeated experiments;
- long-term provenance search and comparison;
- private compiler/provider adapters;
- enterprise identity, RBAC, audit logs, data residency, and support;
- managed benchmark/regression monitoring; and
- APIs for QPlanck Labs and external enterprise systems.

### 54.1 Possible pricing units

Test pricing around value-bearing units:

- planning compute consumed;
- managed executions/workloads;
- retained provenance/artifact volume;
- team/enterprise seats for collaboration and governance;
- private integration/support contracts; and
- SLA/security tiers.

Do not set a permanent pricing model before design partners reveal which value recurs. Avoid adding opaque markups to QPU charges without clear disclosure.

## 55. QPlanck Labs

QPlanck Labs may provide:

- notebooks and an IDE;
- visual circuit/plan comparison;
- experiment tracking;
- hardware discovery and access;
- collaboration;
- learning material;
- an AI assistant that proposes or explains actions; and
- dashboards over QCore artifacts/results.

Labs should call the same versioned QCore APIs available to other clients. It must not require secret internal Plan fields or fork QCore's semantics.

The simplest distinction is:

> **QCore is the engine. QPlanck Labs is an environment around the engine.**

## 56. Commercial moat

Integrations alone are weak moats. A stronger, ethical moat could combine:

- trusted public schemas and ecosystem adoption;
- high-quality compiler/target adapter operations;
- benchmark credibility;
- accumulated target history;
- reliable enterprise workflow and policy;
- prediction-versus-observation datasets collected with valid rights and consent;
- better calibrated plan policies; and
- deep relationships with hardware providers and research users.

### 56.1 Data flywheel

```text
Program features + Target snapshot + Objective
                  ↓
          candidate predictions
                  ↓
          selected execution
                  ↓
        observed result/quality/cost
                  ↓
       evaluated policy improvement
```

Guardrails:

- no training on private programs/results without explicit contractual permission;
- separate telemetry consent from essential service data;
- minimize and classify stored data;
- provide retention/deletion controls;
- prevent one customer's program from leaking into another's recommendations;
- publish model/metric versions and evaluation; and
- allow deterministic non-learning policies for regulated or scientific workflows.

## 57. Open-core failure modes to avoid

- keeping the useful planner closed while open-sourcing only schemas;
- withholding metric definitions while claiming transparent optimisation;
- making local artifacts incompatible with Cloud;
- using provider integrations to lock users into QPlanck;
- collecting scientific workloads by default for a speculative moat;
- neglecting OSS issues while prioritising a premature dashboard; and
- competing with contributors by re-licensing their work without clear governance.

## 58. Commercial proof sequence

```text
credible open benchmark
    ↓
useful local OSS planner
    ↓
external design partners
    ↓
repeat planning/execution workloads
    ↓
managed pilot
    ↓
paid QCore Cloud / enterprise integration
    ↓
QPlanck Labs expansion
```

Fundraising should follow evidence along this sequence. It should not finance a broad cloud build before the technical wedge and user demand are visible.

---

# Part XI — Team, expertise, and safe use of Codex

## 59. Expertise QCore requires

QCore crosses several disciplines. No one founder or model should be expected to own all of them.

| Expertise | Why it matters |
|---|---|
| Quantum information and circuits | Define semantics, equivalence, measurement, noise, and valid benchmark claims. |
| Quantum compilation/synthesis | Evaluate placement, routing, rebasing, pass design, cost models, and compiler literature. |
| Classical compiler engineering | Design IRs, verifiers, passes, diagnostics, MLIR/LLVM integration, and testing. |
| Rust systems engineering | Build safe, performant core models, concurrency, bindings, and artifact infrastructure. |
| Python quantum ecosystem | Integrate Qiskit/TKET/BQSKit/provider packages with good researcher ergonomics. |
| Experimental/statistical design | Prevent biased benchmarks and interpret hardware outcomes correctly. |
| Distributed systems/SRE | Later runtime, idempotency, queues, retries, observability, and managed workers. |
| Security/privacy | Credentials, tenant isolation, supply chain, telemetry, and scientific data governance. |
| Fault tolerance/QEC | Later logical resource models, decoders, error budgets, and architecture-specific constraints. |
| Developer relations/product | Turn research infrastructure into something researchers can learn and trust. |

## 60. Early team shape

For Phases 0–2, the minimum credible team/collaboration shape is:

### Founder / product lead

- owns product thesis, user interviews, partnerships, fundraising, prioritisation, and founder learning;
- can explain the system and interrogate claims;
- does not pretend to be the sole quantum/compiler authority.

### Founding quantum compiler engineer or technical co-founder

- owns compiler architecture, IR/pass decisions, baselines, and technical quality;
- strong in quantum circuits plus classical compiler/software engineering;
- capable of reviewing Rust/Python design even if not the only implementer.

### Quantum information/compiler research adviser or scientist

- reviews semantics, equivalence strategy, cost/error models, benchmarks, and claims;
- helps connect the project to current literature and researchers;
- must have meaningful review time, not be a decorative name on a slide.

### Rust/systems engineer

- owns core model integrity, PyO3, artifacts, performance, concurrency, packaging, and reliability.

### Python/research engineer

- owns framework/provider adapters, experiment harnesses, reproducible environments, and researcher-facing UX.

In a very small team, people can cover multiple roles, but every responsibility must still have a named reviewer.

## 61. Later hires by phase

- **Runtime phase:** provider integration engineer, SRE/distributed-systems engineer, security reviewer.
- **Native compiler phase:** compiler researcher(s) in the specific proven gap, MLIR/LLVM expertise.
- **Cloud phase:** platform/backend, security/identity, enterprise product, developer relations.
- **Hybrid phase:** HPC/GPU/runtime specialist and application-domain researchers.
- **Fault-tolerant phase:** QEC theorist/engineer, architecture/resource-estimation specialist, hardware/QEC partners.

Do not hire a large generic application team before the infrastructure wedge is proven.

## 62. What Codex can safely own

With a human-approved specification and normal code review, Codex can take substantial implementation responsibility for:

- repository scaffolding and package boundaries;
- schema/model boilerplate after fields and invariants are approved;
- serialization, hashing, artifact manifests, and local storage;
- deterministic ranking/Pareto algorithms from explicit definitions;
- CLI/API glue;
- adapters that follow official SDK documentation and fixtures;
- dependency/environment manifests;
- unit, golden, contract, fuzz, and property-test scaffolding;
- benchmark orchestration and reproducible report generation;
- documentation, examples, migration notes, and ADR drafts;
- refactoring, formatting, static analysis, and CI;
- fault injection for worker/runtime state machines; and
- implementation traceability from specification to tests.

Codex is especially useful for repetitive integration work, cross-language consistency, test generation, and maintaining a precise evidence trail.

## 63. What Codex can assist with but must not approve alone

- quantum IR operation semantics;
- equivalence algorithms and numeric tolerances;
- placement/routing or synthesis pass implementations;
- estimated-error and cost models;
- benchmark suite selection and statistical analysis;
- OpenQASM/QIR/MLIR semantic lowering;
- target capability normalization;
- provider retry/idempotency rules;
- security-sensitive credential flows;
- performance claims; and
- real-hardware experiment interpretation.

These areas require named human experts to approve the design, tests, and claim.

## 64. What Codex cannot safely be the sole owner of

- deciding that a novel compiler algorithm is scientifically new;
- proving arbitrary quantum-program equivalence;
- asserting that an error proxy equals real fidelity;
- determining QEC correctness or real-time decoder/control safety;
- signing off production security, privacy, export-control, licence, or patent risk;
- operating unrestricted paid provider credentials;
- deciding whether benchmark evidence is sufficient to fundraise or make scientific claims;
- recruiting/adjudicating expertise based only on generated prose; or
- overriding go/no-go gates because more code can be generated.

The rule is:

> **Codex may implement an approved decision; it does not manufacture scientific authority.**

## 65. Required human review gates

| Change | Required review |
|---|---|
| Core schema/invariant | systems lead + affected domain owner |
| Quantum operation/pass | quantum compiler expert + generated/exact tests |
| Metric/objective change | quantum expert + benchmark/statistics reviewer |
| Provider submission/retry | provider/runtime owner + security review |
| Credential/tenant handling | security owner |
| Benchmark headline | independent technical reviewer + founder |
| Fault-tolerant/QEC model | named QEC specialist |
| Public performance/fidelity claim | technical lead + statistical reviewer + founder |

## 66. Healthy Codex workflow

```text
human-approved issue/spec
        ↓
Codex implementation + tests + traceability
        ↓
automated checks and benchmark fixtures
        ↓
named human domain review
        ↓
reproducible artifact/report
        ↓
merge or revise
```

For scientific code, a passing unit test written by the same agent that wrote the code is not independent validation. Add golden cases from literature, differential checks against trusted tools, generated adversarial cases, and human review.

---

# Part XII — Founder learning roadmap

## 67. Purpose

The founder does not need to become the world's leading quantum compiler researcher before QCore starts. The founder does need enough real understanding to:

- recognise which problems matter;
- question technical claims;
- recruit and evaluate specialists;
- make product/scope decisions;
- explain QCore without memorised jargon;
- understand benchmark limitations; and
- know when expert authority is required.

Follow this roadmap in sequence. Later subjects depend on earlier ones. Measure progress by what you can explain and do, not by videos watched.

## 68. Stage 1 — Classical information, probability, and linear algebra

### Learn

- bits, Boolean logic, functions, state, and deterministic versus probabilistic programs;
- probability distributions, expectation, variance, conditional probability, and sampling;
- real and complex numbers;
- vectors, inner products, norms, bases, and change of basis;
- matrices as transformations;
- matrix multiplication, inverse, conjugate transpose, eigenvalues/eigenvectors; and
- tensor/Kronecker products.

### Why QCore needs it

Quantum states are vectors, gates are linear transformations, composite systems use tensor products, and measurement produces sampled probabilities. Compiler equivalence and fidelity-related quantities rely on this language.

### Practical checkpoint

By hand or in a notebook:

- multiply a 2×2 matrix by a vector;
- show that a simple rotation preserves vector length;
- compute a small probability distribution and expected value; and
- form the tensor product of two two-component vectors.

### Founder exit question

Can you explain why a matrix can represent an operation without saying “because quantum mechanics is weird”?

## 69. Stage 2 — One qubit, gates, and measurement

### Learn

- a qubit state as a normalized complex vector;
- amplitudes versus probabilities;
- global versus relative phase;
- computational and alternative bases;
- X, Y, Z, H, S, T, and rotation gates;
- unitary and reversible operations;
- measurement and repeated shots; and
- the Bloch sphere as a representation, not a literal tiny ball.

### Why QCore needs it

QCore transformations must preserve the computation, including phase where it matters, and must not confuse predicted probability distributions with one finite-shot result.

### Practical checkpoint

- build `|0⟩ → H → measure` in Qiskit and a simulator;
- run with different shot counts;
- explain why outputs vary while the underlying ideal probabilities do not; and
- show an adjacent gate/inverse pair cancelling.

### Founder exit question

Can you explain the difference among state amplitude, measurement probability, and observed count?

## 70. Stage 3 — Multiple qubits and entanglement

### Learn

- tensor-product state spaces;
- controlled gates and CNOT;
- separable versus entangled states;
- Bell-state preparation and correlation;
- reduced information and why individual-qubit intuition can fail;
- no-cloning at a conceptual level; and
- qubit ordering conventions in software.

### Why QCore needs it

Routing and qubit mapping must preserve multi-qubit relationships. Output-order mistakes can make a correct physical run look wrong.

### Practical checkpoint

- create and simulate a Bell circuit;
- reverse displayed bit order and explain what changed versus what did not;
- map logical qubits to different physical positions; and
- inspect the final measurement mapping.

### Founder exit question

Can you explain why moving a logical qubit is a mapping/operation problem, not copying a classical bit?

## 71. Stage 4 — Circuits and algorithmic building blocks

### Learn

- circuit diagrams and time/dependency order;
- interference, phase kickback, and uncomputation;
- oracles and reversible subroutines;
- high-level ideas behind Grover search, phase estimation, QFT, VQE, and QAOA;
- parameters and hybrid optimization loops; and
- why a theoretical speedup is different from a useful near-term workload.

### Why QCore needs it

Different workload structures favour different compiler techniques. A planner cannot be evaluated only on random gates or toy Bell circuits.

### Practical checkpoint

- build one small algorithmic circuit and one parameterized ansatz;
- identify its two-qubit operations and repeated blocks;
- explain which part is the quantum program and which part is the classical loop.

### Founder exit question

Can you explain what the circuit is trying to compute before discussing which QPU runs it?

## 72. Stage 5 — Real quantum hardware and noise

### Learn

- physical versus logical qubits;
- superconducting, trapped-ion, neutral-atom, and photonic modalities at a conceptual level;
- native gates and why modalities differ;
- connectivity/topology;
- gate duration, relaxation/dephasing, readout error, crosstalk, leakage, and drift;
- calibration snapshots;
- shots, queues, provider access, and cost; and
- why one error number is not full application fidelity.

### Why QCore needs it

The Target is a model of these constraints. Adaptive planning only has meaning because machines and their current characteristics differ.

### Practical checkpoint

- inspect a Qiskit fake or saved IBM Target;
- list its native operations and connectivity;
- find asymmetric gate errors or durations;
- manually explain why two possible layouts may differ.

### Founder exit question

Can you explain why “fewest gates” and “best expected result” can disagree?

## 73. Stage 6 — Quantum compilation

### Learn in this order

1. decomposition/rebasing into a gate set;
2. algebraic simplification and local synthesis;
3. logical-to-physical placement/layout;
4. routing and SWAPs under connectivity;
5. scheduling and timing;
6. target-aware/noise-aware cost functions; and
7. stochastic heuristics, seeds, and compilation budgets.

### Why QCore needs it

This is the immediate technical centre of v0.1. QCore assumes that different pipelines find different valid physical implementations and tries to choose among them fairly.

### Practical checkpoint

- compile the same circuit with several Qiskit optimisation levels and seeds;
- compare depth, two-qubit count, layout, and time;
- compile it with TKET if available;
- explain why neither tool is “wrong” when results differ; and
- identify the strongest honest baseline.

### Founder exit question

Can you explain placement, routing, rebasing, and scheduling as different jobs?

## 74. Stage 7 — Classical compiler and runtime concepts

### Learn

- parser, abstract syntax tree, IR, verifier, pass, analysis, lowering, and code generation;
- control flow and data flow;
- why compilers use several IR levels;
- pass preconditions/postconditions;
- deterministic builds, toolchain versions, and artifacts;
- runtime, job state, idempotency, retries, and result normalization;
- MLIR's multi-level/dialect model; and
- QIR's relationship to LLVM IR.

### Why QCore needs it

Without classical compiler discipline, QCore becomes format conversion scripts glued to provider APIs. This stage explains the architecture in Part V.

### Practical checkpoint

- draw `Qiskit source → QCore Program → candidate compiler → target form → Plan`;
- identify what must be preserved at each boundary;
- write a simple transformation's precondition/postcondition in plain English; and
- explain why planning and runtime are separate.

### Founder exit question

Can you distinguish an SDK, IR, compiler, planner, runtime, backend, and Target without circular definitions?

## 75. Stage 8 — Ecosystem fluency

Study hands-on in this order:

1. **Qiskit:** circuits, pass managers, Target/BackendV2, fake backends, layouts, primitives/runtime concepts.
2. **TKET:** circuits, predicates, passes, placement/routing, backends.
3. **BQSKit:** MachineModel, workflows, synthesis limits and approximation.
4. **OpenQASM 2/3:** what the language can express and what v0.1 intentionally rejects.
5. **qBraid/CUDA-Q/Braket:** how existing portability and hybrid/runtime products frame the problem.
6. **MQT/Benchpress/QASMBench/SupermarQ:** how software benchmarks are constructed.

### Practical checkpoint

Create a one-page comparison in your own words:

```text
tool → layer it primarily owns → strongest capability → overlap with QCore
     → why QCore integrates/benchmarks rather than replaces it
```

### Founder exit question

Can you explain QCore's difference from qBraid and TKET without falsely diminishing either project?

## 76. Stage 9 — Experimental design and scientific claims

### Learn

- hypotheses and falsification;
- train/validation/held-out separation;
- paired comparisons and confidence intervals;
- proxy metrics versus outcome metrics;
- confounding, selection bias, and cherry-picking;
- reproducible environments and provenance; and
- what independent review adds.

### Why QCore needs it

The company can easily fool itself with a benchmark chosen, implemented, and interpreted to favour its own planner.

### Practical checkpoint

- preregister one small compiler comparison;
- predict what result would make you stop;
- run it without changing the success threshold;
- publish wins, losses, timeouts, and unsupported cases.

### Founder exit question

Can you state what evidence would prove the current QCore wedge is not worth building?

## 77. Stage 10 — Runtime, hybrid computing, and QEC

Only study these deeply after the v0.1 foundations are solid.

### Runtime/hybrid topics

- asynchronous jobs and queues;
- iterative quantum-classical algorithms;
- CPU/GPU/QPU division of labour;
- data movement and latency;
- distributed workflow failure; and
- CUDA-Q, Braket Hybrid Jobs, and HPC schedulers.

### Fault-tolerant/QEC topics

- physical versus logical error;
- stabilizer codes and syndrome measurement;
- decoder role and real-time constraints;
- code distance and threshold ideas;
- logical gates, transversal operations, lattice surgery at a conceptual level;
- Clifford+T, magic-state distillation, and space-time resource estimates; and
- Qualtran, Stim, and Riverlane/Deltakit boundaries.

### Founder exit question

Can you explain why a fault-tolerant QCore Target needs code/resource information fundamentally different from a NISQ gate-error snapshot?

## 78. Founder mastery checklist

Before approving the v0.1 public thesis, the founder should be able to answer:

1. What exact problem does QCore v0.1 solve?
2. Why is QCore not simply another Qiskit?
3. Why are TKET and qBraid especially close comparisons?
4. What is adaptive performance portability?
5. Why does “best” require an Objective and budget?
6. Why is the Target a snapshot rather than a live device object?
7. Why can fewer two-qubit gates still fail to predict the best hardware outcome?
8. What does the estimated-error proxy omit?
9. How can a final qubit/bit mapping make an apparently correct circuit wrong?
10. What does v0.1 reject from OpenQASM 3 and Qiskit?
11. Why does v0.1 orchestrate existing compilers before building a native one?
12. What benchmark result causes a go, narrow, pivot, or no-go decision?
13. What can Codex implement, and which claims require a human expert?
14. Why are MLIR/QIR a path rather than the first deliverable?
15. Which parts belong in OSS, Cloud, and Labs?

If any answer feels like a slogan, return to the relevant stage and perform the practical checkpoint.

---

# Part XIII — Explicit anti-goals and scope control

## 79. v0.1 anti-goals

QCore v0.1 will not:

1. create a new end-user quantum programming language;
2. support every Qiskit operation or all of OpenQASM 3;
3. compile dynamic circuits, pulse programs, or arbitrary hybrid control flow;
4. integrate every hardware provider;
5. choose among live QPUs using queue and price;
6. submit paid jobs as part of the required planning path;
7. build a general simulator;
8. build a full MLIR dialect/LLVM toolchain before the research gate;
9. claim universal QIR/OpenQASM conformance;
10. create an AI/ML planner;
11. create a cloud control plane, accounts, billing, or multi-tenancy;
12. create the QPlanck Labs IDE/notebook UI;
13. build a marketplace for QPU access;
14. implement quantum error correction or a decoder;
15. promise global optimality or measured fidelity;
16. replace Qiskit, TKET, BQSKit, or qBraid;
17. hide unsupported semantics with “best effort” conversion;
18. optimize for GitHub stars or integration count; or
19. expand because Codex makes additional code cheap to generate.

## 80. Long-term anti-goals

Even if QCore succeeds, it should not:

- pretend hardware differences no longer matter;
- become a pulse/control stack without a separate evidence-backed strategy and hardware expertise;
- make irreversible provider purchases without user policy/approval;
- treat scientific programs/results as training data by default;
- lock public artifacts into a proprietary Cloud-only format;
- claim one scalar score captures all scientific value;
- market predicted fidelity as observed application success;
- centralize every compiler algorithm instead of contributing upstream;
- expand into Academy/Labs features inside the core engine; or
- use “quantum operating system” as a substitute for a precise product boundary.

## 81. Scope admission test

A proposed v0.1 feature enters active work only if all are true:

1. It directly tests the portfolio-planning thesis, protects correctness, or is required to reproduce the experiment.
2. A supported benchmark or named design partner needs it now.
3. The team can define acceptance tests before implementation.
4. A named human owns domain review.
5. It does not require prematurely building a later roadmap phase.

If any answer is no, place it in a later-phase backlog with the evidence that would reopen it.

## 82. Scope budget

At any time, the active v0.1 roadmap should contain:

- one primary semantic profile;
- one provider Target source (IBM);
- three external compiler families plus bounded native experiments;
- one default Objective;
- one benchmark protocol; and
- one founder-facing planning workflow.

Adding something requires removing, completing, or explicitly re-gating something else.

---

# Part XIV — Risk register and decision record

## 83. Principal risks

| Risk | Early warning | Mitigation | Kill/pivot condition |
|---|---|---|---|
| No meaningful gap | Strong Qiskit/TKET defaults win nearly everywhere | Reproduce strong baselines first; run falsification F1/F2 | Equal-budget portfolio uplift misses preregistered gate |
| Semantic conversion bugs | Mismatched outputs or lost maps | Narrow semantics; source artifacts; exact/property/differential checks | Unexplained selected-candidate correctness failure persists |
| Error proxy is misleading | Rankings unstable or disagree with hardware | Label proxy; sensitivity analysis; real-outcome phase | No useful hardware concordance |
| Portfolio too slow | BQSKit/timeouts dominate latency | Budgets, eligibility, pruning, caching, parallel workers | Cost/latency exceeds user value |
| Dependency fragility | Version conflicts and adapter crashes | Isolated workers; pinned manifests; contract tests | Maintenance exceeds demonstrated uplift |
| Provider/API drift | Target fields or execution behaviour changes | Adapters, capability negotiation, fixtures, compatibility matrix | Core requires frequent vendor-specific rewrites |
| Overbuilding IR | Team spends months on dialect infrastructure | Minimal v0.1 IR; phase gate MLIR work | No benchmark/user benefit |
| Incumbent expansion | qBraid/Qiskit/TKET adds similar planning | Re-audit at gates; integrate/contribute/narrow | Incumbent is clearly better on same user need |
| Benchmark self-deception | Wins concentrated in tuned circuits | Held-out suites, external review, full result publication | Advantage disappears under independent rerun |
| Founder expertise gap | Decisions rely on generated jargon | Learning roadmap, technical co-founder/advisers | Founder cannot evaluate core claims/team |
| Security/data failure | Credentials in logs or unclear training use | Late credential binding, classification, consent, review | Unresolved production security/privacy risk |
| Commercial gap | Users like OSS demo but do not repeat/pay | Design partners, recurring-workload proof before Cloud | No willingness to pay for managed value |

## 84. Decisions locked for v0.1

1. The product wedge is explainable compiler-portfolio planning.
2. Qiskit/OpenQASM static circuits are the initial inputs.
3. IBM is the only required live Target source.
4. Qiskit, TKET, and BQSKit are external compiler families; QCore-native work stays conservative and experimental.
5. Rust owns stable models, metrics, ranking, artifacts, and core invariants.
6. Python owns researcher ergonomics and external Python SDK adapters.
7. PyO3 is a thin boundary.
8. MLIR/QIR compatibility is designed now and implemented after the thesis gate.
9. `plan()` and `run()` are separate; external execution is not required for v0.1 acceptance.
10. Estimated error is labelled as a proxy and evaluated by one common implementation.
11. Plans preserve alternatives, failures, explanations, and immutable artifacts.
12. Fair benchmarks include strong equal-budget incumbents and held-out workloads.

Changing a locked decision requires an Architecture Decision Record explaining the evidence, alternatives, migration, and effect on the go/no-go experiment.

## 85. Open decisions before implementation

- exact supported version matrix and environment-isolation mechanism;
- canonical serialization for Qiskit source and QCore IR;
- exact numeric limits for `exact_small` and `randomized_medium` verification;
- whether the first Rust IR is graph-, sequence-, or region-oriented internally;
- adapter protocol serialization and process model;
- exact default seed set and equal-budget policy;
- metric missing-data penalties/fallbacks;
- preregistered benchmark corpus and target snapshots;
- final v0.1 thresholds after adviser review;
- open-source licence/contributor mechanism after legal review; and
- name/trademark availability for QCore.

These are decisions to resolve with evidence, not gaps to hide in code defaults.

## 86. One-page founder decision framework

When evaluating any QCore proposal, ask in order:

```text
1. What user decision becomes better?
2. What existing tool already solves part of it?
3. What exact gap remains?
4. What is the smallest test of that gap?
5. What metric defines success?
6. What result makes us stop?
7. Can we preserve semantics and prove it?
8. Can a user understand why QCore chose the result?
9. Should we build, integrate, contribute, partner, or wait?
10. Which human expert signs off the claim?
```

If those answers are unclear, do not add architecture.

---

# Part XV — Final product statement

## 87. The precise QCore statement

### Founder version

> **QCore is Google Maps for quantum execution: the researcher supplies the computation and what matters, and QCore evaluates available routes, recommends the best route it found, explains the trade-offs, and keeps the receipts.**

The analogy has limits: unlike roads, quantum program equivalence, target calibration, and outcome quality are difficult to know. That is why QCore must expose uncertainty and evidence.

### Technical version

> **QCore is a vendor-neutral, objective-aware planning and execution layer that normalizes quantum programs and target snapshots, orchestrates a bounded portfolio of compiler strategies, independently validates and evaluates candidates, selects an explainable Plan, and preserves end-to-end artifacts and provenance.**

### v0.1 version

> **QCore v0.1 accepts supported Qiskit/OpenQASM static circuits, captures an IBM Target snapshot, generates candidates through Qiskit/TKET/BQSKit/QCore-native recipes, ranks valid candidates by a versioned objective using depth, two-qubit operations, comparable routing/SWAP information, and an explicit estimated-error proxy, then exports an explainable and reproducible Plan.**

## 88. The company-building rule

QCore should not be built because the quantum industry may become enormous. It should be built only if QPlanck can demonstrate a trustworthy execution decision that researchers value.

The first victory is not:

> We built a quantum operating system.

It is:

> **On a fair, reproducible benchmark and then on controlled hardware experiments, QCore made a better execution decision, showed why, and another researcher reproduced it.**

Everything after that is earned.

---

# Reference index

Primary project documentation consulted for the ecosystem and architecture descriptions:

- [Qiskit Target](https://quantum.cloud.ibm.com/docs/en/api/qiskit/2.3/qiskit.transpiler.Target)
- [IBMBackend](https://quantum.cloud.ibm.com/docs/api/qiskit-ibm-runtime/ibm-backend)
- [Qiskit AI-powered transpiler passes](https://quantum.cloud.ibm.com/docs/en/guides/ai-transpiler-passes)
- [Cirq devices](https://quantumai.google/cirq/hardware/devices)
- [PennyLane documentation and architecture](https://docs.pennylane.ai/en/stable/development/guide/architecture.html)
- [TKET compilation](https://docs.quantinuum.com/tket/user-guide/manual/manual_compiler.html)
- [TKET backends](https://docs.quantinuum.com/tket/user-guide/manual/manual_backend.html)
- [CUDA-Q](https://nvidia.github.io/cuda-quantum/latest/index.html)
- [qBraid SDK](https://docs.qbraid.com/v2/sdk/user-guide/overview)
- [QIR Alliance: What is QIR?](https://www.qir-alliance.org/qir-book/concepts/what-is-qir.html)
- [OpenQASM 3 specification](https://openqasm.com/versions/3.0/index.html)
- [BQSKit](https://bqskit.readthedocs.io/en/latest/)
- [Classiq](https://docs.classiq.io/)
- [Amazon Braket](https://aws.amazon.com/documentation-overview/braket/)
- [Amazon Braket Hybrid Jobs](https://docs.aws.amazon.com/braket/latest/developerguide/braket-jobs.html)
- [Munich Quantum Toolkit](https://mqt.readthedocs.io/)
- [MQSS interfaces](https://munich-quantum-software-stack.github.io/MQSS-Interfaces/)
- [Qualtran](https://quantumai.google/qualtran)
- [Stim](https://github.com/quantumlib/Stim)
- [Riverlane Deltakit](https://deltakit-docs.riverlane.com/en/stable/)
- [MLIR](https://mlir.llvm.org/)
- [MQT Bench](https://mqt.readthedocs.io/projects/bench/en/latest/)
- [QASMBench](https://github.com/pnnl/QASMBench)
- [SupermarQ paper](https://arxiv.org/abs/2202.11045)
- [Benchpress paper/project description](https://research.ibm.com/publications/benchmarking-the-performance-of-quantum-computing-software-for-quantum-circuit-creation-manipulation-and-compilation)

Quantum software changes quickly. Version-specific claims and supported integration matrices must be rechecked when implementation begins and at every release. This report defines QCore's intended product and evidence discipline; it does not freeze third-party projects in their August 2026 state.
