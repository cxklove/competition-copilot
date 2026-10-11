"""Eligibility orchestration over formal Domain and abstract data providers."""

from typing import Protocol

from competition_copilot.domain.eligibility import (
    EligibilityContext,
    EligibilityDecision,
    EligibilityRule,
    EligibilityScope,
)
from competition_copilot.domain.eligibility_engine import EligibilityRuleEngine
from competition_copilot.domain.eligibility_policy import (
    EligibilityPolicy,
    PolicyCoverage,
)
from competition_copilot.domain.eligibility_rules import (
    EducationLevelRule,
    IncompletePolicyRule,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.competition import (
    CompetitionRepository,
    RepositoryEntityNotFoundError,
)


class EligibilityPolicyProvider(Protocol):
    """Read a reviewed policy for an exact target, or None when absent."""

    def get_policy(
        self, competition_id: str, edition_id: str, track_id: str | None = None
    ) -> EligibilityPolicy | None: ...


class EligibilityTargetError(ValueError):
    """The requested Competition, Edition, or Track is absent or mismatched."""

    def __init__(self, reason: str, requested_id: str) -> None:
        self.reason = reason
        self.requested_id = requested_id
        super().__init__(f"{reason}: {requested_id}")


def _rules_from_policy(policy: EligibilityPolicy) -> list[EligibilityRule]:
    rules: list[EligibilityRule] = [
        EducationLevelRule(fact) for fact in policy.constraints
    ]
    if policy.coverage is PolicyCoverage.PARTIAL:
        scope = EligibilityScope.TRACK if policy.track_id is not None else EligibilityScope.EDITION
        rules.append(
            IncompletePolicyRule(
                scope=scope,
                target_id=policy.track_id or policy.edition_id,
                coverage_note=policy.coverage_note,
            )
        )
    return rules


class CompetitionEligibilityEvaluator:
    """Resolve a formal target and delegate hard rules to the P5.2 engine."""

    def __init__(
        self,
        repository: CompetitionRepository,
        policy_provider: EligibilityPolicyProvider,
        engine: EligibilityRuleEngine | None = None,
    ) -> None:
        self._repository = repository
        self._policy_provider = policy_provider
        self._engine = engine if engine is not None else EligibilityRuleEngine()

    def evaluate(
        self,
        student_profile: StudentProfile,
        competition_id: str,
        edition_id: str,
        track_id: str | None = None,
    ) -> EligibilityDecision:
        try:
            competition = self._repository.get_competition(competition_id)
            edition = self._repository.get_edition(edition_id)
            track = self._repository.get_track(track_id) if track_id is not None else None
        except RepositoryEntityNotFoundError as exc:
            raise EligibilityTargetError("target_not_found", exc.requested_id) from exc
        if edition.competition_id != competition.id:
            raise EligibilityTargetError("edition_competition_mismatch", edition_id)
        if track is not None and track.edition_id != edition.id:
            raise EligibilityTargetError("track_edition_mismatch", track_id)

        context = EligibilityContext(
            student_profile=student_profile,
            competition=competition,
            edition=edition,
            track=track,
        )
        policy = self._policy_provider.get_policy(competition_id, edition_id, track_id)
        if policy is not None and (
            policy.competition_id, policy.edition_id, policy.track_id
        ) != (competition_id, edition_id, track_id):
            raise EligibilityTargetError("policy_target_mismatch", edition_id)
        rules = _rules_from_policy(policy) if policy is not None else []
        return self._engine.evaluate(context, rules)
