"""P7.1 synthetic contract tests: no artifacts, engines, providers or IO."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain import skill_gap
from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import Skill, SkillLevel, StudentSkill
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapContext,
    SkillGapDecision,
    SkillGapItem,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirement,
    SkillRequirementCoverage,
    SkillRequirementScope,
    SkillRequirementSet,
    SkillRequirementTarget,
    SkillRequirementType,
    requirement_presence_field,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile


def target(track_id=None):
    return SkillRequirementTarget(
        competition_id="competition-a",
        edition_id="edition-a",
        track_id=track_id,
        scope=SkillRequirementScope.TRACK if track_id else SkillRequirementScope.EDITION,
    )


def requirement(
    skill_id="skill-a", kind=SkillRequirementType.REQUIRED,
    *, level=SkillLevel.INTERMEDIATE,
):
    source = SourceMetadata(
        source_url="https://example.org/synthetic-task", source_type="manual",
        observed_at="2026-01-01T00:00:00Z", verification_status="verified",
    )
    return SkillRequirement(
        skill_id=skill_id,
        required_level=level,
        requirement_type=kind,
        presence_evidence=[Evidence(
            code="SYNTHETIC_REQUIREMENT_PRESENCE", message="Synthetic reviewed presence.",
            field=requirement_presence_field(skill_id), value=True, source=source,
        )],
        evidence=[] if level is None else [
            Evidence(
                code="SYNTHETIC_REQUIREMENT",
                message="Synthetic reviewed requirement, not a real competition fact.",
                field=skill_fact_field(SkillFactRole.REQUIREMENT, skill_id),
                value=skill_fact_value(level),
                source=SourceMetadata(
                    source_url="https://example.org/synthetic-task",
                    source_type="manual",
                    observed_at="2026-01-01T00:00:00Z",
                    verification_status="verified",
                ),
            )
        ],
    )


def requirement_set(coverage=SkillRequirementCoverage.COMPLETE, *, track_id=None):
    return SkillRequirementSet(
        target=target(track_id),
        coverage=coverage,
        coverage_note="Explicit synthetic coverage assessment, not inferred from count.",
        requirements=[] if coverage is SkillRequirementCoverage.MISSING else [requirement()],
    )


def item(status=SkillGapItemStatus.SATISFIED, *, fact=None):
    fact = fact or requirement()
    level = {
        SkillGapItemStatus.SATISFIED: SkillLevel.INTERMEDIATE,
        SkillGapItemStatus.GAP: SkillLevel.BEGINNER,
        SkillGapItemStatus.UNKNOWN: None,
    }[status]
    reason = {
        SkillGapItemStatus.SATISFIED: SkillGapReasonCode.REQUIREMENT_SATISFIED,
        SkillGapItemStatus.GAP: SkillGapReasonCode.SKILL_BELOW_REQUIREMENT,
        SkillGapItemStatus.UNKNOWN: SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,
    }[status]
    return SkillGapItem(
        requirement=fact,
        student_level=level,
        status=status,
        reason_codes=(reason,),
        student_evidence=[] if level is None else [
            Evidence(
                code="STUDENT_SKILL_FACT",
                message="Explicit synthetic student proficiency fact.",
                field=skill_fact_field(SkillFactRole.STUDENT_SKILL, fact.skill_id),
                value=skill_fact_value(level),
            )
        ],
    )


def decision(coverage, status, items):
    requirements = requirement_set(coverage)
    reasons = list(dict.fromkeys(reason for i in items for reason in i.reason_codes))
    if coverage is SkillRequirementCoverage.PARTIAL:
        reasons.append(SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE)
    if coverage is SkillRequirementCoverage.MISSING:
        reasons.append(SkillGapReasonCode.REQUIREMENT_DATA_MISSING)
    return SkillGapDecision(
        target=requirements.target,
        requirements=requirements,
        gap_status=status,
        items=items,
        reason_codes=reasons,
        audit_evidence=[Evidence(code="ANALYSIS_AUDIT", message="System assessment.")],
    )


def context(track_id=None):
    return SkillGapContext(
        student_profile=StudentProfile(
            id="student-a",
            interests=["synthetic"],
            goals=["synthetic goal"],
            skills=[StudentSkill(skill_id="skill-a", level=SkillLevel.INTERMEDIATE)],
        ),
        competition=Competition(id="competition-a", name="Synthetic Competition"),
        edition=CompetitionEdition(
            id="edition-a", competition_id="competition-a", year=2026, name="Synthetic"
        ),
        track=CompetitionTrack(id=track_id, edition_id="edition-a", name="Synthetic")
        if track_id else None,
        requirements=requirement_set(track_id=track_id),
        student_skill_evidence=item().student_evidence,
    )


@pytest.mark.parametrize("kind", list(SkillRequirementType))
def test_requirement_reuses_skill_identity_scale_and_verified_evidence(kind):
    skill = Skill(id="skill-a", name="Synthetic Skill")
    fact = requirement(skill.id, kind)
    assert fact.skill_id == skill.id
    assert fact.required_level is SkillLevel.INTERMEDIATE
    assert fact.requirement_type is kind
    assert isinstance(fact.evidence[0], Evidence)
    assert fact.evidence[0].source.source_type.value == "manual"
    assert SkillRequirement.model_validate_json(fact.model_dump_json()) == fact


@pytest.mark.parametrize("bad_id", ["", " ", 42])
def test_invalid_skill_identity_rejected(bad_id):
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(requirement().model_dump() | {"skill_id": bad_id})


@pytest.mark.parametrize("level", [SkillLevel.UNKNOWN, "expert", 0.8])
def test_unknown_or_incompatible_requirement_proficiency_rejected(level):
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(requirement().model_dump() | {"required_level": level})


def test_requirement_cannot_omit_provenance_or_use_unverified_source():
    data = requirement().model_dump()
    for evidence in ([], [Evidence(code="X", message="No source")]):
        with pytest.raises(ValidationError):
            SkillRequirement.model_validate(data | {"evidence": evidence})
    data["evidence"][0]["source"]["verification_status"] = "pending"
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(data)


@pytest.mark.parametrize("track_id", [None, "track-a"])
def test_exact_scope_target_and_context_are_valid(track_id):
    ctx = context(track_id)
    assert ctx.requirements.target.track_id == track_id
    assert SkillGapContext.model_validate_json(ctx.model_dump_json()) == ctx


@pytest.mark.parametrize("invalid", [
    {"scope": "track"},
    {"scope": "edition", "track_id": "track-a"},
    {"scope": "competition"},
    {"competition_id": " "},
    {"edition_id": ""},
    {"track_id": " "},
])
def test_invalid_scope_or_identity_rejected(invalid):
    with pytest.raises(ValidationError):
        SkillRequirementTarget.model_validate(target().model_dump() | invalid)


def test_context_rejects_cross_targets_without_requirement_inheritance():
    ctx = context("track-a")
    base = ctx.model_dump()
    bad_edition = base["edition"] | {"competition_id": "competition-b"}
    bad_track = base["track"] | {"edition_id": "edition-b"}
    bad_set = base["requirements"] | {"target": target("track-b").model_dump()}
    for invalid in (
        {"edition": bad_edition}, {"track": bad_track}, {"requirements": bad_set},
        {"requirements": requirement_set().model_dump()},
    ):
        with pytest.raises(ValidationError):
            SkillGapContext.model_validate(base | invalid)


def test_coverage_is_explicit_not_derived_from_count():
    complete = requirement_set()
    partial = requirement_set(SkillRequirementCoverage.PARTIAL)
    assert complete.requirements == partial.requirements
    assert complete.coverage is SkillRequirementCoverage.COMPLETE
    assert partial.coverage is SkillRequirementCoverage.PARTIAL
    for invalid in ({"coverage_note": " "}, {"coverage": None}):
        with pytest.raises(ValidationError):
            SkillRequirementSet.model_validate(complete.model_dump() | invalid)


@pytest.mark.parametrize("coverage", list(SkillRequirementCoverage))
def test_empty_requirement_data_is_missing_only(coverage):
    if coverage is SkillRequirementCoverage.MISSING:
        assert requirement_set(coverage).requirements == ()
    else:
        with pytest.raises(ValidationError):
            SkillRequirementSet.model_validate(requirement_set().model_dump() | {
                "coverage": coverage, "requirements": [],
            })
    with pytest.raises(ValidationError):
        SkillRequirementSet.model_validate(requirement_set().model_dump() | {
            "coverage": "missing",
        })


@pytest.mark.parametrize("alteration", [
    {}, {"required_level": "advanced"}, {"requirement_type": "desired"},
])
def test_duplicate_or_conflicting_skill_requirement_rejected(alteration):
    data = requirement_set().model_dump()
    second = requirement().model_dump() | alteration
    second["evidence"][0]["value"] = skill_fact_value(
        SkillLevel(second["required_level"])
    )
    data["requirements"] = [
        requirement().model_dump(), second,
    ]
    with pytest.raises(ValidationError, match="duplicate"):
        SkillRequirementSet.model_validate(data)


@pytest.mark.parametrize("status", list(SkillGapItemStatus))
def test_gap_items_have_distinct_status_reason_and_separate_audit(status):
    result = item(status)
    assert result.status is status
    assert result.requirement.evidence[0].source is not None
    if status is SkillGapItemStatus.UNKNOWN:
        assert result.student_level is None and result.student_evidence == ()
        assert "gap_value" not in result.model_dump()
    else:
        assert result.student_evidence[0].source is None
        assert result.student_evidence[0].value == result.student_level.value
    assert SkillGapItem.model_validate_json(result.model_dump_json()) == result


def test_explicit_unknown_level_stays_unknown_without_zero_assumption():
    unknown = SkillGapItem.model_validate(item(SkillGapItemStatus.UNKNOWN).model_dump() | {
        "student_level": SkillLevel.UNKNOWN,
    })
    assert unknown.status is SkillGapItemStatus.UNKNOWN
    assert unknown.student_level is SkillLevel.UNKNOWN


@pytest.mark.parametrize("status, invalid", [
    (SkillGapItemStatus.SATISFIED, {"student_level": "beginner"}),
    (SkillGapItemStatus.GAP, {"student_level": "advanced"}),
    (SkillGapItemStatus.GAP, {"student_level": "intermediate"}),
    (SkillGapItemStatus.UNKNOWN, {"student_level": "beginner"}),
    (SkillGapItemStatus.SATISFIED, {"student_level": None}),
    (SkillGapItemStatus.GAP, {"student_level": "unknown"}),
    (SkillGapItemStatus.SATISFIED, {"student_evidence": []}),
    (SkillGapItemStatus.GAP, {"reason_codes": ["REQUIREMENT_SATISFIED"]}),
])
def test_contradictory_item_snapshots_rejected(status, invalid):
    with pytest.raises(ValidationError):
        SkillGapItem.model_validate(item(status).model_dump() | invalid)


def test_higher_student_level_is_known_satisfied():
    result = SkillGapItem.model_validate(item().model_dump() | {
        "student_level": SkillLevel.ADVANCED,
        "student_evidence": [Evidence(
            code="STUDENT_SKILL_FACT", message="Known advanced level.",
            field=skill_fact_field(SkillFactRole.STUDENT_SKILL, "skill-a"),
            value=skill_fact_value(SkillLevel.ADVANCED),
        )],
    })
    assert result.status is SkillGapItemStatus.SATISFIED


@pytest.mark.parametrize("coverage, status, item_status", [
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.NO_GAP, SkillGapItemStatus.SATISFIED),
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.GAP_IDENTIFIED, SkillGapItemStatus.GAP),
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.UNDETERMINED, SkillGapItemStatus.UNKNOWN),
    (SkillRequirementCoverage.PARTIAL, SkillGapStatus.GAP_IDENTIFIED, SkillGapItemStatus.GAP),
    (SkillRequirementCoverage.PARTIAL, SkillGapStatus.UNDETERMINED, SkillGapItemStatus.SATISFIED),
    (SkillRequirementCoverage.PARTIAL, SkillGapStatus.UNDETERMINED, SkillGapItemStatus.UNKNOWN),
    (SkillRequirementCoverage.MISSING, SkillGapStatus.UNDETERMINED, None),
])
def test_valid_decision_coverage_and_gap_existence_are_separate(coverage, status, item_status):
    result = decision(coverage, status, [item(item_status)] if item_status else [])
    assert result.gap_status is status
    assert result.requirements.coverage is coverage
    assert result.model_dump(mode="json") == json.loads(result.model_dump_json())
    assert SkillGapDecision.model_validate_json(result.model_dump_json()) == result
    assert decision(coverage, status, [item(item_status)] if item_status else []).model_dump_json() == result.model_dump_json()


@pytest.mark.parametrize("coverage, status, item_status", [
    (SkillRequirementCoverage.PARTIAL, SkillGapStatus.NO_GAP, SkillGapItemStatus.SATISFIED),
    (SkillRequirementCoverage.MISSING, SkillGapStatus.NO_GAP, None),
    (SkillRequirementCoverage.MISSING, SkillGapStatus.GAP_IDENTIFIED, None),
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.NO_GAP, SkillGapItemStatus.UNKNOWN),
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.NO_GAP, SkillGapItemStatus.GAP),
    (SkillRequirementCoverage.COMPLETE, SkillGapStatus.GAP_IDENTIFIED, SkillGapItemStatus.SATISFIED),
    (SkillRequirementCoverage.PARTIAL, SkillGapStatus.UNDETERMINED, SkillGapItemStatus.GAP),
])
def test_unsafe_decision_claims_rejected(coverage, status, item_status):
    with pytest.raises(ValidationError):
        decision(coverage, status, [item(item_status)] if item_status else [])


def test_required_and_desired_gaps_preserve_type_without_eligibility_status():
    desired = requirement("skill-b", SkillRequirementType.DESIRED)
    requirements = SkillRequirementSet.model_validate(requirement_set().model_dump() | {
        "requirements": [requirement(), desired],
    })
    result = SkillGapDecision(
        target=requirements.target, requirements=requirements,
        gap_status=SkillGapStatus.GAP_IDENTIFIED,
        items=[item(), item(SkillGapItemStatus.GAP, fact=desired)],
        reason_codes=["REQUIREMENT_SATISFIED", "SKILL_BELOW_REQUIREMENT"],
        audit_evidence=[Evidence(code="AUDIT", message="Synthetic system audit")],
    )
    assert result.items[1].requirement.requirement_type is SkillRequirementType.DESIRED
    assert "eligibility" not in result.model_dump_json()


def test_decision_requires_matching_target_items_and_audit():
    result = decision(SkillRequirementCoverage.COMPLETE, SkillGapStatus.NO_GAP, [item()])
    data = result.model_dump()
    for invalid in (
        {"target": target("other").model_dump()},
        {"items": []}, {"items": [item(), item()]},
        {"items": [item(fact=requirement("other"))]},
        {"items": [item(fact=requirement(kind=SkillRequirementType.DESIRED))]},
        {"reason_codes": []}, {"reason_codes": ["STUDENT_SKILL_DATA_MISSING"]},
        {"reason_codes": ["REQUIREMENT_SATISFIED", "SKILL_BELOW_REQUIREMENT"]},
        {"reason_codes": ["REQUIREMENT_SATISFIED", "REQUIREMENT_SATISFIED"]},
        {"audit_evidence": []}, {"audit_evidence": requirement().evidence},
    ):
        with pytest.raises(ValidationError):
            SkillGapDecision.model_validate(data | invalid)
    partial = decision(
        SkillRequirementCoverage.PARTIAL, SkillGapStatus.UNDETERMINED, [item()],
    )
    with pytest.raises(ValidationError):
        SkillGapDecision.model_validate(partial.model_dump() | {
            "reason_codes": ["REQUIREMENT_SATISFIED"],
        })


@pytest.mark.parametrize("coverage", ["complete", "partial"])
def test_known_required_gap_survives_other_unknown_student_skills(coverage):
    requirements = SkillRequirementSet.model_validate(requirement_set().model_dump() | {
        "coverage": coverage,
        "requirements": [requirement(), requirement("skill-b")],
    })
    reasons = ["SKILL_BELOW_REQUIREMENT", "STUDENT_SKILL_DATA_MISSING"]
    if coverage == "partial":
        reasons.append("PARTIAL_REQUIREMENT_COVERAGE")
    result = SkillGapDecision(
        target=target(), requirements=requirements,
        gap_status=SkillGapStatus.GAP_IDENTIFIED,
        items=[
            item(SkillGapItemStatus.GAP),
            item(SkillGapItemStatus.UNKNOWN, fact=requirement("skill-b")),
        ],
        reason_codes=reasons,
        audit_evidence=[Evidence(code="ANALYSIS", message="Incomplete student facts")],
    )
    assert result.items[1].student_level is None
    assert result.requirements.coverage.value == coverage


@pytest.mark.parametrize("required, student, status", [
    ("beginner", "beginner", "satisfied"),
    ("beginner", "intermediate", "satisfied"),
    ("beginner", "advanced", "satisfied"),
    ("intermediate", "beginner", "gap"),
    ("intermediate", "intermediate", "satisfied"),
    ("intermediate", "advanced", "satisfied"),
    ("advanced", "beginner", "gap"),
    ("advanced", "intermediate", "gap"),
    ("advanced", "advanced", "satisfied"),
])
def test_ordinal_proficiency_snapshot_compatibility(required, student, status):
    data = item(SkillGapItemStatus(status)).model_dump()
    data["requirement"]["required_level"] = required
    data["requirement"]["evidence"][0]["value"] = required
    data["student_level"] = student
    data["student_evidence"][0]["value"] = student
    result = SkillGapItem.model_validate(data)
    assert result.status.value == status


def test_all_snapshots_collections_and_nested_inputs_are_immutable_detached():
    original_profile = StudentProfile(id="s", skills=[StudentSkill(skill_id="skill-a")])
    source_fact = requirement().model_dump()
    original_evidence = Evidence.model_validate(source_fact["evidence"][0])
    fact = SkillRequirement.model_validate(source_fact | {"evidence": [original_evidence]})
    requirements = SkillRequirementSet.model_validate(requirement_set().model_dump() | {
        "requirements": [fact],
    })
    ctx = SkillGapContext.model_validate(context().model_dump() | {
        "student_profile": original_profile, "requirements": requirements,
        "student_skill_evidence": [],
    })
    result = decision(SkillRequirementCoverage.COMPLETE, SkillGapStatus.NO_GAP, [item()])
    before = ctx.model_dump_json(), result.model_dump_json(), fact.model_dump_json()
    original_profile.skills[0].level = SkillLevel.ADVANCED
    original_profile.skills.clear()
    original_evidence.message = "External mutation"
    for model, field, value in (
        (fact, "required_level", SkillLevel.ADVANCED),
        (requirements, "coverage", SkillRequirementCoverage.MISSING),
        (requirements.target, "edition_id", "other"),
        (ctx, "edition", context().edition),
        (ctx.edition, "competition_id", "other"),
        (ctx.competition, "id", "other"),
        (ctx.student_profile.skills[0], "level", SkillLevel.ADVANCED),
        (result, "gap_status", SkillGapStatus.GAP_IDENTIFIED),
        (result.items[0], "status", SkillGapItemStatus.GAP),
        (result.items[0].student_evidence[0], "value", "beginner"),
        (fact.evidence[0], "message", "Changed audit"),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, value)
    for collection in (
        requirements.requirements, fact.evidence, result.items,
        result.reason_codes, result.audit_evidence, ctx.student_profile.skills,
        ctx.student_profile.goals, ctx.student_profile.interests,
    ):
        with pytest.raises(AttributeError):
            collection.append(None)
        if collection:
            with pytest.raises(TypeError):
                collection[0] = None
    with pytest.raises(TypeError):
        result.model_copy(update={"gap_status": "gap_identified"})
    assert (ctx.model_dump_json(), result.model_dump_json(), fact.model_dump_json()) == before
    assert result.model_copy() == result


def test_pure_domain_dependency_boundary_and_no_engine_or_bypass():
    tree = ast.parse(inspect.getsource(skill_gap))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    prohibited = (
        "repositories", "infrastructure", "tools", "ingestion", "eligibility",
        "recommendation", "resource", "pathlib", "requests", "httpx", "openai",
    )
    assert all(not any(p in name for p in prohibited) for name in imports if name)
    assert not any(isinstance(n, ast.Import) for n in ast.walk(tree))
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in ("model_construct", "__setattr__")
        for n in ast.walk(tree)
    )
    assert not any(
        isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in (
            "SkillGapEngine", "compute_gap", "compare_skills", "aggregate_gap",
        ) for n in ast.walk(tree)
    )


def test_requirement_fact_cannot_be_used_as_student_fact_even_at_equal_level():
    data = item().model_dump()
    data["student_evidence"] = requirement().evidence
    with pytest.raises(ValidationError, match="fact role or skill identity"):
        SkillGapItem.model_validate(data)


def test_student_fact_cannot_be_used_as_requirement_fact_even_with_verified_source():
    data = requirement().model_dump()
    # Same skill, same level and verified source: only the role is wrong.
    data["evidence"][0]["field"] = skill_fact_field(
        SkillFactRole.STUDENT_SKILL, "skill-a"
    )
    with pytest.raises(ValidationError, match="fact role or skill identity"):
        SkillRequirement.model_validate(data)


@pytest.mark.parametrize("kind", ["requirement", "student"])
@pytest.mark.parametrize("bad_field", [
    "requirements.skill-a.required_level", "skills.skill-a.level",
    "requirements.required_level", "skills.skill-b.proficiency", None,
])
def test_wrong_role_skill_or_field_with_correct_value_rejected(kind, bad_field):
    fact = requirement("skill-b")
    if kind == "requirement":
        data = fact.model_dump()
        data["evidence"][0]["field"] = bad_field
        model = SkillRequirement
    else:
        data = item(fact=fact).model_dump()
        data["student_evidence"][0]["field"] = bad_field
        model = SkillGapItem
    with pytest.raises(ValidationError, match="fact role or skill identity"):
        model.model_validate(data)


@pytest.mark.parametrize("kind", ["requirement", "student"])
@pytest.mark.parametrize("bad_value", ["beginner", "INTERMEDIATE", "unknown", 0, None])
def test_correct_role_and_skill_with_wrong_level_value_rejected(kind, bad_value):
    fact = requirement("skill-b")
    if kind == "requirement":
        data = fact.model_dump()
        data["evidence"][0]["value"] = bad_value
        model = SkillRequirement
    else:
        data = item(fact=fact).model_dump()
        data["student_evidence"][0]["value"] = bad_value
        model = SkillGapItem
    with pytest.raises(ValidationError, match="fact value"):
        model.model_validate(data)


@pytest.mark.parametrize("skill_id", ["skill-b", "python", "data.science", "数学"])
@pytest.mark.parametrize("required, status", [
    (SkillLevel.BEGINNER, SkillGapItemStatus.SATISFIED),
    (SkillLevel.ADVANCED, SkillGapItemStatus.GAP),
    (SkillLevel.INTERMEDIATE, SkillGapItemStatus.UNKNOWN),
])
def test_correct_fact_binding_is_dynamic_and_serializable(skill_id, required, status):
    result = item(status, fact=requirement(skill_id, level=required))
    assert result.requirement.evidence[0].field == (
        f"requirements.{skill_id}.required_level"
    )
    assert result.requirement.evidence[0].value == required.value
    if status is SkillGapItemStatus.UNKNOWN:
        assert result.student_level is None and not result.student_evidence
    else:
        assert result.student_evidence[0].field == f"skills.{skill_id}.level"
        assert result.student_evidence[0].value == result.student_level.value
        assert result.requirement.evidence[0].field != result.student_evidence[0].field
    assert result.model_dump(mode="json") == json.loads(result.model_dump_json())
    assert SkillGapItem.model_validate_json(result.model_dump_json()) == result


def test_skill_b_requirement_and_student_levels_bind_to_different_facts():
    result = item(SkillGapItemStatus.GAP, fact=requirement("skill-b"))
    assert result.requirement.evidence[0].field == "requirements.skill-b.required_level"
    assert result.requirement.evidence[0].value == "intermediate"
    assert result.student_evidence[0].field == "skills.skill-b.level"
    assert result.student_evidence[0].value == "beginner"


def test_known_student_level_without_fact_evidence_rejected():
    with pytest.raises(ValidationError, match="needs student evidence"):
        SkillGapItem.model_validate(item().model_dump() | {"student_evidence": []})


@pytest.mark.parametrize("level", [None, SkillLevel.UNKNOWN])
def test_unknown_student_has_no_fabricated_known_level_fact(level):
    data = item(SkillGapItemStatus.UNKNOWN, fact=requirement("skill-b")).model_dump()
    data["student_level"] = level
    result = SkillGapItem.model_validate(data)
    assert not result.student_evidence
    with pytest.raises(ValidationError, match="must not carry known-level evidence"):
        SkillGapItem.model_validate(data | {
            "student_evidence": item(fact=requirement("skill-b")).student_evidence,
        })


@pytest.mark.parametrize("kind", ["requirement", "student"])
def test_valid_fact_does_not_hide_an_additional_invalid_fact(kind):
    if kind == "requirement":
        data = requirement("skill-b").model_dump()
        facts = list(data["evidence"])
        facts.append(requirement("skill-a").model_dump()["evidence"][0])
        data["evidence"] = facts
        model = SkillRequirement
    else:
        data = item(fact=requirement("skill-b")).model_dump()
        facts = list(data["student_evidence"])
        facts.append(item().model_dump()["student_evidence"][0])
        data["student_evidence"] = facts
        model = SkillGapItem
    with pytest.raises(ValidationError, match="fact role or skill identity"):
        model.model_validate(data)


def test_canonical_binding_does_not_replace_requirement_source_verification():
    data = requirement("skill-b").model_dump()
    for invalid_source in (None, data["evidence"][0]["source"] | {
        "verification_status": "pending",
    }):
        invalid = data | {"evidence": [data["evidence"][0] | {"source": invalid_source}]}
        with pytest.raises(ValidationError, match="verified source evidence"):
            SkillRequirement.model_validate(invalid)


def test_fact_bindings_are_immutable_and_cannot_be_copy_updated():
    result = item(fact=requirement("skill-b"))
    before = result.model_dump_json()
    for fact in (result.requirement.evidence[0], result.student_evidence[0]):
        for field, value in (
            ("field", "skills.skill-a.level"), ("value", "advanced"),
        ):
            with pytest.raises(ValidationError, match="frozen"):
                setattr(fact, field, value)
        with pytest.raises(TypeError, match="new validated snapshot"):
            fact.model_copy(update={"value": "advanced"})
    assert result.model_dump_json() == before


@pytest.mark.parametrize("level", [SkillLevel.UNKNOWN, "intermediate", None])
def test_canonical_value_requires_known_typed_level(level):
    with pytest.raises(ValueError, match="known SkillLevel"):
        skill_fact_value(level)


def test_context_known_skill_evidence_roundtrip_and_output_reuse():
    ctx = context()
    assert ctx.student_skill_evidence == item().student_evidence
    result = SkillGapItem(
        requirement=ctx.requirements.requirements[0],
        student_level=ctx.student_profile.skills[0].level,
        status=SkillGapItemStatus.SATISFIED,
        reason_codes=(SkillGapReasonCode.REQUIREMENT_SATISFIED,),
        student_evidence=ctx.student_skill_evidence,
    )
    assert result.student_evidence == ctx.student_skill_evidence
    assert ctx.model_dump(mode="json") == json.loads(ctx.model_dump_json())
    assert SkillGapContext.model_validate_json(ctx.model_dump_json()) == ctx


def test_context_known_relevant_skill_without_evidence_rejected():
    with pytest.raises(ValidationError, match="needs student evidence"):
        SkillGapContext.model_validate(context().model_dump() | {
            "student_skill_evidence": [],
        })


@pytest.mark.parametrize("bad_fact", [
    {"field": "requirements.skill-a.required_level"},
    {"field": "skills.skill-b.level"},
    {"field": None},
    {"value": "beginner"},
    {"value": "INTERMEDIATE"},
    {"value": None},
])
def test_context_rejects_wrong_role_skill_or_level(bad_fact):
    data = context().model_dump()
    data["student_skill_evidence"][0].update(bad_fact)
    with pytest.raises(ValidationError):
        SkillGapContext.model_validate(data)


@pytest.mark.parametrize("skills", [[], [StudentSkill(skill_id="skill-a")]])
def test_context_missing_or_unknown_student_skill_needs_no_fake_evidence(skills):
    data = context().model_dump() | {
        "student_profile": StudentProfile(id="student-a", skills=skills),
        "student_skill_evidence": [],
    }
    ctx = SkillGapContext.model_validate(data)
    assert not ctx.student_skill_evidence
    with pytest.raises(ValidationError):
        SkillGapContext.model_validate(data | {
            "student_skill_evidence": item().student_evidence,
        })


@pytest.mark.parametrize("include_extra_evidence", [False, True])
def test_context_irrelevant_skill_evidence_is_optional_but_validated(include_extra_evidence):
    data = context().model_dump()
    data["student_profile"]["skills"] += (
        StudentSkill(skill_id="skill-b", level=SkillLevel.INTERMEDIATE).model_dump(),
    )
    extra = item(fact=requirement("skill-b")).student_evidence
    if include_extra_evidence:
        data["student_skill_evidence"] += tuple(e.model_dump() for e in extra)
    ctx = SkillGapContext.model_validate(data)
    assert len(ctx.student_skill_evidence) == 1 + include_extra_evidence
    if include_extra_evidence:
        data["student_skill_evidence"][-1]["value"] = "advanced"
        with pytest.raises(ValidationError, match="fact value"):
            SkillGapContext.model_validate(data)


def test_context_multiple_matching_sources_preserved_conflict_rejected():
    data = context().model_dump()
    second = data["student_skill_evidence"][0] | {
        "code": "SECOND_STUDENT_SOURCE",
        "source": requirement().evidence[0].source.model_dump(),
    }
    data["student_skill_evidence"] += (second,)
    ctx = SkillGapContext.model_validate(data)
    assert len(ctx.student_skill_evidence) == 2
    assert ctx.student_skill_evidence[1].source is not None
    second["value"] = "beginner"
    with pytest.raises(ValidationError, match="fact value"):
        SkillGapContext.model_validate(data)


def test_context_student_evidence_snapshot_is_detached_and_immutable():
    original = Evidence.model_validate(item().student_evidence[0].model_dump())
    supplied = [original]
    ctx = SkillGapContext.model_validate(context().model_dump() | {
        "student_skill_evidence": supplied,
    })
    before = ctx.model_dump_json()
    original.value = "beginner"
    supplied.clear()
    with pytest.raises(ValidationError, match="frozen"):
        ctx.student_skill_evidence[0].field = "skills.other.level"
    with pytest.raises(ValidationError, match="frozen"):
        ctx.student_skill_evidence = ()
    with pytest.raises(AttributeError):
        ctx.student_skill_evidence.append(None)
    with pytest.raises(TypeError):
        ctx.student_skill_evidence[0] = None
    assert ctx.model_dump_json() == before


@pytest.mark.parametrize("skill_id", ["skill-b", "data.science", "数学"])
def test_context_student_fact_binding_uses_exact_dynamic_skill_identity(skill_id):
    data = context().model_dump() | {
        "student_profile": StudentProfile(id="s", skills=[
            StudentSkill(skill_id=skill_id, level=SkillLevel.INTERMEDIATE),
        ]),
        "requirements": SkillRequirementSet(
            target=target(), coverage=SkillRequirementCoverage.COMPLETE,
            coverage_note="Synthetic coverage.", requirements=[requirement(skill_id)],
        ),
        "student_skill_evidence": item(fact=requirement(skill_id)).student_evidence,
    }
    ctx = SkillGapContext.model_validate(data)
    assert ctx.student_skill_evidence[0].field == f"skills.{skill_id}.level"
    with pytest.raises(ValidationError):
        SkillGapContext.model_validate(data | {
            "student_skill_evidence": item().student_evidence,
        })


@pytest.mark.parametrize("kind", list(SkillRequirementType))
@pytest.mark.parametrize("level", [None, SkillLevel.INTERMEDIATE])
def test_presence_and_threshold_are_independent_validated_channels(kind, level):
    fact = requirement("skill-b", kind, level=level)
    assert fact.required_level is level
    assert fact.presence_evidence[0].field == "requirements.skill-b.present"
    assert fact.presence_evidence[0].value is True
    assert bool(fact.evidence) == (level is not None)
    assert SkillRequirement.model_validate_json(fact.model_dump_json()) == fact
    if level is None:
        assert fact.model_dump(mode="json")["required_level"] is None
        requirements = SkillRequirementSet(
            target=target(), coverage=SkillRequirementCoverage.COMPLETE,
            coverage_note="Synthetic complete requirement set; no threshold specified.",
            requirements=(fact,),
        )
        assert requirements.coverage is SkillRequirementCoverage.COMPLETE


@pytest.mark.parametrize("level", [None, SkillLevel.INTERMEDIATE])
def test_requirement_presence_is_always_mandatory(level):
    data = requirement(level=level).model_dump()
    for invalid in ({"presence_evidence": []}, {"presence_evidence": requirement().evidence}):
        with pytest.raises(ValidationError):
            SkillRequirement.model_validate(data | invalid)
    del data["presence_evidence"]
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(data)


@pytest.mark.parametrize("field, value", [
    ("field", "requirements.other.present"), ("field", "skills.skill-a.level"),
    ("value", False), ("value", 1), ("value", "true"), ("value", None),
    ("source", None),
])
def test_presence_fact_rejects_wrong_role_skill_value_or_provenance(field, value):
    data = requirement(level=None).model_dump()
    data["presence_evidence"][0][field] = value
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(data)


@pytest.mark.parametrize("value", [None, "unknown", "intermediate"])
def test_unspecified_threshold_rejects_any_level_evidence(value):
    data = requirement(level=None).model_dump()
    data["evidence"] = [requirement().evidence[0].model_dump() | {"value": value}]
    with pytest.raises(ValidationError, match="must not carry level evidence"):
        SkillRequirement.model_validate(data)


def test_specified_threshold_still_requires_exact_level_evidence():
    data = requirement().model_dump()
    with pytest.raises(ValidationError, match="needs level evidence"):
        SkillRequirement.model_validate(data | {"evidence": []})
    with pytest.raises(ValidationError, match="fact role or skill identity"):
        SkillRequirement.model_validate(data | {"evidence": requirement().presence_evidence})


def unspecified_item(student_level=None):
    reasons = (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,)
    if student_level in (None, SkillLevel.UNKNOWN):
        reasons += (SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,)
        evidence = ()
    else:
        evidence = (Evidence(
            code="SYNTHETIC_STUDENT", message="Explicit synthetic student fact.",
            field=skill_fact_field(SkillFactRole.STUDENT_SKILL, "skill-b"),
            value=skill_fact_value(student_level),
        ),)
    return SkillGapItem(
        requirement=requirement("skill-b", level=None), student_level=student_level,
        status=SkillGapItemStatus.UNKNOWN, reason_codes=reasons, student_evidence=evidence,
    )


@pytest.mark.parametrize("student_level", [None, SkillLevel.UNKNOWN, SkillLevel.ADVANCED])
def test_unspecified_threshold_keeps_student_facts_and_all_uncertainty(student_level):
    result = unspecified_item(student_level)
    assert result.student_level is student_level
    assert result.status is SkillGapItemStatus.UNKNOWN
    assert result.reason_codes[0] is SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED
    assert len(result.reason_codes) == (2 if student_level in (None, SkillLevel.UNKNOWN) else 1)
    assert bool(result.student_evidence) == (student_level is SkillLevel.ADVANCED)
    assert SkillGapItem.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        SkillGapItem.model_validate(result.model_dump() | {"status": "satisfied"})
    if student_level is SkillLevel.ADVANCED:
        with pytest.raises(ValidationError, match="needs student evidence"):
            SkillGapItem.model_validate(result.model_dump() | {"student_evidence": []})


@pytest.mark.parametrize("reasons", [
    [], ["STUDENT_SKILL_DATA_MISSING"], ["REQUIREMENT_PROFICIENCY_UNSPECIFIED"],
    ["STUDENT_SKILL_DATA_MISSING", "REQUIREMENT_PROFICIENCY_UNSPECIFIED"],
    ["REQUIREMENT_PROFICIENCY_UNSPECIFIED", "STUDENT_SKILL_DATA_MISSING", "STUDENT_SKILL_DATA_MISSING"],
    ["REQUIREMENT_SATISFIED"],
])
def test_item_uncertainty_reasons_are_exact_unique_and_canonically_ordered(reasons):
    with pytest.raises(ValidationError):
        SkillGapItem.model_validate(unspecified_item().model_dump() | {"reason_codes": reasons})


def test_unspecified_presence_and_reason_collections_are_immutable():
    result = unspecified_item(SkillLevel.ADVANCED)
    before = result.model_dump_json()
    for collection in (result.reason_codes, result.requirement.presence_evidence, result.requirement.evidence):
        with pytest.raises(AttributeError):
            collection.append(None)
        if collection:
            with pytest.raises(TypeError):
                collection[0] = None
    with pytest.raises(ValidationError, match="frozen"):
        result.requirement.presence_evidence[0].value = False
    assert result.model_dump_json() == before


def test_complete_unspecified_threshold_cannot_claim_no_gap_or_drop_reason():
    gap_item = unspecified_item(SkillLevel.ADVANCED)
    requirements = SkillRequirementSet(
        target=target(), coverage="complete", coverage_note="Synthetic complete set.",
        requirements=(gap_item.requirement,),
    )
    data = dict(
        target=target(), requirements=requirements, gap_status="undetermined", items=(gap_item,),
        reason_codes=gap_item.reason_codes,
        audit_evidence=(Evidence(code="AUDIT", message="Synthetic analysis."),),
    )
    result = SkillGapDecision(**data)
    assert result.requirements.coverage is SkillRequirementCoverage.COMPLETE
    with pytest.raises(ValidationError, match="NO_GAP"):
        SkillGapDecision(**(data | {"gap_status": "no_gap"}))
    with pytest.raises(ValidationError):
        SkillGapDecision(**(data | {"reason_codes": (SkillGapReasonCode.REQUIREMENT_SATISFIED,)}))


def test_unspecified_is_explicit_null_not_unknown_enum_or_omitted_field():
    data = requirement(level=None).model_dump()
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(data | {"required_level": SkillLevel.UNKNOWN})
    del data["required_level"]
    with pytest.raises(ValidationError):
        SkillRequirement.model_validate(data)


def test_pending_presence_source_cannot_assert_known_requirement():
    data = requirement(level=None).model_dump()
    data["presence_evidence"][0]["source"]["verification_status"] = "pending"
    with pytest.raises(ValidationError, match="verified"):
        SkillRequirement.model_validate(data)
