"""Form rules for a new measure's name and expression.

Shared by candidate generation (step 7) and new model specs (step 8), so both refuse the same shapes.
The rules come from the example models: no production measure name has square brackets, and no
production expression starts with '='. Dots and '#' are allowed because production names use them
(for example '01.RABT_ASLY' and '#.PAYROLL_COUNT').
"""

from __future__ import annotations

FORBIDDEN_NAME_CHARACTERS = ("[", "]")


def measure_form_reasons(measure_name: str, expression: str) -> list[str]:
    """Return the reasons a measure name or expression is refused. An empty list means the form is accepted."""
    reasons: list[str] = []
    if any(character in measure_name for character in FORBIDDEN_NAME_CHARACTERS):
        reasons.append("measure name must not contain '[' or ']'")
    if expression.lstrip().startswith("="):
        reasons.append("expression must not start with '=' (write the DAX formula only)")
    return reasons
