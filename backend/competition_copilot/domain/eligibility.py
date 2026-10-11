"""Contracts for deterministic, evidence-backed hard eligibility decisions.

Rule coverage and aggregation belong to a later Domain Service. These models do
not infer that an unrecorded restriction is absent.
"""

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import DecisionResult, Evidence
from competition_copilot.domain.student import StudentProfile


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class EligibilityScope(str, Enum):
    COMPETITION = "competition"
    EDITION = "edition"
    TRACK = "track"


class EligibilityReasonCode(str, Enum):
    RULE_SATISFIED = "RULE_SATISFIED"
    RULE_VIOLATED = "RULE_VIOLATED"
    PROFILE_DATA_MISSING = "PROFILE_DATA_MISSING"
    RULE_DATA_MISSING = "RULE_DATA_MISSING"


class EligibilityContext(BaseModel):
    """Explicit student and formal target snapshot supplied to a pure rule.

    Rules must not fetch data. Any future evaluation time must likewise be an
    explicit input, rather than read from the system clock.
    """

    model_config = ConfigDict(extra="forbid")

    student_profile: StudentProfile
    competition: Competition
    edition: CompetitionEdition
    track: CompetitionTrack | None = None

    @model_validator(mode="after")
    def check_relationships(self) -> "EligibilityContext":
        if self.edition.competition_id != self.competition.id:
            raise ValueError("edition must belong to competition")
        if self.track is not None and self.track.edition_id != self.edition.id:
            raise ValueError("track must belong to edition")
        return self

    @property
    def competition_id(self) -> str:
        return self.competition.id

    @property
    def edition_id(self) -> str:
        return self.edition.id

    @property
    def track_id(self) -> str | None:
        return self.track.id if self.track is not None else None


class RuleEvaluation(BaseModel):
    """One rule's conclusion for one explicit competition/edition/track target."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    scope: EligibilityScope
    target_id: str
    status: EligibilityStatus
    reason_code: EligibilityReasonCode
    message: str
    evidence: list[Evidence] = Field(min_length=1)

    @field_validator("rule_id", "target_id", "message")
    @classmethod
    def strip_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def check_status_reason(self) -> "RuleEvaluation":
        allowed = {
            EligibilityStatus.ELIGIBLE: {EligibilityReasonCode.RULE_SATISFIED},
            EligibilityStatus.INELIGIBLE: {EligibilityReasonCode.RULE_VIOLATED},
            EligibilityStatus.UNKNOWN: {
                EligibilityReasonCode.PROFILE_DATA_MISSING,
                EligibilityReasonCode.RULE_DATA_MISSING,
            },
        }
        if self.reason_code not in allowed[self.status]:
            raise ValueError("reason_code is inconsistent with rule status")
        return self


class EligibilityRule(Protocol):
    """A stable, pure hard-constraint rule; applicability is handled separately.

    Implementations must not mutate context or use IO, clocks, random values,
    repositories, tools, or LLMs. A rule ID is public audit identity, not a
    Python class name.
    """

    @property
    def rule_id(self) -> str: ...

    @property
    def scope(self) -> EligibilityScope: ...

    def evaluate(self, context: EligibilityContext) -> RuleEvaluation: ...


class EligibilityDecision(DecisionResult):
    """Eligibility-specific DecisionResult with target and rule audit trail.

    Construction validates internal consistency, not completeness of official
    rules. A future Domain Service must establish coverage before ELIGIBLE.
    """

    status: EligibilityStatus
    competition_id: str
    edition_id: str
    track_id: str | None = None
    rule_evaluations: list[RuleEvaluation] = Field(default_factory=list)

    @field_validator("competition_id", "edition_id", "track_id")
    @classmethod
    def strip_target_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("target ID must not be blank")
        return stripped

    @model_validator(mode="after")
    def check_decision_audit(self) -> "EligibilityDecision":
        if not self.reason_codes:
            raise ValueError("eligibility decision needs a reason code")
        if not self.evidence:
            raise ValueError("eligibility decision needs evidence")
        targets = {
            EligibilityScope.COMPETITION: self.competition_id,
            EligibilityScope.EDITION: self.edition_id,
            EligibilityScope.TRACK: self.track_id,
        }
        for item in self.rule_evaluations:
            if item.target_id != targets[item.scope]:
                raise ValueError("rule evaluation target does not match decision")
            if item.reason_code.value not in self.reason_codes:
                raise ValueError("rule evaluation reason is missing from decision")
        if self.status is EligibilityStatus.INELIGIBLE and not any(
            item.status is EligibilityStatus.INELIGIBLE for item in self.rule_evaluations
        ):
            raise ValueError("ineligible decision needs a violated rule")
        if self.status is EligibilityStatus.UNKNOWN and not (
            any(item.status is EligibilityStatus.UNKNOWN for item in self.rule_evaluations)
            or any(
                code in {
                    EligibilityReasonCode.PROFILE_DATA_MISSING.value,
                    EligibilityReasonCode.RULE_DATA_MISSING.value,
                }
                for code in self.reason_codes
            )
        ):
            raise ValueError("unknown decision needs an unknown reason")
        if self.status is EligibilityStatus.ELIGIBLE and (
            not self.rule_evaluations
            or any(
                item.status is not EligibilityStatus.ELIGIBLE
                for item in self.rule_evaluations
            )
            or any(
                code in {
                    EligibilityReasonCode.RULE_VIOLATED.value,
                    EligibilityReasonCode.PROFILE_DATA_MISSING.value,
                    EligibilityReasonCode.RULE_DATA_MISSING.value,
                }
                for code in self.reason_codes
            )
        ):
            raise ValueError("eligible decision needs satisfied rules only")
        return self
