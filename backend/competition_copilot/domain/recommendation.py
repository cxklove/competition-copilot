"""Single-candidate, auditable soft recommendation contracts.

Eligibility is supplied by P5 and remains authoritative. Scoring and ranking
are separate later capabilities; this module only validates their data boundary.
"""

import re
from collections.abc import Mapping
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import DecisionResult, Evidence
from competition_copilot.domain.eligibility import (
    EligibilityDecision,
    EligibilityStatus,
    RuleEvaluation,
)
from competition_copilot.domain.skill import StudentSkill
from competition_copilot.domain.student import StudentProfile


class _RecommendationSnapshot(BaseModel):
    """Immutable P6 view; shared Domain inputs are validated into detached data."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def detach_domain_model(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @field_validator("evidence", mode="before", check_fields=False)
    @classmethod
    def detach_evidence(cls, values: Any) -> Any:
        return tuple(
            item.model_dump() if isinstance(item, Evidence) else item
            for item in values
        )

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated snapshot instead of updating a copy")
        return super().model_copy(deep=deep)


class _CompetitionSnapshot(Competition, _RecommendationSnapshot):
    pass


class _EditionSnapshot(CompetitionEdition, _RecommendationSnapshot):
    pass


class _TrackSnapshot(CompetitionTrack, _RecommendationSnapshot):
    pass


class _StudentSkillSnapshot(StudentSkill, _RecommendationSnapshot):
    pass


class _StudentProfileSnapshot(StudentProfile, _RecommendationSnapshot):
    interests: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    skills: tuple[_StudentSkillSnapshot, ...] = ()

    @field_validator("interests", "goals", "skills")
    @classmethod
    def immutable_collections(cls, values: Any) -> tuple:
        return tuple(values)


class _RuleEvaluationSnapshot(RuleEvaluation, _RecommendationSnapshot):
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class RecommendationEligibilitySnapshot(EligibilityDecision, _RecommendationSnapshot):
    """Immutable P6 copy of a P5 decision, with its original semantics and audit.

    Adds no eligibility fields or rules; inherits all P5 decision invariants.
    """

    reason_codes: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()
    rule_evaluations: tuple[_RuleEvaluationSnapshot, ...] = ()

    @field_validator("reason_codes")
    @classmethod
    def immutable_reasons(cls, values: Any) -> tuple[str, ...]:
        return tuple(values)


class RecommendationStatus(str, Enum):
    RECOMMENDED = "recommended"
    NOT_RECOMMENDED = "not_recommended"
    SUITABILITY_UNDETERMINED = "suitability_undetermined"
    ELIGIBILITY_UNCERTAIN = "eligibility_uncertain"
    ELIGIBILITY_BLOCKED = "eligibility_blocked"


class RecommendationReasonCode(str, Enum):
    ELIGIBILITY_BLOCKED = "ELIGIBILITY_BLOCKED"
    ELIGIBILITY_UNKNOWN = "ELIGIBILITY_UNKNOWN"
    SUITABILITY_ASSESSED = "SUITABILITY_ASSESSED"
    SOFT_PROFILE_DATA_MISSING = "SOFT_PROFILE_DATA_MISSING"


class RecommendationCandidate(_RecommendationSnapshot):
    """Stable identity of one competition, edition, and optional track."""

    competition_id: str = Field(strict=True)
    edition_id: str = Field(strict=True)
    track_id: str | None = Field(default=None, strict=True)

    @field_validator("competition_id", "edition_id", "track_id")
    @classmethod
    def nonblank_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("candidate ID must not be blank")
        return value


class RecommendationContext(_RecommendationSnapshot):
    """Prepared Domain snapshot for one candidate; no lookup or scoring."""

    student_profile: _StudentProfileSnapshot
    candidate: RecommendationCandidate
    competition: _CompetitionSnapshot
    edition: _EditionSnapshot
    track: _TrackSnapshot | None = None
    eligibility_decision: RecommendationEligibilitySnapshot

    @model_validator(mode="after")
    def check_target(self) -> "RecommendationContext":
        candidate = self.candidate
        if self.edition.competition_id != self.competition.id:
            raise ValueError("edition must belong to competition")
        if self.track is not None and self.track.edition_id != self.edition.id:
            raise ValueError("track must belong to edition")
        if (candidate.competition_id, candidate.edition_id, candidate.track_id) != (
            self.competition.id,
            self.edition.id,
            self.track.id if self.track is not None else None,
        ):
            raise ValueError("candidate does not match target snapshot")
        if (candidate.competition_id, candidate.edition_id, candidate.track_id) != (
            self.eligibility_decision.competition_id,
            self.eligibility_decision.edition_id,
            self.eligibility_decision.track_id,
        ):
            raise ValueError("eligibility decision does not match candidate")
        return self


class RecommendationScoreComponent(_RecommendationSnapshot):
    """One future soft-suitability contribution, without a prescribed weight."""

    component_id: str = Field(strict=True, pattern=r"^[a-z][a-z0-9_.-]*$")
    score: float = Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    reason_code: str = Field(strict=True, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @field_validator("component_id", "reason_code", "message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("component identity and explanation must not be blank")
        return value


class RecommendationEvaluation(DecisionResult, _RecommendationSnapshot):
    """Final result for one candidate, with P5 eligibility kept intact.

    A score describes soft suitability on [0, 1], never eligibility probability.
    No ranking position, candidate comparison, or scoring formula is defined.
    """

    status: RecommendationStatus
    candidate: RecommendationCandidate
    eligibility_decision: RecommendationEligibilitySnapshot
    reason_codes: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()
    suitability_score: float | None = Field(
        default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False
    )
    score_components: tuple[RecommendationScoreComponent, ...] = ()

    @field_validator("reason_codes")
    @classmethod
    def machine_readable_reasons(cls, values: list[str]) -> tuple[str, ...]:
        if any(re.fullmatch(r"[A-Z][A-Z0-9_]*", value) is None for value in values):
            raise ValueError("recommendation reason codes must be machine-readable")
        return tuple(values)

    @model_validator(mode="after")
    def check_recommendation(self) -> "RecommendationEvaluation":
        candidate = self.candidate
        eligibility = self.eligibility_decision
        if (candidate.competition_id, candidate.edition_id, candidate.track_id) != (
            eligibility.competition_id,
            eligibility.edition_id,
            eligibility.track_id,
        ):
            raise ValueError("eligibility decision does not match candidate")
        if not self.reason_codes or not self.evidence:
            raise ValueError("recommendation requires reason codes and evidence")

        expected = {
            RecommendationStatus.ELIGIBILITY_BLOCKED: (
                EligibilityStatus.INELIGIBLE,
                RecommendationReasonCode.ELIGIBILITY_BLOCKED,
            ),
            RecommendationStatus.ELIGIBILITY_UNCERTAIN: (
                EligibilityStatus.UNKNOWN,
                RecommendationReasonCode.ELIGIBILITY_UNKNOWN,
            ),
            RecommendationStatus.RECOMMENDED: (
                EligibilityStatus.ELIGIBLE,
                RecommendationReasonCode.SUITABILITY_ASSESSED,
            ),
            RecommendationStatus.NOT_RECOMMENDED: (
                EligibilityStatus.ELIGIBLE,
                RecommendationReasonCode.SUITABILITY_ASSESSED,
            ),
            RecommendationStatus.SUITABILITY_UNDETERMINED: (
                EligibilityStatus.ELIGIBLE,
                RecommendationReasonCode.SOFT_PROFILE_DATA_MISSING,
            ),
        }
        required_eligibility, required_reason = expected[self.status]
        if eligibility.status is not required_eligibility:
            raise ValueError("recommendation status conflicts with eligibility")
        base_reasons = {item.value for item in RecommendationReasonCode}
        if required_reason.value not in self.reason_codes or any(
            code in base_reasons and code != required_reason.value
            for code in self.reason_codes
        ):
            raise ValueError("reason codes conflict with recommendation status")
        if self.status in {
            RecommendationStatus.ELIGIBILITY_BLOCKED,
            RecommendationStatus.SUITABILITY_UNDETERMINED,
        } and self.suitability_score is not None:
            raise ValueError("blocked or undetermined suitability has no overall score")
        if self.status is RecommendationStatus.ELIGIBILITY_BLOCKED and self.score_components:
            raise ValueError("blocked candidate cannot carry suitability components")
        if self.status in {
            RecommendationStatus.RECOMMENDED,
            RecommendationStatus.NOT_RECOMMENDED,
        } and (self.suitability_score is None or not self.score_components):
            raise ValueError("assessed suitability needs a score and components")
        if self.suitability_score is not None and not self.score_components:
            raise ValueError("overall score needs auditable components")
        return self
