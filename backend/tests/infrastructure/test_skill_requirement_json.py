"""Synthetic tmp_path artifacts only. Provider has no skill gap responsibilities."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.infrastructure import skill_requirement_json
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
    SkillRequirementLoadError,
)
from tests.domain.test_skill_requirement_artifact import artifact_data


def write_artifact(directory, name, data):
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_order_exact_queries_snapshot_and_read_only(tmp_path):
    second = write_artifact(tmp_path, "b.json", artifact_data(edition_id="edition-b"))
    first = write_artifact(tmp_path, "a.json", artifact_data(edition_id="edition-a"))
    track = write_artifact(tmp_path, "c.json", artifact_data(
        edition_id="edition-a", track_id="track-a",
    ))
    before = {p: p.read_bytes() for p in (first, second, track)}
    provider = JsonSkillRequirementProvider(tmp_path)
    assert [a.requirement_set.target.edition_id for a in provider.list_artifacts()] == [
        "edition-a", "edition-b", "edition-a",
    ]
    result = provider.get_requirements("synthetic-competition", "edition-a")
    assert result.target.track_id is None
    assert provider.get_requirements("synthetic-competition", "edition-a", "track-a").target.track_id == "track-a"
    for ids in (
        ("synthetic-competition", "edition-a", "track-b"),
        ("other", "edition-a", None), ("synthetic-competition", "other", None),
    ):
        assert provider.get_requirements(*ids) is None
    assert {p: p.read_bytes() for p in before} == before
    with pytest.raises(ValidationError, match="frozen"):
        result.coverage_note = "mutated"
    # Loaded snapshot survives source-file changes; query never re-reads or rewrites.
    first.write_text("broken", encoding="utf-8")
    assert provider.get_requirements("synthetic-competition", "edition-a") == result


def test_no_edition_track_or_year_fallback(tmp_path):
    write_artifact(tmp_path, "edition.json", artifact_data())
    provider = JsonSkillRequirementProvider(tmp_path)
    assert provider.get_requirements("synthetic-competition", "synthetic-edition", "track") is None
    assert provider.get_requirements("synthetic-competition", "next-edition") is None


def test_empty_directory_and_missing_directory_are_distinct(tmp_path):
    provider = JsonSkillRequirementProvider(tmp_path)
    assert provider.list_artifacts() == ()
    assert provider.get_requirements("c", "e") is None
    with pytest.raises(SkillRequirementLoadError, match="DIRECTORY_INVALID"):
        JsonSkillRequirementProvider(tmp_path / "absent")
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(SkillRequirementLoadError, match="DIRECTORY_INVALID"):
        JsonSkillRequirementProvider(file_path)


def test_duplicate_target_including_different_version_rejected(tmp_path):
    write_artifact(tmp_path, "a.json", artifact_data())
    write_artifact(tmp_path, "b.json", artifact_data() | {"requirement_version": "v2"})
    with pytest.raises(SkillRequirementLoadError, match="DUPLICATE_REQUIREMENT_TARGET"):
        JsonSkillRequirementProvider(tmp_path)


@pytest.mark.parametrize("bad_json", ["{", "[]", "null", '{"unknown": true}'])
def test_invalid_later_file_aborts_entire_load_with_cause(tmp_path, bad_json):
    write_artifact(tmp_path, "a.json", artifact_data())
    bad_path = tmp_path / "z.json"
    bad_path.write_text(bad_json, encoding="utf-8")
    with pytest.raises(SkillRequirementLoadError) as caught:
        JsonSkillRequirementProvider(tmp_path)
    assert caught.value.reason == "REQUIREMENT_ARTIFACT_INVALID"
    assert caught.value.artifact_path == bad_path
    assert isinstance(caught.value.__cause__, ValidationError)


@pytest.mark.parametrize("invalid", ["wrong_fact", "unknown_skill", "duplicate_requirement"])
def test_invalid_nested_data_fail_fast(tmp_path, invalid):
    data = artifact_data()
    if invalid == "wrong_fact":
        data["requirement_set"]["requirements"][0]["evidence"][0]["value"] = "beginner"
    elif invalid == "unknown_skill":
        data["skills"] = []
    else:
        data["requirement_set"]["requirements"] *= 2
    write_artifact(tmp_path, "invalid.json", data)
    with pytest.raises(SkillRequirementLoadError, match="ARTIFACT_INVALID"):
        JsonSkillRequirementProvider(tmp_path)


def test_shared_skill_identity_conflict_rejected(tmp_path):
    write_artifact(tmp_path, "a.json", artifact_data())
    data = artifact_data(edition_id="other")
    data["skills"][0]["name"] = "Different Meaning"
    write_artifact(tmp_path, "b.json", data)
    with pytest.raises(SkillRequirementLoadError, match="CONFLICTING_SKILL_IDENTITY"):
        JsonSkillRequirementProvider(tmp_path)


def test_provider_import_boundary():
    tree = ast.parse(inspect.getsource(skill_requirement_json))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {
        "pathlib", "types", "pydantic", "competition_copilot.application.skill_requirements",
        "competition_copilot.domain.skill_gap", "competition_copilot.domain.skill_requirement_artifact",
    }


def test_io_failure_aborts_load_preserving_original_cause(tmp_path, monkeypatch):
    from pathlib import Path

    path = write_artifact(tmp_path, "a.json", artifact_data())

    def deny_read(self):
        raise PermissionError("synthetic read failure")

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    with pytest.raises(SkillRequirementLoadError) as caught:
        JsonSkillRequirementProvider(tmp_path)
    assert caught.value.artifact_path == path
    assert isinstance(caught.value.__cause__, PermissionError)
