"""Line-based unified diff of two serialized Model.bim files, for review artifacts."""

from __future__ import annotations

import difflib


def unified_text_diff(before_bytes: bytes, after_bytes: bytes, label: str) -> str:
    """Return a unified diff of the two files as text. Identical files give an empty string."""
    before_lines = before_bytes.decode("utf-8").splitlines()
    after_lines = after_bytes.decode("utf-8").splitlines()
    return "\n".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"{label} (before)",
            tofile=f"{label} (after)",
            lineterm="",
        )
    )
