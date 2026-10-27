"""Read-only composition, bounded advice and exact lineage, using formal seed facts."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_detail import (
    CompetitionDetailQuery,
    CompetitionDetailReader,
)
from competition_copilot.application.planning_workspace import (
    MappedPlanInputLineageReader,
    PlanningWorkspaceProjection,
    PlanningWorkspaceQuery,
    PlanningWorkspaceReader,
)
from competition_copilot.application.profile_freshness import DerivedProfileBinding
from competition_copilot.application.profile_skills import SkillCatalogReader
from competition_copilot.application.profiles import ProfileActorBinding
from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.repositories.student_memory import (
    InMemoryStudentProfileRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.infrastructure.temporal_evidence_json import (
    JsonTemporalEvidenceProvider,
)
from competition_copilot.integrations.local_runtime.plans import InMemoryPlanRegistry
from competition_copilot.repositories.student import (
    ProfileError,
    StudentProfileSnapshot,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
QUERY = dict(student_id="student", competition_id="comap-mcm", edition_id="comap-mcm-2027")


def reader(*, level="intermediate", hours=10):
    profile = StudentProfile(id="student", weekly_available_hours=hours,
        goals=["My free-text goal"], interests=["My interest"],
        skills=[] if level is None else [dict(skill_id="mathematical-modeling", level=level)])
    profiles = InMemoryStudentProfileRepository([profile], created_at=NOW)
    repo = JsonSeedCompetitionRepository(ROOT / "data/seed")
    requirements = JsonSkillRequirementProvider(ROOT / "data/skill_requirements")
    details = CompetitionDetailReader(repo, JsonEligibilityPolicyProvider(ROOT / "data/eligibility"),
        requirements, repo, JsonTemporalEvidenceProvider(ROOT / "data/temporal_evidence/candidates.json", ROOT, repo))
    result = PlanningWorkspaceReader(profiles, InMemoryPlanRegistry(), MappedPlanInputLineageReader({}),
        details, SkillCatalogReader(requirements), ProfileActorBinding(actor_id="test", permitted_student_ids=("student",)))
    return result


def read(value, **changes):
    return value.read(PlanningWorkspaceQuery(**{**QUERY, **changes}))


def register(value, *, bind=True):
    plan = CompetitionPlan(id="read-only-plan", student_id="student", competition_id="comap-mcm",
        edition_id="comap-mcm-2027", milestones=[dict(id="manual", title="Original", dependency_ids=[])],
        created_at=NOW, updated_at=NOW)
    reference = value.plans.register(plan)
    if bind:
        value.lineage.bindings["result"] = DerivedProfileBinding(kind="CompetitionPlan", result_ref_id="result",
            input_profile_ref=value.profiles.get("student").profile_ref, plan_ref=reference,
            competition_id=plan.competition_id, edition_id=plan.edition_id)
    return plan, reference


def change(value, **fields):
    current = value.profiles.get("student")
    return value.profiles.replace(StudentProfileSnapshot.model_validate({**current.domain_profile().model_dump(), **fields}),
        expected=current.profile_ref, updated_at=NOW, actor="test")


@pytest.mark.parametrize("level,count,state", [("intermediate", 3, "recorded"), ("advanced", 3, "recorded"),
    ("beginner", 3, "recorded"), ("unknown", 1, "unknown"), (None, 1, "missing")])
def test_known_missing_unknown_are_not_gap_decisions(level, count, state):
    value = reader(level=level)
    projection = read(value)
    assert len(projection.preparation_suggestions) == count
    assert all(t.source_basis.profile_skill_state == state for t in projection.preparation_suggestions)
    assert all(t.advisory and t.profile_ref == projection.current_profile_ref for t in projection.preparation_suggestions)
    assert not any(c.type == "skill_level" for c in projection.confirmed_constraints)
    assert any("REQUIREMENT_PROFICIENCY_UNSPECIFIED" in p.reason_codes for p in projection.pending_confirmations)
    assert read(value) == projection
    assert PlanningWorkspaceProjection.model_validate_json(projection.model_dump_json()) == projection
    assert not any(word in t.description for t in projection.preparation_suggestions for word in ("必须提升", "能力不足"))


@pytest.mark.parametrize("hours", [None, 0, 7.5, 10, 168])
def test_profile_display_only_and_no_schedule_allocation(hours):
    value = reader(hours=hours)
    projection = read(value)
    assert projection.profile_context.weekly_available_hours == hours
    assert projection.profile_context.goals == ("My free-text goal",)
    tasks = projection.preparation_suggestions
    change(value, goals=["AI win prizes"], interests=["NEW TOPIC"])
    after = read(value)
    assert [t.title for t in tasks] == [t.title for t in after.preparation_suggestions]
    assert all("due_at" not in t.model_dump() and "estimated_hours" not in t.model_dump() for t in tasks)


def test_verified_constraints_and_evidence_scope_and_partial_time():
    projection = read(reader())
    assert any(c.type == "skill_identity" and c.value == "Mathematical Modeling" for c in projection.confirmed_constraints)
    assert all(c.source.verification_status.value == "verified" for c in projection.confirmed_constraints)
    assert all(c.scope == "edition" for c in projection.confirmed_constraints)
    assert any(t.kind == "VERIFIED" and t.field == "registration_end" for t in projection.time_references)
    assert any(p.type == "time" for p in projection.pending_confirmations)
    assert any(p.reason_codes == ("PARTIAL_REQUIREMENT_COVERAGE",) for p in projection.pending_confirmations)


def test_candidate_is_reference_only_and_track_does_not_inherit_requirements():
    value = reader()
    projection = read(value, competition_id="huawei-ict", edition_id="huawei-ict-2026", track_id="huawei-ict-2026-innovation")
    candidates = [t for t in projection.time_references if t.kind == "OFFICIAL_CANDIDATE"]
    assert candidates
    assert all(t.value is None and t.raw_text and t.scope == "edition" for t in candidates)
    assert not projection.preparation_suggestions
    assert not any(c.type == "skill_identity" for c in projection.confirmed_constraints)
    assert projection.plan_original_json is None


def test_no_edition_no_auto_selection_and_no_skill_name_heuristic():
    projection = read(reader(), edition_id=None)
    assert projection.target.edition_id is None and projection.target.track_id is None
    assert projection.preparation_suggestions == ()
    assert any("NOT_REQUESTED" in p.reason_codes for p in projection.pending_confirmations)


@pytest.mark.parametrize("mode", ["current", "stale", "legacy", "cross-host"])
def test_exact_plan_freshness_without_plan_mutation(mode):
    value = reader()
    plan, reference = register(value, bind=mode != "legacy")
    original = plan.model_dump_json()
    if mode == "stale":
        change(value, major="Updated")
    elif mode == "cross-host":
        value.profiles = reader().profiles
    with patch.object(BaselineCompetitionPlanBuilder, "build", side_effect=AssertionError("No P8 on read")):
        projection = read(value, plan_ref=reference)
    assert projection.plan_freshness.status == {"current": "CURRENT", "stale": "STALE", "legacy": "UNKNOWN", "cross-host": "UNKNOWN"}[mode]
    assert value.plans.resolve(reference).model_dump_json() == original
    assert projection.plan_original_json == original
    assert value.plans.revisions(plan.id) == ()
    assert PlanReference.from_plan(value.plans.resolve(reference)) == reference
    assert all(t.profile_ref == projection.current_profile_ref for t in projection.preparation_suggestions)


@pytest.mark.parametrize("change_ref", ["student_id", "target", "version", "content_digest"])
def test_mismatched_plan_reference_fails_closed(change_ref):
    value = reader()
    _, reference = register(value)
    raw = reference.model_dump(mode="json")
    raw[change_ref] = {**raw["target"], "competition_id": "wrong"} if change_ref == "target" else (
        2 if change_ref == "version" else "f" * 64 if change_ref == "content_digest" else "other")
    with pytest.raises(ProfileError):
        read(value, plan_ref=raw)


def test_missing_plan_and_unauthorized_student_fail_closed():
    value = reader()
    _, reference = register(value)
    value.plans = InMemoryPlanRegistry()
    with pytest.raises(ProfileError, match="PLAN_REFERENCE_UNAVAILABLE"):
        read(value, plan_ref=reference)
    with pytest.raises(ProfileError, match="PROFILE_EDIT_FORBIDDEN"):
        read(value, student_id="other")


def test_registry_plans_are_not_implicitly_selected():
    value = reader()
    register(value)
    result = read(value)
    assert result.plan_ref is None and result.plan_summary is None
    assert result.section_availability.plan == "NOT_SELECTED"


def test_snapshot_race_provider_failure_and_deep_immutability():
    value = reader()
    before = value.profiles.get("student").profile_ref
    original = value.details.read

    def during(query):
        change(value, major="Changed during read")
        return original(query)

    with patch.object(value.details, "read", side_effect=during):
        projection = read(value)
    assert projection.current_profile_ref == before
    assert all(t.profile_ref == before for t in projection.preparation_suggestions)
    with pytest.raises(ValidationError):
        projection.preparation_suggestions[0].source_basis.profile_ref.version = 99
    with pytest.raises(TypeError):
        projection.profile_context.goals[0] = "changed"
    with patch.object(value.details, "read", side_effect=ValueError("provider corrupt")):
        with pytest.raises(ValueError, match="provider corrupt"):
            read(value)


def test_advisory_no_raw_name_or_goals_heuristic_and_stable_sort():
    value = reader()
    projection = read(value)
    assert list(projection.preparation_suggestions) == sorted(projection.preparation_suggestions,
        key=lambda t: (t.suggested_sequence, t.task_id))
    assert len(set(t.task_id for t in projection.preparation_suggestions)) == 3
    artifact = value.details.read(CompetitionDetailQuery(**{k: v for k, v in QUERY.items() if k != "student_id"})).skill_requirements
    with pytest.raises(ValueError, match="scope mismatch"):
        value.advisory.prepare(value.profiles.get("student"), CompetitionDetailQuery(competition_id="wrong"), artifact, {})


@pytest.mark.parametrize("endpoints", ["full", "start", "end", "none"])
def test_verified_window_full_partial_and_null_preserve_endpoint_semantics(endpoints):
    value = reader()
    detail = value.details.read(CompetitionDetailQuery(**{k: v for k, v in QUERY.items() if k != "student_id"}))
    raw = detail.model_dump(mode="json")
    window = raw["selected_edition"]["competition_window"]
    if endpoints == "none":
        raw["selected_edition"]["competition_window"] = None
    elif endpoints == "start":
        window["end_at"] = None
    elif endpoints == "end":
        window["start_at"] = None
    raw["editions"] = [raw["selected_edition"] if e["id"] == QUERY["edition_id"] else e for e in raw["editions"]]
    with patch.object(value.details, "read", return_value=type(detail).model_validate(raw)):
        result = read(value)
    confirmed = {t.field for t in result.time_references if t.kind == "VERIFIED" and t.field.startswith("competition_")}
    assert confirmed == {"full": {"competition_start", "competition_end"}, "start": {"competition_start"},
                         "end": {"competition_end"}, "none": set()}[endpoints]


def test_verified_level_constraint_and_missing_coverage_do_not_recompute_gap():
    from competition_copilot.domain.skill import SkillLevel
    from competition_copilot.domain.skill_gap import (
        SkillFactRole,
        skill_fact_field,
        skill_fact_value,
    )

    value = reader()
    detail = value.details.read(CompetitionDetailQuery(**{k: v for k, v in QUERY.items() if k != "student_id"}))
    raw = detail.model_dump(mode="json")
    requirement = raw["skill_requirements"]["requirement_set"]["requirements"][0]
    requirement["required_level"] = "advanced"
    fact = {**requirement["presence_evidence"][0], "field": skill_fact_field(SkillFactRole.REQUIREMENT, "mathematical-modeling"),
            "value": skill_fact_value(SkillLevel.ADVANCED), "message": "TEST ONLY synthetic level evidence"}
    requirement["evidence"] = [fact]
    with patch.object(value.details, "read", return_value=type(detail).model_validate(raw)):
        result = read(value)
    assert any(c.type == "skill_level" and c.value == "advanced" for c in result.confirmed_constraints)
    assert len(result.preparation_suggestions) == 3
    assert not any("REQUIREMENT_PROFICIENCY_UNSPECIFIED" in p.reason_codes for p in result.pending_confirmations)
    raw["skill_requirements"]["requirement_set"].update(coverage="missing", requirements=[])
    raw["skill_requirements"]["skills"] = []
    with patch.object(value.details, "read", return_value=type(detail).model_validate(raw)):
        missing = read(value)
    assert not missing.preparation_suggestions
    assert any("REQUIREMENT_DATA_MISSING" in p.reason_codes for p in missing.pending_confirmations)


def test_ambiguous_lineage_never_selects_last_or_current_profile():
    value = reader()
    _, reference = register(value)
    newer = change(value, major="New")
    value.lineage.bindings["another"] = DerivedProfileBinding(kind="CompetitionPlan", result_ref_id="another",
        plan_ref=reference, input_profile_ref=newer.profile_ref)
    with pytest.raises(ValueError, match="Conflicting exact Plan input lineage"):
        read(value, plan_ref=reference)
