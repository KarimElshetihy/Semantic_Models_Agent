"""The traceability matrix names only test files that exist, so it cannot point at nothing."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "docs" / "PHASE1_TRACEABILITY.md"
TEST_FILE_PATTERN = re.compile(r"`(tests/(?:unit|integration)/test_[a-z0-9_]+\.py)`")


def test_matrix_names_test_files_and_every_named_file_exists():
    named = set(TEST_FILE_PATTERN.findall(MATRIX_PATH.read_text(encoding="utf-8")))

    assert len(named) >= 20
    assert sorted(name for name in named if not (REPO_ROOT / name).is_file()) == []
