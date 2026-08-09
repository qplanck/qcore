"""Stable errors raised by the Amazon Braket adapter."""

from qplanck.errors import QPlanckError


class BraketAdapterError(QPlanckError):
    """Base class for adapter validation and execution failures."""


class BraketCapabilityError(BraketAdapterError):
    """Raised when a captured Braket device cannot preserve requested semantics."""


class BraketSnapshotMismatchError(BraketAdapterError):
    """Raised when target or pulse capabilities changed before submission."""


class BraketSubmissionError(BraketAdapterError):
    """Raised when a Braket quantum task cannot be created or normalized."""
