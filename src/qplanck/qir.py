"""Conservative QIR 2.x text export for QCore's static circuit subset.

The exporter targets the QIR Base Profile with opaque pointers and static
qubit/result resources.  QIR profiles constrain the classical program shape;
the quantum instruction set (QIS) is a separate target capability, represented
by :class:`QIRCapabilities` below.

This module deliberately emits human-readable LLVM IR rather than bitcode.  A
consumer should assemble or validate the text with an LLVM/QIR toolchain before
submission to hardware.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from qplanck.errors import InteropError
from qplanck.interop import ConversionResult, InteropIssue, InteropIssueKind, LossReport
from qplanck.ir import CircuitIR, Parameter

if TYPE_CHECKING:
    from qplanck.circuit import Circuit


__all__ = [
    "OUTPUT_LABELING_SCHEMA",
    "QIR_MAJOR_VERSION",
    "QIR_MINOR_VERSION",
    "SUPPORTED_QIS",
    "QIRCapabilities",
    "QIRExportError",
    "QIRManifest",
    "QIRMeasurementMap",
    "QIRModule",
    "QIRProfile",
    "QIRSourceMapEntry",
    "dumps",
    "export_qir",
    "validate_capabilities",
]


QIR_MAJOR_VERSION = 2
QIR_MINOR_VERSION = 0
OUTPUT_LABELING_SCHEMA = "qplanck.cbit.v1"


class QIRExportError(InteropError):
    """Raised when a QCore circuit cannot be represented by the selected QIR target."""


class QIRProfile(StrEnum):
    """QIR classical capability profiles supported by this exporter."""

    BASE = "base_profile"
    BASE_PROFILE = "base_profile"


@dataclass(frozen=True)
class _GateSpec:
    qir_name: str
    qubits: int
    params: int


_GATE_SPECS: dict[str, _GateSpec] = {
    "h": _GateSpec("h", 1, 0),
    "x": _GateSpec("x", 1, 0),
    "y": _GateSpec("y", 1, 0),
    "z": _GateSpec("z", 1, 0),
    "s": _GateSpec("s", 1, 0),
    "t": _GateSpec("t", 1, 0),
    "rx": _GateSpec("rx", 1, 1),
    "ry": _GateSpec("ry", 1, 1),
    "rz": _GateSpec("rz", 1, 1),
    "cx": _GateSpec("cnot", 2, 0),
    "cz": _GateSpec("cz", 2, 0),
}

SUPPORTED_QIS = frozenset({spec.qir_name for spec in _GATE_SPECS.values()} | {"mz"})


@dataclass(frozen=True)
class QIRCapabilities:
    """A target's profile, QIS, and optional static resource limits.

    ``supported_qis`` contains canonical QIR function stems such as ``h``,
    ``cnot``, and ``mz`` rather than QCore operation names.  Extra target QIS
    names are allowed; export only verifies that every required stem is present.
    """

    profile: QIRProfile = QIRProfile.BASE
    supported_qis: frozenset[str] = SUPPORTED_QIS
    max_qubits: int | None = None
    max_results: int | None = None

    def __post_init__(self) -> None:
        try:
            profile = QIRProfile(self.profile)
        except ValueError as exc:
            raise QIRExportError(f"Unsupported QIR profile: {self.profile!r}.") from exc

        qis = frozenset(str(name).strip().lower() for name in self.supported_qis)
        if "" in qis:
            raise QIRExportError("QIR capability names must be non-empty.")
        for field_name, limit in (
            ("max_qubits", self.max_qubits),
            ("max_results", self.max_results),
        ):
            if limit is not None and (
                isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
            ):
                raise QIRExportError(f"{field_name} must be a non-negative integer or None.")

        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "supported_qis", qis)


@dataclass(frozen=True)
class QIRSourceMapEntry:
    """Provenance for one QIS call emitted from a QCore IR item."""

    qis_call_index: int
    block: Literal["body", "measurements"]
    source_kind: Literal["operation", "measurement"]
    source_index: int
    source_operation: str
    qir_function: str
    qubits: tuple[int, ...]
    result_id: int | None = None
    classical_bit: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qis_call_index": self.qis_call_index,
            "block": self.block,
            "source_kind": self.source_kind,
            "source_index": self.source_index,
            "source_operation": self.source_operation,
            "qir_function": self.qir_function,
            "qubits": list(self.qubits),
            "result_id": self.result_id,
            "classical_bit": self.classical_bit,
        }


@dataclass(frozen=True)
class QIRMeasurementMap:
    """Mapping from a QCore classical bit to a dense static QIR result resource."""

    source_index: int
    qubit: int
    classical_bit: int
    result_id: int
    output_index: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_index": self.source_index,
            "qubit": self.qubit,
            "classical_bit": self.classical_bit,
            "result_id": self.result_id,
            "output_index": self.output_index,
            "label": self.label,
        }


@dataclass(frozen=True)
class QIRManifest:
    """Machine-readable account of the QIR lowering boundary."""

    profile: QIRProfile
    entry_point: str
    required_num_qubits: int
    required_num_results: int
    required_qis: tuple[str, ...]
    measurement_map: tuple[QIRMeasurementMap, ...]
    source_map: tuple[QIRSourceMapEntry, ...]
    qir_major_version: int = QIR_MAJOR_VERSION
    qir_minor_version: int = QIR_MINOR_VERSION
    output_labeling_schema: str = OUTPUT_LABELING_SCHEMA
    dynamic_qubit_management: bool = False
    dynamic_result_management: bool = False

    @property
    def qir_version(self) -> str:
        return f"{self.qir_major_version}.{self.qir_minor_version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "qir_version": self.qir_version,
            "profile": self.profile.value,
            "entry_point": self.entry_point,
            "required_num_qubits": self.required_num_qubits,
            "required_num_results": self.required_num_results,
            "required_qis": list(self.required_qis),
            "output_labeling_schema": self.output_labeling_schema,
            "dynamic_qubit_management": self.dynamic_qubit_management,
            "dynamic_result_management": self.dynamic_result_management,
            "measurement_map": [item.to_dict() for item in self.measurement_map],
            "source_map": [item.to_dict() for item in self.source_map],
        }


@dataclass(frozen=True)
class QIRModule:
    """Human-readable LLVM/QIR plus its deterministic export manifest."""

    text: str
    manifest: QIRManifest

    @property
    def metadata(self) -> dict[str, Any]:
        """Return a fresh dictionary form of :attr:`manifest`."""

        return self.manifest.to_dict()

    @property
    def profile(self) -> QIRProfile:
        return self.manifest.profile

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class _Lowering:
    ir: CircuitIR
    profile: QIRProfile
    measurements: tuple[QIRMeasurementMap, ...]
    required_qis: tuple[str, ...]


def validate_capabilities(
    source: Circuit | CircuitIR,
    capabilities: QIRCapabilities | None = None,
    *,
    profile: QIRProfile | str = QIRProfile.BASE,
) -> None:
    """Validate ``source`` against the supported Base Profile and target QIS."""

    ir = _as_ir(source)
    selected_profile = _coerce_profile(profile)
    target = capabilities if capabilities is not None else QIRCapabilities(profile=selected_profile)
    _prepare_lowering(ir, selected_profile, target)


def export_qir(
    source: Circuit | CircuitIR,
    *,
    profile: QIRProfile | str = QIRProfile.BASE,
    capabilities: QIRCapabilities | None = None,
    entry_point: str = "qplanck_main",
) -> QIRModule:
    """Export a circuit to deterministic Base Profile LLVM/QIR text.

    Measurements are ordered by classical-bit index.  They are assigned dense
    QIR result resources, and the exact mapping is retained in the returned
    manifest.  Unsupported or ambiguous constructs raise :class:`QIRExportError`.
    """

    ir = _as_ir(source)
    selected_profile = _coerce_profile(profile)
    target = capabilities if capabilities is not None else QIRCapabilities(profile=selected_profile)
    lowering = _prepare_lowering(ir, selected_profile, target)
    _validate_entry_point(entry_point)

    text, source_map = _emit_module(lowering, entry_point)
    manifest = QIRManifest(
        profile=selected_profile,
        entry_point=entry_point,
        required_num_qubits=ir.qubit_count,
        required_num_results=len(lowering.measurements),
        required_qis=lowering.required_qis,
        measurement_map=lowering.measurements,
        source_map=source_map,
    )
    return QIRModule(text=text, manifest=manifest)


def export_qir_with_report(
    source: Circuit | CircuitIR,
    *,
    profile: QIRProfile | str = QIRProfile.BASE,
    capabilities: QIRCapabilities | None = None,
    entry_point: str = "qplanck_main",
) -> ConversionResult[QIRModule]:
    """Export QIR and report QCore information not represented in the module."""

    ir = _as_ir(source)
    issues: list[InteropIssue] = []
    if ir.metadata:
        issues.append(
            InteropIssue(
                code="QCORE-INTEROP-CIRCUIT-METADATA-DROPPED",
                kind=InteropIssueKind.LOSS,
                message="QCore circuit metadata is not encoded in the QIR module.",
                path="metadata",
            )
        )
    for index, operation in enumerate(ir.operations):
        if operation.metadata:
            issues.append(
                InteropIssue(
                    code="QCORE-INTEROP-OPERATION-METADATA-DROPPED",
                    kind=InteropIssueKind.LOSS,
                    message="QCore operation metadata is not encoded in the QIR module.",
                    path=f"operations[{index}].metadata",
                )
            )
    for index, measurement in enumerate(ir.measurements):
        if measurement.metadata:
            issues.append(
                InteropIssue(
                    code="QCORE-INTEROP-MEASUREMENT-METADATA-DROPPED",
                    kind=InteropIssueKind.LOSS,
                    message="QCore measurement metadata is not encoded in the QIR module.",
                    path=f"measurements[{index}].metadata",
                )
            )

    module = export_qir(
        ir,
        profile=profile,
        capabilities=capabilities,
        entry_point=entry_point,
    )
    report = LossReport(
        source_format=ir.schema_version,
        target_format=f"qir-{module.manifest.qir_version}-{module.profile.value}",
        preserved=(
            "operation order",
            "source operation mapping",
            "supported gate semantics",
            "numeric parameters",
            "terminal measurement mapping",
            "qubit count",
        ),
        issues=tuple(issues),
    )
    return ConversionResult(value=module, report=report)


def dumps(
    source: Circuit | CircuitIR,
    *,
    profile: QIRProfile | str = QIRProfile.BASE,
    capabilities: QIRCapabilities | None = None,
    entry_point: str = "qplanck_main",
) -> str:
    """Return deterministic human-readable LLVM/QIR text."""

    return export_qir(
        source,
        profile=profile,
        capabilities=capabilities,
        entry_point=entry_point,
    ).text


def _as_ir(source: Circuit | CircuitIR) -> CircuitIR:
    if isinstance(source, CircuitIR):
        return source

    from qplanck.circuit import Circuit

    if isinstance(source, Circuit):
        return source.ir
    raise QIRExportError("QIR export expects a qplanck.Circuit or qplanck.ir.CircuitIR.")


def _coerce_profile(profile: QIRProfile | str) -> QIRProfile:
    try:
        return QIRProfile(profile)
    except ValueError as exc:
        raise QIRExportError(f"Unsupported QIR profile: {profile!r}.") from exc


def _prepare_lowering(
    ir: CircuitIR,
    profile: QIRProfile,
    capabilities: QIRCapabilities,
) -> _Lowering:
    if profile is not QIRProfile.BASE:
        raise QIRExportError(f"QIR profile {profile.value!r} is not implemented.")
    if capabilities.profile is not profile:
        raise QIRExportError(
            f"Selected profile {profile.value!r} does not match target profile "
            f"{capabilities.profile.value!r}."
        )
    if ir.schema_version != CircuitIR.SUPPORTED_SCHEMA:
        raise QIRExportError(f"Unsupported QCore IR schema version: {ir.schema_version}.")
    if ir.qubit_count > (2**63 - 1):
        raise QIRExportError("QIR required_num_qubits exceeds the supported i64 range.")

    used_qis: set[str] = set()
    for index, operation in enumerate(ir.operations):
        spec = _GATE_SPECS.get(operation.name)
        if spec is None:
            raise QIRExportError(
                f"Operation {index} uses unsupported gate {operation.name!r} for QIR export."
            )
        if len(operation.qubits) != spec.qubits:
            raise QIRExportError(
                f"Operation {index} ({operation.name!r}) expects {spec.qubits} qubit(s), "
                f"got {len(operation.qubits)}."
            )
        if len(operation.params) != spec.params:
            raise QIRExportError(
                f"Operation {index} ({operation.name!r}) expects {spec.params} parameter(s), "
                f"got {len(operation.params)}."
            )
        if operation.name in {"cx", "cz"} and operation.qubits[0] == operation.qubits[1]:
            raise QIRExportError(
                f"Operation {index} ({operation.name!r}) requires distinct qubits."
            )
        for parameter in operation.params:
            if isinstance(parameter, Parameter):
                raise QIRExportError(
                    f"Operation {index} ({operation.name!r}) has a symbolic parameter; "
                    "Base Profile export requires numeric constants."
                )
            if not math.isfinite(parameter):
                raise QIRExportError(
                    f"Operation {index} ({operation.name!r}) has a non-finite parameter."
                )
        used_qis.add(spec.qir_name)

    seen_qubits: set[int] = set()
    seen_cbits: set[int] = set()
    indexed_measurements = list(enumerate(ir.measurements))
    for source_index, measurement in indexed_measurements:
        if measurement.qubit in seen_qubits:
            raise QIRExportError(
                f"Measurement {source_index} reuses qubit {measurement.qubit}; "
                "the Base Profile forbids using a qubit after an irreversible call."
            )
        if measurement.cbit in seen_cbits:
            raise QIRExportError(
                f"Measurement {source_index} reuses classical bit {measurement.cbit}."
            )
        seen_qubits.add(measurement.qubit)
        seen_cbits.add(measurement.cbit)

    ordered = sorted(indexed_measurements, key=lambda item: item[1].cbit)
    measurements = tuple(
        QIRMeasurementMap(
            source_index=source_index,
            qubit=measurement.qubit,
            classical_bit=measurement.cbit,
            result_id=result_id,
            output_index=result_id,
            label=f"qplanck.cbit.{measurement.cbit}",
        )
        for result_id, (source_index, measurement) in enumerate(ordered)
    )
    if measurements:
        used_qis.add("mz")
    if len(measurements) > (2**63 - 1):
        raise QIRExportError("QIR required_num_results exceeds the supported i64 range.")

    required_qis = tuple(sorted(used_qis))
    missing_qis = sorted(set(required_qis) - capabilities.supported_qis)
    if missing_qis:
        raise QIRExportError(
            "Target QIS is missing required instruction(s): " + ", ".join(missing_qis) + "."
        )
    if capabilities.max_qubits is not None and ir.qubit_count > capabilities.max_qubits:
        raise QIRExportError(
            f"Circuit requires {ir.qubit_count} qubits, but the target limit is "
            f"{capabilities.max_qubits}."
        )
    if capabilities.max_results is not None and len(measurements) > capabilities.max_results:
        raise QIRExportError(
            f"Circuit requires {len(measurements)} results, but the target limit is "
            f"{capabilities.max_results}."
        )

    return _Lowering(
        ir=ir,
        profile=profile,
        measurements=measurements,
        required_qis=required_qis,
    )


def _validate_entry_point(entry_point: str) -> None:
    if not isinstance(entry_point, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_.$-]*", entry_point
    ):
        raise QIRExportError(
            f"Invalid LLVM entry-point identifier {entry_point!r}; use an unquoted identifier."
        )


def _emit_module(
    lowering: _Lowering, entry_point: str
) -> tuple[str, tuple[QIRSourceMapEntry, ...]]:
    ir = lowering.ir
    labels = (
        ["qplanck.results", *(item.label for item in lowering.measurements)]
        if lowering.measurements
        else []
    )
    lines = ["; ModuleID = 'qplanck'", 'source_filename = "qplanck"', ""]
    for index, label in enumerate(labels):
        size = len(label.encode("ascii")) + 1
        lines.append(f'@qplanck_label_{index} = internal constant [{size} x i8] c"{label}\\00"')
    if labels:
        lines.append("")

    lines.extend(
        [
            f"define i64 @{entry_point}() #0 {{",
            "entry:",
            "  call void @__quantum__rt__initialize(ptr null)",
            "  br label %body",
            "",
            "body:",
        ]
    )

    source_map: list[QIRSourceMapEntry] = []
    for source_index, operation in enumerate(ir.operations):
        spec = _GATE_SPECS[operation.name]
        qir_function = _qis_symbol(spec.qir_name)
        args = [*(_double_literal(_numeric_parameter(value)) for value in operation.params)]
        args.extend(_pointer(qubit) for qubit in operation.qubits)
        typed_args = _typed_gate_args(operation.name, args)
        lines.append(f"  call void @{qir_function}({', '.join(typed_args)})")
        source_map.append(
            QIRSourceMapEntry(
                qis_call_index=len(source_map),
                block="body",
                source_kind="operation",
                source_index=source_index,
                source_operation=operation.name,
                qir_function=qir_function,
                qubits=operation.qubits,
            )
        )

    lines.extend(["  br label %measurements", "", "measurements:"])
    for measurement in lowering.measurements:
        qir_function = _qis_symbol("mz")
        lines.append(
            f"  call void @{qir_function}(ptr {_pointer(measurement.qubit)}, "
            f"ptr writeonly {_pointer(measurement.result_id)})"
        )
        source_map.append(
            QIRSourceMapEntry(
                qis_call_index=len(source_map),
                block="measurements",
                source_kind="measurement",
                source_index=measurement.source_index,
                source_operation="measure",
                qir_function=qir_function,
                qubits=(measurement.qubit,),
                result_id=measurement.result_id,
                classical_bit=measurement.classical_bit,
            )
        )

    lines.extend(["  br label %output", "", "output:"])
    if lowering.measurements:
        lines.append(
            "  call void @__quantum__rt__tuple_record_output"
            f"(i64 {len(lowering.measurements)}, ptr @qplanck_label_0)"
        )
        for index, measurement in enumerate(lowering.measurements, start=1):
            lines.append(
                "  call void @__quantum__rt__result_record_output"
                f"(ptr {_pointer(measurement.result_id)}, ptr @qplanck_label_{index})"
            )
    lines.extend(["  ret i64 0", "}", ""])

    declaration_lines = [_qis_declaration(name) for name in lowering.required_qis]
    lines.extend(declaration_lines)
    if declaration_lines:
        lines.append("")
    lines.append("declare void @__quantum__rt__initialize(ptr)")
    if lowering.measurements:
        lines.extend(
            [
                "declare void @__quantum__rt__tuple_record_output(i64, ptr)",
                "declare void @__quantum__rt__result_record_output(ptr, ptr)",
            ]
        )
    lines.append("")

    attributes = (
        f'attributes #0 = {{ "entry_point" "qir_profiles"="{lowering.profile.value}" '
        f'"output_labeling_schema"="{OUTPUT_LABELING_SCHEMA}" '
        f'"required_num_qubits"="{ir.qubit_count}" '
        f'"required_num_results"="{len(lowering.measurements)}" }}'
    )
    lines.append(attributes)
    if lowering.measurements:
        lines.append('attributes #1 = { "irreversible" }')
    lines.extend(
        [
            "",
            "!llvm.module.flags = !{!0, !1, !2, !3}",
            "",
            f'!0 = !{{i32 1, !"qir_major_version", i32 {QIR_MAJOR_VERSION}}}',
            f'!1 = !{{i32 7, !"qir_minor_version", i32 {QIR_MINOR_VERSION}}}',
            '!2 = !{i32 1, !"dynamic_qubit_management", i1 false}',
            '!3 = !{i32 1, !"dynamic_result_management", i1 false}',
            "",
        ]
    )
    return "\n".join(lines), tuple(source_map)


def _typed_gate_args(operation_name: str, args: list[str]) -> list[str]:
    if operation_name in {"rx", "ry", "rz"}:
        return [f"double {args[0]}", f"ptr {args[1]}"]
    return [f"ptr {arg}" for arg in args]


def _qis_symbol(name: str) -> str:
    return f"__quantum__qis__{name}__body"


def _qis_declaration(name: str) -> str:
    symbol = _qis_symbol(name)
    if name in {"rx", "ry", "rz"}:
        return f"declare void @{symbol}(double, ptr)"
    if name in {"cnot", "cz"}:
        return f"declare void @{symbol}(ptr, ptr)"
    if name == "mz":
        return f"declare void @{symbol}(ptr, ptr writeonly) #1"
    return f"declare void @{symbol}(ptr)"


def _pointer(index: int) -> str:
    if index == 0:
        return "null"
    return f"inttoptr (i64 {index} to ptr)"


def _double_literal(value: float) -> str:
    """Return an exact LLVM hexadecimal ``double`` constant."""

    return "0x" + struct.pack(">d", value).hex().upper()


def _numeric_parameter(value: float | Parameter) -> float:
    if isinstance(value, Parameter):
        raise QIRExportError("Internal QIR lowering error: symbolic parameter was not rejected.")
    return value
