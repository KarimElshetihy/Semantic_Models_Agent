"""File access for Model.bim: read, and write atomically so a failed write never leaves a half-written file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ssas_agent.bim.document import BimDocument


def load_bim_file(model_path: Path) -> BimDocument:
    return BimDocument.from_bytes(Path(model_path).read_bytes())


def save_bim_file(document: BimDocument, model_path: Path) -> None:
    """Save an edited document. Refuses if the original file could not be reproduced exactly."""
    document.ensure_editable()
    write_bytes_atomically(Path(model_path), document.to_bytes())


def write_bytes_atomically(target_path: Path, data: bytes) -> None:
    """Write to a temporary file in the same folder, then replace the target in one step."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=target_path.parent, prefix=f".{target_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target_path)
    except BaseException:
        _remove_if_exists(temp_name)
        raise


def _remove_if_exists(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
