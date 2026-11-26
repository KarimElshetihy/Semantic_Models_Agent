"""Approval states, actions and the only legal transitions between them (design section 8).

Cancel is allowed only before a change is applied. After APPLIED, the run must end
as VERIFIED or FAILED, so the recorded state always matches the file on disk.
"""

from __future__ import annotations

from enum import Enum

from ssas_agent.approval.errors import InvalidTransitionError


class State(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Action(str, Enum):
    CREATE = "create"
    SUBMIT = "submit"
    APPROVE = "approve"
    REQUEST_REVISION = "request_revision"
    REVISE = "revise"
    REJECT = "reject"
    EDIT = "edit"
    CANCEL = "cancel"
    APPLY = "apply"
    VERIFY_PASS = "verify_pass"
    VERIFY_FAIL = "verify_fail"


TERMINAL_STATES = frozenset({State.VERIFIED, State.FAILED, State.REJECTED, State.CANCELLED})
_CANCELLABLE_STATES = (State.DRAFT, State.PROPOSED, State.REVISION_REQUESTED, State.APPROVED)

LEGAL_TRANSITIONS: dict[tuple[State | None, Action], State] = {
    (None, Action.CREATE): State.DRAFT,
    (State.DRAFT, Action.SUBMIT): State.PROPOSED,
    (State.PROPOSED, Action.APPROVE): State.APPROVED,
    (State.PROPOSED, Action.REQUEST_REVISION): State.REVISION_REQUESTED,
    (State.PROPOSED, Action.REJECT): State.REJECTED,
    (State.REVISION_REQUESTED, Action.REVISE): State.DRAFT,
    (State.APPROVED, Action.EDIT): State.DRAFT,
    (State.APPROVED, Action.APPLY): State.APPLIED,
    (State.APPLIED, Action.VERIFY_PASS): State.VERIFIED,
    (State.APPLIED, Action.VERIFY_FAIL): State.FAILED,
    **{(state, Action.CANCEL): State.CANCELLED for state in _CANCELLABLE_STATES},
}


def next_state(current: State | None, action: Action) -> State:
    """Return the state reached by the action, or raise InvalidTransitionError."""
    key = (current, action)
    if key not in LEGAL_TRANSITIONS:
        source = current.value if current is not None else "no run"
        raise InvalidTransitionError(f"cannot '{action.value}' from {source}")
    return LEGAL_TRANSITIONS[key]
