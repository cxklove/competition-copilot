"""Pure V1 signal, synthetic facts only; no actual proficiency claim."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain import verified_skill_overlap
from competition_copilot.domain.recommendation import (
    RecommendationContext,
    RecommendationSkillRequirements,
)
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.verified_skill_overlap import (
    POLICY_VERSION,
    VerifiedSkillOverlapScorer,
)
from tests.domain.test_recommendation_scoring import context as base_context
from tests.domain.test_skill_requirement_artifact import artifact_data


def context(*, level="intermediate", required_level=None, kind="required", coverage="partial",
            missing=False, eligibility="eligible"):
    raw = base_context(eligibility).model_dump(mode="json")
    artifact = artifact_data(edition_id="e")
    facts = artifact["requirement_set"]
    facts["target"]["competition_id"] = "c"
    facts["coverage"] = coverage
    requirement = facts["requirements"][0]
    requirement["requirement_type"] = kind
    requirement["required_level"] = required_level
    if required_level is None:
        requirement["evidence"] = []
    else:
        requirement["evidence"][0]["value"] = required_level
    raw["skill_requirements"] = {"requirement_version": artifact["requirement_version"], "requirement_set": facts}
    raw["student_profile"]["skills"] = [] if missing else [{"skill_id": "synthetic-skill",
        "level": level, "self_assessed": True, "note": "Synthetic test fact"}]
    return RecommendationContext.model_validate(raw)


@pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
def test_any_explicit_known_level_scores_one_without_proficiency_comparison(level):
    value = context(level=level)
    scorer = VerifiedSkillOverlapScorer()
    result = scorer.evaluate(value)
    assert result.score == 1.0 and result.component_id == result.evidence[0].value == POLICY_VERSION
    assert scorer.unavailability_reason(value) is None
    assert result.reason_code == "VERIFIED_SKILL_OVERLAP"
    assert "coverage=partial" in result.message and "presence-only" in result.message
    assert "does not establish" in result.message
    assert any(e.field == "skill_requirements.requirement_version" and e.value == "synthetic-v1" for e in result.evidence)
    assert any(e.field == "skill_requirements.coverage" and e.value == "partial" for e in result.evidence)
    assert any(e.field == "skills.synthetic-skill.self_assessed" and e.value is True and e.source is None for e in result.evidence)
    assert any(e.field == "skills.synthetic-skill.level" and e.value == level for e in result.evidence)
    assert any(e.source and e.source.verification_status == "verified" for e in result.evidence)
    assert value.skill_requirements.requirement_set.coverage == "partial"


@pytest.mark.parametrize("changes,reason", [
    ({"level": "unknown"}, "SOFT_PROFILE_DATA_MISSING"),
    ({"missing": True}, "SOFT_PROFILE_DATA_MISSING"),
    ({"required_level": "intermediate"}, "SKILL_LEVEL_POLICY_UNSUPPORTED"),
    ({"kind": "desired"}, "SOFT_SIGNAL_UNAVAILABLE"),
])
def test_unavailable_is_none_never_zero(changes, reason):
    value = context(**changes)
    scorer = VerifiedSkillOverlapScorer()
    assert scorer.evaluate(value) is None and scorer.unavailability_reason(value) == reason
    evaluation = RecommendationScoringEngine([WeightedSuitabilityScorer(scorer)]).evaluate(value)
    assert evaluation.suitability_score is None
    assert "SOFT_SIGNAL_UNAVAILABLE" in evaluation.reason_codes
    assert "NO_ACTIVE_SOFT_SIGNALS" in evaluation.reason_codes


def test_absent_missing_or_nonofficial_requirements_have_no_signal():
    scorer = VerifiedSkillOverlapScorer()
    assert scorer.evaluate(base_context()) is None
    raw = context().model_dump(mode="json")
    facts = raw["skill_requirements"]["requirement_set"]
    facts["coverage"], facts["requirements"] = "missing", []
    assert scorer.evaluate(RecommendationContext.model_validate(raw)) is None
    raw = context().model_dump(mode="json")
    raw["skill_requirements"]["requirement_set"]["requirements"][0]["presence_evidence"][0]["source"]["source_type"] = "manual"
    assert scorer.evaluate(RecommendationContext.model_validate(raw)) is None


def test_all_required_skills_needed_but_desired_is_not_v1_input():
    raw = context().model_dump(mode="json")
    requirements = raw["skill_requirements"]["requirement_set"]["requirements"]
    second = json.loads(json.dumps(requirements[0]))
    second["skill_id"] = "other"
    second["presence_evidence"][0]["field"] = "requirements.other.present"
    requirements.append(second)
    assert VerifiedSkillOverlapScorer().evaluate(RecommendationContext.model_validate(raw)) is None
    second["requirement_type"] = "desired"
    assert VerifiedSkillOverlapScorer().evaluate(RecommendationContext.model_validate(raw)).score == 1.0


@pytest.mark.parametrize("field,value", [("competition_id", "other"), ("edition_id", "other"), ("track_id", "other")])
def test_exact_target_mismatch_rejected_by_context(field, value):
    raw = context().model_dump(mode="json")
    target = raw["skill_requirements"]["requirement_set"]["target"]
    target[field] = value
    if field == "track_id":
        target["scope"] = "track"
    with pytest.raises(ValidationError, match="skill requirements do not match candidate"):
        RecommendationContext.model_validate(raw)


def test_snapshot_immutable_version_required_and_old_contexts_still_valid():
    old = base_context().model_dump(mode="json")
    old.pop("skill_requirements")
    assert RecommendationContext.model_validate(old).skill_requirements is None
    value = context()
    for model, field, replacement in ((value, "skill_requirements", None),
        (value.skill_requirements, "requirement_version", "other"),
        (value.skill_requirements.requirement_set, "coverage", "complete"),
        (value.skill_requirements.requirement_set.requirements[0], "required_level", "advanced")):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, replacement)
    with pytest.raises(TypeError):
        value.skill_requirements.model_copy(update={"requirement_version": "other"})
    raw = value.skill_requirements.model_dump(mode="json")
    for version in ("", " ", None, 1):
        with pytest.raises(ValidationError):
            RecommendationSkillRequirements.model_validate({**raw, "requirement_version": version})
    assert RecommendationContext.model_validate_json(value.model_dump_json()) == value


def test_unknown_stays_uncertain_and_ineligible_skips_scorer():
    scorer = VerifiedSkillOverlapScorer()
    engine = RecommendationScoringEngine([WeightedSuitabilityScorer(scorer)])
    result = engine.evaluate(context(eligibility="unknown"))
    assert result.suitability_score == 1.0 and result.status == "eligibility_uncertain"
    ranking = RecommendationRankingEngine().rank([result])
    assert not ranking.confirmed and len(ranking.uncertain) == 1

    class NeverCalled(VerifiedSkillOverlapScorer):
        def evaluate(self, context):
            pytest.fail("P5 INELIGIBLE must bypass scorer")

    blocked = RecommendationScoringEngine([WeightedSuitabilityScorer(NeverCalled())]).evaluate(
        context(eligibility="ineligible"))
    assert blocked.status == "eligibility_blocked" and blocked.suitability_score is None


def test_deterministic_pure_scorer_no_io(monkeypatch):
    value = context()
    before = value.model_dump_json()
    tree = ast.parse(inspect.getsource(verified_skill_overlap))
    assert not any(isinstance(n, ast.Import) for n in ast.walk(tree))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(name.startswith("competition_copilot.domain.") for name in imports)
    assert not any(isinstance(n, ast.Name) and n.id in ("open", "eval", "exec") for n in ast.walk(tree))
    def forbid(*args, **kwargs):
        pytest.fail("No scorer filesystem access")
    monkeypatch.setattr("builtins.open", forbid)
    first = VerifiedSkillOverlapScorer().evaluate(value)
    assert first == VerifiedSkillOverlapScorer().evaluate(value)
    assert value.model_dump_json() == before
