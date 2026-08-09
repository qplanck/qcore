"""Versioned byte boundary for QCore's required Rust kernel.

The extension is loaded lazily so documentation and static tooling can import
``qplanck`` from a source checkout. Production compilation and QIR lowering do
not have a Python fallback: an absent or incompatible extension raises
``NativeCompilerError`` at the point where native execution is required.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from importlib import import_module
from types import ModuleType
from typing import Any, Final, Literal

from qplanck.errors import (
    CircuitError,
    NativeCompilerError,
    ResourceLimitError,
    UnsupportedOperationError,
)

NATIVE_ABI_VERSION: Final = "qplanck.native.abi.v1"
CORE_CONTRACT_VERSION: Final = "qplanck.core.contract.v1"
COMPILE_REQUEST_SCHEMA: Final = "qplanck.native.compile.request.v1"
COMPILE_RESPONSE_SCHEMA: Final = "qplanck.native.compile.response.v1"
QIR_REQUEST_SCHEMA: Final = "qplanck.native.qir.request.v1"
QIR_RESPONSE_SCHEMA: Final = "qplanck.native.qir.response.v1"
SIMULATE_REQUEST_SCHEMA: Final = "qplanck.native.simulate.request.v1"
SIMULATE_RESPONSE_SCHEMA: Final = "qplanck.native.simulate.response.v1"


def _extension() -> ModuleType:
    try:
        module = import_module("qplanck._qplanck_native")
    except ImportError as error:
        raise NativeCompilerError(
            "QCore requires its Rust extension, but qplanck._qplanck_native could not be "
            "imported. Install a supported qplanck wheel or build the source tree with "
            "`maturin develop`. No Python compiler fallback was attempted."
        ) from error

    abi_version = getattr(module, "ABI_VERSION", None)
    if abi_version != NATIVE_ABI_VERSION:
        raise NativeCompilerError(
            f"QCore native ABI mismatch: Python requires {NATIVE_ABI_VERSION!r}, "
            f"extension provides {abi_version!r}. Reinstall qplanck."
        )
    core_contract_version = getattr(module, "CORE_CONTRACT_VERSION", None)
    if core_contract_version != CORE_CONTRACT_VERSION:
        raise NativeCompilerError(
            f"QCore contract mismatch: Python requires {CORE_CONTRACT_VERSION!r}, "
            f"extension provides {core_contract_version!r}. Reinstall qplanck."
        )
    return module


def implementation_info() -> dict[str, str]:
    """Return observational build identity for the loaded native kernel."""

    module = _extension()
    try:
        payload = json.loads(module.implementation_info())
    except (AttributeError, TypeError, ValueError) as error:
        raise NativeCompilerError(
            "The QCore native kernel returned invalid build metadata."
        ) from error
    if not isinstance(payload, dict):
        raise NativeCompilerError("The QCore native kernel returned invalid build metadata.")
    return {str(key): str(value) for key, value in payload.items()}


def compile_ir(
    ir_json: str,
    options: Mapping[str, object],
    *,
    target: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Invoke native compilation through the stable serialized ABI."""

    request = {
        "schema_version": COMPILE_REQUEST_SCHEMA,
        "ir_json": ir_json,
        "options": dict(options),
        "target": None if target is None else dict(target),
        "target_hash": (
            None
            if target is None
            else "sha256:"
            + hashlib.sha256(
                json.dumps(target, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest()
        ),
    }
    return _invoke(
        "compile_ir",
        request,
        response_schema=COMPILE_RESPONSE_SCHEMA,
        invalid_error=CircuitError,
    )


def lower_qir(
    ir_json: str,
    *,
    profile: str,
    supported_qis: frozenset[str],
    max_qubits: int | None,
    max_results: int | None,
    entry_point: str,
) -> dict[str, Any]:
    """Invoke native QIR Base Profile lowering through the serialized ABI."""

    request = {
        "schema_version": QIR_REQUEST_SCHEMA,
        "ir_json": ir_json,
        "profile": profile,
        "supported_qis": sorted(supported_qis),
        "max_qubits": max_qubits,
        "max_results": max_results,
        "entry_point": entry_point,
    }
    # QIR maps native validation errors to QIRExportError at its public boundary.
    return _invoke("lower_qir", request, response_schema=QIR_RESPONSE_SCHEMA)


def simulate_ir(
    ir_json: str,
    *,
    mode: Literal["run", "statevector", "probabilities"],
    shots: int | None,
    seed: int | None,
    trace: bool,
    max_statevector_bytes: int,
    max_result_bytes: int | None,
    max_trace_qubits: int,
) -> dict[str, Any]:
    """Execute the frozen Rust statevector contract without a Python fallback."""

    request = {
        "schema_version": SIMULATE_REQUEST_SCHEMA,
        "ir_json": ir_json,
        "mode": mode,
        "shots": shots,
        "seed": seed,
        "trace": trace,
        "max_statevector_bytes": max_statevector_bytes,
        "max_result_bytes": max_result_bytes,
        "max_trace_qubits": max_trace_qubits,
    }
    return _invoke(
        "simulate_ir",
        request,
        response_schema=SIMULATE_RESPONSE_SCHEMA,
        invalid_error=CircuitError,
        resource_error=ResourceLimitError,
        unsupported_error=UnsupportedOperationError,
    )


def _invoke(
    function_name: str,
    request: Mapping[str, object],
    *,
    response_schema: str,
    invalid_error: type[Exception] = ValueError,
    resource_error: type[Exception] = ResourceLimitError,
    unsupported_error: type[Exception] = UnsupportedOperationError,
) -> dict[str, Any]:
    module = _extension()
    request_bytes = json.dumps(
        request,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    try:
        response_bytes = getattr(module, function_name)(request_bytes)
    except ValueError as error:
        raise invalid_error(str(error)) from error
    except OverflowError as error:
        raise resource_error(str(error)) from error
    except NotImplementedError as error:
        raise unsupported_error(str(error)) from error
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit | GeneratorExit):
            raise
        raise NativeCompilerError(
            f"The QCore native kernel failed during {function_name}; no Python fallback was attempted."
        ) from error

    try:
        response = json.loads(bytes(response_bytes))
    except (TypeError, ValueError) as error:
        raise NativeCompilerError(
            f"The QCore native kernel returned invalid JSON during {function_name}."
        ) from error
    if not isinstance(response, dict) or response.get("schema_version") != response_schema:
        actual = response.get("schema_version") if isinstance(response, dict) else None
        raise NativeCompilerError(
            f"Native response schema mismatch during {function_name}: "
            f"expected {response_schema!r}, got {actual!r}."
        )
    return response


__all__ = [
    "COMPILE_REQUEST_SCHEMA",
    "COMPILE_RESPONSE_SCHEMA",
    "CORE_CONTRACT_VERSION",
    "NATIVE_ABI_VERSION",
    "QIR_REQUEST_SCHEMA",
    "QIR_RESPONSE_SCHEMA",
    "SIMULATE_REQUEST_SCHEMA",
    "SIMULATE_RESPONSE_SCHEMA",
    "compile_ir",
    "implementation_info",
    "lower_qir",
    "simulate_ir",
]
