"""QCore public Python API.

QCore is the product brand. ``qplanck`` is the importable Python package.
"""

from qplanck import gates
from qplanck.circuit import Circuit
from qplanck.errors import (
    CircuitError,
    InteropError,
    QASMError,
    QPlanckError,
    UnsupportedOperationError,
)
from qplanck.ir import CircuitIR, MeasurementSpec, Operation, Parameter
from qplanck.results import ExecutionTrace, ProbabilityResult, RunResult, StatevectorResult
from qplanck.simulator import Simulator

__all__ = [
    "Circuit",
    "CircuitError",
    "CircuitIR",
    "ExecutionTrace",
    "InteropError",
    "MeasurementSpec",
    "Operation",
    "Parameter",
    "ProbabilityResult",
    "QASMError",
    "QPlanckError",
    "RunResult",
    "Simulator",
    "StatevectorResult",
    "UnsupportedOperationError",
    "gates",
]

__version__ = "0.1.0a1"
