"""Intent CAS, exact result selection and deterministic presentation policy."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.application.my_competitions import (
    DerivedSummary,
    MyCompetitionCommand,
    MyCompetitionEditor,
    next_action,
)
from competition_copilot.application.profile_freshness import resolve_profile_freshness
from competition_copilot.application.profiles import ProfileActorBinding
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.student_competition_memory import (
    InMemoryDerivedResultReadStore,
    InMemoryStudentCompetitionRepository,
)
from competition_copilot.repositories.student import ProfileError, ProfileReference
from competition_copilot.repositories.student_competition import (
    DerivedResultReference,
    MyCompetitionTarget,
    RetainedDerivedResult,
    canonical_json,
    content_digest,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TARGET = MyCompetitionTarget(competition_id="comap-mcm", edition_id="comap-mcm-2027")
PROFILE = ProfileReference(student_id="student", version=1, content_digest="a" * 64, host_scope="host")


def retained(sequence=1, identity="result", student="student"):
    decision = CompetitionEligibilityEvaluator(JsonSeedCompetitionRepository(ROOT / "data/seed"),
        JsonEligibilityPolicyProvider(ROOT / "data/eligibility")).evaluate(
            StudentProfile(id=student, education_level="undergraduate"), **TARGET.model_dump())
    return RetainedDerivedResult(reference=DerivedResultReference(result_ref_id=identity,
        student_id=student, target=TARGET, kind="ELIGIBILITY",
        content_digest=content_digest(decision.model_dump(mode="json"))),
        payload_json=canonical_json(decision.model_dump(mode="json")),
        input_profile_ref=PROFILE if student == "student" else None, execution_sequence=sequence)


@pytest.mark.parametrize("patch", [{"edition_id": None}, {"track_id": ""}, {"competition_id": " "}])
def test_invalid_partial_or_blank_target(patch):
    with pytest.raises(ValidationError):
        MyCompetitionTarget(**{**TARGET.model_dump(), **patch})


@pytest.mark.parametrize("state", ["SAVED", "PREPARING"])
def test_relationship_state_and_deep_immutable_roundtrip(state):
    repository = InMemoryStudentCompetitionRepository()
    value = repository.add("student", TARGET, state, now=NOW)
    assert value.relationship.state == state
    assert value == type(value).model_validate_json(value.model_dump_json())
    assert value.relationship_ref.content_digest == content_digest(value.relationship.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        value.relationship.state = "PREPARING"
    with pytest.raises(ValidationError):
        value.relationship_ref.target.track_id = "another"
    with pytest.raises(ValidationError):
        repository.replace_state(value.relationship_ref, "REGISTERED", now=NOW)
    assert repository.get_exact("student", TARGET) == value


def test_unique_key_student_edition_track_and_stable_order():
    repository = InMemoryStudentCompetitionRepository()
    for student, target, state in [
        ("student", TARGET, "SAVED"), ("other", TARGET, "SAVED"),
        ("student", MyCompetitionTarget(competition_id="comap-mcm", edition_id="comap-mcm-2026"), "PREPARING"),
        ("student", MyCompetitionTarget(**{**TARGET.model_dump(), "track_id": "track-a"}), "SAVED"),
        ("student", MyCompetitionTarget(**{**TARGET.model_dump(), "track_id": "track-b"}), "SAVED"),
    ]:
        repository.add(student, target, state, now=NOW)
    with pytest.raises(ProfileError, match="ALREADY_EXISTS"):
        repository.add("student", TARGET, "SAVED", now=NOW)
    assert len(repository.list_for_student("student")) == 4
    assert len(repository.list_for_student("other")) == 1
    assert repository.list_for_student("missing") == ()
    assert repository.list_for_student("student")[0].relationship.state == "PREPARING"
    assert repository.get_exact("student", TARGET).relationship.track_id is None


def test_cas_both_state_directions_remove_readd_and_host_restart():
    repository = InMemoryStudentCompetitionRepository()
    first = repository.add("student", TARGET, "SAVED", now=NOW)
    second = repository.replace_state(first.relationship_ref, "PREPARING", now=NOW)
    assert second.relationship.version == 2
    assert second.relationship_ref.content_digest != first.relationship_ref.content_digest
    with pytest.raises(ProfileError, match="VERSION_CONFLICT"):
        repository.replace_state(first.relationship_ref, "SAVED", now=NOW)
    with pytest.raises(ProfileError, match="VERSION_CONFLICT"):
        repository.remove(first.relationship_ref)
    third = repository.replace_state(second.relationship_ref, "SAVED", now=NOW)
    repository.remove(third.relationship_ref)
    again = repository.add("student", TARGET, "SAVED", now=NOW)
    assert again.relationship.relationship_id != first.relationship.relationship_id
    with pytest.raises(ProfileError, match="VERSION_CONFLICT"):
        repository.remove(third.relationship_ref)
    restarted = InMemoryStudentCompetitionRepository()
    assert restarted.list_for_student("student") == ()
    assert restarted.host_scope != repository.host_scope


def test_concurrent_duplicate_add_is_atomic():
    repository = InMemoryStudentCompetitionRepository()
    def add(_):
        try:
            repository.add("student", TARGET, "SAVED", now=NOW)
            return True
        except ProfileError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(add, range(20))) == 1


@pytest.mark.parametrize("target", [
    {"competition_id": "missing", "edition_id": "comap-mcm-2027"},
    {"competition_id": "huawei-ict", "edition_id": "comap-mcm-2027"},
    {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027", "track_id": "missing"},
])
def test_editor_rejects_invalid_canonical_targets(target):
    repository = InMemoryStudentCompetitionRepository()
    editor = MyCompetitionEditor(repository, JsonSeedCompetitionRepository(ROOT / "data/seed"),
        ProfileActorBinding(actor_id="operator", permitted_student_ids=("student",)), clock=lambda: NOW)
    with pytest.raises(ProfileError, match="INVALID_TARGET"):
        editor.mutate(MyCompetitionCommand(operation="add", student_id="student", target=target))
    assert repository.list_for_student("student") == ()


@pytest.mark.parametrize("operation", ["add", "update", "remove"])
def test_editor_authorization_before_access(operation):
    class Unreachable:
        def __getattr__(self, name):
            raise AssertionError("Unauthorised repository access")
    editor = MyCompetitionEditor(Unreachable(), Unreachable(),
        ProfileActorBinding(actor_id="operator", permitted_student_ids=("student",)), clock=lambda: NOW)
    with pytest.raises(ProfileError, match="FORBIDDEN"):
        editor.mutate(MyCompetitionCommand(operation=operation, student_id="other", target=TARGET, state="SAVED"))


def test_editor_cannot_patch_identity_or_target_and_remove_preserves_results():
    repository, store = InMemoryStudentCompetitionRepository(), InMemoryDerivedResultReadStore()
    editor = MyCompetitionEditor(repository, JsonSeedCompetitionRepository(ROOT / "data/seed"),
        ProfileActorBinding(actor_id="operator", permitted_student_ids=("student",)), clock=lambda: NOW)
    snapshot = editor.mutate(MyCompetitionCommand(operation="add", student_id="student", target=TARGET)).snapshot
    result = retained()
    store.retain_and_select(result)
    with pytest.raises(ValidationError):
        MyCompetitionCommand(operation="update", student_id="student", target=TARGET, state="SAVED", version=9)
    other = MyCompetitionTarget(**{**TARGET.model_dump(), "track_id": "other"})
    with pytest.raises(ProfileError, match="INVALID_REFERENCE"):
        editor.mutate(MyCompetitionCommand(operation="update", student_id="student", target=other, state="SAVED",
            expected_reference=snapshot.relationship_ref))
    editor.mutate(MyCompetitionCommand(operation="remove", student_id="student", target=TARGET,
        expected_reference=snapshot.relationship_ref))
    assert store.selected("student", TARGET, "ELIGIBILITY") == result.reference
    assert store.resolve(result.reference) == result


def test_state_update_cannot_default_silently_to_saved():
    with pytest.raises(ValidationError, match="explicitly supplied state"):
        MyCompetitionCommand(operation="update", student_id="student", target=TARGET)


def test_result_selection_uses_invocation_sequence_not_completion_order():
    store = InMemoryDerivedResultReadStore()
    older = retained(store.next_sequence(), "old")
    newer = retained(store.next_sequence(), "new")
    store.retain_and_select(newer)
    store.retain_and_select(older)
    assert store.selected("student", TARGET, "ELIGIBILITY") == newer.reference
    assert store.resolve(older.reference) == older
    for _ in range(3):
        assert store.resolve(newer.reference) == newer
        assert store.selected("other", TARGET, "ELIGIBILITY") is None
    with pytest.raises(ProfileError, match="INVALID_REFERENCE"):
        store.resolve(DerivedResultReference(**{**newer.reference.model_dump(), "content_digest": "b" * 64}))
    with pytest.raises(ValidationError):
        RetainedDerivedResult(**{**older.model_dump(), "input_profile_ref": {
            **PROFILE.model_dump(), "student_id": "other"}})


@pytest.mark.parametrize("case,expected", [
    ("target", "TARGET_UNAVAILABLE"), ("profile", "CURRENT_PROFILE_UNAVAILABLE"),
    ("eligibility_missing", "ELIGIBILITY_NOT_ANALYZED"),
    ("eligibility_unknown", "ELIGIBILITY_REVIEW_REQUIRED"),
    ("eligibility_ineligible", "ELIGIBILITY_REVIEW_REQUIRED"),
    ("eligibility_stale", "ELIGIBILITY_PROFILE_NOT_CURRENT"),
    ("gap_missing", "SKILL_GAP_NOT_ANALYZED"), ("gap_stale", "SKILL_GAP_PROFILE_NOT_CURRENT"),
    ("gap_unknown", "SKILL_GAP_PROFILE_NOT_CURRENT"), ("gap_invalid", "SKILL_GAP_UNAVAILABLE"),
    ("plan_missing", "PLAN_NOT_SELECTED"), ("plan_stale", "PLAN_PROFILE_STALE"),
    ("plan_current", "PLAN_PROFILE_CURRENT"), ("plan_unknown", "PLAN_PROFILE_UNKNOWN"),
    ("plan_invalid", "PLAN_REFERENCE_UNAVAILABLE"),
])
def test_next_action_transparent_priority(case, expected):
    current = resolve_profile_freshness(PROFILE, PROFILE, student_id="student")
    stale = resolve_profile_freshness(PROFILE, ProfileReference(**{**PROFILE.model_dump(), "version": 2}), student_id="student")
    unknown = resolve_profile_freshness(None, PROFILE, student_id="student")
    values = {k: DerivedSummary(availability="AVAILABLE", status="eligible" if k == "eligibility" else "draft",
        label="supplied", profile_freshness=current) for k in ("eligibility", "skill_gap", "plan")}
    if case.startswith("eligibility_"):
        key, suffix = "eligibility", case[len("eligibility_"):]
    elif case.startswith("gap_"):
        key, suffix = "skill_gap", case[len("gap_"):]
    else:
        key, suffix = "plan", case[len("plan_"):]
    if suffix in ("missing", "invalid", "stale", "unknown", "ineligible") and case not in ("profile", "target"):
        patch = {"profile_freshness": stale if suffix == "stale" else unknown} if suffix in ("stale", "unknown") else {}
        if suffix == "unknown" and key == "eligibility":
            patch = {"status": "unknown"}
        if suffix == "ineligible":
            patch = {"status": "ineligible"}
        if suffix == "missing":
            patch = {"availability": "NOT_SELECTED" if key == "plan" else "NOT_ANALYZED"}
        if suffix == "invalid":
            patch = {"availability": "INVALID_REFERENCE"}
        values[key] = DerivedSummary(**{**values[key].model_dump(), **patch})
    args = dict(target_available=case != "target", profile_available=case != "profile", **values)
    first = next_action(TARGET, **args)
    assert first.reason_code == expected
    assert first == next_action(TARGET, **args)
