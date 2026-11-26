"""Phase 0 round-trip and fail-closed tests for Model.bim files.

Offline only. Uses the sanitized fixtures in tests/fixtures/.
"""

import json
from pathlib import Path

import pytest

from ssas_agent.bim import (
    BimDocument,
    InvalidBimError,
    NonReproducibleBimError,
    load_bim_file,
    save_bim_file,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_MODELS = sorted(FIXTURES_ROOT.rglob("Model.bim"))
EXPECTED_FIXTURE_COUNT = 4


def fixture_id(model_path):
    return model_path.parent.name


def write_model(folder, raw_bytes):
    model_path = folder / "Model.bim"
    model_path.write_bytes(raw_bytes)
    return model_path


def fixture_bytes(index=0):
    return FIXTURE_MODELS[index].read_bytes()


def test_all_four_fixtures_are_present():
    assert len(FIXTURE_MODELS) == EXPECTED_FIXTURE_COUNT


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=fixture_id)
def test_fixture_is_reproducible_on_load(model_path):
    assert load_bim_file(model_path).reproducible_on_load


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=fixture_id)
def test_fixture_round_trips_byte_for_byte(model_path):
    document = load_bim_file(model_path)
    assert document.to_bytes() == model_path.read_bytes()


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=fixture_id)
def test_save_without_edit_keeps_bytes_identical(model_path, tmp_path):
    target = tmp_path / "Model.bim"
    save_bim_file(load_bim_file(model_path), target)
    assert target.read_bytes() == model_path.read_bytes()


def test_unknown_property_survives_edit_and_save(tmp_path):
    target = write_model(tmp_path, fixture_bytes())
    document = load_bim_file(target)
    document.data["model"]["unknownFutureProperty"] = {"keepMe": [1, 2, 3]}

    save_bim_file(document, target)

    reloaded = load_bim_file(target).data
    assert reloaded["model"]["unknownFutureProperty"] == {"keepMe": [1, 2, 3]}


def test_edit_changes_only_the_edited_value(tmp_path):
    target = write_model(tmp_path, fixture_bytes())
    document = load_bim_file(target)
    document.data["model"]["culture"] = "ar-EG"

    save_bim_file(document, target)

    expected = json.loads(fixture_bytes().decode("utf-8"))
    expected["model"]["culture"] = "ar-EG"
    assert json.loads(target.read_bytes().decode("utf-8")) == expected


def test_lf_line_endings_refuse_edit(tmp_path):
    lf_bytes = fixture_bytes().replace(b"\r\n", b"\n")
    target = write_model(tmp_path, lf_bytes)
    document = load_bim_file(target)

    assert not document.reproducible_on_load
    with pytest.raises(NonReproducibleBimError, match="LF instead of CRLF"):
        document.ensure_editable()


def test_lf_file_save_is_refused_and_leaves_file_unchanged(tmp_path):
    lf_bytes = fixture_bytes().replace(b"\r\n", b"\n")
    target = write_model(tmp_path, lf_bytes)
    document = load_bim_file(target)

    with pytest.raises(NonReproducibleBimError):
        save_bim_file(document, target)

    assert target.read_bytes() == lf_bytes


def test_bom_file_refuses_edit(tmp_path):
    bom_bytes = b"\xef\xbb\xbf" + fixture_bytes()
    target = write_model(tmp_path, bom_bytes)
    document = load_bim_file(target)

    with pytest.raises(NonReproducibleBimError, match="byte order mark"):
        document.ensure_editable()


def test_trailing_newline_refuses_edit(tmp_path):
    target = write_model(tmp_path, fixture_bytes() + b"\r\n")

    with pytest.raises(NonReproducibleBimError, match="trailing newline"):
        load_bim_file(target).ensure_editable()


def test_invalid_json_is_rejected(tmp_path):
    target = write_model(tmp_path, b"{ not json")

    with pytest.raises(InvalidBimError, match="not valid UTF-8 JSON"):
        load_bim_file(target)


def test_missing_model_section_is_rejected(tmp_path):
    target = write_model(tmp_path, b'{"name": "SemanticModel"}')

    with pytest.raises(InvalidBimError, match="missing top-level 'model'"):
        load_bim_file(target)


def test_from_bytes_matches_load_from_file(tmp_path):
    raw_bytes = fixture_bytes()
    target = write_model(tmp_path, raw_bytes)

    assert BimDocument.from_bytes(raw_bytes).data == load_bim_file(target).data
