"""Scan Model.bim files in a folder for strings that should not appear in shared fixtures.

Read-only. Prints data source blocks and the distinct host-like, address-like,
email-like and path-like strings found. Run it on example_models/ to decide what
to sanitize, then on tests/fixtures/ to confirm nothing sensitive is left.

Run from the project root:
    python tools/scan_sensitive_strings.py [folder]
"""

import json
import re

from bim_format import (
    EXAMPLES_ROOT,
    find_model_files,
    project_label,
    resolve_root_from_arguments,
)

SENSITIVE_PATTERNS = {
    "ip_address": r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "url": r"https?://[^\s\"']+",
    "unc_or_drive_path": r"(?:\\\\\\\\[\w.$-]+\\\\|[A-Za-z]:\\\\)[^\s\"']*",
    "host_like": r"\b(?:ef|EF)[-_][\w-]*\d+\b|\bdwhdb\w*|\b[\w-]+-scan\b",
}


def print_data_sources(label, document):
    for source in document["model"].get("dataSources", []):
        print(f"[{label}] dataSource:", json.dumps(source, ensure_ascii=False))


def distinct_matches(text, pattern):
    return sorted(set(re.findall(pattern, text)))


def print_pattern_hits(label, text):
    for name, pattern in SENSITIVE_PATTERNS.items():
        hits = distinct_matches(text, pattern)
        if hits:
            print(f"[{label}] {name}: {hits[:10]}")


def main():
    root = resolve_root_from_arguments(EXAMPLES_ROOT)
    for model_path in find_model_files(root):
        label = project_label(model_path, root)
        text = model_path.read_text(encoding="utf-8")
        print_data_sources(label, json.loads(text))
        print_pattern_hits(label, text)


if __name__ == "__main__":
    main()
