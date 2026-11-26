"""Create sanitized Model.bim fixtures in tests/fixtures/ from example_models/.

Only Model.bim is copied. Layout files, build output, IDE state and nested git
repositories are left behind. Table and column names are kept so tests stay
realistic; hostnames, service names and the Oracle account name are replaced.

Replacements are applied to the raw text, not to re-serialized JSON, so every
other byte of the file is preserved. The script then checks that each fixture
is valid JSON, still round-trips byte for byte, and contains no leaked values.

Run from the project root:
    python tools/sanitize_fixtures.py
"""

import json
import re
import sys

from bim_format import (
    EXAMPLES_ROOT,
    FIXTURES_ROOT,
    find_model_files,
    project_label,
    round_trips_byte_for_byte,
)

REPLACEMENT_RULES = (
    (re.compile(re.escape("dwhdbhq-scan:1521/dwhdb_srv"), re.IGNORECASE), "oracle-host:1521/oracle_service"),
    (re.compile("epaysetts", re.IGNORECASE), "oracle_user"),
)
LEAK_PATTERNS = (
    re.compile("dwhdb", re.IGNORECASE),
    re.compile("epaysetts", re.IGNORECASE),
)


def sanitize_text(text):
    """Return the sanitized text and the number of replacements made."""
    replacement_count = 0
    for pattern, replacement in REPLACEMENT_RULES:
        text, count = pattern.subn(replacement, text)
        replacement_count += count
    return text, replacement_count


def find_leaks(text):
    return [pattern.pattern for pattern in LEAK_PATTERNS if pattern.search(text)]


def verify_fixture_bytes(fixture_bytes):
    """Return a list of problems; an empty list means the fixture is safe to keep."""
    problems = []
    text = fixture_bytes.decode("utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        return [f"invalid JSON: {error}"]
    if not round_trips_byte_for_byte(fixture_bytes, document):
        problems.append("does not round-trip byte for byte")
    problems.extend(f"leaked value matching '{leak}'" for leak in find_leaks(text))
    return problems


def write_fixture(label, fixture_bytes):
    fixture_path = FIXTURES_ROOT / label / "Model.bim"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_bytes(fixture_bytes)
    return fixture_path


def build_fixture(model_path):
    """Sanitize one model. Return (label, fixture_bytes, replacement_count)."""
    original_text = model_path.read_bytes().decode("utf-8")
    sanitized_text, replacement_count = sanitize_text(original_text)
    label = project_label(model_path, EXAMPLES_ROOT)
    return label, sanitized_text.encode("utf-8"), replacement_count


def main():
    failed = False
    for model_path in find_model_files(EXAMPLES_ROOT):
        label, fixture_bytes, replacement_count = build_fixture(model_path)
        problems = verify_fixture_bytes(fixture_bytes)
        if problems:
            failed = True
            print(f"FAILED  {label}: {'; '.join(problems)}")
            continue
        fixture_path = write_fixture(label, fixture_bytes)
        print(f"OK      {label}: {replacement_count} replacements -> {fixture_path.relative_to(FIXTURES_ROOT.parent.parent)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
