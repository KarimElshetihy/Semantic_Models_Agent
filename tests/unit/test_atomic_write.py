"""Atomic write tests: a failed write must never leave a half-written or stray file."""

import os

import pytest

from ssas_agent.bim import write_bytes_atomically


def leftover_temp_files(folder):
    return [name for name in os.listdir(folder) if name.endswith(".tmp")]


def test_write_creates_file_with_exact_bytes(tmp_path):
    target = tmp_path / "Model.bim"

    write_bytes_atomically(target, b"payload")

    assert target.read_bytes() == b"payload"
    assert leftover_temp_files(tmp_path) == []


def test_write_replaces_existing_file(tmp_path):
    target = tmp_path / "Model.bim"
    target.write_bytes(b"old")

    write_bytes_atomically(target, b"new")

    assert target.read_bytes() == b"new"


def test_failed_replace_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / "Model.bim"
    target.write_bytes(b"original")

    def failing_replace(source, destination):
        raise OSError("simulated failure during replace")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated failure"):
        write_bytes_atomically(target, b"changed")

    assert target.read_bytes() == b"original"
    assert leftover_temp_files(tmp_path) == []
