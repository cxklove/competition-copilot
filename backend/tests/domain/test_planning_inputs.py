"""P8.2 synthetic P7 inputs; no engine, plan, milestone, repository or provider."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain import planning_inputs
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.plan import PlanningNeed, PlanningNeedType
from competition_copilot.domain.planning_inputs import PlanningInputDeriver
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapDecision,
    SkillGapItem,
    SkillGapReasonCode,
    SkillRequirement,
    SkillRequirementSet,
    SkillRequirementTarget,
    requirement_presence_field,
    skill_fact_field,
    skill_fact_value,
)


def make_decision(rows, coverage="complete", competition_id="c", edition_id="e", track_id=None):
    """Rows specify conclusions: (skill ID, gap/satisfied/threshold/missing/dual, type).

    The synthetic author supplies overall status explicitly; no P7 engine runs.
    All facts go through normal validated P7 constructors.
    """
    target = SkillRequirementTarget(
        competition_id=competition_id, edition_id=edition_id, track_id=track_id,
        scope="track" if track_id is not None else "edition",
    )
    requirements, items = [], []
    source = {"source_url": "https://example.org/synthetic", "source_type": "manual",
              "observed_at": "2026-01-01T00:00:00Z", "verification_status": "verified"}
    for skill_id, conclusion, requirement_type in rows:
        required = None if conclusion in ("threshold", "dual") else SkillLevel.INTERMEDIATE
        student = None if conclusion in ("missing", "dual") else (
            SkillLevel.BEGINNER if conclusion == "gap" else SkillLevel.ADVANCED
        )
        requirement = SkillRequirement(
            skill_id=skill_id, requirement_type=requirement_type, required_level=required,
            presence_evidence=[Evidence(
                code="TEST_ONLY_PRESENCE", message="Synthetic reviewed presence.",
                field=requirement_presence_field(skill_id), value=True, source=source,
            )],
            evidence=[] if required is None else [Evidence(
                code="TEST_ONLY_THRESHOLD", message="Synthetic reviewed threshold.",
                field=skill_fact_field(SkillFactRole.REQUIREMENT, skill_id),
                value=skill_fact_value(required), source=source,
            )],
        )
        reasons = {
            "gap": (SkillGapReasonCode.SKILL_BELOW_REQUIREMENT,),
            "satisfied": (SkillGapReasonCode.REQUIREMENT_SATISFIED,),
            "threshold": (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,),
            "missing": (SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,),
            "dual": (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,
                     SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING),
        }[conclusion]
        items.append(SkillGapItem(
            requirement=requirement, student_level=student,
            status=conclusion if conclusion in ("gap", "satisfied") else "unknown",
            reason_codes=reasons,
            student_evidence=[] if student is None else [Evidence(
                code="TEST_ONLY_STUDENT", message="Synthetic supplied student fact.",
                field=skill_fact_field(SkillFactRole.STUDENT_SKILL, skill_id),
                value=skill_fact_value(student),
            )],
        ))
        requirements.append(requirement)
    status = "gap_identified" if any(row[1] == "gap" for row in rows) else (
        "no_gap" if coverage == "complete" and all(row[1] == "satisfied" for row in rows)
        else "undetermined"
    )
    reasons = tuple(dict.fromkeys(r for item in items for r in item.reason_codes))
    if coverage == "partial":
        reasons += (SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,)
    elif coverage == "missing":
        reasons += (SkillGapReasonCode.REQUIREMENT_DATA_MISSING,)
    return SkillGapDecision(
        target=target,
        requirements=SkillRequirementSet(target=target, coverage=coverage,
                                        coverage_note="Synthetic explicit coverage.", requirements=requirements),
        gap_status=status, items=items, reason_codes=reasons,
        audit_evidence=[Evidence(code="TEST_ONLY_ANALYSIS", message="Supplied synthetic conclusion.")],
    )


@pytest.mark.parametrize("requirement_type", ["required", "desired"])
def test_confirmed_gap_retains_all_source_facts_and_evidence(requirement_type):
    decision = make_decision([("skill-x", "gap", requirement_type)])
    needs = PlanningInputDeriver().derive(decision)
    assert len(needs) == 1
    need = needs[0]
    assert need.kind is PlanningNeedType.SKILL_IMPROVEMENT
    assert need.source_item == decision.items[0]
    assert need.source_item.requirement.skill_id == "skill-x"
    assert need.source_item.requirement.requirement_type.value == requirement_type
    assert need.reason_codes == decision.items[0].reason_codes
    assert need.source_item.requirement.required_level is SkillLevel.INTERMEDIATE
    assert need.source_item.student_level is SkillLevel.BEGINNER
    assert need.source_item.requirement.presence_evidence == decision.items[0].requirement.presence_evidence
    assert need.source_item.requirement.evidence == decision.items[0].requirement.evidence
    assert need.source_item.student_evidence == decision.items[0].student_evidence


def test_complete_all_satisfied_has_no_needs():
    decision = make_decision([("a", "satisfied", "required"), ("b", "satisfied", "desired")])
    assert decision.gap_status.value == "no_gap"
    assert PlanningInputDeriver().derive(decision) == ()


@pytest.mark.parametrize("uncertainty", ["threshold", "missing", "dual"])
def test_unknown_is_one_information_need_preserving_every_reason(uncertainty):
    decision = make_decision([("a", uncertainty, "required")])
    needs = PlanningInputDeriver().derive(decision)
    assert len(needs) == 1
    assert needs[0].kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert needs[0].source_item == decision.items[0]
    assert needs[0].reason_codes == decision.items[0].reason_codes
    assert len(needs[0].reason_codes) == (2 if uncertainty == "dual" else 1)
    assert PlanningNeed.model_validate_json(needs[0].model_dump_json()) == needs[0]


def test_gap_unknown_satisfied_follow_item_order_not_overall_or_skill_sort():
    decision = make_decision([
        ("z", "gap", "required"), ("b", "dual", "desired"), ("a", "satisfied", "required"),
    ])
    needs = PlanningInputDeriver().derive(decision)
    assert decision.gap_status.value == "gap_identified"
    assert [n.source_item.requirement.skill_id for n in needs] == ["z", "b"]
    assert [n.kind.value for n in needs] == ["skill_improvement", "uncertainty_resolution"]


@pytest.mark.parametrize("conclusion", ["gap", "satisfied", "threshold", "missing", "dual"])
def test_partial_adds_one_separate_requirement_set_uncertainty(conclusion):
    decision = make_decision([("a", conclusion, "required")], coverage="partial")
    needs = PlanningInputDeriver().derive(decision)
    assert len(needs) == (1 if conclusion == "satisfied" else 2)
    coverage_need = needs[-1]
    assert coverage_need.kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert coverage_need.source_item is None
    assert coverage_need.reason_codes == (SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,)
    assert all(SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE not in n.reason_codes for n in needs[:-1])


def test_missing_requirements_yield_data_uncertainty_not_safe_empty():
    needs = PlanningInputDeriver().derive(make_decision([], coverage="missing"))
    assert len(needs) == 1
    assert needs[0].source_item is None
    assert needs[0].kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert needs[0].reason_codes == (SkillGapReasonCode.REQUIREMENT_DATA_MISSING,)


def test_source_audit_is_faithful_projection_without_plan_construction():
    decision = make_decision([("a", "dual", "required")], coverage="partial", track_id="t")
    audit = PlanningInputDeriver().source_audit(decision)
    assert audit.target == decision.target
    assert audit.coverage == decision.requirements.coverage
    assert audit.gap_status == decision.gap_status
    assert audit.reason_codes == decision.reason_codes
    assert json.loads(audit.model_dump_json()) == audit.model_dump(mode="json")


def test_stable_ids_are_unambiguous_and_target_specific():
    derive = PlanningInputDeriver().derive
    first = derive(make_decision([("a:b", "gap", "required")], competition_id="x", edition_id="y:z"))[0].id
    second = derive(make_decision([("b", "gap", "required")], competition_id="x:y", edition_id="z:a"))[0].id
    assert first != second
    for options in ({"competition_id": "other"}, {"edition_id": "other"}, {"track_id": "t"}):
        assert derive(make_decision([("a:b", "gap", "required")], **options))[0].id != first
    # A literal skill ID resembling a set scope remains a real skill, not a fake
    # scope placeholder; tagged tuple encoding prevents collision with coverage.
    needs = derive(make_decision([("requirement_set", "dual", "required")], coverage="partial"))
    assert len({n.id for n in needs}) == len(needs)


def test_repeatability_serialization_input_read_only_and_output_immutable():
    decision = make_decision([("z", "gap", "required"), ("a", "dual", "desired")], coverage="partial")
    before = decision.model_dump_json()
    service = PlanningInputDeriver()
    first, second = service.derive(decision), service.derive(decision)
    assert first == second
    assert tuple(n.model_dump_json() for n in first) == tuple(n.model_dump_json() for n in second)
    assert decision.model_dump_json() == before
    assert len({n.id for n in first}) == len(first)
    for need in first:
        assert json.loads(need.model_dump_json()) == need.model_dump(mode="json")
        assert PlanningNeed.model_validate_json(need.model_dump_json()) == need
        with pytest.raises(ValidationError):
            need.kind = PlanningNeedType.UNCERTAINTY_RESOLUTION
    with pytest.raises(AttributeError):
        first.append(first[0])
    with pytest.raises(ValidationError):
        first[0].source_item.student_level = SkillLevel.ADVANCED


@pytest.mark.parametrize("raw", [None, {}, "decision"])
def test_unvalidated_inputs_fail_fast(raw):
    with pytest.raises(TypeError):
        PlanningInputDeriver().derive(raw)
    with pytest.raises(TypeError):
        PlanningInputDeriver().source_audit(raw)


def test_pure_imports_and_no_identity_randomness_or_validation_bypass():
    tree = ast.parse(inspect.getsource(planning_inputs))
    assert {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} == {
        "competition_copilot.domain.plan", "competition_copilot.domain.skill_gap",
    }
    assert {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} == {"json"}
    assert not any(isinstance(n, ast.Attribute) and n.attr in (
        "model_construct", "__setattr__", "uuid4", "now"
    ) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "hash" for n in ast.walk(tree))
