"""Renders a requirements spec as Markdown: the table of fields with sources, the missing definitions,
and any drafts the code dropped."""

from __future__ import annotations

from ssas_agent.requirements.fields import FIELD_LABELS, RequirementField, RequirementSpec

NOT_STATED = "_not stated_"
NONE_LISTED = "- none"
REVIEW_NOTE = "Values drafted by the model must be reviewed before use."


def render_markdown(spec: RequirementSpec) -> str:
    lines = [
        "# Requirements specification (draft)",
        "",
        "## Request",
        "",
        spec.request_text,
        "",
        "## Fields",
        "",
        "| Field | Value | Source |",
        "|---|---|---|",
        *_field_rows(spec),
        "",
        "## Missing definitions",
        "",
        *_bullets([FIELD_LABELS[field] for field in spec.missing_fields()]),
    ]
    if spec.dropped_drafts:
        lines += _section("Dropped drafts (contain words not in the request)", _labels(spec.dropped_drafts))
    if spec.draft_note:
        lines += _section("Draft note", [spec.draft_note])
    lines += ["", REVIEW_NOTE, ""]
    return "\n".join(lines)


def _field_rows(spec: RequirementSpec) -> list[str]:
    rows = []
    for field in RequirementField:
        value = spec.values[field]
        text = _table_cell(value.text) if value.text else NOT_STATED
        rows.append(f"| {FIELD_LABELS[field]} | {text} | {value.source} |")
    return rows


def _table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _labels(fields: tuple[RequirementField, ...]) -> list[str]:
    return [FIELD_LABELS[field] for field in fields]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or [NONE_LISTED]


def _section(title: str, items: list[str]) -> list[str]:
    return ["", f"## {title}", "", *_bullets(items)]
