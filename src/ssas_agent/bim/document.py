"""In-memory representation of a Model.bim file that can be reproduced byte for byte.

The raw JSON dictionary is the canonical form. Unknown properties are kept
exactly as they were loaded. Before any edit, the loaded file must reproduce
its own bytes; otherwise editing is refused.
"""

from __future__ import annotations

import codecs
import hashlib
import json
from dataclasses import dataclass
from typing import Any

UTF8_BOM = codecs.BOM_UTF8
LINE_BREAK = "\r\n"
JSON_INDENT = 2
REQUIRED_TOP_LEVEL_KEY = "model"


class InvalidBimError(ValueError):
    """Raised when bytes are not a Model.bim document (bad encoding, bad JSON, or no model section)."""


class NonReproducibleBimError(RuntimeError):
    """Raised when editing is refused because the file cannot be reproduced byte for byte."""


def serialize_visual_studio_bytes(document: dict[str, Any]) -> bytes:
    """Serialize as Visual Studio 2019 does: 2-space indent, UTF-8 without BOM, CRLF, no trailing newline."""
    text = json.dumps(document, indent=JSON_INDENT, ensure_ascii=False)
    return text.replace("\n", LINE_BREAK).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_bim_json(raw_bytes: bytes) -> dict[str, Any]:
    """Parse UTF-8 JSON (with or without BOM) and check the top-level structure."""
    try:
        document = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidBimError(f"not valid UTF-8 JSON: {error}") from error
    if not isinstance(document, dict) or REQUIRED_TOP_LEVEL_KEY not in document:
        raise InvalidBimError(f"missing top-level '{REQUIRED_TOP_LEVEL_KEY}' section")
    return document


def explain_reproduction_mismatch(raw_bytes: bytes) -> list[str]:
    """Return the likely reasons a file cannot be reproduced. Empty means no specific cause was found."""
    reasons = []
    if raw_bytes.startswith(UTF8_BOM):
        reasons.append("file starts with a UTF-8 byte order mark")
    crlf_count = raw_bytes.count(b"\r\n")
    lf_only_count = raw_bytes.count(b"\n") - crlf_count
    if lf_only_count:
        reasons.append(f"{lf_only_count} line(s) use LF instead of CRLF")
    if raw_bytes.endswith(b"\n"):
        reasons.append("file ends with a trailing newline")
    return reasons


@dataclass
class BimDocument:
    """A parsed Model.bim plus the evidence needed to decide whether it may be edited."""

    source_bytes: bytes
    data: dict[str, Any]
    reproducible_on_load: bool

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> BimDocument:
        data = parse_bim_json(raw_bytes)
        reproducible = serialize_visual_studio_bytes(data) == raw_bytes
        return cls(source_bytes=raw_bytes, data=data, reproducible_on_load=reproducible)

    def ensure_editable(self) -> None:
        """Refuse editing when the loaded file would not be reproduced byte for byte."""
        if self.reproducible_on_load:
            return
        reasons = explain_reproduction_mismatch(self.source_bytes)
        detail = "; ".join(reasons) or "re-serialized JSON differs from the original bytes"
        raise NonReproducibleBimError(f"editing refused, file cannot be reproduced exactly: {detail}")

    def to_bytes(self) -> bytes:
        return serialize_visual_studio_bytes(self.data)
