"""Small real target + P5 policy integration, separate from P2 ingestion."""

from pathlib import Path

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.eligibility import EligibilityStatus
from competition_copilot.domain.student import EducationLevel, StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)

ROOT = Path(__file__).resolve().parents[3]


def test_real_verified_targets_and_structured_p5_policies() -> None:
    repository = JsonSeedCompetitionRepository(ROOT / "data" / "seed")
    policies = JsonEligibilityPolicyProvider(ROOT / "data" / "eligibility")
    evaluator = CompetitionEligibilityEvaluator(repository, policies)

    undergraduate = StudentProfile(id="undergrad", education_level=EducationLevel.UNDERGRADUATE)
    graduate = StudentProfile(id="grad", education_level=EducationLevel.GRADUATE)
    missing = StudentProfile(id="unknown")
    gcxl_id = "gcxl-engineering-practice-innovation"
    gcxl_edition = "gcxl-engineering-practice-innovation-2027"
    grad_id = "china-graduate-math-modeling"
    grad_edition = "china-graduate-math-modeling-2026"

    assert repository.get_edition(gcxl_edition).competition_id == gcxl_id
    assert repository.get_edition(grad_edition).competition_id == grad_id

    violated = evaluator.evaluate(graduate, gcxl_id, gcxl_edition)
    satisfied_but_partial = evaluator.evaluate(undergraduate, gcxl_id, gcxl_edition)
    profile_missing = evaluator.evaluate(missing, gcxl_id, gcxl_edition)
    incoming_graduate_unknown = evaluator.evaluate(undergraduate, grad_id, grad_edition)
    graduate_but_partial = evaluator.evaluate(graduate, grad_id, grad_edition)
    no_policy = evaluator.evaluate(graduate, "c4-big-data-challenge", "c4-big-data-challenge-2026")

    assert violated.status is EligibilityStatus.INELIGIBLE
    assert "RULE_VIOLATED" in violated.reason_codes
    assert satisfied_but_partial.status is EligibilityStatus.UNKNOWN
    assert "RULE_SATISFIED" in satisfied_but_partial.reason_codes
    assert satisfied_but_partial.rule_evaluations[0].evidence[0].source is not None
    assert satisfied_but_partial.rule_evaluations[-1].message == policies.get_policy(gcxl_id, gcxl_edition).coverage_note
    assert all(piece.source is None for piece in satisfied_but_partial.rule_evaluations[-1].evidence)
    assert profile_missing.status is EligibilityStatus.UNKNOWN
    assert "PROFILE_DATA_MISSING" in profile_missing.reason_codes
    assert incoming_graduate_unknown.status is EligibilityStatus.UNKNOWN
    alternate_rule = incoming_graduate_unknown.rule_evaluations[0]
    assert alternate_rule.status is EligibilityStatus.UNKNOWN
    assert alternate_rule.reason_code.value == "PROFILE_DATA_MISSING"
    assert "graduate_admission_status" in alternate_rule.message
    assert any(
        piece.field == "education_level" and piece.value == "undergraduate"
        for piece in alternate_rule.evidence
    )
    assert not any(
        piece.field == "graduate_admission_status" and piece.value == "undergraduate"
        for piece in alternate_rule.evidence
    )
    assert graduate_but_partial.status is EligibilityStatus.UNKNOWN
    assert graduate_but_partial.rule_evaluations[0].evidence[0].source is not None
    assert graduate_but_partial.rule_evaluations[-1].message == policies.get_policy(grad_id, grad_edition).coverage_note
    assert all(piece.source is None for piece in graduate_but_partial.rule_evaluations[-1].evidence)
    assert no_policy.status is EligibilityStatus.UNKNOWN
    assert no_policy.reason_codes == ["RULE_DATA_MISSING"]

    for result in (
        violated,
        satisfied_but_partial,
        profile_missing,
        incoming_graduate_unknown,
        graduate_but_partial,
        no_policy,
    ):
        assert result.model_dump(mode="json")
        assert result.model_dump_json()
    assert violated.evidence[0].source is not None
    assert violated.evidence[0].source.verification_status.value == "verified"
