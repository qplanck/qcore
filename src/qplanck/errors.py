"""QPlanck exception hierarchy."""


class QPlanckError(Exception):
    """Base class for all QPlanck errors."""


class CircuitError(QPlanckError):
    """Raised when a circuit is invalid."""


class UnsupportedOperationError(CircuitError):
    """Raised when an operation is outside the supported static circuit subset."""


class QASMError(QPlanckError):
    """Raised when OpenQASM 3 import or export fails."""


class InteropError(QPlanckError):
    """Raised when a framework adapter cannot convert an object."""


class ResourceLimitError(QPlanckError):
    """Raised before an operation would exceed an explicit local resource budget."""
