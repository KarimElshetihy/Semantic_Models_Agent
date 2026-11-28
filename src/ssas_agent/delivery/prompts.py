"""The human approval prompt and the plain-text summaries it shows. Shared by the command line and the exit-gate demo.

A person approves by typing the approval word. Nothing else approves a run.
"""

from __future__ import annotations

from collections.abc import Callable

from ssas_agent.approval import ApprovalError, ApprovalWorkflow, ProposalBinding, State
from ssas_agent.delivery.apply import DeliveryResult, approve_change
from ssas_agent.policy import PathPolicy

APPROVAL_WORD = "approve"
SHORT_HASH_LENGTH = 12
REVIEW_FILES_HINT = "diff.txt and run.json (read these before approving)"

ReadLine = Callable[[str], str]
WriteLine = Callable[[str], None]


def request_approval(
    workflow: ApprovalWorkflow,
    policy: PathPolicy,
    run_id: str,
    actor: str,
    read_line: ReadLine,
    write_line: WriteLine,
) -> bool:
    """Show the submitted proposal and approve it only if the person types the approval word.

    Returns False when the answer is not the approval word; nothing is recorded in that case.
    Raises ApprovalError when the run is not waiting for approval.
    """
    state = workflow.resume(run_id).state
    if state is not State.PROPOSED:
        raise ApprovalError(f"run {run_id} is {state.value}, not waiting for approval")
    for line in describe_proposal(workflow.submitted_proposal(run_id)):
        write_line(line)
    if read_line(f"Type '{APPROVAL_WORD}' to approve this change: ").strip() != APPROVAL_WORD:
        write_line("Not approved. Nothing was changed.")
        return False
    approve_change(workflow, policy, run_id, actor)
    write_line(f"Approved by {actor}. Nothing has been written yet; the apply step is next.")
    return True


def describe_proposal(proposal: ProposalBinding) -> list[str]:
    what_happens = (
        "creates a new file"
        if proposal.base_sha256 is None
        else f"replaces the model that has hash {_short(proposal.base_sha256)}"
    )
    return [
        f"Run:        {proposal.run_id}",
        f"Target:     {proposal.target_path}",
        f"Applying:   {what_happens}",
        f"Candidate:  hash {_short(proposal.candidate_sha256)}",
        f"Review:     artifacts/{proposal.run_id}/{REVIEW_FILES_HINT}",
    ]


def describe_result(result: DeliveryResult) -> list[str]:
    checks = result.verification
    return [
        f"Run:        {result.run_id}",
        f"Target:     {result.target_path}",
        f"Outcome:    {result.outcome.value}",
        f"State:      {result.state.value}",
        f"Hash match: {checks['hash_matches']}; reads back identically: {checks['reads_back_identically']}",
    ]


def _short(sha256: str) -> str:
    return sha256[:SHORT_HASH_LENGTH]
