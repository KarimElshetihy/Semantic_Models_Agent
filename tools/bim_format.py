"""Shared helpers for the repository tools that read Visual Studio 2019 Model.bim files.

The serialization rules and expression helpers live in the ssas_agent package.
This module only adds folder conventions and command-line handling for the tools.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = PROJECT_ROOT / "example_models"
FIXTURES_ROOT = PROJECT_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ssas_agent.bim.document import (  # noqa: E402  (import after the path is set up)
    UTF8_BOM,
    parse_bim_json,
    serialize_visual_studio_bytes,
)
from ssas_agent.bim.expressions import (  # noqa: E402
    expression_form,
    expression_text,
    m_partition_shape,
)


def resolve_root_from_arguments(default_root):
    """Return the folder given as the first command-line argument, or the default."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return default_root


def find_model_files(root):
    return sorted(root.rglob("Model.bim"))


def project_label(model_path, root):
    """Name of the top-level project folder that contains the model file."""
    return model_path.relative_to(root).parts[0]


def has_bom(raw_bytes):
    return raw_bytes.startswith(UTF8_BOM)


def load_document(model_path):
    """Return (raw_bytes, parsed JSON document)."""
    raw_bytes = model_path.read_bytes()
    return raw_bytes, parse_bim_json(raw_bytes)


def round_trips_byte_for_byte(raw_bytes, document):
    return serialize_visual_studio_bytes(document) == raw_bytes
