"""QCore public Python API.

QCore is the product brand. ``qplanck`` is the importable Python package.
"""

from qplanck import gates, pulse, qir
from qplanck.circuit import Circuit
from qplanck.compiler import (
    CompilationTrace,
    CompiledCircuit,
    CompileOptions,
    DependencyGraph,
    ResourceMetrics,
)
from qplanck.compiler import (
    compile as compile_circuit,
)
from qplanck.errors import (
    CircuitError,
    InteropError,
    QASMError,
    QPlanckError,
    ResourceLimitError,
    UnsupportedOperationError,
)
from qplanck.interop import ConversionResult, InteropIssue, InteropIssueKind, LossReport
from qplanck.ir import CircuitIR, MeasurementSpec, Operation, Parameter
from qplanck.qir import (
    QIRCapabilities,
    QIRExportError,
    QIRManifest,
    QIRModule,
    QIRProfile,
    export_qir,
    export_qir_with_report,
)
from qplanck.results import ExecutionTrace, ProbabilityResult, RunResult, StatevectorResult
from qplanck.simulator import Simulator

__all__ = [
    "Circuit",
    "CircuitError",
    "CircuitIR",
    "CompilationTrace",
    "CompiledCircuit",
    "CompileOptions",
    "ConversionResult",
    "DependencyGraph",
    "ExecutionTrace",
    "InteropError",
    "InteropIssue",
    "InteropIssueKind",
    "LossReport",
    "MeasurementSpec",
    "Operation",
    "Parameter",
    "ProbabilityResult",
    "QASMError",
    "QIRCapabilities",
    "QIRExportError",
    "QIRManifest",
    "QIRModule",
    "QIRProfile",
    "QPlanckError",
    "ResourceLimitError",
    "ResourceMetrics",
    "RunResult",
    "Simulator",
    "StatevectorResult",
    "UnsupportedOperationError",
    "compile_circuit",
    "export_qir",
    "export_qir_with_report",
    "gates",
    "pulse",
    "qir",
]

__version__ = "0.2.0a1"
