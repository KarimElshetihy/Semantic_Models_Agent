"""Errors raised when an approval operation is refused. Each refusal is also recorded as an attempt."""


class ApprovalError(RuntimeError):
    """Base class for refused approval operations."""


class InvalidTransitionError(ApprovalError):
    """The action is not allowed from the run's current state."""


class ApprovalRequiredError(ApprovalError):
    """No valid approval exists for the requested operation."""


class StaleApprovalError(ApprovalError):
    """The approved files no longer match the hashes that were approved."""
