"""Candidate enumeration and real P5/P6, with explicitly synthetic formal records."""

from pathlib import Path

import pytest

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.application.recommendation import (
    RecommendationContextAssembler,
)
from competition_copilot.domain.competition import Competition
from competition_copilot.domain.recommendation import RecommendationCandidate
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError

from .recommendation_test_support import Policies, Repository


class UnavailableSignal:
    component_id = "test-unavailable"

    def evaluate(self, context):
        return None


def build(repository=None):
    repository = repository or Repository()
    return RecommendationContextAssembler(repository, CompetitionEligibilityEvaluator(repository, Policies()))


def test_three_candidates_real_p5_buckets_anchor_dedup_and_no_invented_scores():
    student = StudentProfile(id="student", education_level="graduate")
    anchor = RecommendationCandidate(competition_id="c", edition_id="c-2026")
    contexts = build().assemble(student, anchor=anchor)
    assert [c.candidate.competition_id for c in contexts] == ["a", "b", "c"]
    assert [c.eligibility_decision.status for c in contexts] == ["eligible", "unknown", "ineligible"]
    scoring = RecommendationScoringEngine([WeightedSuitabilityScorer(UnavailableSignal())])
    ranking = RecommendationRankingEngine().rank(tuple(scoring.evaluate(c) for c in contexts))
    assert [r.evaluation.candidate.competition_id for r in ranking.confirmed] == ["a"]
    assert [r.evaluation.candidate.competition_id for r in ranking.uncertain] == ["b"]
    assert [r.candidate.competition_id for r in ranking.blocked] == ["c"]
    assert ranking.confirmed[0].evaluation.suitability_score is None
    assert contexts == build().assemble(student, anchor=anchor)


def test_exact_anchor_track_is_retained_without_choosing_alternative_tracks():
    contexts = build().assemble(StudentProfile(id="student"), anchor=RecommendationCandidate(
        competition_id="c", edition_id="c-2026", track_id="c-track"))
    assert [c.candidate.track_id for c in contexts] == [None, None, None, "c-track"]


def test_prerequisite_failure_propagates_instead_of_dropping_candidate():
    class Broken:
        def evaluate(self, *args):
            raise RuntimeError("P5 execution unavailable")

    with pytest.raises(RuntimeError, match="P5 execution unavailable"):
        RecommendationContextAssembler(Repository(), Broken()).assemble(StudentProfile(id="student"))


def test_single_formal_candidate_compatible():
    class Single(Repository):
        def list_competitions(self):
            return [Competition(id="a", name="A")]

    assert len(build(Single()).assemble(StudentProfile(id="student"))) == 1


def test_invalid_anchor_is_not_invented():
    with pytest.raises(RepositoryEntityNotFoundError):
        build().assemble(StudentProfile(id="student"), anchor=RecommendationCandidate(
            competition_id="c", edition_id="c-2026", track_id="nonexistent"))


def test_all_editions_not_a_guessed_latest_and_duplicate_enumeration_is_stable():
    class Several(Repository):
        def list_editions_by_competition(self, key):
            return [self.get_edition(key + suffix) for suffix in ("-old", "-new", "-old")]

    contexts = build(Several()).assemble(StudentProfile(id="student"))
    assert [(c.candidate.competition_id, c.candidate.edition_id) for c in contexts] == [
        (key, key + suffix) for key in ("a", "b", "c") for suffix in ("-new", "-old")]


def test_real_formal_repository_only_anchor_blocked_alternatives_retained():
    from competition_copilot.infrastructure.eligibility_policy_json import (
        JsonEligibilityPolicyProvider,
    )
    from competition_copilot.infrastructure.repositories.json_seed import (
        JsonSeedCompetitionRepository,
    )

    root = Path(__file__).resolve().parents[3]
    repository = JsonSeedCompetitionRepository(root / "data/seed")
    evaluator = CompetitionEligibilityEvaluator(repository, JsonEligibilityPolicyProvider(root / "data/eligibility"))
    anchor = RecommendationCandidate(competition_id="gcxl-engineering-practice-innovation",
        edition_id="gcxl-engineering-practice-innovation-2027")
    contexts = RecommendationContextAssembler(repository, evaluator).assemble(
        StudentProfile(id="local-graduate", education_level="graduate"), anchor=anchor)
    expected = sorted((e.competition_id, e.id) for e in repository.list_editions())
    assert [(c.candidate.competition_id, c.candidate.edition_id) for c in contexts] == expected
    assert len(contexts) > 1
    assert next(c for c in contexts if c.candidate == anchor).eligibility_decision.status == "ineligible"
    for context in contexts:
        assert context.eligibility_decision.model_dump(mode="json") == evaluator.evaluate(
            StudentProfile(id="local-graduate", education_level="graduate"),
            context.candidate.competition_id, context.candidate.edition_id).model_dump(mode="json")
