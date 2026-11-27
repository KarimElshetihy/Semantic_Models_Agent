"""Reader for the project's .env file. Read-only, and only through the path policy.

Format, one setting per line:
- KEY=VALUE. Spaces around the key and the value are ignored.
- Blank lines and lines starting with # are ignored.
- An optional "export " prefix is allowed.
- A value may be in single or double quotes. Quoted text is kept as it is (no escapes).
- An unquoted value may end with a comment: whitespace followed by #.
- No variable expansion. A key may appear only once.

Errors give the line number and the key name. They never show a value.
"""

from __future__ import annotations

import re

from ssas_agent.llm.errors import EnvFileError
from ssas_agent.policy import Operation, PathPolicy

ENV_FILE_NAME = ".env"
EXPORT_PREFIX = "export "
COMMENT_START = re.compile(r"(?:^|\s)#")
KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
QUOTE_CHARACTERS = ('"', "'")


def read_env_file(policy: PathPolicy) -> dict[str, str]:
    """Return the values in the project's .env file, or an empty dict when there is no such file."""
    resolved = policy.enforce(Operation.READ, ENV_FILE_NAME)
    if not resolved.is_file():
        return {}
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise EnvFileError(f"{ENV_FILE_NAME} could not be read as UTF-8 text") from None
    return parse_env_text(text)


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = _parse_assignment(line, line_number)
        if key in values:
            raise EnvFileError(f"line {line_number}: '{key}' is set more than once")
        values[key] = value
    return values


def _parse_assignment(line: str, line_number: int) -> tuple[str, str]:
    body = line.removeprefix(EXPORT_PREFIX).lstrip()
    key, separator, raw_value = body.partition("=")
    key = key.strip()
    if not separator or not KEY_PATTERN.fullmatch(key):
        raise EnvFileError(f"line {line_number}: expected KEY=VALUE with a plain name")
    return key, _parse_value(raw_value.strip(), line_number, key)


def _parse_value(raw_value: str, line_number: int, key: str) -> str:
    if raw_value[:1] in QUOTE_CHARACTERS:
        return _parse_quoted(raw_value, line_number, key)
    return COMMENT_START.split(raw_value, maxsplit=1)[0].strip()


def _parse_quoted(raw_value: str, line_number: int, key: str) -> str:
    quote = raw_value[0]
    closing = raw_value.find(quote, 1)
    if closing == -1:
        raise EnvFileError(f"line {line_number}: the quoted value of '{key}' is not closed")
    trailing = raw_value[closing + 1 :].strip()
    if trailing and not trailing.startswith("#"):
        raise EnvFileError(f"line {line_number}: unexpected text after the quoted value of '{key}'")
    return raw_value[1:closing]
