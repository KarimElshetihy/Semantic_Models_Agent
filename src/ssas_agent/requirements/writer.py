"""Writes the spec into the run's artifacts folder. Nothing is written to workspaces or to example folders."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from ssas_agent.audit import RunRecorder
from ssas_agent.requirements.fields import RequirementSpec
from ssas_agent.requirements.render import render_markdown

SPEC_FILE_NAME = "spec.md"


class RequirementEvent(StrEnum):
    SPEC_WRITTEN = "spec_written"


def write_spec(recorder: RunRecorder, spec: RequirementSpec) -> Path:
    path = recorder.write_text(SPEC_FILE_NAME, render_markdown(spec))
    recorder.append_event(
        RequirementEvent.SPEC_WRITTEN,
        {
            "missing_count": len(spec.missing_fields()),
            "dropped_count": len(spec.dropped_drafts),
            "draft_note_present": bool(spec.draft_note),
        },
    )
    return path
