"""P5 policy, rule, provider, and application tests with synthetic data."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.eligibility import (
    CompetitionEligibilityEvaluator,
    EligibilityTargetError,
)
from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.eligibility import (
    EligibilityContext,
    EligibilityReasonCode,
    EligibilityScope,
    EligibilityStatus,
)
from competition_copilot.domain.eligibility_engine import EligibilityRuleEngine
from competition_copilot.domain.eligibility_policy import (
    EducationLevelConstraint,
    EligibilityPolicy,
    PolicyCoverage,
)
from competition_copilot.domain.eligibility_rules import EducationLevelRule
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.student import EducationLevel, StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    EligibilityPolicyLoadError,
    JsonEligibilityPolicyProvider,
)
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError


def source(*, verified: bool = True) -> SourceMetadata:
    return SourceMetadata(
        source_url="https://example.org/official-rules",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 11, tzinfo=timezone.utc),
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
        ),
    )


def policy(
    *, coverage: PolicyCoverage = PolicyCoverage.COMPLETE,
    rule_id: str = "education-level",
) -> EligibilityPolicy:
    return EligibilityPolicy(
        competition_id="competition-a",
        edition_id="edition-a",
        coverage=coverage,
        coverage_note="All official restrictions checked." if coverage is PolicyCoverage.COMPLETE else "Other official conditions are not structured.",
        source=source(),
        constraints=[
            EducationLevelConstraint(
                rule_id=rule_id,
                scope=EligibilityScope.EDITION,
                target_id="edition-a",
                allowed_levels=[EducationLevel.GRADUATE],
                source=source(),
                evidence_text="Only graduate students may enter.",
            )
        ],
    )


def write_policy(path: Path, item: EligibilityPolicy) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact_type": "eligibility_policy",
                "policy": item.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )


class FakeRepository:
    def __init__(self) -> None:
        self.competitions = {
            "competition-a": Competition(id="competition-a", name="A"),
            "competition-b": Competition(id="competition-b", name="B"),
        }
        self.editions = {
            "edition-a": CompetitionEdition(
                id="edition-a", competition_id="competition-a", year=2026, name="A 2026"
            ),
            "edition-b": CompetitionEdition(
                id="edition-b", competition_id="competition-b", year=2026, name="B 2026"
            ),
        }
        self.tracks = {
            "track-a": CompetitionTrack(id="track-a", edition_id="edition-a", name="A"),
            "track-b": CompetitionTrack(id="track-b", edition_id="edition-b", name="B"),
        }

    def get_competition(self, requested_id: str) -> Competition:
        try:
            return self.competitions[requested_id]
        except KeyError as exc:
            raise RepositoryEntityNotFoundError("competition", requested_id) from exc

    def get_edition(self, requested_id: str) -> CompetitionEdition:
        try:
            return self.editions[requested_id]
        except KeyError as exc:
            raise RepositoryEntityNotFoundError("edition", requested_id) from exc

    def get_track(self, requested_id: str) -> CompetitionTrack:
        try:
            return self.tracks[requested_id]
        except KeyError as exc:
            raise RepositoryEntityNotFoundError("track", requested_id) from exc


class FakeProvider:
    def __init__(self, item: EligibilityPolicy | None) -> None:
        self.item = item

    def get_policy(
        self, competition_id: str, edition_id: str, track_id: str | None = None
    ) -> EligibilityPolicy | None:
        return self.item


def evaluate(
    profile_level: EducationLevel | None,
    item: EligibilityPolicy | None,
):
    return CompetitionEligibilityEvaluator(FakeRepository(), FakeProvider(item)).evaluate(
        StudentProfile(id="student", education_level=profile_level),
        "competition-a",
        "edition-a",
    )


@pytest.mark.parametrize(
    ("level", "expected", "reason"),
    [
        (EducationLevel.GRADUATE, EligibilityStatus.ELIGIBLE, "RULE_SATISFIED"),
        (EducationLevel.UNDERGRADUATE, EligibilityStatus.INELIGIBLE, "RULE_VIOLATED"),
        (None, EligibilityStatus.UNKNOWN, "PROFILE_DATA_MISSING"),
    ],
)
def test_complete_policy_decisions(level, expected, reason) -> None:
    result = evaluate(level, policy())
    assert result.status is expected
    assert result.reason_codes == [reason]
    assert result.rule_evaluations[0].rule_id == "education-level"
    assert result.evidence[0].source == source()
    assert result.evidence[1].source is None
    assert result.evidence[1].field == "education_level"
    assert result.evidence[1].value == (level.value if level is not None else None)
    assert result.model_dump_json() == evaluate(level, policy()).model_dump_json()


def test_partial_policy_uses_engine_precedence() -> None:
    item = policy(coverage=PolicyCoverage.PARTIAL)
    satisfied = evaluate(EducationLevel.GRADUATE, item)
    violated = evaluate(EducationLevel.UNDERGRADUATE, item)
    assert satisfied.status is EligibilityStatus.UNKNOWN
    assert violated.status is EligibilityStatus.INELIGIBLE
    for decision in (satisfied, violated):
        known_rule, coverage_gap = decision.rule_evaluations
        assert [entry.rule_id for entry in decision.rule_evaluations] == [
            "education-level", "policy-coverage-incomplete"
        ]
        assert known_rule.evidence[0].source == item.constraints[0].source
        assert coverage_gap.status is EligibilityStatus.UNKNOWN
        assert coverage_gap.reason_code is EligibilityReasonCode.RULE_DATA_MISSING
        assert coverage_gap.message == item.coverage_note
        assert all(piece.source is None for piece in coverage_gap.evidence)
        assert decision.evidence[-1].source is None
    assert satisfied.rule_evaluations[0].status is EligibilityStatus.ELIGIBLE
    assert violated.rule_evaluations[0].status is EligibilityStatus.INELIGIBLE
    assert satisfied.model_dump_json() == evaluate(EducationLevel.GRADUATE, item).model_dump_json()


def test_missing_policy_is_business_unknown() -> None:
    result = evaluate(EducationLevel.GRADUATE, None)
    partial = evaluate(EducationLevel.GRADUATE, policy(coverage=PolicyCoverage.PARTIAL))
    assert result.status is EligibilityStatus.UNKNOWN
    assert result.reason_codes == ["RULE_DATA_MISSING"]
    assert result.rule_evaluations == []
    assert partial.status is EligibilityStatus.UNKNOWN
    assert partial.rule_evaluations
    assert partial.reason_codes == ["RULE_SATISFIED", "RULE_DATA_MISSING"]


def test_provider_policy_target_mismatch_is_rejected() -> None:
    wrong = policy().model_copy(update={"edition_id": "edition-b"})
    evaluator = CompetitionEligibilityEvaluator(FakeRepository(), FakeProvider(wrong))
    with pytest.raises(EligibilityTargetError) as caught:
        evaluator.evaluate(StudentProfile(id="student"), "competition-a", "edition-a")
    assert caught.value.reason == "policy_target_mismatch"


@pytest.mark.parametrize(
    ("competition_id", "edition_id", "track_id", "reason"),
    [
        ("missing", "edition-a", None, "target_not_found"),
        ("competition-a", "missing", None, "target_not_found"),
        ("competition-a", "edition-a", "missing", "target_not_found"),
        ("competition-a", "edition-b", None, "edition_competition_mismatch"),
        ("competition-a", "edition-a", "track-b", "track_edition_mismatch"),
    ],
)
def test_invalid_target_is_not_business_unknown(
    competition_id: str, edition_id: str, track_id: str | None, reason: str
) -> None:
    evaluator = CompetitionEligibilityEvaluator(FakeRepository(), FakeProvider(policy()))
    with pytest.raises(EligibilityTargetError) as caught:
        evaluator.evaluate(StudentProfile(id="student"), competition_id, edition_id, track_id)
    assert caught.value.reason == reason


def test_application_delegates_aggregation_to_engine() -> None:
    class SpyEngine(EligibilityRuleEngine):
        calls = 0

        def evaluate(self, context, rules):
            self.calls += 1
            return super().evaluate(context, rules)

    engine = SpyEngine()
    result = CompetitionEligibilityEvaluator(
        FakeRepository(), FakeProvider(policy()), engine
    ).evaluate(StudentProfile(id="student", education_level=EducationLevel.GRADUATE), "competition-a", "edition-a")
    assert engine.calls == 1
    assert result.status is EligibilityStatus.ELIGIBLE


def test_real_rule_alternative_profile_field_is_unknown_not_violation() -> None:
    fact = policy().constraints[0].model_copy(
        update={"alternative_profile_field": "graduate_admission_status"}
    )
    target = EligibilityContext(
        student_profile=StudentProfile(id="student", education_level=EducationLevel.UNDERGRADUATE),
        competition=FakeRepository().get_competition("competition-a"),
        edition=FakeRepository().get_edition("edition-a"),
    )
    result = EducationLevelRule(fact).evaluate(target)
    assert result.status is EligibilityStatus.UNKNOWN
    assert result.reason_code.value == "PROFILE_DATA_MISSING"
    assert "graduate_admission_status" in result.message
    assert result.evidence[1].field == "education_level"
    assert result.evidence[1].value == "undergraduate"
    assert not any(
        piece.field == "graduate_admission_status" and piece.value == "undergraduate"
        for piece in result.evidence
    )


def test_policy_schema_rejects_unverified_fact_duplicate_id_and_wrong_target() -> None:
    item = policy()
    missing_source = item.constraints[0].model_dump()
    del missing_source["source"]
    with pytest.raises(ValidationError, match="source"):
        EducationLevelConstraint.model_validate(missing_source)
    with pytest.raises(ValidationError, match="verified source"):
        EducationLevelConstraint.model_validate(
            {**item.constraints[0].model_dump(), "source": source(verified=False)}
        )
    with pytest.raises(ValidationError, match="duplicate"):
        EligibilityPolicy.model_validate(
            {**item.model_dump(), "constraints": [item.constraints[0], item.constraints[0]]}
        )
    with pytest.raises(ValidationError, match="target does not match"):
        EligibilityPolicy.model_validate(
            {**item.model_dump(), "constraints": [item.constraints[0].model_copy(update={"target_id": "wrong"})]}
        )


def test_json_provider_load_missing_invalid_duplicate_and_read_only(tmp_path: Path) -> None:
    assert JsonEligibilityPolicyProvider(tmp_path).get_policy("competition-a", "edition-a") is None
    write_policy(tmp_path / "b.json", policy())
    provider = JsonEligibilityPolicyProvider(tmp_path)
    loaded = provider.get_policy("competition-a", "edition-a")
    assert loaded == policy()
    loaded.constraints.clear()
    assert provider.get_policy("competition-a", "edition-a").constraints
    assert provider.get_policy("other", "edition-a") is None

    with pytest.raises(EligibilityPolicyLoadError, match="POLICY_DIRECTORY_INVALID"):
        JsonEligibilityPolicyProvider(tmp_path / "missing")
    (tmp_path / "invalid.json").write_text("{", encoding="utf-8")
    with pytest.raises(EligibilityPolicyLoadError, match="POLICY_ARTIFACT_INVALID"):
        JsonEligibilityPolicyProvider(tmp_path)
    assert provider.get_policy("competition-a", "edition-a") is not None
    (tmp_path / "invalid.json").unlink()
    write_policy(tmp_path / "a.json", policy())
    with pytest.raises(EligibilityPolicyLoadError, match="DUPLICATE_POLICY_TARGET"):
        JsonEligibilityPolicyProvider(tmp_path)


def test_json_provider_preserves_constraint_order_and_rejects_schema(tmp_path: Path) -> None:
    first = policy()
    second = first.constraints[0].model_copy(update={"rule_id": "second"})
    item = first.model_copy(update={"constraints": [second, first.constraints[0]]})
    write_policy(tmp_path / "policy.json", item)
    loaded = JsonEligibilityPolicyProvider(tmp_path).get_policy("competition-a", "edition-a")
    assert [fact.rule_id for fact in loaded.constraints] == ["second", "education-level"]
    path = tmp_path / "policy.json"
    path.write_text('{"schema_version":"9.9","artifact_type":"eligibility_policy","policy":{}}', encoding="utf-8")
    with pytest.raises(EligibilityPolicyLoadError, match="POLICY_ARTIFACT_INVALID"):
        JsonEligibilityPolicyProvider(tmp_path)
