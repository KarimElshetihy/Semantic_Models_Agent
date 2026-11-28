"""Command line for the human steps of the approval flow, and the exit-gate demonstration.

Staging is done by code (an edit function). Approval is a separate command that a person runs and confirms by typing
a word, so no run can be approved by accident or by the code that staged it.

    python -m ssas_agent approve --run-id RUN --actor NAME
    python -m ssas_agent apply   --run-id RUN --actor NAME
    python -m ssas_agent demo    --actor NAME
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from enum import IntEnum, StrEnum
from pathlib import Path

from ssas_agent.approval import ApprovalError, ApprovalWorkflow
from ssas_agent.audit.run_ids import InvalidRunIdError
from ssas_agent.delivery import apply_and_verify, open_workflow
from ssas_agent.delivery.prompts import ReadLine, WriteLine, describe_result, request_approval
from ssas_agent.demo import DemoRefusedError, run_exit_gate
from ssas_agent.newmodel import SpecError
from ssas_agent.policy import DEFAULT_APPLY_FOLDER, PathPolicy, PolicyConfigurationError, PolicyDeniedError

PARSER_DESCRIPTION = "Human steps of the approval flow, and the Phase 1 exit-gate demonstration."
REFUSAL_PREFIX = "Refused: "
REFUSAL_ERRORS = (
    ApprovalError,
    PolicyDeniedError,
    PolicyConfigurationError,
    InvalidRunIdError,
    DemoRefusedError,
    SpecError,
)


class Command(StrEnum):
    APPROVE = "approve"
    APPLY = "apply"
    DEMO = "demo"


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
        if arguments.command == Command.DEMO:
            return _demo(policy, arguments, read_line, write_line)
        workflow = open_workflow(policy)
        if arguments.command == Command.APPROVE:
            return _approve(workflow, policy, arguments, read_line, write_line)
        return _apply(workflow, policy, arguments, write_line)
    except REFUSAL_ERRORS as error:
        write_line(f"{REFUSAL_PREFIX}{error}")
        return ExitCode.REFUSED_OR_FAILED


def _approve(
    workflow: ApprovalWorkflow,
    policy: PathPolicy,
    arguments: argparse.Namespace,
    read_line: ReadLine,
    write_line: WriteLine,
) -> int:
    approved = request_approval(workflow, policy, arguments.run_id, arguments.actor, read_line, write_line)
    return ExitCode.OK if approved else ExitCode.REFUSED_OR_FAILED


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


def _demo(policy: PathPolicy, arguments: argparse.Namespace, read_line: ReadLine, write_line: WriteLine) -> int:
    result = run_exit_gate(
        policy,
        approver=arguments.actor,
        run_prefix=arguments.run_prefix,
        read_line=read_line,
        write_line=write_line,
    )
    write_line(f"Exit gate: {'PASSED' if result.passed else 'NOT PASSED'}")
    return ExitCode.OK if result.passed else ExitCode.REFUSED_OR_FAILED


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
    demo_parser = commands.add_parser(Command.DEMO.value, help="run the Phase 1 exit-gate demonstration")
    demo_parser.add_argument("--actor", required=True, type=_non_blank, help="your name; you approve the edit")
    demo_parser.add_argument("--run-prefix", type=_non_blank, default=None, help="prefix for the demo's run IDs")
    return parser
