"""Path policy: deny by default, protect the example and fixture folders from writes."""

from ssas_agent.policy.path_policy import (
    APPLY_TARGET_FILE,
    DEFAULT_APPLY_FOLDER,
    PROTECTED_FOLDERS,
    READABLE_FILES,
    READABLE_FOLDERS,
    WRITABLE_FOLDERS,
    Operation,
    PathPolicy,
    PolicyConfigurationError,
    PolicyDecision,
    PolicyDeniedError,
)

__all__ = [
    "APPLY_TARGET_FILE",
    "DEFAULT_APPLY_FOLDER",
    "PROTECTED_FOLDERS",
    "READABLE_FILES",
    "READABLE_FOLDERS",
    "WRITABLE_FOLDERS",
    "Operation",
    "PathPolicy",
    "PolicyConfigurationError",
    "PolicyDecision",
    "PolicyDeniedError",
]
