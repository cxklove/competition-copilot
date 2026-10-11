"""P7.2 synthetic acceptance tests; no repository, provider or artifact access."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain import skill_gap_engine
from competition_copilot.domain.competition import Competition, CompetitionEdition
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import SkillLevel, StudentSkill
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapContext,
    SkillGapDecision,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirement,
    SkillRequirementCoverage,
    SkillRequirementSet,
    SkillRequirementTarget,
    SkillRequirementType,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.skill_gap_engine import LEVEL_ORDER, SkillGapEngine
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile


def make_context(rows, coverage=SkillRequirementCoverage.COMPLETE):
    """Rows are exact (skill_id, required level, student level or None, type)."""
    source = SourceMetadata(
        source_url="https://example.org/test-only-requirements",
        source_type="manual", observed_at="2026-01-01T00:00:00Z",
        verification_status="verified",
    )
    requirements, skills, student_evidence = [], [], []
    for skill_id, required, student, kind in rows:
        requirements.append(SkillRequirement(
            skill_id=skill_id, required_level=required, requirement_type=kind,
            evidence=[Evidence(
                code="SYNTHETIC_REQUIREMENT", message="Test-only reviewed skill fact.",
                field=skill_fact_field(SkillFactRole.REQUIREMENT, skill_id),
                value=skill_fact_value(required), source=source,
            )],
        ))
        if student is not None:
            skills.append(StudentSkill(skill_id=skill_id, level=student))
            if student is not SkillLevel.UNKNOWN:
                student_evidence.append(Evidence(
                    code="SYNTHETIC_STUDENT_FACT", message="Test-only supplied student fact.",
                    field=skill_fact_field(SkillFactRole.STUDENT_SKILL, skill_id),
                    value=skill_fact_value(student),
                ))
    return SkillGapContext(
        competition=Competition(id="c", name="Unrelated display name"),
        edition=CompetitionEdition(id="e", competition_id="c", name="Synthetic", year=2026),
        student_profile=StudentProfile(id="s", skills=skills),
        requirements=SkillRequirementSet(
            target=SkillRequirementTarget(competition_id="c", edition_id="e", scope="edition"),
            coverage=coverage, coverage_note="Explicit synthetic coverage assessment.",
            requirements=requirements,
        ),
        student_skill_evidence=student_evidence,
    )


BEGINNER = SkillLevel.BEGINNER
INTERMEDIATE = SkillLevel.INTERMEDIATE
ADVANCED = SkillLevel.ADVANCED
REQUIRED = SkillRequirementType.REQUIRED
DESIRED = SkillRequirementType.DESIRED


@pytest.mark.parametrize("required, student, expected", [
    (BEGINNER, BEGINNER, "satisfied"), (BEGINNER, INTERMEDIATE, "satisfied"), (BEGINNER, ADVANCED, "satisfied"),
    (INTERMEDIATE, BEGINNER, "gap"), (INTERMEDIATE, INTERMEDIATE, "satisfied"), (INTERMEDIATE, ADVANCED, "satisfied"),
    (ADVANCED, BEGINNER, "gap"), (ADVANCED, INTERMEDIATE, "gap"), (ADVANCED, ADVANCED, "satisfied"),
])
def test_all_known_ordinal_pairs_and_fact_preservation(required, student, expected):
    ctx = make_context([("data.science", required, student, REQUIRED)])
    result = SkillGapEngine().evaluate(ctx)
    item = result.items[0]
    assert item.status.value == expected
    assert item.student_level is student
    assert item.requirement == ctx.requirements.requirements[0]
    assert item.requirement.evidence == ctx.requirements.requirements[0].evidence
    assert item.student_evidence == ctx.student_skill_evidence
    assert item.reason_code is (
        SkillGapReasonCode.REQUIREMENT_SATISFIED if expected == "satisfied"
        else SkillGapReasonCode.SKILL_BELOW_REQUIREMENT
    )


def test_level_order_is_explicit_exhaustive_and_immutable():
    assert set(LEVEL_ORDER) == set(SkillLevel)
    assert LEVEL_ORDER[SkillLevel.UNKNOWN] is None
    assert LEVEL_ORDER[BEGINNER] < LEVEL_ORDER[INTERMEDIATE] < LEVEL_ORDER[ADVANCED]
    with pytest.raises(TypeError):
        LEVEL_ORDER[BEGINNER] = 9


@pytest.mark.parametrize("student", [None, SkillLevel.UNKNOWN])
def test_missing_or_unknown_student_is_not_lowest_known_level(student):
    result = SkillGapEngine().evaluate(make_context([("python", BEGINNER, student, REQUIRED)]))
    item = result.items[0]
    assert item.status is SkillGapItemStatus.UNKNOWN
    assert item.student_level is student
    assert item.student_evidence == ()
    assert item.reason_code is SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING
    assert result.gap_status is SkillGapStatus.UNDETERMINED
    assert "gap_value" not in item.model_dump()


@pytest.mark.parametrize("coverage, students, expected", [
    ("complete", [INTERMEDIATE, ADVANCED], "no_gap"),
    ("complete", [INTERMEDIATE, BEGINNER], "gap_identified"),
    ("complete", [INTERMEDIATE, None], "undetermined"),
    ("complete", [BEGINNER, None], "gap_identified"),
    ("partial", [INTERMEDIATE, ADVANCED], "undetermined"),
    ("partial", [INTERMEDIATE, BEGINNER], "gap_identified"),
    ("partial", [INTERMEDIATE, None], "undetermined"),
    ("partial", [BEGINNER, None], "gap_identified"),
])
def test_coverage_aggregation_and_roundtrip(coverage, students, expected):
    ctx = make_context([
        ("skill-a", INTERMEDIATE, students[0], REQUIRED), ("skill-b", INTERMEDIATE, students[1], DESIRED),
    ], SkillRequirementCoverage(coverage))
    result = SkillGapEngine().evaluate(ctx)
    assert result.gap_status.value == expected
    assert result.requirements == ctx.requirements
    assert len(result.items) == 2
    assert result.items[1].requirement.requirement_type is DESIRED
    expected_reasons = {item.reason_code for item in result.items}
    if coverage == "partial":
        expected_reasons.add(SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE)
    assert set(result.reason_codes) == expected_reasons
    assert len(result.reason_codes) == len(expected_reasons)
    assert result.model_dump(mode="json") == json.loads(result.model_dump_json())
    assert SkillGapDecision.model_validate_json(result.model_dump_json()) == result
    assert result.audit_evidence[0].source is None
    assert result.audit_evidence[0].field == "gap_status"
    assert result.audit_evidence[0].value == expected


def test_missing_requirements_is_undetermined_not_no_gap():
    ctx = make_context([], SkillRequirementCoverage.MISSING)
    result = SkillGapEngine().evaluate(ctx)
    assert result.gap_status is SkillGapStatus.UNDETERMINED
    assert result.items == ()
    assert result.reason_codes == (SkillGapReasonCode.REQUIREMENT_DATA_MISSING,)
    assert SkillGapDecision.model_validate_json(result.model_dump_json()) == result
    assert result.model_dump(mode="json") == json.loads(result.model_dump_json())


def test_all_requirements_in_order_no_short_circuit_cross_skill_or_source_loss():
    ctx = make_context([
        ("skill-z", ADVANCED, BEGINNER, REQUIRED), ("skill-a", BEGINNER, ADVANCED, DESIRED), ("skill-b", INTERMEDIATE, None, REQUIRED),
    ])
    data = ctx.model_dump()
    # Reverse profile/evidence order, add an irrelevant skill with no provenance,
    # and provide a second matching source for skill-z.
    data["student_profile"]["skills"] = tuple(reversed(
        data["student_profile"]["skills"]
    )) + (StudentSkill(skill_id="irrelevant", level=ADVANCED).model_dump(),)
    second = data["student_skill_evidence"][0] | {"code": "SECOND_SOURCE"}
    data["student_skill_evidence"] = tuple(reversed(
        data["student_skill_evidence"]
    )) + (second,)
    ctx = SkillGapContext.model_validate(data)
    result = SkillGapEngine().evaluate(ctx)
    assert [i.requirement.skill_id for i in result.items] == ["skill-z", "skill-a", "skill-b"]
    assert [i.status.value for i in result.items] == ["gap", "satisfied", "unknown"]
    assert len(result.items) == len(ctx.requirements.requirements)
    assert len(result.items[0].student_evidence) == 2
    for item in result.items:
        assert item.requirement in ctx.requirements.requirements
        assert item.student_evidence == tuple(
            e for e in ctx.student_skill_evidence
            if e.field == skill_fact_field(SkillFactRole.STUDENT_SKILL, item.requirement.skill_id)
        )


@pytest.mark.parametrize("invalid", [
    {"student_skill_evidence": []},
    {"student_skill_evidence": [Evidence(
        code="WRONG", message="Wrong skill", field="skills.other.level", value="intermediate",
    )]},
])
def test_invalid_student_evidence_rejected_before_engine_input(invalid):
    data = make_context([("skill-a", INTERMEDIATE, INTERMEDIATE, REQUIRED)]).model_dump()
    with pytest.raises(ValidationError):
        SkillGapContext.model_validate(data | invalid)


@pytest.mark.parametrize("raw", [None, {}, "path.json"])
def test_engine_only_accepts_context_snapshots(raw):
    with pytest.raises(TypeError, match="SkillGapContext"):
        SkillGapEngine().evaluate(raw)


def test_later_item_error_propagates_without_partial_decision(monkeypatch):
    ctx = make_context([("a", INTERMEDIATE, BEGINNER, REQUIRED), ("b", INTERMEDIATE, INTERMEDIATE, REQUIRED)])
    original = skill_gap_engine.SkillGapItem
    calls = []

    def fail_second(**kwargs):
        calls.append(kwargs["requirement"].skill_id)
        if len(calls) == 2:
            raise ValueError("invalid second item")
        return original(**kwargs)

    monkeypatch.setattr(skill_gap_engine, "SkillGapItem", fail_second)
    with pytest.raises(ValueError, match="invalid second item"):
        SkillGapEngine().evaluate(ctx)
    assert calls == ["a", "b"]


def test_engine_is_deterministic_read_only_and_output_immutable():
    ctx = make_context([("z", ADVANCED, BEGINNER, REQUIRED), ("a", BEGINNER, ADVANCED, DESIRED), ("b", INTERMEDIATE, None, REQUIRED)])
    before = ctx.model_dump_json()
    engine = SkillGapEngine()
    first, second = engine.evaluate(ctx), engine.evaluate(ctx)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert ctx.model_dump_json() == before
    for model, field, value in (
        (first, "gap_status", SkillGapStatus.NO_GAP),
        (first.items[0], "status", SkillGapItemStatus.SATISFIED),
        (first.items[0].student_evidence[0], "value", "advanced"),
        (first.items[0].requirement, "required_level", BEGINNER),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, value)
    with pytest.raises(AttributeError):
        first.items.append(None)
    with pytest.raises(TypeError):
        first.items[0] = None
    assert first.model_dump_json() == second.model_dump_json()


def test_display_names_and_descriptions_do_not_affect_analysis():
    ctx = make_context([("opaque-id", INTERMEDIATE, INTERMEDIATE, REQUIRED)])
    data = ctx.model_dump()
    data["competition"]["name"] = "AI mathematics Python deep learning"
    data["competition"]["description"] = "Completely different description"
    changed = SkillGapContext.model_validate(data)
    assert SkillGapEngine().evaluate(changed) == SkillGapEngine().evaluate(ctx)


def test_domain_imports_are_pure_and_no_validation_bypass():
    tree = ast.parse(inspect.getsource(skill_gap_engine))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules == {
        "types", "competition_copilot.domain.decision", "competition_copilot.domain.skill",
        "competition_copilot.domain.skill_gap",
    }
    assert not any(isinstance(n, ast.Import) for n in ast.walk(tree))
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in ("model_construct", "__setattr__")
        for n in ast.walk(tree)
    )
