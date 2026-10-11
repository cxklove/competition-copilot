"""P6.4 real Repository/P5 pipeline with explicitly test-only soft signals.

Real partial/missing policies never become confirmed eligible. The three normal
P6 cases use synthetic ELIGIBLE decisions for real targets, not official facts.
No synthetic eligibility or skill mapping is written to production artifacts.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import (
    EligibilityDecision,
    EligibilityReasonCode,
    EligibilityScope,
    EligibilityStatus,
    RuleEvaluation,
)
from competition_copilot.domain.eligibility_policy import (
    EligibilityPolicy,
    PolicyCoverage,
)
from competition_copilot.domain.recommendation import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationScoreComponent,
    RecommendationStatus,
)
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
    RecommendationRankingError,
    RecommendationRankingResult,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.student import EducationLevel, StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "data" / "seed"
POLICY_DIR = ROOT / "data" / "eligibility"


def target(value):
    return value.competition_id, value.edition_id, value.track_id


@pytest.fixture
def dataset():
    seed_files = tuple(sorted(SEED_DIR.glob("*.json")))
    policy_files = tuple(sorted(POLICY_DIR.glob("*.json")))
    assert seed_files and policy_files
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonEligibilityPolicyProvider(POLICY_DIR)
    policies = tuple(
        EligibilityPolicy.model_validate_json(
            json.dumps(json.loads(path.read_text(encoding="utf-8"))["policy"])
        )
        for path in policy_files
    )
    return repository, provider, policies, seed_files + policy_files


@dataclass
class SyntheticTargetScorer:
    """Test-only ID lookup; values are fixture signals, not real skill mapping."""

    scores: dict[tuple[str, str, str | None], float | None]
    calls: list[tuple[str, str, str | None]]
    component_id: str = "synthetic-pipeline-signal"

    def evaluate(self, context):
        key = target(context.candidate)
        self.calls.append(key)
        score = self.scores[key]
        if score is None:
            return None
        return RecommendationScoreComponent(
            component_id=self.component_id,
            score=score,
            reason_code="SYNTHETIC_TEST_SIGNAL",
            message="Test-only prepared signal; no real competition skill mapping.",
            evidence=[
                Evidence(
                    code="SYNTHETIC_TEST_SIGNAL",
                    message="Explicit test fixture target score.",
                    field="test_signals.target_score",
                    value=score,
                )
            ],
        )


def synthetic_eligible(key):
    """Validated test-only eligibility for normal P6 paths, never official data."""
    competition_id, edition_id, track_id = key
    evidence = Evidence(
        code="SYNTHETIC_ELIGIBILITY",
        message="Test-only confirmed eligibility, not an official conclusion.",
    )
    return EligibilityDecision(
        competition_id=competition_id,
        edition_id=edition_id,
        track_id=track_id,
        status=EligibilityStatus.ELIGIBLE,
        reason_codes=[EligibilityReasonCode.RULE_SATISFIED.value],
        evidence=[evidence],
        rule_evaluations=[
            RuleEvaluation(
                rule_id="synthetic-eligibility-fixture",
                scope=EligibilityScope.EDITION,
                target_id=edition_id,
                status=EligibilityStatus.ELIGIBLE,
                reason_code=EligibilityReasonCode.RULE_SATISFIED,
                message="Synthetic normal-path fixture.",
                evidence=[evidence],
            )
        ],
    )


def prepare_context(repository, profile, decision):
    key = target(decision)
    return RecommendationContext(
        student_profile=profile,
        candidate=RecommendationCandidate(
            competition_id=key[0], edition_id=key[1], track_id=key[2]
        ),
        competition=repository.get_competition(key[0]),
        edition=repository.get_edition(key[1]),
        track=repository.get_track(key[2]) if key[2] is not None else None,
        eligibility_decision=decision,
    )


def run_pipeline(dataset):
    """Test orchestration only; production engines perform all decisions."""
    repository, provider, policies, _ = dataset
    evaluator = CompetitionEligibilityEvaluator(repository, provider)
    partial = next(p for p in policies if p.coverage is PolicyCoverage.PARTIAL)
    violation_policy = next(
        p
        for p in policies
        if any(
            c.alternative_profile_field is None
            and any(level not in c.allowed_levels for level in EducationLevel)
            for c in p.constraints
        )
        and target(p) != target(partial)
    )
    violation_fact = next(
        c
        for c in violation_policy.constraints
        if c.alternative_profile_field is None
        and any(level not in c.allowed_levels for level in EducationLevel)
    )
    satisfied = StudentProfile(
        id="p6-partial", education_level=partial.constraints[0].allowed_levels[0]
    )
    violated = StudentProfile(
        id="p6-violation",
        education_level=next(
            level
            for level in EducationLevel
            if level not in violation_fact.allowed_levels
        ),
    )
    uncovered = [
        edition
        for edition in repository.list_editions()
        if provider.get_policy(edition.competition_id, edition.id) is None
    ]
    assert len(uncovered) >= 4, (
        "Need distinct real targets for missing and synthetic cases"
    )
    missing_profile = StudentProfile(id="p6-missing-policy")
    decisions = {
        "partial": evaluator.evaluate(satisfied, *target(partial)),
        "blocked": evaluator.evaluate(violated, *target(violation_policy)),
        "missing-policy": evaluator.evaluate(
            missing_profile, uncovered[0].competition_id, uncovered[0].id
        ),
    }
    profiles = {
        "partial": satisfied,
        "blocked": violated,
        "missing-policy": missing_profile,
    }
    for label, edition in zip(
        ("synthetic-high", "synthetic-low", "synthetic-missing"),
        uncovered[1:4],
        strict=True,
    ):
        tracks = repository.list_tracks(edition.id)
        track_id = tracks[0].id if label == "synthetic-missing" and tracks else None
        decisions[label] = synthetic_eligible(
            (edition.competition_id, edition.id, track_id)
        )
        profiles[label] = StudentProfile(id=label)
    scores = {
        target(decisions[label]): score
        for label, score in (
            ("partial", 1.0),
            ("missing-policy", 0.9),
            ("blocked", 1.0),
            ("synthetic-high", 0.8),
            ("synthetic-low", 0.3),
            ("synthetic-missing", None),
        )
    }
    scorer = SyntheticTargetScorer(scores, [])
    engine = RecommendationScoringEngine([WeightedSuitabilityScorer(scorer)])
    profiles_before = {
        label: profile.model_dump_json() for label, profile in profiles.items()
    }
    decisions_before = {
        label: decision.model_dump_json() for label, decision in decisions.items()
    }
    contexts = {
        label: prepare_context(repository, profiles[label], decision)
        for label, decision in decisions.items()
    }
    before = {label: ctx.model_dump_json() for label, ctx in contexts.items()}
    results = {label: engine.evaluate(ctx) for label, ctx in contexts.items()}
    assert {label: ctx.model_dump_json() for label, ctx in contexts.items()} == before
    ranking = RecommendationRankingEngine().rank(list(results.values()))
    assert {
        label: profile.model_dump_json() for label, profile in profiles.items()
    } == profiles_before
    assert {
        label: decision.model_dump_json() for label, decision in decisions.items()
    } == decisions_before
    return decisions, results, ranking, scorer, profiles, contexts


def test_real_p5_to_p6_scoring_and_mixed_ranking_acceptance(dataset):
    decisions, results, ranking, scorer, _, _ = run_pipeline(dataset)
    assert decisions["blocked"].status is EligibilityStatus.INELIGIBLE
    blocked = results["blocked"]
    assert blocked.status is RecommendationStatus.ELIGIBILITY_BLOCKED
    assert blocked.suitability_score is None and blocked.score_components == ()
    assert target(blocked.candidate) not in scorer.calls
    assert scorer.calls == [
        target(r.candidate) for label, r in results.items() if label != "blocked"
    ]
    assert decisions["partial"].status is EligibilityStatus.UNKNOWN
    assert decisions["partial"].rule_evaluations[0].status is EligibilityStatus.ELIGIBLE
    assert (
        decisions["partial"].rule_evaluations[-1].reason_code
        is EligibilityReasonCode.RULE_DATA_MISSING
    )
    assert all(
        e.source is None for e in decisions["partial"].rule_evaluations[-1].evidence
    )
    assert results["partial"].status is RecommendationStatus.ELIGIBILITY_UNCERTAIN
    assert results["partial"].suitability_score == 1.0
    assert decisions["missing-policy"].reason_codes == ["RULE_DATA_MISSING"]
    assert not decisions["missing-policy"].rule_evaluations
    assert (
        results["missing-policy"].status is RecommendationStatus.ELIGIBILITY_UNCERTAIN
    )
    assert results["synthetic-high"].status is RecommendationStatus.RECOMMENDED
    assert results["synthetic-low"].status is RecommendationStatus.NOT_RECOMMENDED
    assert (
        results["synthetic-missing"].status
        is RecommendationStatus.SUITABILITY_UNDETERMINED
    )
    assert results["synthetic-missing"].suitability_score is None
    assert [entry.evaluation for entry in ranking.confirmed] == [
        results[label]
        for label in ("synthetic-high", "synthetic-low", "synthetic-missing")
    ]
    assert [entry.rank for entry in ranking.confirmed] == [1, 2, 3]
    assert [entry.evaluation for entry in ranking.uncertain] == [
        results["partial"],
        results["missing-policy"],
    ]
    assert [entry.rank for entry in ranking.uncertain] == [1, 2]
    assert ranking.blocked == (blocked,)
    assert not hasattr(blocked, "rank")


def test_full_nested_audit_json_determinism_and_duplicate_rejection(dataset):
    decisions, results, ranking, _, _, _ = run_pipeline(dataset)
    for label, result in results.items():
        assert result.eligibility_decision.model_dump(mode="json") == decisions[
            label
        ].model_dump(mode="json")
        assert result.reason_codes and result.evidence
        if label != "blocked":
            assert any(
                e.code == "COMPONENT_WEIGHT" and e.value == 1.0 for e in result.evidence
            )
            assert any(
                e.field == "scoring.recommendation_threshold" and e.value == 0.5
                for e in result.evidence
            )
            assert any("weighted-average-v1" in e.message for e in result.evidence)
    assert "SOFT_SIGNAL_UNAVAILABLE" in results["synthetic-missing"].reason_codes
    assert any(
        e.code == "SOFT_SIGNAL_UNAVAILABLE"
        for e in results["synthetic-missing"].evidence
    )
    assert any(
        e.source is not None for e in results["partial"].eligibility_decision.evidence
    )
    assert results["missing-policy"].eligibility_decision.rule_evaluations == ()
    assert results["partial"].eligibility_decision.rule_evaluations
    assert ranking.ranking_policy == "eligibility_buckets_score_desc_target_id_v1"
    assert ranking.model_dump(mode="json") == json.loads(ranking.model_dump_json())
    assert (
        RecommendationRankingResult.model_validate_json(ranking.model_dump_json())
        == ranking
    )
    values = list(results.values())
    before = [v.model_dump_json() for v in values]
    assert (
        RecommendationRankingEngine().rank(values[::-1]).model_dump_json()
        == ranking.model_dump_json()
    )
    assert [v.model_dump_json() for v in values] == before
    repeated_decisions, repeated_results, repeated_ranking, _, _, _ = run_pipeline(
        dataset
    )
    assert {k: v.model_dump_json() for k, v in decisions.items()} == {
        k: v.model_dump_json() for k, v in repeated_decisions.items()
    }
    assert results == repeated_results
    assert ranking.model_dump_json() == repeated_ranking.model_dump_json()
    with pytest.raises(RecommendationRankingError, match="duplicate"):
        RecommendationRankingEngine().rank(values + [values[0]])


def test_real_cross_target_contexts_are_rejected(dataset):
    repository, _, _, _ = dataset
    decisions, _, _, _, _, contexts = run_pipeline(dataset)
    ctx = contexts["partial"]
    other_edition = next(
        e for e in repository.list_editions() if e.competition_id != ctx.competition.id
    )
    other_track = next(
        t
        for e in repository.list_editions()
        if e.id != ctx.edition.id
        for t in repository.list_tracks(e.id)
    )
    for invalid in (
        {"edition": other_edition},
        {"track": other_track},
        {"eligibility_decision": decisions["missing-policy"]},
    ):
        with pytest.raises(ValidationError):
            RecommendationContext.model_validate(ctx.model_dump() | invalid)


def test_runtime_raw_independence_and_readonly_snapshots(dataset, monkeypatch):
    repository, provider, policies, files = dataset
    bytes_before = {path: path.read_bytes() for path in files}
    competitions_before = repository.list_competitions()
    editions_before = repository.list_editions()
    tracks_before = {e.id: repository.list_tracks(e.id) for e in editions_before}
    policies_before = [provider.get_policy(*target(p)) for p in policies]
    original_bytes, original_text = Path.read_bytes, Path.read_text

    def guard(path):
        assert not path.resolve().is_relative_to(ROOT / "data" / "raw")
        assert not path.resolve().is_relative_to(ROOT / "data" / "review")

    def read_bytes(path):
        guard(path)
        return original_bytes(path)

    def read_text(path, *args, **kwargs):
        guard(path)
        return original_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    # Reconstruct real adapters under the guard, not just their cached queries.
    fresh = (
        JsonSeedCompetitionRepository(SEED_DIR),
        JsonEligibilityPolicyProvider(POLICY_DIR),
        policies,
        files,
    )
    repository, provider = fresh[:2]
    _, _, _, _, profiles, contexts = run_pipeline(fresh)
    assert [p.model_dump() for p in profiles.values()] == [
        c.student_profile.model_dump()
        | {
            "interests": list(c.student_profile.interests),
            "goals": list(c.student_profile.goals),
            "skills": list(c.student_profile.skills),
        }
        for c in contexts.values()
    ]
    assert repository.list_competitions() == competitions_before
    assert repository.list_editions() == editions_before
    assert {
        e.id: repository.list_tracks(e.id) for e in editions_before
    } == tracks_before
    assert [provider.get_policy(*target(p)) for p in policies] == policies_before
    assert {path: path.read_bytes() for path in files} == bytes_before


def test_dynamic_artifact_targets_valid_and_snapshot_report(dataset, record_property):
    repository, provider, policies, files = dataset
    editions = repository.list_editions()
    for policy in policies:
        assert (
            repository.get_edition(policy.edition_id).competition_id
            == policy.competition_id
        )
        assert repository.get_competition(policy.competition_id)
        if policy.track_id is not None:
            assert repository.get_track(policy.track_id).edition_id == policy.edition_id
        assert provider.get_policy(*target(policy)) == policy
    summary = {
        "seed_files": sum(p.parent == SEED_DIR for p in files),
        "competitions": len(repository.list_competitions()),
        "editions": len(editions),
        "tracks": sum(len(repository.list_tracks(e.id)) for e in editions),
        "eligibility_policies": len(policies),
        "complete_policies": sum(
            p.coverage is PolicyCoverage.COMPLETE for p in policies
        ),
        "partial_policies": sum(p.coverage is PolicyCoverage.PARTIAL for p in policies),
        "edition_targets_without_exact_policy": sum(
            provider.get_policy(e.competition_id, e.id) is None for e in editions
        ),
    }
    record_property("dataset_snapshot", json.dumps(summary, sort_keys=True))
    print("P6 dataset snapshot:", json.dumps(summary, sort_keys=True))
