"""Catalog authority, atomic self-report edits and profile CAS boundaries."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from competition_copilot.application.profile_skills import (
    SkillCatalogProjection,
    SkillCatalogQuery,
    SkillCatalogReader,
    SkillCommand,
    SkillMutationInput,
    StudentSkillEditor,
)
from competition_copilot.application.profiles import (
    ProfileActorBinding,
    ProfilePatch,
    ProfileUpdate,
    StudentProfileEditor,
    UpdateProfileInput,
)
from competition_copilot.domain.skill import Skill
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.student_memory import (
    InMemoryStudentProfileRepository,
)
from competition_copilot.repositories.student import ProfileError

NOW = datetime(2026, 10, 25, tzinfo=UTC)


def catalog(*skills):
    return SkillCatalogReader(SimpleNamespace(list_artifacts=lambda: tuple(
        SimpleNamespace(skills=(skill,)) for skill in skills)))


def setup():
    repo = InMemoryStudentProfileRepository([StudentProfile(id="student", skills=[
        {"skill_id": "unresolved", "level": "unknown", "self_assessed": False}])], created_at=NOW)
    actor = ProfileActorBinding(actor_id="operator", permitted_student_ids=("student",))
    editor = StudentSkillEditor(repo, actor, clock=lambda: NOW,
        catalog=catalog(Skill(id="modeling", name="Modeling", aliases=["Model"])))
    return repo, editor


def mutate(repo, editor, operation="add", skill_id="modeling", **fields):
    return editor.mutate(SkillMutationInput(student_id="student", request_id="request",
        command=SkillCommand(operation=operation, skill_id=skill_id,
            expected_profile_ref=repo.get("student").profile_ref, **fields)))


def test_catalog_stable_dedup_conflicts_json_immutable():
    a, b = Skill(id="a", name="A"), Skill(id="b", name="B", description="description")
    value = catalog(b, a, a).read(SkillCatalogQuery())
    assert [s.skill_id for s in value.skills] == ["a", "b"]
    assert SkillCatalogProjection.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        value.skills[0].name = "changed"
    with pytest.raises(ProfileError, match="SKILL_CATALOG_CONFLICT"):
        catalog(a, Skill(id="a", name="Conflict")).read(SkillCatalogQuery())
    assert catalog().read(SkillCatalogQuery()).skills == ()


@pytest.mark.parametrize("level", ["unknown", "beginner", "intermediate", "advanced"])
def test_add_levels_reference_and_evidence(level):
    repo, editor = setup()
    old = repo.get("student")
    result = mutate(repo, editor, level=level, note=" Course project ")
    skill = result.profile.skills[-1]
    assert (skill.level, skill.note, skill.self_assessed) == (level, "Course project", True)
    assert result.profile.profile_ref.version == old.profile_ref.version + 1
    assert result.profile.profile_ref.content_digest != old.profile_ref.content_digest
    assert result.profile.skills[0] == old.skills[0]  # historical unresolved ID retained
    evidence = repo.get_record("student").evidence
    assert len(evidence) == (0 if level == "unknown" else 1)
    if evidence:
        assert evidence[0].value == level
        assert evidence[0].source is None
        assert "Course project" not in evidence[0].message
        with pytest.raises(ValidationError):
            evidence[0].value = "advanced"


@pytest.mark.parametrize("skill,error", [("unresolved", "SKILL_ALREADY_EXISTS"),
                                       ("invented", "SKILL_NOT_IN_CATALOG")])
def test_add_invalid_identity_unchanged(skill, error):
    repo, editor = setup()
    before = repo.get_record("student")
    with pytest.raises(ProfileError, match=error):
        mutate(repo, editor, skill_id=skill)
    assert repo.get_record("student") == before


@pytest.mark.parametrize("first,second", [("beginner", "intermediate"),
    ("intermediate", "advanced"), ("intermediate", "unknown")])
def test_update_level_replaces_old_evidence_once(first, second):
    repo, editor = setup()
    before = mutate(repo, editor, level=first).profile
    result = mutate(repo, editor, "update", level=second)
    assert result.profile.profile_ref.version == before.profile_ref.version + 1
    facts = repo.get_record("student").evidence
    assert [fact.value for fact in facts] == ([] if second == "unknown" else [second])
    assert result.profile.skills[-1].level == second


def test_note_only_preserves_level_and_false_is_not_certification():
    repo, editor = setup()
    result = mutate(repo, editor, "update", "unresolved", note=" Annotation ")
    assert result.profile.skills[0].note == "Annotation"
    assert result.profile.skills[0].level == "unknown"
    assert result.profile.skills[0].self_assessed is False
    assert repo.get_record("student").evidence == ()


def test_remove_means_missing_and_removes_evidence():
    repo, editor = setup()
    before = mutate(repo, editor, level="beginner").profile
    result = mutate(repo, editor, "remove")
    assert all(s.skill_id != "modeling" for s in result.profile.skills)
    assert repo.get_record("student").evidence == ()
    assert result.profile.profile_ref.version == before.profile_ref.version + 1
    with pytest.raises(ProfileError, match="SKILL_NOT_FOUND"):
        mutate(repo, editor, "remove")


def test_validation_failure_is_atomic():
    repo, editor = setup()
    mutate(repo, editor, level="beginner")
    old = repo.get_record("student")
    with patch("competition_copilot.application.profile_skills.prepare_student_skill_evidence",
               side_effect=ValueError("invalid evidence")):
        with pytest.raises(ProfileError, match="SKILL_EVIDENCE_INCONSISTENT"):
            mutate(repo, editor, "update", level="advanced")
    assert repo.get_record("student") == old


def test_concurrent_profile_and_skill_mutations_both_directions():
    repo, editor = setup()
    base_editor = StudentProfileEditor(repo, editor.actor, clock=lambda: NOW)
    old = repo.get("student").profile_ref
    command = SkillMutationInput(student_id="student", request_id="skill", command=SkillCommand(
        operation="add", skill_id="modeling", expected_profile_ref=old))
    base = UpdateProfileInput(student_id="student", request_id="profile", update=ProfileUpdate(
        expected_profile_ref=old, patch=ProfilePatch(major="Science")))
    base_editor.edit(base)
    with pytest.raises(ProfileError, match="PROFILE_VERSION_CONFLICT"):
        editor.mutate(command)
    current = repo.get("student").profile_ref
    mutate(repo, editor)
    with pytest.raises(ProfileError, match="PROFILE_VERSION_CONFLICT"):
        base_editor.edit(UpdateProfileInput(student_id="student", request_id="profile", update=ProfileUpdate(
            expected_profile_ref=current, patch=ProfilePatch(major="Other"))))
    stale = command.model_dump()
    stale["command"]["expected_profile_ref"] = current
    with pytest.raises(ProfileError, match="PROFILE_VERSION_CONFLICT"):
        editor.mutate(SkillMutationInput.model_validate(stale))


@pytest.mark.parametrize("operation", ["add", "update", "remove"])
def test_identity_is_not_authorization(operation):
    repo, editor = setup()
    editor.actor = ProfileActorBinding(actor_id="other", permitted_student_ids=())
    with pytest.raises(ProfileError, match="PROFILE_EDIT_FORBIDDEN"):
        mutate(repo, editor, operation)


@pytest.mark.parametrize("fields", [{"level": "expert"}, {"note": " "},
    {"self_assessed": False}, {"new_skill_id": "other"}])
def test_invalid_write_fields(fields):
    repo, _ = setup()
    with pytest.raises(ValidationError):
        SkillCommand(operation="update", skill_id="modeling",
            expected_profile_ref=repo.get("student").profile_ref, **fields)
