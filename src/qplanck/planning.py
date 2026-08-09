"""Provider-neutral, deterministic offline planning contracts for QCore.

This module is the small v0.1 research-kernel boundary.  It compares explicit
compiler strategies against immutable :class:`~qplanck.targets.Target`
snapshots; it does not discover providers, submit jobs, or claim that an
estimated metric predicts hardware outcomes.

Canonical identities deliberately exclude wall-clock timestamps and compiler
latency.  Those values are retained as observational evidence, but they cannot
change selection, ranking, or a semantic artifact hash.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, TypedDict, runtime_checkable

from qplanck.circuit import Circuit
from qplanck.compiler import CompiledCircuit, CompileOptions, compile
from qplanck.ir import CircuitIR
from qplanck.targets import Layout, Target

PROGRAM_SCHEMA_VERSION = "qcore.program.v0.1"
OBJECTIVE_SCHEMA_VERSION = "qcore.objective.v0.1"
METRICS_SCHEMA_VERSION = "qcore.plan-metrics.v0.1"
CANDIDATE_SCHEMA_VERSION = "qcore.candidate-plan.v0.1"
PLAN_SCHEMA_VERSION = "qcore.plan-decision.v0.1"
MANIFEST_SCHEMA_VERSION = "qcore.planning-manifest.v0.1"
SCORER_VERSION = "weighted_loss_v1"
ERROR_MODEL_VERSION = "independent_instruction_error_v1"

_SUPPORTED_METRICS = frozenset(
    {
        "estimated_error",
        "circuit_depth",
        "two_qubit_gate_count",
        "inserted_swap_count",
    }
)
_OBSERVATIONAL_METRICS = frozenset({"compilation_latency_ms"})
_SECRET_KEY = re.compile(
    r"(?:^|_)(?:passwords?|passwd|secrets?|tokens?|credentials?|auth|authorization|"
    r"bearer|cookies?|api_keys?|access_keys?|session_keys?|private_keys?|"
    r"connection_strings?|dsn)(?:$|_)",
    re.IGNORECASE,
)
_STRATEGY_REASON_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_STRATEGY_REASON_DIAGNOSTIC_PREFIX = "strategy_reason_code:"
_ERROR_MODEL_ASSUMPTIONS = (
    "Instruction failures are independent stochastic events.",
    "Only gate instructions are included; readout error is excluded.",
    "Rates describe the immutable target snapshot used for planning.",
)
_ERROR_MODEL_LIMITATIONS = (
    "Does not model coherent error, crosstalk, correlated noise, or state dependence.",
    "Does not model calibration drift, scheduling interactions, queue effects, or cost.",
    "This estimate is a planning heuristic, not a hardware-fidelity guarantee.",
)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown-source-tree"


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise TypeError(
            "Planning artifacts must contain only finite, JSON-serializable values; "
            "provider SDK objects are forbidden."
        ) from error


def _content_hash(value: object) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in sorted(value.items())}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Planning artifact floats must be finite.")
        return value
    raise TypeError(
        f"Provider SDK object {type(value).__name__} is forbidden; "
        "planning artifacts must contain only JSON values."
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_json(item) for item in value]
    return value


def _assert_secret_free(value: object, *, path: str = "artifact") -> None:
    """Fail closed on secret-shaped fields before durable serialization.

    Values are not inspected heuristically because arbitrary circuit labels may
    legitimately resemble tokens.  Secret-bearing *field names* are forbidden,
    and non-JSON provider/session objects are rejected by canonicalization.
    """

    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            # Normalize kebab/snake/camel/Pascal spellings before checking so
            # ``credentials``, ``accessToken``, and ``APIKey`` cannot bypass
            # the durable-artifact policy through naming style alone.
            normalized_key = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
            normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized_key)
            normalized_key = re.sub(r"[^A-Za-z0-9]+", "_", normalized_key).strip("_")
            if _SECRET_KEY.search(normalized_key.lower()):
                raise ValueError(f"Secret-bearing field {path}.{key} is forbidden.")
            _assert_secret_free(item, path=f"{path}.{key}")
    elif isinstance(value, tuple | list):
        for index, item in enumerate(value):
            _assert_secret_free(item, path=f"{path}[{index}]")
    elif not (value is None or isinstance(value, str | bool | int | float)):
        raise TypeError(f"Provider SDK object {type(value).__name__} is forbidden at {path}.")
    _canonical_json(_thaw_json(value))


def _non_empty(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _hash_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _semantic_ir_dict(ir: CircuitIR) -> dict[str, object]:
    """Return static-subset semantics without unversioned descriptive metadata."""

    payload = ir.to_dict()
    payload["metadata"] = {}
    for operation in payload["operations"]:
        operation["metadata"] = {}
    for measurement in payload["measurements"]:
        measurement["metadata"] = {}
    return payload


@dataclass(frozen=True)
class Program:
    """Normalized, immutable program plus direct frontend provenance."""

    ir: CircuitIR
    input_hash: str
    frontend: str
    frontend_version: str
    parser: str
    parser_version: str
    assumptions: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    schema_version: str = PROGRAM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROGRAM_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Program schema: {self.schema_version}.")
        if not isinstance(self.ir, CircuitIR):
            raise TypeError("Program.ir must be a CircuitIR.")
        # Reuse the public circuit validator, including terminal measurement rules.
        Circuit.from_ir(self.ir)
        if not self.input_hash.startswith("sha256:"):
            raise ValueError("Program.input_hash must be a SHA-256 identity.")
        for label in ("frontend", "frontend_version", "parser", "parser_version"):
            object.__setattr__(self, label, _non_empty(getattr(self, label), label=label))
        object.__setattr__(self, "assumptions", tuple(str(item) for item in self.assumptions))
        object.__setattr__(self, "diagnostics", tuple(str(item) for item in self.diagnostics))
        _assert_secret_free(self.ir.to_dict(), path="program.normalized_ir")

    @classmethod
    def from_input(cls, source: Program | Circuit | CircuitIR | str | object) -> Program:
        """Normalize a supported QCore, OpenQASM 3, or Qiskit input directly."""

        if isinstance(source, cls):
            return source
        package_version = _package_version("qplanck")
        if isinstance(source, Circuit):
            ir = source.ir
            frontend = "qplanck.circuit"
            frontend_version = package_version
            parser = "qplanck.circuit.direct"
            parser_version = "1"
            input_payload = ir.to_json()
        elif isinstance(source, CircuitIR):
            ir = source
            frontend = "qcore.circuit-ir"
            frontend_version = source.schema_version
            parser = "qplanck.ir.direct"
            parser_version = "1"
            input_payload = ir.to_json()
        elif isinstance(source, str):
            circuit = Circuit.from_qasm3(source)
            ir = circuit.ir
            frontend = "openqasm3"
            frontend_version = "3"
            parser = "qplanck.qasm3.safe-subset"
            parser_version = package_version
            input_payload = source
        else:
            # Circuit.from_qiskit performs optional capability detection and
            # rejects unsupported semantics without importing Qiskit in core.
            circuit = Circuit.from_qiskit(source)
            ir = circuit.ir
            frontend = "qiskit"
            frontend_version = _package_version("qiskit")
            parser = "qplanck.qiskit-adapter.direct"
            parser_version = package_version
            input_payload = _canonical_json(
                {
                    "frontend": frontend,
                    "frontend_version": frontend_version,
                    "normalized_ir": ir.to_dict(),
                }
            )
        return cls(
            ir=ir,
            input_hash=_hash_text(input_payload),
            frontend=frontend,
            frontend_version=frontend_version,
            parser=parser,
            parser_version=parser_version,
        )

    @property
    def program_hash(self) -> str:
        """Semantic Program identity, intentionally independent of frontend."""

        return _content_hash(
            {
                "schema_version": self.schema_version,
                "ir_schema_version": self.ir.schema_version,
                "normalized_ir": _semantic_ir_dict(self.ir),
            }
        )

    @property
    def content_hash(self) -> str:
        return self.program_hash

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "program_hash": self.program_hash,
            "input_hash": self.input_hash,
            "normalized_ir": self.ir.to_dict(),
            "ir_schema_version": self.ir.schema_version,
            "frontend": self.frontend,
            "frontend_version": self.frontend_version,
            "parser": self.parser,
            "parser_version": self.parser_version,
            "assumptions": list(self.assumptions),
            "diagnostics": list(self.diagnostics),
        }
        # CircuitIR metadata is shallowly immutable in the legacy v0.1 IR.
        # Revalidate at serialization time so a nested caller-owned object
        # cannot introduce a provider object or secret after construction.
        _assert_secret_free(payload, path="program")
        return payload

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), allow_nan=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Program:
        raw_ir = data.get("normalized_ir")
        if not isinstance(raw_ir, Mapping):
            raise ValueError("Program normalized_ir must be an object.")
        program = cls(
            ir=CircuitIR.from_dict(raw_ir),
            input_hash=str(data["input_hash"]),
            frontend=str(data["frontend"]),
            frontend_version=str(data["frontend_version"]),
            parser=str(data["parser"]),
            parser_version=str(data["parser_version"]),
            assumptions=tuple(str(item) for item in data.get("assumptions", ())),
            diagnostics=tuple(str(item) for item in data.get("diagnostics", ())),
            schema_version=str(data.get("schema_version", PROGRAM_SCHEMA_VERSION)),
        )
        expected = data.get("program_hash")
        if expected is not None and expected != program.program_hash:
            raise ValueError("Program hash does not match normalized content.")
        return program

    @classmethod
    def from_json(cls, text: str) -> Program:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Program JSON must contain an object.")
        return cls.from_dict(value)


@dataclass(frozen=True)
class MetricConstraint:
    """Inclusive lower and/or upper bound for one named metric."""

    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        for label in ("minimum", "maximum"):
            value = getattr(self, label)
            if value is not None:
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise ValueError(f"Constraint {label} must be finite or None.")
                object.__setattr__(self, label, numeric)
        if self.minimum is None and self.maximum is None:
            raise ValueError("A metric constraint requires minimum and/or maximum.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Constraint minimum cannot exceed maximum.")

    @classmethod
    def from_value(cls, value: MetricConstraint | Mapping[str, object]) -> MetricConstraint:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("Metric constraints must be MetricConstraint objects or mappings.")
        allowed = {"min", "max", "minimum", "maximum"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown metric constraint fields: {sorted(unknown)!r}.")
        return cls(
            minimum=value.get("minimum", value.get("min")),  # type: ignore[arg-type]
            maximum=value.get("maximum", value.get("max")),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, float | None]:
        return {"minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class Objective:
    """Explicit hard constraints and deterministic weighted minimization."""

    weights: Mapping[str, float]
    constraints: Mapping[str, MetricConstraint] = field(default_factory=dict)
    scales: Mapping[str, float] = field(default_factory=dict)
    tie_break: tuple[str, ...] = ("candidate_hash",)
    unknown_policy: str = "reject_required"
    unknown_penalty: float | None = None
    scorer_version: str = SCORER_VERSION
    schema_version: str = OBJECTIVE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OBJECTIVE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Objective schema: {self.schema_version}.")
        if self.scorer_version != SCORER_VERSION:
            raise ValueError(f"Unsupported scorer version: {self.scorer_version}.")
        if self.unknown_policy not in {"reject_required", "penalize"}:
            raise ValueError("unknown_policy must be 'reject_required' or 'penalize'.")

        weights: dict[str, float] = {}
        for name, raw_weight in sorted(self.weights.items()):
            metric = _validate_metric_name(name)
            weight = float(raw_weight)
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError("Objective weights must be finite and positive.")
            weights[metric] = weight
        if not weights:
            raise ValueError("Objective requires at least one weighted metric.")

        constraints: dict[str, MetricConstraint] = {}
        for name, constraint in sorted(self.constraints.items()):
            metric = _validate_metric_name(name)
            constraints[metric] = MetricConstraint.from_value(constraint)

        scales: dict[str, float] = {}
        for name in weights:
            scale = float(self.scales.get(name, 1.0))
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("Objective scales must be finite and positive.")
            scales[name] = scale
        extra_scales = set(self.scales) - set(weights)
        if extra_scales:
            raise ValueError(f"Scales supplied for unweighted metrics: {sorted(extra_scales)!r}.")

        tie_break = tuple(self.tie_break)
        if not tie_break or tie_break[-1] != "candidate_hash":
            raise ValueError("Objective tie_break must end with 'candidate_hash'.")
        for item in tie_break[:-1]:
            _validate_metric_name(item)
        if len(set(tie_break)) != len(tie_break):
            raise ValueError("Objective tie_break fields must be unique.")

        penalty = self.unknown_penalty
        if self.unknown_policy == "penalize":
            if penalty is None or not math.isfinite(float(penalty)) or float(penalty) < 0:
                raise ValueError("penalize policy requires a finite, non-negative penalty.")
            penalty = float(penalty)
        elif penalty is not None:
            raise ValueError("unknown_penalty is only valid with unknown_policy='penalize'.")

        object.__setattr__(self, "weights", MappingProxyType(weights))
        object.__setattr__(self, "constraints", MappingProxyType(constraints))
        object.__setattr__(self, "scales", MappingProxyType(scales))
        object.__setattr__(self, "tie_break", tie_break)
        object.__setattr__(self, "unknown_penalty", penalty)

    @classmethod
    def minimize(
        cls,
        metric: str,
        *,
        constraints: Mapping[str, MetricConstraint | Mapping[str, object]] | None = None,
        tie_break: tuple[str, ...] = ("candidate_hash",),
        scale: float = 1.0,
    ) -> Objective:
        normalized = _validate_metric_name(metric)
        normalized_constraints = {
            name: MetricConstraint.from_value(value)
            for name, value in ({} if constraints is None else constraints).items()
        }
        return cls(
            weights={normalized: 1.0},
            constraints=normalized_constraints,
            scales={normalized: scale},
            tie_break=tie_break,
        )

    @classmethod
    def minimize_error(
        cls,
        *,
        constraints: Mapping[str, MetricConstraint | Mapping[str, object]] | None = None,
    ) -> Objective:
        return cls.minimize(
            "estimated_error",
            constraints=constraints,
            tie_break=("two_qubit_gate_count", "circuit_depth", "candidate_hash"),
        )

    @classmethod
    def minimize_depth(
        cls,
        *,
        constraints: Mapping[str, MetricConstraint | Mapping[str, object]] | None = None,
    ) -> Objective:
        return cls.minimize(
            "circuit_depth",
            constraints=constraints,
            tie_break=("two_qubit_gate_count", "inserted_swap_count", "candidate_hash"),
        )

    @classmethod
    def minimize_two_qubit(
        cls,
        *,
        constraints: Mapping[str, MetricConstraint | Mapping[str, object]] | None = None,
    ) -> Objective:
        return cls.minimize(
            "two_qubit_gate_count",
            constraints=constraints,
            tie_break=("inserted_swap_count", "circuit_depth", "candidate_hash"),
        )

    @classmethod
    def from_name(cls, value: str) -> Objective:
        normalized = value.strip().lower().replace("-", "_")
        constructors = {
            "minimize_error": cls.minimize_error,
            "minimize_depth": cls.minimize_depth,
            "minimize_two_qubit": cls.minimize_two_qubit,
            "minimize_two_qubit_gates": cls.minimize_two_qubit,
        }
        try:
            constructor = constructors[normalized]
        except KeyError as error:
            raise ValueError(f"Unknown built-in Objective {value!r}.") from error
        return constructor()

    @property
    def objective_hash(self) -> str:
        return _content_hash(self.to_dict(include_hash=False))

    @property
    def content_hash(self) -> str:
        return self.objective_hash

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "scorer_version": self.scorer_version,
            "weights": dict(self.weights),
            "scales": dict(self.scales),
            "constraints": {
                name: constraint.to_dict() for name, constraint in self.constraints.items()
            },
            "tie_break": list(self.tie_break),
            "unknown_policy": self.unknown_policy,
            "unknown_penalty": self.unknown_penalty,
        }
        if include_hash:
            payload["objective_hash"] = self.objective_hash
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Objective:
        raw_constraints = data.get("constraints", {})
        if not isinstance(raw_constraints, Mapping):
            raise ValueError("Objective constraints must be an object.")
        objective = cls(
            weights=dict(data.get("weights", {})),
            constraints={
                str(name): MetricConstraint.from_value(value)
                for name, value in raw_constraints.items()
            },
            scales=dict(data.get("scales", {})),
            tie_break=tuple(str(item) for item in data.get("tie_break", ("candidate_hash",))),
            unknown_policy=str(data.get("unknown_policy", "reject_required")),
            unknown_penalty=data.get("unknown_penalty"),
            scorer_version=str(data.get("scorer_version", SCORER_VERSION)),
            schema_version=str(data.get("schema_version", OBJECTIVE_SCHEMA_VERSION)),
        )
        expected = data.get("objective_hash")
        if expected is not None and expected != objective.objective_hash:
            raise ValueError("Objective hash does not match normalized content.")
        return objective


def _validate_metric_name(name: str) -> str:
    normalized = _non_empty(name, label="metric").strip().lower()
    if normalized in _OBSERVATIONAL_METRICS:
        raise ValueError(f"Observational metric {normalized!r} cannot influence selection.")
    if normalized not in _SUPPORTED_METRICS:
        raise ValueError(f"Unsupported planning metric {normalized!r}.")
    return normalized


@dataclass(frozen=True)
class PlanMetrics:
    """Required physical-artifact metrics and their evidence limitations."""

    circuit_depth: int
    two_qubit_gate_count: int
    two_qubit_operation_families: tuple[str, ...]
    inserted_swap_count: int | None
    inserted_swap_unknown_reason: str | None
    user_authored_swap_count: int
    estimated_error: float | None
    estimated_error_unknown_reason: str | None
    compilation_latency_ms: float | None = None
    error_model: str = ERROR_MODEL_VERSION
    error_model_assumptions: tuple[str, ...] = _ERROR_MODEL_ASSUMPTIONS
    error_model_limitations: tuple[str, ...] = _ERROR_MODEL_LIMITATIONS
    schema_version: str = METRICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != METRICS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported PlanMetrics schema: {self.schema_version}.")
        if self.error_model != ERROR_MODEL_VERSION:
            raise ValueError(f"Unsupported error model: {self.error_model}.")
        for label in ("circuit_depth", "two_qubit_gate_count", "user_authored_swap_count"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer.")
        if self.inserted_swap_count is not None and (
            isinstance(self.inserted_swap_count, bool)
            or not isinstance(self.inserted_swap_count, int)
            or self.inserted_swap_count < 0
        ):
            raise ValueError("inserted_swap_count must be non-negative or unknown.")
        _validate_known_unknown_pair(
            self.inserted_swap_count,
            self.inserted_swap_unknown_reason,
            label="inserted_swap_count",
        )
        if self.estimated_error is not None:
            error = float(self.estimated_error)
            if not math.isfinite(error) or not 0.0 <= error <= 1.0:
                raise ValueError("estimated_error must be in [0, 1] or unknown.")
            object.__setattr__(self, "estimated_error", error)
        _validate_known_unknown_pair(
            self.estimated_error,
            self.estimated_error_unknown_reason,
            label="estimated_error",
        )
        if self.compilation_latency_ms is not None:
            latency = float(self.compilation_latency_ms)
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("compilation_latency_ms must be finite and non-negative.")
            object.__setattr__(self, "compilation_latency_ms", latency)
        object.__setattr__(
            self,
            "two_qubit_operation_families",
            tuple(sorted(set(self.two_qubit_operation_families))),
        )
        object.__setattr__(self, "error_model_assumptions", tuple(self.error_model_assumptions))
        object.__setattr__(self, "error_model_limitations", tuple(self.error_model_limitations))

    def metric_value(self, name: str) -> int | float | None:
        normalized = _validate_metric_name(name)
        return {
            "circuit_depth": self.circuit_depth,
            "two_qubit_gate_count": self.two_qubit_gate_count,
            "inserted_swap_count": self.inserted_swap_count,
            "estimated_error": self.estimated_error,
        }[normalized]

    def unknown_reason(self, name: str) -> str | None:
        normalized = _validate_metric_name(name)
        if normalized == "inserted_swap_count":
            return self.inserted_swap_unknown_reason
        if normalized == "estimated_error":
            return self.estimated_error_unknown_reason
        return None

    def to_dict(self, *, include_observations: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "circuit_depth": self.circuit_depth,
            "two_qubit_gate_count": self.two_qubit_gate_count,
            "two_qubit_operation_families": list(self.two_qubit_operation_families),
            "inserted_swap_count": self.inserted_swap_count,
            "inserted_swap_unknown_reason": self.inserted_swap_unknown_reason,
            "user_authored_swap_count": self.user_authored_swap_count,
            "estimated_error": self.estimated_error,
            "estimated_error_unknown_reason": self.estimated_error_unknown_reason,
            "error_model": self.error_model,
            "error_model_assumptions": list(self.error_model_assumptions),
            "error_model_limitations": list(self.error_model_limitations),
        }
        if include_observations:
            payload["compilation_latency_ms"] = self.compilation_latency_ms
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlanMetrics:
        return cls(
            circuit_depth=int(data["circuit_depth"]),
            two_qubit_gate_count=int(data["two_qubit_gate_count"]),
            two_qubit_operation_families=tuple(
                str(item) for item in data.get("two_qubit_operation_families", ())
            ),
            inserted_swap_count=data.get("inserted_swap_count"),
            inserted_swap_unknown_reason=data.get("inserted_swap_unknown_reason"),
            user_authored_swap_count=int(data.get("user_authored_swap_count", 0)),
            estimated_error=data.get("estimated_error"),
            estimated_error_unknown_reason=data.get("estimated_error_unknown_reason"),
            compilation_latency_ms=data.get("compilation_latency_ms"),
            error_model=str(data.get("error_model", ERROR_MODEL_VERSION)),
            error_model_assumptions=tuple(
                str(item) for item in data.get("error_model_assumptions", _ERROR_MODEL_ASSUMPTIONS)
            ),
            error_model_limitations=tuple(
                str(item) for item in data.get("error_model_limitations", _ERROR_MODEL_LIMITATIONS)
            ),
            schema_version=str(data.get("schema_version", METRICS_SCHEMA_VERSION)),
        )


def _validate_known_unknown_pair(value: object, reason: str | None, *, label: str) -> None:
    if value is None and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError(f"Unknown {label} requires a reason.")
    if value is not None and reason is not None:
        raise ValueError(f"Known {label} cannot carry an unknown reason.")


class CandidateDisposition(StrEnum):
    VALID = "valid"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    REJECTED = "rejected"


class StrategyError(RuntimeError):
    """Base class for stable, evidence-bearing strategy dispositions.

    ``reason_code`` is the only exception detail persisted by the planner. Raw
    exception messages remain useful to a direct caller but can contain
    provider-controlled text, so they never enter durable candidate evidence.
    """

    default_reason_code = "strategy.error"

    def __init__(self, message: str = "", *, reason_code: str | None = None) -> None:
        if not isinstance(message, str):
            raise TypeError("Strategy error messages must be strings.")
        resolved = self.default_reason_code if reason_code is None else reason_code
        if (
            not isinstance(resolved, str)
            or len(resolved) > 128
            or _STRATEGY_REASON_CODE.fullmatch(resolved) is None
        ):
            raise ValueError(
                "Strategy reason_code must be a stable lowercase identifier of at most "
                "128 characters."
            )
        self.reason_code = resolved
        super().__init__(message)


class StrategyUnavailableError(StrategyError):
    default_reason_code = "strategy.unavailable"


class StrategyUnsupportedError(StrategyError):
    default_reason_code = "strategy.unsupported"


class StrategyTimeoutError(StrategyError):
    default_reason_code = "strategy.timeout"


@dataclass(frozen=True)
class StrategyResult:
    """Normalized output returned by a compiler-strategy plugin boundary."""

    artifact: CircuitIR | Circuit | CompiledCircuit
    semantic_equivalent: bool
    semantic_evidence: tuple[str, ...] = ()
    inserted_swap_count: int | None = None
    inserted_swap_unknown_reason: str | None = None
    compilation_latency_ms: float | None = None
    assumptions: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, CircuitIR | Circuit | CompiledCircuit):
            raise TypeError("StrategyResult.artifact must be a QCore circuit artifact.")
        if not isinstance(self.semantic_equivalent, bool):
            raise TypeError("semantic_equivalent must be a boolean.")
        if self.inserted_swap_count is not None and (
            isinstance(self.inserted_swap_count, bool)
            or not isinstance(self.inserted_swap_count, int)
            or self.inserted_swap_count < 0
        ):
            raise ValueError("inserted_swap_count must be non-negative or unknown.")
        _validate_known_unknown_pair(
            self.inserted_swap_count,
            self.inserted_swap_unknown_reason,
            label="inserted_swap_count",
        )
        if self.compilation_latency_ms is not None:
            latency = float(self.compilation_latency_ms)
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("compilation_latency_ms must be finite and non-negative.")
            object.__setattr__(self, "compilation_latency_ms", latency)
        provenance = _freeze_json(self.provenance)
        _assert_secret_free(provenance, path="strategy.provenance")
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "semantic_evidence", tuple(self.semantic_evidence))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@runtime_checkable
class CompilerStrategy(Protocol):
    """Optional compiler plugin normalized at a provider-neutral boundary."""

    @property
    def strategy_id(self) -> str: ...

    @property
    def strategy_version(self) -> str: ...

    @property
    def options(self) -> Mapping[str, Any]: ...

    def run(self, program: Program, target: Target) -> StrategyResult: ...


@dataclass(frozen=True)
class QCoreNativeStrategy:
    """Adapter for QCore's required Rust O2 compiler and router."""

    compile_options: CompileOptions = field(
        default_factory=lambda: CompileOptions(optimization_level=2)
    )
    strategy_id: str = "qcore-native"
    strategy_version: str = field(default_factory=lambda: _package_version("qplanck"))

    def __post_init__(self) -> None:
        if not isinstance(self.compile_options, CompileOptions):
            raise TypeError("compile_options must be CompileOptions.")
        if self.compile_options.optimization_level != 2:
            raise ValueError("QCoreNativeStrategy requires optimization_level=2.")
        object.__setattr__(self, "strategy_id", _non_empty(self.strategy_id, label="strategy_id"))
        object.__setattr__(
            self,
            "strategy_version",
            _non_empty(self.strategy_version, label="strategy_version"),
        )

    @property
    def options(self) -> Mapping[str, Any]:
        return MappingProxyType(self.compile_options.to_dict())

    def run(self, program: Program, target: Target) -> StrategyResult:
        started = time.perf_counter_ns()
        compiled = compile(program.ir, self.compile_options, target=target)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        trace = compiled.routing_trace
        return StrategyResult(
            artifact=compiled,
            semantic_equivalent=True,
            semantic_evidence=(
                "QCore native exact-rewrite and target-routing compiler contract.",
                f"Compilation trace {compiled.trace.content_hash}.",
            ),
            inserted_swap_count=None if trace is None else len(trace.steps),
            inserted_swap_unknown_reason=(
                "Native compilation returned no routing trace." if trace is None else None
            ),
            compilation_latency_ms=elapsed_ms,
            provenance={
                "compiler": "qplanck.native",
                "compiler_version": self.strategy_version,
                "compiled_evidence_hash": compiled.content_hash,
                "trace_hash": compiled.trace.content_hash,
            },
        )


@dataclass(frozen=True)
class CandidatePlan:
    """Evidence for one Program x strategy x Target candidate."""

    program_hash: str
    target: Target
    strategy_id: str
    strategy_version: str
    strategy_options: Mapping[str, Any]
    disposition: CandidateDisposition
    artifact_ir: CircuitIR | None = None
    artifact_hash: str | None = None
    metrics: PlanMetrics | None = None
    semantic_evidence: tuple[str, ...] = ()
    validation_evidence: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    score: Decimal | None = None
    score_components: Mapping[str, Decimal] = field(default_factory=dict)
    rank: int | None = None
    pareto: bool = False
    schema_version: str = CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CANDIDATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported CandidatePlan schema: {self.schema_version}.")
        if not self.program_hash.startswith("sha256:"):
            raise ValueError("Candidate program_hash must be a SHA-256 identity.")
        if not isinstance(self.target, Target):
            raise TypeError("Candidate target must be a Target snapshot.")
        _assert_secret_free(self.target.to_dict(), path="candidate.target")
        object.__setattr__(self, "strategy_id", _non_empty(self.strategy_id, label="strategy_id"))
        object.__setattr__(
            self,
            "strategy_version",
            _non_empty(self.strategy_version, label="strategy_version"),
        )
        try:
            disposition = CandidateDisposition(self.disposition)
        except ValueError as error:
            raise ValueError(f"Unknown candidate disposition {self.disposition!r}.") from error
        object.__setattr__(self, "disposition", disposition)
        options = _freeze_json(self.strategy_options)
        provenance = _freeze_json(self.provenance)
        _assert_secret_free(options, path="candidate.strategy_options")
        _assert_secret_free(provenance, path="candidate.provenance")
        object.__setattr__(self, "strategy_options", options)
        object.__setattr__(self, "provenance", provenance)
        if self.artifact_ir is not None and not isinstance(self.artifact_ir, CircuitIR):
            raise TypeError("Candidate artifact_ir must be CircuitIR or None.")
        if self.artifact_ir is None and self.artifact_hash is not None:
            raise ValueError("Candidate without an artifact cannot carry artifact_hash.")
        if self.artifact_ir is not None:
            _assert_secret_free(self.artifact_ir.to_dict(), path="candidate.artifact_ir")
            expected_artifact_hash = _content_hash(self.artifact_ir.to_dict())
            if self.artifact_hash is None:
                object.__setattr__(self, "artifact_hash", expected_artifact_hash)
            elif self.artifact_hash != expected_artifact_hash:
                raise ValueError("Candidate artifact_hash does not match artifact_ir.")
        if disposition is CandidateDisposition.VALID:
            if self.artifact_ir is None or self.metrics is None or self.rejection_reasons:
                raise ValueError(
                    "Valid candidates require artifact and metrics, without rejections."
                )
        elif not self.rejection_reasons:
            raise ValueError("Non-valid candidates require at least one rejection reason.")
        if self.score is not None:
            object.__setattr__(self, "score", _decimal(self.score))
        components = {
            str(name): _decimal(value) for name, value in sorted(self.score_components.items())
        }
        object.__setattr__(self, "score_components", MappingProxyType(components))
        if disposition is not CandidateDisposition.VALID and (
            self.score is not None or components or self.rank is not None or self.pareto
        ):
            raise ValueError("Rejected candidates cannot carry ranking evidence.")
        if self.rank is not None and (
            isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1
        ):
            raise ValueError("Candidate rank must be a positive integer or None.")
        if not isinstance(self.pareto, bool):
            raise TypeError("Candidate pareto must be a boolean.")
        for label in (
            "semantic_evidence",
            "validation_evidence",
            "rejection_reasons",
            "assumptions",
            "diagnostics",
        ):
            object.__setattr__(self, label, tuple(str(item) for item in getattr(self, label)))

    @property
    def candidate_id(self) -> str:
        return _content_hash(
            {
                "schema_version": self.schema_version,
                "program_hash": self.program_hash,
                "target_hash": self.target.content_hash,
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "strategy_options": _thaw_json(self.strategy_options),
            }
        )

    @property
    def candidate_hash(self) -> str:
        payload = self.to_dict(include_hash=False, include_observations=False)
        # Candidate identity describes compiler output and validation evidence,
        # not its later position in one particular Objective decision.
        for field_name in ("score", "score_components", "rank", "pareto"):
            payload.pop(field_name, None)
        return _content_hash(payload)

    @property
    def content_hash(self) -> str:
        return self.candidate_hash

    def to_dict(
        self,
        *,
        include_hash: bool = True,
        include_observations: bool = False,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "program_hash": self.program_hash,
            "target": self.target.to_dict(),
            "target_hash": self.target.content_hash,
            "strategy": {
                "id": self.strategy_id,
                "version": self.strategy_version,
                "options": _thaw_json(self.strategy_options),
            },
            "disposition": self.disposition.value,
            "artifact_ir": None if self.artifact_ir is None else self.artifact_ir.to_dict(),
            "artifact_hash": self.artifact_hash,
            "metrics": (
                None
                if self.metrics is None
                else self.metrics.to_dict(include_observations=include_observations)
            ),
            "semantic_evidence": list(self.semantic_evidence),
            "validation_evidence": list(self.validation_evidence),
            "rejection_reasons": list(self.rejection_reasons),
            "assumptions": list(self.assumptions),
            "diagnostics": list(self.diagnostics),
            "provenance": _thaw_json(self.provenance),
            "score": None if self.score is None else _decimal_text(self.score),
            "score_components": {
                name: _decimal_text(value) for name, value in self.score_components.items()
            },
            "rank": self.rank,
            "pareto": self.pareto,
        }
        if include_hash:
            payload["candidate_hash"] = self.candidate_hash
        _assert_secret_free(payload, path="candidate")
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CandidatePlan:
        raw_target = data.get("target")
        raw_strategy = data.get("strategy")
        raw_ir = data.get("artifact_ir")
        raw_metrics = data.get("metrics")
        if not isinstance(raw_target, dict) or not isinstance(raw_strategy, Mapping):
            raise ValueError("Candidate target and strategy must be objects.")
        candidate = cls(
            program_hash=str(data["program_hash"]),
            target=Target.from_dict(raw_target),
            strategy_id=str(raw_strategy["id"]),
            strategy_version=str(raw_strategy["version"]),
            strategy_options=dict(raw_strategy.get("options", {})),
            disposition=CandidateDisposition(str(data["disposition"])),
            artifact_ir=(None if raw_ir is None else CircuitIR.from_dict(raw_ir)),
            artifact_hash=data.get("artifact_hash"),
            metrics=None if raw_metrics is None else PlanMetrics.from_dict(raw_metrics),
            semantic_evidence=tuple(str(item) for item in data.get("semantic_evidence", ())),
            validation_evidence=tuple(str(item) for item in data.get("validation_evidence", ())),
            rejection_reasons=tuple(str(item) for item in data.get("rejection_reasons", ())),
            assumptions=tuple(str(item) for item in data.get("assumptions", ())),
            diagnostics=tuple(str(item) for item in data.get("diagnostics", ())),
            provenance=dict(data.get("provenance", {})),
            score=None if data.get("score") is None else _decimal(data["score"]),
            score_components={
                str(name): _decimal(value)
                for name, value in dict(data.get("score_components", {})).items()
            },
            rank=data.get("rank"),
            pareto=bool(data.get("pareto", False)),
            schema_version=str(data.get("schema_version", CANDIDATE_SCHEMA_VERSION)),
        )
        for field_name, actual in (
            ("candidate_id", candidate.candidate_id),
            ("candidate_hash", candidate.candidate_hash),
            ("target_hash", candidate.target.content_hash),
        ):
            expected = data.get(field_name)
            if expected is not None and expected != actual:
                raise ValueError(f"Candidate {field_name} does not match normalized content.")
        return candidate


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Score values must be finite decimal numbers.") from error
    if not result.is_finite():
        raise ValueError("Score values must be finite decimal numbers.")
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


@dataclass(frozen=True)
class PlanExplanation:
    """Structured, printable explanation for one planning decision."""

    winner: Mapping[str, Any]
    alternatives: tuple[Mapping[str, Any], ...]
    rejected_by_reason: Mapping[str, tuple[str, ...]]
    assumptions: tuple[str, ...]
    caveat: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "winner", _freeze_json(self.winner))
        object.__setattr__(
            self,
            "alternatives",
            tuple(_freeze_json(item) for item in self.alternatives),
        )
        object.__setattr__(
            self,
            "rejected_by_reason",
            MappingProxyType(
                {str(key): tuple(values) for key, values in sorted(self.rejected_by_reason.items())}
            ),
        )
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

    def to_dict(self) -> dict[str, object]:
        return {
            "winner": _thaw_json(self.winner),
            "alternatives": [_thaw_json(item) for item in self.alternatives],
            "rejected_by_reason": {
                reason: list(candidate_ids)
                for reason, candidate_ids in self.rejected_by_reason.items()
            },
            "assumptions": list(self.assumptions),
            "caveat": self.caveat,
        }

    def to_text(self) -> str:
        winner = self.winner
        lines = [
            (
                f"Selected {winner['strategy_id']} on {winner['target_id']} "
                f"(rank {winner['rank']}, score {winner['score']})."
            ),
            f"Metrics: {_canonical_json(_thaw_json(winner['metrics']))}.",
            f"Why it won: {winner['why']}.",
        ]
        if self.alternatives:
            closest = self.alternatives[0]
            lines.append(
                f"Closest alternative: {closest['strategy_id']} on {closest['target_id']} "
                f"(rank {closest['rank']}, score {closest['score']}): {closest['why_lost']}."
            )
        if self.rejected_by_reason:
            summary = ", ".join(
                f"{reason}={len(candidate_ids)}"
                for reason, candidate_ids in self.rejected_by_reason.items()
            )
            lines.append(f"Rejected candidates: {summary}.")
        if self.assumptions:
            lines.append(f"Assumptions: {'; '.join(self.assumptions)}.")
        lines.append(self.caveat)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True)
class Plan:
    """Frozen offline planning decision containing all candidate evidence."""

    program: Program
    objective: Objective
    candidates: tuple[CandidatePlan, ...]
    selected_candidate_id: str
    planner_version: str = field(default_factory=lambda: _package_version("qplanck"))
    observations: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    schema_version: str = PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Plan schema: {self.schema_version}.")
        if not isinstance(self.program, Program) or not isinstance(self.objective, Objective):
            raise TypeError("Plan requires Program and Objective objects.")
        candidates = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
        if not candidates:
            raise ValueError("Plan requires candidate evidence.")
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise ValueError("Plan candidate IDs must be unique.")
        if any(item.program_hash != self.program.program_hash for item in candidates):
            raise ValueError("Every Plan candidate must reference the Plan Program hash.")
        selected = [item for item in candidates if item.candidate_id == self.selected_candidate_id]
        if len(selected) != 1 or selected[0].disposition is not CandidateDisposition.VALID:
            raise ValueError("selected_candidate_id must identify exactly one valid candidate.")
        valid_candidates = tuple(
            item for item in candidates if item.disposition is CandidateDisposition.VALID
        )
        if any(item.rank is None for item in valid_candidates):
            raise ValueError("Every valid candidate must have a rank.")
        valid_ranks = sorted(item.rank for item in valid_candidates if item.rank is not None)
        if valid_ranks != list(range(1, len(valid_ranks) + 1)):
            raise ValueError("Valid candidate ranks must be contiguous from one.")
        if selected[0].rank != 1:
            raise ValueError("selected_candidate_id must identify the rank-one candidate.")

        # Scores, Pareto membership, and ranks are reconstructible entirely
        # from immutable candidate evidence plus the Objective. Validate them
        # rather than trusting serialized decision fields.
        expected_candidates = {
            item.candidate_id: item for item in _rank_candidates(candidates, self.objective)
        }
        for candidate in valid_candidates:
            expected = expected_candidates[candidate.candidate_id]
            if (
                candidate.score != expected.score
                or dict(candidate.score_components) != dict(expected.score_components)
                or candidate.rank != expected.rank
                or candidate.pareto != expected.pareto
            ):
                raise ValueError(
                    "Plan candidate ranking evidence does not match the deterministic Objective."
                )
        observations = _freeze_json(self.observations)
        _assert_secret_free(observations, path="plan.observations")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(
            self, "planner_version", _non_empty(self.planner_version, label="planner_version")
        )
        object.__setattr__(self, "observations", observations)

    @property
    def selected(self) -> CandidatePlan:
        return next(
            item for item in self.candidates if item.candidate_id == self.selected_candidate_id
        )

    @property
    def alternatives(self) -> tuple[CandidatePlan, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.candidates
                    if item.disposition is CandidateDisposition.VALID
                    and item.candidate_id != self.selected_candidate_id
                ),
                key=lambda item: item.rank if item.rank is not None else sys.maxsize,
            )
        )

    @property
    def pareto_alternatives(self) -> tuple[CandidatePlan, ...]:
        return tuple(item for item in self.alternatives if item.pareto)

    @property
    def rejected(self) -> tuple[CandidatePlan, ...]:
        return tuple(
            item for item in self.candidates if item.disposition is not CandidateDisposition.VALID
        )

    @property
    def plan_hash(self) -> str:
        return _content_hash(self.to_dict(include_hash=False, include_observations=False))

    @property
    def content_hash(self) -> str:
        return self.plan_hash

    @property
    def manifest(self) -> PlanningManifest:
        return PlanningManifest.from_plan(self)

    def to_dict(
        self,
        *,
        include_hash: bool = True,
        include_observations: bool = False,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "planner_version": self.planner_version,
            "program": self.program.to_dict(),
            "objective": self.objective.to_dict(),
            "candidates": [
                item.to_dict(include_observations=include_observations) for item in self.candidates
            ],
            "selected_candidate_id": self.selected_candidate_id,
        }
        if include_observations:
            payload["observations"] = _thaw_json(self.observations)
        if include_hash:
            payload["plan_hash"] = self.plan_hash
        _assert_secret_free(payload, path="plan")
        return payload

    def to_json(
        self,
        *,
        indent: int | None = None,
        include_observations: bool = False,
    ) -> str:
        return json.dumps(
            self.to_dict(include_observations=include_observations),
            allow_nan=False,
            indent=indent,
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Plan:
        raw_program = data.get("program")
        raw_objective = data.get("objective")
        raw_candidates = data.get("candidates")
        if not isinstance(raw_program, Mapping) or not isinstance(raw_objective, Mapping):
            raise ValueError("Plan program and objective must be objects.")
        if not isinstance(raw_candidates, list):
            raise ValueError("Plan candidates must be a list.")
        decision = cls(
            program=Program.from_dict(raw_program),
            objective=Objective.from_dict(raw_objective),
            candidates=tuple(CandidatePlan.from_dict(item) for item in raw_candidates),
            selected_candidate_id=str(data["selected_candidate_id"]),
            planner_version=str(data.get("planner_version", "unknown")),
            observations=dict(data.get("observations", {})),
            schema_version=str(data.get("schema_version", PLAN_SCHEMA_VERSION)),
        )
        expected = data.get("plan_hash")
        if expected is not None and expected != decision.plan_hash:
            raise ValueError("Plan hash does not match normalized content.")
        return decision

    @classmethod
    def from_json(cls, text: str) -> Plan:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Plan JSON must contain an object.")
        return cls.from_dict(value)

    def explain(self) -> PlanExplanation:
        winner = self.selected
        if winner.metrics is None or winner.score is None or winner.rank is None:
            raise RuntimeError("Selected candidate is missing ranking evidence.")
        weighted_metrics = ", ".join(
            f"{name}={winner.metrics.metric_value(name)} x {self.objective.weights[name]}"
            for name in self.objective.weights
        )
        winner_payload = {
            "candidate_id": winner.candidate_id,
            "target_id": winner.target.target_id,
            "target_hash": winner.target.content_hash,
            "strategy_id": winner.strategy_id,
            "strategy_version": winner.strategy_version,
            "rank": winner.rank,
            "score": _decimal_text(winner.score),
            "score_components": {
                name: _decimal_text(value) for name, value in winner.score_components.items()
            },
            "metrics": winner.metrics.to_dict(),
            "why": f"lowest deterministic rank tuple; weighted terms were {weighted_metrics}",
            "validation_evidence": list(winner.validation_evidence),
        }
        alternatives: list[Mapping[str, Any]] = []
        for candidate in self.alternatives:
            if candidate.metrics is None or candidate.score is None:
                continue
            differences = []
            for metric in self.objective.weights:
                selected_value = winner.metrics.metric_value(metric)
                candidate_value = candidate.metrics.metric_value(metric)
                differences.append(f"{metric}={candidate_value} versus selected {selected_value}")
            alternatives.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "target_id": candidate.target.target_id,
                    "strategy_id": candidate.strategy_id,
                    "rank": candidate.rank,
                    "score": _decimal_text(candidate.score),
                    "pareto": candidate.pareto,
                    "metrics": candidate.metrics.to_dict(),
                    "why_lost": (
                        "higher deterministic score or tie-break; " + "; ".join(differences)
                    ),
                }
            )
        rejected: dict[str, list[str]] = {}
        for candidate in self.rejected:
            for reason in candidate.rejection_reasons:
                rejected.setdefault(reason, []).append(candidate.candidate_id)
            for diagnostic in candidate.diagnostics:
                if diagnostic.startswith(_STRATEGY_REASON_DIAGNOSTIC_PREFIX):
                    rejected.setdefault(diagnostic, []).append(candidate.candidate_id)
        assumptions = tuple(
            dict.fromkeys(
                (
                    *winner.assumptions,
                    *winner.metrics.error_model_assumptions,
                )
            )
        )
        return PlanExplanation(
            winner=winner_payload,
            alternatives=tuple(alternatives),
            rejected_by_reason={
                reason: tuple(sorted(candidate_ids))
                for reason, candidate_ids in sorted(rejected.items())
            },
            assumptions=assumptions,
            caveat=(
                "Selection is an offline planning result. Estimated error is not a "
                "hardware-performance or fidelity guarantee; no remote execution occurred."
            ),
        )


@dataclass(frozen=True)
class PlanningManifest:
    """Secret-free reproducibility manifest for an offline planning decision."""

    program: Program
    objective: Objective
    targets: tuple[Target, ...]
    candidates: tuple[CandidatePlan, ...]
    selected_plan_hash: str
    selected_candidate_id: str
    planner_version: str
    environment: Mapping[str, Any]
    observations: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported PlanningManifest schema: {self.schema_version}.")
        targets = tuple(sorted(self.targets, key=lambda item: item.content_hash))
        candidates = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
        environment = _freeze_json(self.environment)
        observations = _freeze_json(self.observations)
        semantic_payload = {
            "program": self.program.to_dict(),
            "objective": self.objective.to_dict(),
            "targets": [item.to_dict() for item in targets],
            "candidates": [item.to_dict() for item in candidates],
            "environment": _thaw_json(environment),
        }
        _assert_secret_free(semantic_payload, path="manifest")
        _assert_secret_free(observations, path="manifest.observations")
        if not self.selected_plan_hash.startswith("sha256:"):
            raise ValueError("Manifest selected_plan_hash must be a SHA-256 identity.")
        selected = [item for item in candidates if item.candidate_id == self.selected_candidate_id]
        if len(selected) != 1 or selected[0].disposition is not CandidateDisposition.VALID:
            raise ValueError("Manifest selected_candidate_id must identify one valid candidate.")
        target_hashes = {item.content_hash for item in targets}
        candidate_target_hashes = {item.target.content_hash for item in candidates}
        if target_hashes != candidate_target_hashes:
            raise ValueError("Manifest targets must exactly match the candidate target snapshots.")

        reconstructed_plan = Plan(
            program=self.program,
            objective=self.objective,
            candidates=candidates,
            selected_candidate_id=self.selected_candidate_id,
            planner_version=self.planner_version,
            observations=observations,
        )
        if self.selected_plan_hash != reconstructed_plan.plan_hash:
            raise ValueError("Manifest selected_plan_hash does not match the reconstructed Plan.")
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "observations", observations)

    @classmethod
    def from_plan(cls, decision: Plan) -> PlanningManifest:
        unique_targets = {item.target.content_hash: item.target for item in decision.candidates}
        return cls(
            program=decision.program,
            objective=decision.objective,
            targets=tuple(unique_targets.values()),
            candidates=decision.candidates,
            selected_plan_hash=decision.plan_hash,
            selected_candidate_id=decision.selected_candidate_id,
            planner_version=decision.planner_version,
            environment={
                "qplanck_version": decision.planner_version,
                "python_implementation": platform.python_implementation(),
                "python_version": platform.python_version(),
                "operating_system": platform.system(),
                "machine": platform.machine(),
            },
            observations=decision.observations,
        )

    @property
    def manifest_hash(self) -> str:
        return _content_hash(self.to_dict(include_hash=False, include_observations=False))

    @property
    def content_hash(self) -> str:
        return self.manifest_hash

    def to_dict(
        self,
        *,
        include_hash: bool = True,
        include_observations: bool = False,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "deterministic_mode": True,
            "execution_profile": "offline-planning-only",
            "planner_version": self.planner_version,
            "program": self.program.to_dict(),
            "objective": self.objective.to_dict(),
            "targets": [item.to_dict() for item in self.targets],
            "target_hashes": [item.content_hash for item in self.targets],
            "candidates": [
                item.to_dict(include_observations=include_observations) for item in self.candidates
            ],
            "selected_candidate_id": self.selected_candidate_id,
            "selected_plan_hash": self.selected_plan_hash,
            "environment": _thaw_json(self.environment),
            "secrets_recorded": False,
            "provider_sdk_objects_recorded": False,
        }
        if include_observations:
            payload["observations"] = _thaw_json(self.observations)
        if include_hash:
            payload["manifest_hash"] = self.manifest_hash
        return payload

    def to_json(
        self,
        *,
        indent: int | None = None,
        include_observations: bool = False,
    ) -> str:
        return json.dumps(
            self.to_dict(include_observations=include_observations),
            allow_nan=False,
            indent=indent,
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlanningManifest:
        raw_program = data.get("program")
        raw_objective = data.get("objective")
        raw_targets = data.get("targets")
        raw_candidates = data.get("candidates")
        if not isinstance(raw_program, Mapping) or not isinstance(raw_objective, Mapping):
            raise ValueError("Manifest program and objective must be objects.")
        if not isinstance(raw_targets, list) or not isinstance(raw_candidates, list):
            raise ValueError("Manifest targets and candidates must be lists.")
        manifest = cls(
            program=Program.from_dict(raw_program),
            objective=Objective.from_dict(raw_objective),
            targets=tuple(Target.from_dict(item) for item in raw_targets),
            candidates=tuple(CandidatePlan.from_dict(item) for item in raw_candidates),
            selected_plan_hash=str(data["selected_plan_hash"]),
            selected_candidate_id=str(data["selected_candidate_id"]),
            planner_version=str(data.get("planner_version", "unknown")),
            environment=dict(data.get("environment", {})),
            observations=dict(data.get("observations", {})),
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
        )
        expected_target_hashes = data.get("target_hashes")
        if expected_target_hashes is not None and list(expected_target_hashes) != [
            item.content_hash for item in manifest.targets
        ]:
            raise ValueError("Manifest target_hashes do not match target snapshots.")
        expected = data.get("manifest_hash")
        if expected is not None and expected != manifest.manifest_hash:
            raise ValueError("Manifest hash does not match normalized content.")
        return manifest

    @classmethod
    def from_json(cls, text: str) -> PlanningManifest:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("PlanningManifest JSON must contain an object.")
        return cls.from_dict(value)

    def write(
        self,
        path: str | Path,
        *,
        include_observations: bool = True,
    ) -> None:
        """Write a manifest artifact; the destination path is never recorded."""

        Path(path).write_text(
            self.to_json(indent=2, include_observations=include_observations) + "\n",
            encoding="utf-8",
        )


class PlanningError(ValueError):
    """Raised when no valid candidate remains, with ordered rejection evidence."""

    def __init__(self, message: str, *, candidates: tuple[CandidatePlan, ...]):
        super().__init__(message)
        self.candidates = candidates


class _CandidateBase(TypedDict):
    program_hash: str
    target: Target
    strategy_id: str
    strategy_version: str
    strategy_options: Mapping[str, Any]


def plan(
    source: Program | Circuit | CircuitIR | str | object,
    *,
    targets: Sequence[Target],
    strategies: Sequence[CompilerStrategy] | None = None,
    objective: Objective | str = "minimize_error",
) -> Plan:
    """Evaluate explicit offline candidates and return one explainable decision.

    This function never discovers credentials, contacts a provider, or submits a
    job.  Candidate latency is observed for benchmark evidence but cannot affect
    selection or any semantic hash.
    """

    started_at = datetime.now(UTC)
    program = Program.from_input(source)
    resolved_objective = Objective.from_name(objective) if isinstance(objective, str) else objective
    if not isinstance(resolved_objective, Objective):
        raise TypeError("objective must be an Objective or built-in objective name.")
    normalized_targets = tuple(sorted(targets, key=lambda item: item.content_hash))
    if not normalized_targets or any(not isinstance(item, Target) for item in normalized_targets):
        raise ValueError("targets must contain at least one Target snapshot.")

    resolved_strategies: Sequence[CompilerStrategy]
    if strategies is None:
        resolved_strategies = (
            QCoreNativeStrategy(strategy_id="qcore-native.adaptive"),
            QCoreNativeStrategy(
                compile_options=CompileOptions(
                    optimization_level=2,
                    initial_layout=Layout.identity(program.ir.qubit_count),
                    placement_trials=1,
                ),
                strategy_id="qcore-native.identity-baseline",
            ),
        )
    else:
        resolved_strategies = strategies

    descriptors = []
    for strategy in resolved_strategies:
        if not isinstance(strategy, CompilerStrategy):
            raise TypeError("Every strategy must satisfy CompilerStrategy.")
        strategy_id = _non_empty(strategy.strategy_id, label="strategy_id")
        strategy_version = _non_empty(strategy.strategy_version, label="strategy_version")
        options = _freeze_json(strategy.options)
        _assert_secret_free(options, path=f"strategy.{strategy_id}.options")
        descriptors.append(
            (strategy_id, strategy_version, _canonical_json(_thaw_json(options)), strategy)
        )
    descriptors.sort(key=lambda item: item[:3])
    if not descriptors:
        raise ValueError("strategies must contain at least one CompilerStrategy.")

    descriptor_keys = [item[:3] for item in descriptors]
    if len(set(descriptor_keys)) != len(descriptor_keys):
        raise ValueError("Strategy descriptors must be unique by ID, version, and options.")

    candidates: list[CandidatePlan] = []
    for target in normalized_targets:
        _assert_secret_free(target.to_dict(), path=f"target.{target.target_id}")
        for strategy_id, strategy_version, _, strategy in descriptors:
            options = dict(strategy.options)
            candidate = _run_candidate(
                program,
                target,
                resolved_objective,
                strategy,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                options=options,
            )
            candidates.append(candidate)

    ranked = _rank_candidates(tuple(candidates), resolved_objective)
    valid = tuple(item for item in ranked if item.disposition is CandidateDisposition.VALID)
    if not valid:
        ordered = tuple(sorted(ranked, key=lambda item: item.candidate_id))
        reasons = sorted({reason for item in ordered for reason in item.rejection_reasons})
        raise PlanningError(
            "No valid planning candidate remained; rejection reasons: " + ", ".join(reasons),
            candidates=ordered,
        )
    selected = min(valid, key=lambda item: item.rank if item.rank is not None else sys.maxsize)
    finished_at = datetime.now(UTC)
    observations = {
        "planning_started_at": started_at.isoformat(),
        "planning_finished_at": finished_at.isoformat(),
        "planning_latency_ms": (finished_at - started_at).total_seconds() * 1000.0,
    }
    return Plan(
        program=program,
        objective=resolved_objective,
        candidates=ranked,
        selected_candidate_id=selected.candidate_id,
        observations=observations,
    )


def _run_candidate(
    program: Program,
    target: Target,
    objective: Objective,
    strategy: CompilerStrategy,
    *,
    strategy_id: str,
    strategy_version: str,
    options: Mapping[str, Any],
) -> CandidatePlan:
    base: _CandidateBase = {
        "program_hash": program.program_hash,
        "target": target,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "strategy_options": options,
    }
    try:
        result = strategy.run(program, target)
    except StrategyUnavailableError as error:
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.UNAVAILABLE,
            rejection_reasons=("strategy_unavailable",),
            diagnostics=(f"{_STRATEGY_REASON_DIAGNOSTIC_PREFIX}{error.reason_code}",),
        )
    except StrategyUnsupportedError as error:
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.UNSUPPORTED,
            rejection_reasons=("strategy_unsupported",),
            diagnostics=(f"{_STRATEGY_REASON_DIAGNOSTIC_PREFIX}{error.reason_code}",),
        )
    except StrategyTimeoutError as error:
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.TIMED_OUT,
            rejection_reasons=("strategy_timed_out",),
            diagnostics=(f"{_STRATEGY_REASON_DIAGNOSTIC_PREFIX}{error.reason_code}",),
        )
    except Exception as error:  # noqa: BLE001 - plugin failures become stable evidence
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.FAILED,
            rejection_reasons=("strategy_failed",),
            diagnostics=(f"Strategy raised {type(error).__module__}.{type(error).__qualname__}.",),
        )
    if not isinstance(result, StrategyResult):
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.FAILED,
            rejection_reasons=("invalid_strategy_result",),
        )

    artifact_ir, compiled_hash, source_matches = _normalize_strategy_artifact(
        result.artifact, program
    )
    rejection_reasons: list[str] = []
    validation_evidence: list[str] = []
    if not result.semantic_equivalent:
        rejection_reasons.append("semantic_validation_failed")
    elif not result.semantic_evidence:
        rejection_reasons.append("semantic_evidence_missing")
    else:
        validation_evidence.append("strategy_reported_semantic_equivalence")
    if source_matches is False:
        rejection_reasons.append("compiled_source_mismatch")

    unsupported_operations = tuple(
        (index, operation.name, operation.qubits)
        for index, operation in enumerate(artifact_ir.operations)
        if not target.supports_operation(operation)
    )
    if unsupported_operations:
        rejection_reasons.append("target_validation_failed")
    else:
        validation_evidence.append("all_final_operations_supported_by_target_snapshot")

    estimated_error, error_reason = _estimate_instruction_error(artifact_ir, target)
    metrics = PlanMetrics(
        circuit_depth=_circuit_depth(artifact_ir),
        two_qubit_gate_count=sum(len(item.qubits) == 2 for item in artifact_ir.operations),
        two_qubit_operation_families=tuple(
            item.name for item in artifact_ir.operations if len(item.qubits) == 2
        ),
        inserted_swap_count=result.inserted_swap_count,
        inserted_swap_unknown_reason=result.inserted_swap_unknown_reason,
        user_authored_swap_count=sum(item.name == "swap" for item in program.ir.operations),
        estimated_error=estimated_error,
        estimated_error_unknown_reason=error_reason,
        compilation_latency_ms=result.compilation_latency_ms,
    )
    rejection_reasons.extend(_constraint_rejections(metrics, objective))
    if rejection_reasons:
        return CandidatePlan(
            **base,
            disposition=CandidateDisposition.REJECTED,
            artifact_ir=artifact_ir,
            metrics=metrics,
            semantic_evidence=result.semantic_evidence,
            validation_evidence=tuple(validation_evidence),
            rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
            assumptions=result.assumptions,
            diagnostics=(*result.diagnostics, *(_unsupported_diagnostics(unsupported_operations))),
            provenance={
                **dict(result.provenance),
                **({"compiled_evidence_hash": compiled_hash} if compiled_hash else {}),
            },
        )
    return CandidatePlan(
        **base,
        disposition=CandidateDisposition.VALID,
        artifact_ir=artifact_ir,
        metrics=metrics,
        semantic_evidence=result.semantic_evidence,
        validation_evidence=tuple(validation_evidence),
        assumptions=result.assumptions,
        diagnostics=result.diagnostics,
        provenance={
            **dict(result.provenance),
            **({"compiled_evidence_hash": compiled_hash} if compiled_hash else {}),
        },
    )


def _normalize_strategy_artifact(
    artifact: CircuitIR | Circuit | CompiledCircuit,
    program: Program,
) -> tuple[CircuitIR, str | None, bool | None]:
    if isinstance(artifact, CompiledCircuit):
        source_matches = _content_hash(artifact.source_ir.to_dict()) == _content_hash(
            program.ir.to_dict()
        )
        return artifact.ir, artifact.content_hash, source_matches
    if isinstance(artifact, Circuit):
        return artifact.ir, None, None
    return artifact, None, None


def _unsupported_diagnostics(
    operations: tuple[tuple[int, str, tuple[int, ...]], ...],
) -> tuple[str, ...]:
    return tuple(
        f"Operation {index} {name}{qubits!r} is unsupported by the target snapshot."
        for index, name, qubits in operations
    )


def _circuit_depth(ir: CircuitIR) -> int:
    last_depth = [0] * ir.qubit_count
    maximum = 0
    for operation in ir.operations:
        depth = 1 + max((last_depth[qubit] for qubit in operation.qubits), default=0)
        for qubit in operation.qubits:
            last_depth[qubit] = depth
        maximum = max(maximum, depth)
    # Measurements are terminal observations and excluded from v0.1 gate depth.
    return maximum


def _estimate_instruction_error(ir: CircuitIR, target: Target) -> tuple[float | None, str | None]:
    if not ir.operations:
        return 0.0, None
    raw_errors = target.metadata.get("instruction_errors")
    if not isinstance(raw_errors, Mapping):
        return None, "Target snapshot has no instruction_errors evidence map."
    log_success = 0.0
    missing: list[str] = []
    for operation in ir.operations:
        location = ",".join(str(item) for item in operation.qubits)
        exact_key = f"{operation.name}:{location}"
        error_value = raw_errors.get(exact_key, raw_errors.get(operation.name))
        if error_value is None and operation.name in {"cz", "swap"} and len(operation.qubits) == 2:
            reverse = f"{operation.name}:{operation.qubits[1]},{operation.qubits[0]}"
            error_value = raw_errors.get(reverse)
        if error_value is None:
            missing.append(exact_key)
            continue
        if isinstance(error_value, bool) or not isinstance(error_value, int | float):
            return None, f"Instruction error evidence for {exact_key} is not numeric."
        rate = float(error_value)
        if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
            return None, f"Instruction error evidence for {exact_key} is outside [0, 1]."
        if rate == 1.0:
            log_success = -math.inf
        elif log_success != -math.inf:
            log_success += math.log1p(-rate)
    if missing:
        return None, "Missing instruction error evidence for: " + ", ".join(sorted(set(missing)))
    return (1.0 if log_success == -math.inf else -math.expm1(log_success)), None


def _constraint_rejections(metrics: PlanMetrics, objective: Objective) -> tuple[str, ...]:
    reasons: list[str] = []
    for name, constraint in objective.constraints.items():
        value = metrics.metric_value(name)
        if value is None:
            reasons.append(f"constraint_metric_unknown:{name}")
            continue
        if constraint.minimum is not None and value < constraint.minimum:
            reasons.append(f"constraint_minimum_violated:{name}")
        if constraint.maximum is not None and value > constraint.maximum:
            reasons.append(f"constraint_maximum_violated:{name}")
    for name in objective.weights:
        if metrics.metric_value(name) is None and objective.unknown_policy == "reject_required":
            reasons.append(f"required_metric_unknown:{name}")
    return tuple(reasons)


def _rank_candidates(
    candidates: tuple[CandidatePlan, ...], objective: Objective
) -> tuple[CandidatePlan, ...]:
    scored: list[CandidatePlan] = []
    rejected = [item for item in candidates if item.disposition is not CandidateDisposition.VALID]
    for candidate in candidates:
        if candidate.disposition is not CandidateDisposition.VALID:
            continue
        if candidate.metrics is None:
            raise RuntimeError("Valid candidate is missing metrics.")
        components: dict[str, Decimal] = {}
        for metric, weight in objective.weights.items():
            raw = candidate.metrics.metric_value(metric)
            if raw is None:
                if objective.unknown_policy != "penalize" or objective.unknown_penalty is None:
                    raise RuntimeError("Unknown required metric escaped validation.")
                loss = _decimal(objective.unknown_penalty)
            else:
                loss = _decimal(raw) / _decimal(objective.scales[metric])
            components[metric] = _decimal(weight) * loss
        score = sum(components.values(), start=Decimal(0))
        scored.append(replace(candidate, score=score, score_components=components))

    pareto_ids = _pareto_ids(tuple(scored), objective)
    ranked = sorted(scored, key=lambda item: _rank_key(item, objective))
    ranked = [
        replace(item, rank=index, pareto=item.candidate_id in pareto_ids)
        for index, item in enumerate(ranked, start=1)
    ]
    return tuple(sorted((*ranked, *rejected), key=lambda item: item.candidate_id))


def _rank_key(candidate: CandidatePlan, objective: Objective) -> tuple[object, ...]:
    if candidate.metrics is None or candidate.score is None:
        raise RuntimeError("Only scored valid candidates can be ranked.")
    terms: list[object] = [candidate.score]
    for name in objective.tie_break:
        if name == "candidate_hash":
            terms.append(candidate.candidate_hash)
            continue
        value = candidate.metrics.metric_value(name)
        terms.append((value is None, 0 if value is None else value))
    return tuple(terms)


def _pareto_ids(candidates: tuple[CandidatePlan, ...], objective: Objective) -> frozenset[str]:
    result: set[str] = set()
    metrics = tuple(objective.weights)
    for candidate in candidates:
        if candidate.metrics is None:
            continue
        values = tuple(candidate.metrics.metric_value(name) for name in metrics)
        if any(value is None for value in values):
            continue
        known_values = tuple(float(value) for value in values if value is not None)
        dominated = False
        for other in candidates:
            if other.candidate_id == candidate.candidate_id or other.metrics is None:
                continue
            other_values = tuple(other.metrics.metric_value(name) for name in metrics)
            if any(value is None for value in other_values):
                continue
            known_other_values = tuple(float(value) for value in other_values if value is not None)
            if all(
                left <= right for left, right in zip(known_other_values, known_values, strict=True)
            ) and any(
                left < right for left, right in zip(known_other_values, known_values, strict=True)
            ):
                dominated = True
                break
        if not dominated:
            result.add(candidate.candidate_id)
    return frozenset(result)


# Concise public name used by the v0.1 product vocabulary.
Manifest = PlanningManifest


__all__ = [
    "CANDIDATE_SCHEMA_VERSION",
    "CandidateDisposition",
    "CandidatePlan",
    "CompilerStrategy",
    "ERROR_MODEL_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "Manifest",
    "METRICS_SCHEMA_VERSION",
    "MetricConstraint",
    "OBJECTIVE_SCHEMA_VERSION",
    "Objective",
    "PLAN_SCHEMA_VERSION",
    "PROGRAM_SCHEMA_VERSION",
    "Plan",
    "PlanExplanation",
    "PlanMetrics",
    "PlanningError",
    "PlanningManifest",
    "Program",
    "QCoreNativeStrategy",
    "SCORER_VERSION",
    "StrategyError",
    "StrategyResult",
    "StrategyTimeoutError",
    "StrategyUnavailableError",
    "StrategyUnsupportedError",
    "plan",
]
