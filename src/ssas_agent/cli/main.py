"""Command line for the two human steps of the approval flow: approve a staged change, then apply and verify it.

Staging is done by code (an edit function). Approval is a separate command that a person runs and confirms by typing
a word, so no run can be approved by accident or by the code that staged it.

    python -m ssas_agent approve --run-id RUN --actor NAME
    python -m ssas_agent apply   --run-id RUN --actor NAME
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from enum import IntEnum, StrEnum
from pathlib import Path

from ssas_agent.approval import ApprovalError, ApprovalWorkflow, ProposalBinding, State, WorkflowStore
from ssas_agent.audit.run_ids import InvalidRunIdError
from ssas_agent.delivery import DeliveryResult, apply_and_verify, approve_change
from ssas_agent.policy import DEFAULT_APPLY_FOLDER, PathPolicy, PolicyConfigurationError, PolicyDeniedError

WORKFLOW_DATABASE = Path("artifacts") / "state" / "workflow.sqlite3"
APPROVAL_WORD = "approve"
SHORT_HASH_LENGTH = 12
PARSER_DESCRIPTION = "Human steps of the approval flow: approve a staged change, then apply and verify it."

ReadLine = Callable[[str], str]
WriteLine = Callable[[str], None]


class Command(StrEnum):
    APPROVE = "approve"
    APPLY = "apply"


class ExitCode(IntEnum):
    OK = 0
    REFUSED_OR_FAILED = 1


def main(
    argv: Sequence[str] | None = None,
    *,
    read_line: ReadLine = input,
    write_line: WriteLine = print,
) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        policy = PathPolicy(project_root=arguments.project_root, apply_folder=arguments.apply_folder)
        workflow = ApprovalWorkflow(policy, WorkflowStore(policy, WORKFLOW_DATABASE))
        if arguments.command == Command.APPROVE:
            return _approve(workflow, policy, arguments, read_line, write_line)
        return _apply(workflow, policy, arguments, write_line)
    except (ApprovalError, PolicyDeniedError, PolicyConfigurationError, InvalidRunIdError) as error:
        write_line(f"Refused: {error}")
        return ExitCode.REFUSED_OR_FAILED


def _approve(
    workflow: ApprovalWorkflow,
    policy: PathPolicy,
    arguments: argparse.Namespace,
    read_line: ReadLine,
    write_line: WriteLine,
) -> int:
    state = workflow.resume(arguments.run_id).state
    if state is not State.PROPOSED:
        raise ApprovalError(f"run {arguments.run_id} is {state.value}, not waiting for approval")
    for line in describe_proposal(workflow.submitted_proposal(arguments.run_id)):
        write_line(line)
    if read_line(f"Type '{APPROVAL_WORD}' to approve this change: ").strip() != APPROVAL_WORD:
        write_line("Not approved. Nothing was changed.")
        return ExitCode.REFUSED_OR_FAILED
    approve_change(workflow, policy, arguments.run_id, arguments.actor)
    write_line(f"Approved by {arguments.actor}. Nothing has been written yet; run the apply command next.")
    return ExitCode.OK


def _apply(
    workflow: ApprovalWorkflow,
    policy: PathPolicy,
    arguments: argparse.Namespace,
    write_line: WriteLine,
) -> int:
    result = apply_and_verify(workflow, policy, arguments.run_id, arguments.actor)
    for line in describe_result(result):
        write_line(line)
    return ExitCode.OK if result.verified else ExitCode.REFUSED_OR_FAILED


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
        f"Review:     artifacts/{proposal.run_id}/diff.txt and run.json (read these before approving)",
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


def _non_blank(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return value.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ssas_agent", description=PARSER_DESCRIPTION)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="project root (default: current folder)")
    parser.add_argument(
        "--apply-folder",
        type=Path,
        default=Path(DEFAULT_APPLY_FOLDER),
        help=f"destination folder for approved changes (default: {DEFAULT_APPLY_FOLDER})",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command, summary in (
        (Command.APPROVE, "review and approve a staged change"),
        (Command.APPLY, "write an approved change to its destination and verify it"),
    ):
        command_parser = commands.add_parser(command.value, help=summary)
        command_parser.add_argument("--run-id", required=True)
        command_parser.add_argument("--actor", required=True, type=_non_blank, help="your name, recorded in the log")
    return parser
