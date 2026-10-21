"""Assemble formal recommendation candidates with authoritative P5 decisions.

Repository enumeration supplies candidates; P5 owns eligibility and P6 owns
scoring/buckets. No ingestion data, model calls or suitability rules live here.
"""

from typing import Protocol

from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.recommendation import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationSkillRequirements,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.competition import CompetitionRepository


class CandidateEligibilityEvaluator(Protocol):
    def evaluate(self, student_profile: StudentProfile, competition_id: str,
                 edition_id: str, track_id: str | None = None) -> EligibilityDecision: ...


class RecommendationContextAssembler:
    """All formal editions, plus the exact optional anchor, in identity order.

    The repository has no current-edition policy. Alternatives therefore remain
    edition-level, without arbitrarily selecting a track. An explicit anchor
    track is retained separately. Prerequisite exceptions propagate fail closed;
    a normal P5 UNKNOWN remains a context and is never treated as an exception.
    """

    def __init__(self, repository: CompetitionRepository,
                 eligibility: CandidateEligibilityEvaluator,
                 requirements: SkillRequirementProvider | None = None):
        self._repository = repository
        self._eligibility = eligibility
        self._requirements = requirements
        self._versions = {}
        if requirements is not None:
            for artifact in requirements.list_artifacts():
                target = artifact.requirement_set.target
                key = (target.competition_id, target.edition_id, target.track_id)
                if key in self._versions:
                    raise ValueError("Duplicate requirement target")
                self._versions[key] = RecommendationSkillRequirements(
                    requirement_version=artifact.requirement_version,
                    requirement_set=artifact.requirement_set)

    def _prepare_requirements(self, candidate):
        if self._requirements is None:
            return None
        key = (candidate.competition_id, candidate.edition_id, candidate.track_id)
        facts = self._requirements.get_requirements(*key)
        if facts is None:
            if key in self._versions:
                raise ValueError("Requirement version snapshot mismatch")
            return None
        target = facts.target
        if (target.competition_id, target.edition_id, target.track_id) != key:
            raise ValueError("Requirement target mismatch")
        snapshot = self._versions.get(key)
        if snapshot is None or snapshot.requirement_set != facts:
            raise ValueError("Requirement version snapshot mismatch")
        return snapshot

    def assemble(self, student: StudentProfile, *,
                 anchor: RecommendationCandidate | None = None) -> tuple[RecommendationContext, ...]:
        candidates = {}
        for competition in self._repository.list_competitions():
            for edition in self._repository.list_editions_by_competition(competition.id):
                if edition.competition_id != competition.id:
                    raise ValueError("Formal edition parent mismatch")
                candidate = RecommendationCandidate(
                    competition_id=competition.id, edition_id=edition.id)
                candidates[(candidate.competition_id, candidate.edition_id, "")] = candidate
        if anchor is not None:
            candidates[(anchor.competition_id, anchor.edition_id, anchor.track_id or "")] = anchor
        contexts = []
        for key in sorted(candidates):
            candidate = candidates[key]
            competition = self._repository.get_competition(candidate.competition_id)
            edition = self._repository.get_edition(candidate.edition_id)
            track = self._repository.get_track(candidate.track_id) if candidate.track_id else None
            # P5 resolves/validates the exact formal target, including parent links.
            decision = self._eligibility.evaluate(
                student, candidate.competition_id, candidate.edition_id, candidate.track_id)
            contexts.append(RecommendationContext(
                student_profile=student, candidate=candidate, competition=competition,
                edition=edition, track=track, eligibility_decision=decision,
                skill_requirements=self._prepare_requirements(candidate)))
        return tuple(contexts)
