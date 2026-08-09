import hashlib
import sys
from types import SimpleNamespace

import pytest

from qplanck import Circuit, CircuitIR, Operation, Parameter
from qplanck._native import NATIVE_ABI_VERSION, compile_ir, implementation_info, lower_qir
from qplanck.compiler import CompileOptions, _compile_reference, compile
from qplanck.errors import CircuitError, NativeCompilerError
from qplanck.qir import SUPPORTED_QIS, _export_qir_reference
from qplanck.routing import route
from qplanck.targets import InstructionSupport, Layout, Target, Topology


def _routing_target(
    topology: Topology,
    basis: frozenset[str] = frozenset({"h", "x", "rz", "cx"}),
) -> Target:
    return Target(
        "native-test-target",
        topology,
        tuple(
            InstructionSupport(name, 2 if name in {"cx", "cz", "swap"} else 1)
            for name in sorted(basis)
        ),
    )


def test_native_kernel_reports_versioned_build_identity() -> None:
    info = implementation_info()

    assert info["name"] == "qplanck-native"
    assert info["abi_version"] == NATIVE_ABI_VERSION
    assert info["version"] == "0.3.0-alpha.1"
    assert info["rust_version"] == "1.85.0"


def test_native_compile_returns_complete_deterministic_o1_artifact() -> None:
    circuit = Circuit(2, name="native").h(0).h(0).cx(0, 1).measure_all()

    response = compile_ir(
        circuit.to_json(),
        {"optimization_level": 1, "angle_tolerance": 0.0},
    )

    compiled_ir = CircuitIR.from_dict(response["compiled_ir"])
    expected_hash = "sha256:" + hashlib.sha256(compiled_ir.to_json().encode()).hexdigest()
    assert compiled_ir.operations == (Operation("cx", (0, 1)),)
    assert response["output_ir_hash"] == expected_hash
    assert response["compiled_graph"] == {"operation_count": 1, "edges": []}
    assert response["after_metrics"]["gate_counts"] == {"cx": 1}
    assert [event["index"] for event in response["events"]] == [0, 1, 2]
    assert response["events"][1]["rewrites"][0]["rule"] == "self-inverse-adjacent"


def test_native_rotation_merge_matches_fsum_semantics() -> None:
    circuit = Circuit(1).rx(1.0e100, 0).rx(1.0, 0).rx(-1.0e100, 0)

    response = compile_ir(
        circuit.to_json(),
        {"optimization_level": 1, "angle_tolerance": 0.0},
    )

    compiled_ir = CircuitIR.from_dict(response["compiled_ir"])
    assert compiled_ir.operations == (Operation("rx", (0,), (1.0,)),)


@pytest.mark.parametrize(
    "value",
    [
        -0.0,
        1.234_567_890_123_45e-5,
        1.0e-7,
        1.0e20,
        float.fromhex("0x0.0000000000001p-1022"),
        sys.float_info.max,
    ],
)
def test_native_canonical_hashes_match_python_for_extreme_floats_and_unicode(
    value: float,
) -> None:
    ir = CircuitIR(
        1,
        (Operation("rx", (0,), (value,), metadata={"label": "café"}),),
        metadata={"owner": "雪"},
    )
    options = CompileOptions(optimization_level=0)

    native = compile(ir, options)
    oracle = _compile_reference(ir, options)

    assert native.ir.to_json() == oracle.ir.to_json()
    assert native.trace == oracle.trace


@pytest.mark.parametrize("optimization_level", [0, 1])
def test_production_native_matches_frozen_python_oracle(optimization_level: int) -> None:
    circuit = Circuit(3).h(0).x(2).h(0).rz(0.25, 1).rz(0.5, 1).cx(1, 2)
    options = CompileOptions(optimization_level=optimization_level)

    native = compile(circuit, options)
    oracle = _compile_reference(circuit, options)

    assert native.ir == oracle.ir
    assert native.source_graph == oracle.source_graph
    assert native.dependency_graph == oracle.dependency_graph
    assert native.before_metrics == oracle.before_metrics
    assert native.after_metrics == oracle.after_metrics
    assert native.trace == oracle.trace


def test_native_compile_maps_invalid_circuit_to_public_error() -> None:
    ir = CircuitIR(1, operations=(Operation("rx", (0,), (Parameter("theta"),)),))

    with pytest.raises(CircuitError, match="finite numeric gate parameters"):
        compile_ir(ir.to_json(), {"optimization_level": 1, "angle_tolerance": 0.0})


def test_native_o2_matches_readable_routing_reference() -> None:
    ir = Circuit(5).cx(0, 4).cx(1, 3).cx(4, 2).measure_all().ir
    target = _routing_target(Topology.line(5))

    response = compile_ir(
        ir.to_json(),
        {
            "optimization_level": 2,
            "angle_tolerance": 0.0,
            "initial_layout": None,
            "routing_seed": 9,
            "placement_trials": 4,
            "max_inserted_swaps": None,
        },
        target=target.to_dict(),
    )
    reference = route(ir, target, routing_seed=9)

    assert response["routed_ir"] == reference.routed_ir.to_dict()
    assert response["compiled_ir"] == reference.final_ir.to_dict()
    assert response["initial_layout"] == reference.initial_layout.to_dict()
    assert response["final_layout"] == reference.final_layout.to_dict()
    assert response["routing_trace"] == reference.trace.to_dict()
    assert response["target_hash"] == target.content_hash
    assert response["routed_metrics"]["gate_counts"].get("swap", 0) == len(reference.trace.steps)
    assert response["routing_trace"]["trials"][0]["inserted_swaps"] == 0
    assert response["routing_trace"]["trials"][-1]["baseline"] is True
    assert response["routing_trace"]["trials"][-1]["inserted_swaps"] == 3
    assert [event["pass"]["id"] for event in response["events"]] == [
        "validate.static",
        "opt.local-exact",
        "route.target-deterministic",
        "lower.target-basis-exact",
        "analyze.resources",
    ]


def test_native_o2_exactly_lowers_reverse_directed_cx() -> None:
    target = _routing_target(
        Topology(2, ((0, 1),), directed=True),
        frozenset({"h", "cx"}),
    )
    ir = Circuit(2).cx(1, 0).ir

    response = compile_ir(
        ir.to_json(),
        {
            "optimization_level": 2,
            "angle_tolerance": 0.0,
            "initial_layout": Layout.identity(2).to_dict(),
            "routing_seed": 0,
            "placement_trials": 1,
            "max_inserted_swaps": None,
        },
        target=target.to_dict(),
    )

    assert [operation["name"] for operation in response["compiled_ir"]["operations"]] == [
        "h",
        "h",
        "cx",
        "h",
        "h",
    ]


def test_native_o2_matches_exact_disconnected_component_assignment() -> None:
    topology = Topology(
        9,
        ((0, 1), (1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8)),
    )
    target = _routing_target(topology)
    ir = Circuit(9).cx(0, 1).cx(1, 2).cx(3, 4).cx(5, 6).cx(7, 8).measure_all().ir

    response = compile_ir(
        ir.to_json(),
        {
            "optimization_level": 2,
            "angle_tolerance": 0.0,
            "initial_layout": None,
            "routing_seed": 11,
            "placement_trials": 4,
            "max_inserted_swaps": None,
        },
        target=target.to_dict(),
    )
    reference = route(ir, target, routing_seed=11)

    assert response["compiled_ir"] == reference.final_ir.to_dict()
    assert response["initial_layout"] == reference.initial_layout.to_dict()
    assert response["routing_trace"] == reference.trace.to_dict()


def test_native_qir_matches_reference_text_and_expands_swap() -> None:
    circuit = Circuit(2).swap(0, 1).measure_all()

    response = lower_qir(
        circuit.to_json(),
        profile="base_profile",
        supported_qis=SUPPORTED_QIS,
        max_qubits=None,
        max_results=None,
        entry_point="qplanck_main",
    )

    assert response["text"] == _export_qir_reference(circuit).text
    assert response["required_qis"] == ["cnot", "mz"]
    assert [entry["qubits"] for entry in response["source_map"][:3]] == [
        [0, 1],
        [1, 0],
        [0, 1],
    ]


def test_missing_native_extension_never_falls_back(monkeypatch) -> None:
    from qplanck import _native

    def missing_extension(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(_native, "import_module", missing_extension)

    with pytest.raises(NativeCompilerError, match="No Python compiler fallback"):
        _native.implementation_info()


def test_native_panic_boundary_maps_base_exception_to_public_error(monkeypatch) -> None:
    from qplanck import _native

    class SimulatedPanic(BaseException):
        pass

    def panic(_request: bytes) -> bytes:
        raise SimulatedPanic("rust panic")

    monkeypatch.setattr(
        _native,
        "_extension",
        lambda: SimpleNamespace(compile_ir=panic),
    )

    with pytest.raises(NativeCompilerError, match="no Python fallback"):
        _native.compile_ir(Circuit(1).to_json(), {"optimization_level": 0})
