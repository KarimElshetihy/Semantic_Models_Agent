"""Path policy: deny by default, protect the example and fixture folders from writes."""

from ssas_agent.policy.path_policy import (
    PROTECTED_FOLDERS,
    READABLE_FOLDERS,
    WRITABLE_FOLDERS,
    Operation,
    PathPolicy,
    PolicyDecision,
    PolicyDeniedError,
)

__all__ = [
    "PROTECTED_FOLDERS",
    "READABLE_FOLDERS",
    "WRITABLE_FOLDERS",
    "Operation",
    "PathPolicy",
    "PolicyDecision",
    "PolicyDeniedError",
]
