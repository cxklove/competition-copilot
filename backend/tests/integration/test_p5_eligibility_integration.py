"""P5.4 acceptance of the real Repository + Policy + Eligibility chain."""

import json
from pathlib import Path

import pytest

from competition_copilot.application.eligibility import (
    CompetitionEligibilityEvaluator,
    EligibilityTargetError,
)
from competition_copilot.domain.eligibility import (
    EligibilityDecision,
    EligibilityReasonCode,
    EligibilityStatus,
)
from competition_copilot.domain.eligibility_engine import EligibilityRuleEngine
from competition_copilot.domain.eligibility_policy import (
    EligibilityPolicy,
    PolicyCoverage,
)
from competition_copilot.domain.source_metadata import SourceType, VerificationStatus
from competition_copilot.domain.student import EducationLevel, StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.repositories.competition import CompetitionRepository

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "data" / "seed"
POLICY_DIR = ROOT / "data" / "eligibility"
GRADUATE_POLICY_FILE = "china-graduate-math-modeling-2026"
GCXL_POLICY_FILE = "gcxl-engineering-practice-innovation-2027"


@pytest.fixture(scope="module")
def repository() -> CompetitionRepository:
    assert list(SEED_DIR.glob("*.json")), "Verified Seed artifacts are required"
    return JsonSeedCompetitionRepository(SEED_DIR)


@pytest.fixture(scope="module")
def provider() -> JsonEligibilityPolicyProvider:
    assert list(POLICY_DIR.glob("*.json")), "P5 policy artifacts are required"
    return JsonEligibilityPolicyProvider(POLICY_DIR)


@pytest.fixture(scope="module")
def policies() -> dict[str, EligibilityPolicy]:
    artifacts = sorted(POLICY_DIR.glob("*.json"))
    assert artifacts
    return {
        path.stem: EligibilityPolicy.model_validate(
            json.loads(path.read_text(encoding="utf-8"))["policy"]
        )
        for path in artifacts
    }


@pytest.fixture(scope="module")
def evaluator(
    repository: CompetitionRepository, provider: JsonEligibilityPolicyProvider
) -> CompetitionEligibilityEvaluator:
    return CompetitionEligibilityEvaluator(repository, provider)


def _assert_json_boundary(decision: EligibilityDecision) -> None:
    def assert_primitives(value: object) -> None:
        if isinstance(value, dict):
            assert all(isinstance(key, str) for key in value)
            for item in value.values():
                assert_primitives(item)
        elif isinstance(value, list):
            for item in value:
                assert_primitives(item)
        else:
            assert type(value) in (str, int, float, bool, type(None))

    dumped = decision.model_dump(mode="json")
    assert_primitives(dumped)
    assert json.loads(decision.model_dump_json()) == dumped
    assert EligibilityDecision.model_validate_json(decision.model_dump_json()) == decision


def _assert_partial_audit(
    decision: EligibilityDecision,
    policy: EligibilityPolicy,
    known_status: EligibilityStatus,
    known_reason: EligibilityReasonCode,
    profile_value: str | None,
) -> None:
    known, gap = decision.rule_evaluations
    assert decision.competition_id == policy.competition_id
    assert decision.edition_id == policy.edition_id
    assert decision.track_id == policy.track_id
    assert known.rule_id == policy.constraints[0].rule_id
    assert known.status is known_status
    assert known.reason_code is known_reason
    assert known.evidence[0].source == policy.constraints[0].source
    assert known.evidence[0].message == policy.constraints[0].evidence_text
    assert known.evidence[1].field == "education_level"
    assert known.evidence[1].value == profile_value
    assert gap.rule_id == "policy-coverage-incomplete"
    assert gap.status is EligibilityStatus.UNKNOWN
    assert gap.reason_code is EligibilityReasonCode.RULE_DATA_MISSING
    assert gap.message == policy.coverage_note
    assert gap.evidence and all(item.source is None for item in gap.evidence)
    assert decision.evidence == known.evidence + gap.evidence
    assert decision.reason_codes == [known_reason.value, gap.reason_code.value]
    _assert_json_boundary(decision)


def test_all_real_policy_targets_and_sources_are_valid(
    repository: CompetitionRepository,
    provider: JsonEligibilityPolicyProvider,
    policies: dict[str, EligibilityPolicy],
    evaluator: CompetitionEligibilityEvaluator,
) -> None:
    assert repository.list_competitions()
    assert repository.list_editions()
    assert len(policies) == len({
        (item.competition_id, item.edition_id, item.track_id)
        for item in policies.values()
    })

    for policy in policies.values():
        competition = repository.get_competition(policy.competition_id)
        edition = repository.get_edition(policy.edition_id)
        assert edition.competition_id == competition.id
        if policy.track_id is not None:
            assert repository.get_track(policy.track_id).edition_id == edition.id
        assert provider.get_policy(
            policy.competition_id, policy.edition_id, policy.track_id
        ) == policy
        assert policy.source.source_type is SourceType.OFFICIAL
        assert policy.source.verification_status is VerificationStatus.VERIFIED
        for constraint in policy.constraints:
            assert constraint.source.source_type is SourceType.OFFICIAL
            assert constraint.source.verification_status is VerificationStatus.VERIFIED
            assert constraint.evidence_text

        decision = evaluator.evaluate(
            StudentProfile(id="audit", education_level=None),
            policy.competition_id,
            policy.edition_id,
            policy.track_id,
        )
        assert decision.competition_id == policy.competition_id
        assert decision.edition_id == policy.edition_id
        assert decision.track_id == policy.track_id
        if policy.coverage is PolicyCoverage.PARTIAL:
            gap = decision.rule_evaluations[-1]
            assert gap.reason_code is EligibilityReasonCode.RULE_DATA_MISSING
            assert all(item.source is None for item in gap.evidence)


def test_real_decisions_preserve_precedence_audit_and_json(
    repository: CompetitionRepository,
    provider: JsonEligibilityPolicyProvider,
    policies: dict[str, EligibilityPolicy],
    evaluator: CompetitionEligibilityEvaluator,
) -> None:
    graduate_policy = policies[GRADUATE_POLICY_FILE]
    gcxl_policy = policies[GCXL_POLICY_FILE]
    assert graduate_policy.coverage is PolicyCoverage.PARTIAL
    assert gcxl_policy.coverage is PolicyCoverage.PARTIAL
    undergraduate = StudentProfile(id="undergraduate", education_level=EducationLevel.UNDERGRADUATE)
    graduate = StudentProfile(id="graduate", education_level=EducationLevel.GRADUATE)
    missing = StudentProfile(id="missing")
    profiles_before = [item.model_dump() for item in (undergraduate, graduate, missing)]
    competitions_before = repository.list_competitions()
    editions_before = repository.list_editions()
    tracks_before = {
        edition.id: repository.list_tracks(edition.id) for edition in editions_before
    }
    policy_before = provider.get_policy(gcxl_policy.competition_id, gcxl_policy.edition_id)

    def evaluate(profile: StudentProfile, policy: EligibilityPolicy) -> EligibilityDecision:
        return evaluator.evaluate(
            profile, policy.competition_id, policy.edition_id, policy.track_id
        )

    violated = evaluate(graduate, gcxl_policy)
    assert violated.status is EligibilityStatus.INELIGIBLE
    _assert_partial_audit(
        violated, gcxl_policy, EligibilityStatus.INELIGIBLE,
        EligibilityReasonCode.RULE_VIOLATED, "graduate",
    )
    satisfied = evaluate(undergraduate, gcxl_policy)
    assert satisfied.status is EligibilityStatus.UNKNOWN
    _assert_partial_audit(
        satisfied, gcxl_policy, EligibilityStatus.ELIGIBLE,
        EligibilityReasonCode.RULE_SATISFIED, "undergraduate",
    )
    missing_profile = evaluate(missing, gcxl_policy)
    assert missing_profile.status is EligibilityStatus.UNKNOWN
    _assert_partial_audit(
        missing_profile, gcxl_policy, EligibilityStatus.UNKNOWN,
        EligibilityReasonCode.PROFILE_DATA_MISSING, None,
    )
    assert "education level" in missing_profile.rule_evaluations[0].message.lower()

    graduate_satisfied = evaluate(graduate, graduate_policy)
    assert graduate_satisfied.status is EligibilityStatus.UNKNOWN
    _assert_partial_audit(
        graduate_satisfied, graduate_policy, EligibilityStatus.ELIGIBLE,
        EligibilityReasonCode.RULE_SATISFIED, "graduate",
    )
    alternate = evaluate(undergraduate, graduate_policy)
    assert alternate.status is EligibilityStatus.UNKNOWN
    _assert_partial_audit(
        alternate, graduate_policy, EligibilityStatus.UNKNOWN,
        EligibilityReasonCode.PROFILE_DATA_MISSING, "undergraduate",
    )
    assert "graduate_admission_status" in alternate.rule_evaluations[0].message
    assert not any(
        item.field == "graduate_admission_status" and item.value == "undergraduate"
        for item in alternate.evidence
    )

    assert evaluate(graduate, gcxl_policy).model_dump_json() == violated.model_dump_json()
    assert evaluate(undergraduate, graduate_policy).model_dump_json() == alternate.model_dump_json()
    assert [item.model_dump() for item in (undergraduate, graduate, missing)] == profiles_before
    assert repository.list_competitions() == competitions_before
    assert repository.list_editions() == editions_before
    assert {
        edition.id: repository.list_tracks(edition.id) for edition in editions_before
    } == tracks_before
    assert provider.get_policy(gcxl_policy.competition_id, gcxl_policy.edition_id) == policy_before


def test_real_missing_policy_is_distinct_from_partial_policy(
    repository: CompetitionRepository,
    policies: dict[str, EligibilityPolicy],
    evaluator: CompetitionEligibilityEvaluator,
) -> None:
    policy_targets = {
        (item.competition_id, item.edition_id, item.track_id)
        for item in policies.values()
    }
    uncovered = next(
        (
            edition for edition in repository.list_editions()
            if (edition.competition_id, edition.id, None) not in policy_targets
        ),
        None,
    )
    if uncovered is None:
        pytest.skip("Every current edition has a structured policy")

    profile = StudentProfile(id="missing-policy", education_level=EducationLevel.UNDERGRADUATE)
    absent = evaluator.evaluate(profile, uncovered.competition_id, uncovered.id)
    partial_policy = policies[GCXL_POLICY_FILE]
    partial = evaluator.evaluate(
        profile, partial_policy.competition_id, partial_policy.edition_id
    )
    assert absent.status is EligibilityStatus.UNKNOWN
    assert absent.reason_codes == [EligibilityReasonCode.RULE_DATA_MISSING.value]
    assert absent.rule_evaluations == []
    assert absent.evidence and all(item.source is None for item in absent.evidence)
    assert partial.status is EligibilityStatus.UNKNOWN
    assert partial.rule_evaluations
    assert partial.reason_codes != absent.reason_codes
    _assert_json_boundary(absent)


def test_unknown_and_cross_target_requests_are_rejected(
    repository: CompetitionRepository,
    policies: dict[str, EligibilityPolicy],
    evaluator: CompetitionEligibilityEvaluator,
) -> None:
    policy = policies[GCXL_POLICY_FILE]
    other_edition = next(
        item for item in repository.list_editions()
        if item.competition_id != policy.competition_id
    )
    other_track = next(
        track for edition in repository.list_editions()
        if edition.id != policy.edition_id
        for track in repository.list_tracks(edition.id)
    )
    unknown = "p5-integration-unknown-target"
    assert unknown not in {item.id for item in repository.list_competitions()}
    assert unknown not in {item.id for item in repository.list_editions()}
    assert all(
        unknown not in {track.id for track in repository.list_tracks(edition.id)}
        for edition in repository.list_editions()
    )
    profile = StudentProfile(id="target-check", education_level=EducationLevel.GRADUATE)
    cases = (
        (unknown, policy.edition_id, None, "target_not_found"),
        (policy.competition_id, unknown, None, "target_not_found"),
        (policy.competition_id, policy.edition_id, unknown, "target_not_found"),
        (policy.competition_id, other_edition.id, None, "edition_competition_mismatch"),
        (policy.competition_id, policy.edition_id, other_track.id, "track_edition_mismatch"),
    )
    for competition_id, edition_id, track_id, reason in cases:
        with pytest.raises(EligibilityTargetError) as caught:
            evaluator.evaluate(profile, competition_id, edition_id, track_id)
        assert caught.value.reason == reason


def test_real_application_uses_p5_rule_engine(
    repository: CompetitionRepository,
    provider: JsonEligibilityPolicyProvider,
    policies: dict[str, EligibilityPolicy],
) -> None:
    class CountingEngine(EligibilityRuleEngine):
        calls = 0

        def evaluate(self, context, rules):
            self.calls += 1
            return super().evaluate(context, rules)

    engine = CountingEngine()
    policy = policies[GCXL_POLICY_FILE]
    result = CompetitionEligibilityEvaluator(repository, provider, engine).evaluate(
        StudentProfile(id="engine-check", education_level=EducationLevel.GRADUATE),
        policy.competition_id,
        policy.edition_id,
    )
    assert engine.calls == 1
    assert result.status is EligibilityStatus.INELIGIBLE
