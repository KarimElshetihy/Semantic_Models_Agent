"""Approval state machine: persisted transitions, bound approvals and enforced apply."""

from ssas_agent.approval.errors import (
    ApprovalError,
    ApprovalRequiredError,
    InvalidTransitionError,
    StaleApprovalError,
)
from ssas_agent.approval.proposal import ProposalBinding
from ssas_agent.approval.states import LEGAL_TRANSITIONS, TERMINAL_STATES, Action, State, next_state
from ssas_agent.approval.store import WorkflowStore
from ssas_agent.approval.workflow import ApplyOutcome, ApprovalWorkflow, RunStatus

__all__ = [
    "LEGAL_TRANSITIONS",
    "TERMINAL_STATES",
    "Action",
    "ApplyOutcome",
    "ApprovalError",
    "ApprovalRequiredError",
    "ApprovalWorkflow",
    "InvalidTransitionError",
    "ProposalBinding",
    "RunStatus",
    "StaleApprovalError",
    "State",
    "WorkflowStore",
    "next_state",
]
