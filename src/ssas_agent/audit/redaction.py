"""Redact credential values from text before it is written to any artifact or log.

Two forms are handled: JSON properties such as "Username": "value", and
connection-string style pairs such as Password=value;.
"""

from __future__ import annotations

import re

REDACTED = "<redacted>"

_JSON_SECRET_PATTERN = re.compile(
    r'("(?:Username|Password|pwd)"\s*:\s*)"[^"]*"',
    re.IGNORECASE,
)
_CONNECTION_STRING_SECRET_PATTERN = re.compile(
    r"\b(Password|Pwd|User ID|UID)(\s*=\s*)[^;\"\s]+",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    redacted = _JSON_SECRET_PATTERN.sub(rf'\1"{REDACTED}"', text)
    return _CONNECTION_STRING_SECRET_PATTERN.sub(rf"\1\2{REDACTED}", redacted)
