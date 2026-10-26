"""Profile repository and use cases: immutable snapshots and authorized CAS."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.application.profiles import (
    GetProfileQuery,
    ProfileActorBinding,
    ProfilePatch,
    ProfileUpdate,
    StudentProfileEditor,
    StudentProfileReader,
    UpdateProfileInput,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.student_memory import (
    InMemoryStudentProfileRepository,
)
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileReference,
    StudentProfileProjection,
    StudentProfileSnapshot,
    profile_digest,
)

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


@pytest.fixture
def env():
    profile = StudentProfile(id="student", major="Original", skills=[
        {"skill_id": "unresolved-but-existing", "level": "unknown", "self_assessed": False}])
    repository = InMemoryStudentProfileRepository([profile, StudentProfile(id="other")], created_at=NOW)
    actor = ProfileActorBinding(actor_id="trusted-test-operator", permitted_student_ids=("student",))
    return repository, StudentProfileEditor(repository, actor, clock=lambda: NOW)


def command(repository, patch):
    return UpdateProfileInput(student_id="student", request_id="explicit-save",
        update=ProfileUpdate(expected_profile_ref=repository.get("student").profile_ref,
                             patch=ProfilePatch(**patch)))


def test_bootstrap_get_missing_and_not_found(env):
    repository, editor = env
    assert repository.get("missing") is None
    assert repository.get("student").major == "Original"
    with pytest.raises(ProfileError, match="PROFILE_NOT_FOUND"):
        editor.read(GetProfileQuery(student_id="missing"))
    assert isinstance(editor, StudentProfileReader)


@pytest.mark.parametrize("patch,expected", [
    ({"education_level": "graduate"}, "graduate"),
    ({"grade": " Year 2 "}, "Year 2"),
    ({"school": " School "}, "School"),
    ({"major": " Computing "}, "Computing"),
    ({"interests": [" AI ", "AI", "ai"]}, ("AI", "ai")),
    ({"goals": [" Learn ", "Learn"]}, ("Learn",)),
    ({"weekly_available_hours": 0}, 0),
    ({"weekly_available_hours": 7.5}, 7.5),
    ({"weekly_available_hours": 168}, 168),
    ({"major": None}, None),
    ({"interests": []}, ()),
    ({"goals": []}, ()),
    ({"weekly_available_hours": None}, None),
])
def test_edit_and_json_roundtrip_omission(env, patch, expected):
    repository, editor = env
    before = repository.get("student")
    update = command(repository, patch)
    update = UpdateProfileInput.model_validate_json(update.model_dump_json())
    result = editor.edit(update)
    key = next(iter(patch))
    assert getattr(result.profile, key) == expected
    assert result.profile.skills == before.skills
    if key != "major":
        assert result.profile.major == "Original"
    assert set(update.update.patch.model_fields_set) == set(patch)
    assert StudentProfileProjection.model_validate_json(result.profile.model_dump_json()) == result.profile


@pytest.mark.parametrize("patch", [
    {"weekly_available_hours": -1}, {"weekly_available_hours": 169},
    {"weekly_available_hours": float("nan")}, {"weekly_available_hours": float("inf")},
    {"education_level": "phd"}, {"grade": " "}, {"school": " "}, {"major": " "},
    {"interests": [" "]}, {"goals": [""]}, {"interests": None},
    {"skills": []}, {"id": "another"}, {"owner": "another"}, {"version": 9},
    {"profile_ref": {}}, {"updated_at": NOW},
])
def test_invalid_patch_rejected_without_write(env, patch):
    repository, _ = env
    before = repository.get("student")
    with pytest.raises(ValidationError):
        command(repository, patch)
    assert repository.get("student") == before


def test_optimistic_concurrency_and_actor(env):
    repository, editor = env
    stale = command(repository, {"major": "Stale write"})
    changed = editor.edit(command(repository, {"major": "New"}))
    assert changed.profile.profile_ref.version == 2
    assert changed.profile.profile_ref != stale.update.expected_profile_ref
    assert changed.changed_fields == ("major",)
    assert changed.profile.updated_by == "trusted-test-operator"
    with pytest.raises(ProfileError, match="PROFILE_VERSION_CONFLICT"):
        editor.edit(stale)
    forbidden = UpdateProfileInput(student_id="other", request_id="forbidden",
        update=ProfileUpdate(expected_profile_ref=repository.get("other").profile_ref,
                             patch=ProfilePatch(major="Unauthorized")))
    with pytest.raises(ProfileError, match="PROFILE_EDIT_FORBIDDEN"):
        editor.edit(forbidden)


def test_repository_cas_even_after_application_preflight(env):
    repository, _ = env
    before = repository.get("student")
    content = StudentProfileSnapshot.model_validate(before.domain_profile())
    wrong = ProfileReference(**{**before.profile_ref.model_dump(), "version": 99})
    with pytest.raises(ProfileError, match="PROFILE_VERSION_CONFLICT"):
        repository.replace(content, expected=wrong, updated_at=NOW, actor="operator")


def test_digest_scope_deep_immutability_and_detachment(env):
    repository, _ = env
    snapshot = repository.get("student")
    domain = snapshot.domain_profile()
    domain.skills.clear()
    assert len(snapshot.skills) == 1
    with pytest.raises(ValidationError):
        snapshot.skills[0].level = "advanced"
    with pytest.raises(ValidationError):
        snapshot.major = "tampered"
    assert isinstance(snapshot.interests, tuple)
    assert isinstance(snapshot.goals, tuple)
    assert isinstance(snapshot.skills, tuple)
    content = StudentProfileSnapshot.model_validate(snapshot.domain_profile())
    assert profile_digest(content) == profile_digest(StudentProfileSnapshot.model_validate_json(content.model_dump_json()))
    another = InMemoryStudentProfileRepository([snapshot.domain_profile()], created_at=NOW).get("student")
    assert another.profile_ref.host_scope != snapshot.profile_ref.host_scope
    assert another.profile_ref.content_digest == snapshot.profile_ref.content_digest


def test_noop_and_reference_integrity(env):
    repository, editor = env
    current = repository.get("student")
    result = editor.edit(command(repository, {}))
    assert result.changed_fields == ()
    assert result.profile == current
    with pytest.raises(ValidationError):
        StudentProfileProjection(**{**current.model_dump(), "major": "tampered"})
