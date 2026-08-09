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


class TargetError(CircuitError):
    """Raised when a compilation or execution target is malformed or incompatible."""


class RoutingError(TargetError):
    """Raised when a circuit cannot be placed or routed onto a target."""


class BackendError(QPlanckError):
    """Raised when a backend rejects or cannot execute a program."""


class JobError(BackendError):
    """Base class for stable job lifecycle failures."""


class JobCancelledError(JobError):
    """Raised when a result is requested from a cancelled job."""


class JobFailedError(JobError):
    """Raised when a result is requested from a failed job."""


class JobTimeoutError(TimeoutError, JobError):
    """Raised when waiting for a job exceeds the caller's timeout."""


class NativeCompilerError(QPlanckError):
    """Raised when the required native compiler/QIR kernel is unavailable or fails."""
