"""Structured, source-backed hard eligibility facts independent of storage."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from competition_copilot.domain.eligibility import EligibilityScope
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.student import EducationLevel


class PolicyCoverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class EducationLevelConstraint(BaseModel):
    """An official allowed education level fact, not executable rule logic."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    scope: EligibilityScope
    target_id: str
    allowed_levels: list[EducationLevel] = Field(min_length=1)
    alternative_profile_field: str | None = None
    source: SourceMetadata
    evidence_text: str

    @field_validator("rule_id", "target_id", "evidence_text", "alternative_profile_field")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_fact(self) -> "EducationLevelConstraint":
        if self.source.source_type is not SourceType.OFFICIAL:
            raise ValueError("eligibility fact requires an official source")
        if self.source.verification_status is not VerificationStatus.VERIFIED:
            raise ValueError("eligibility fact requires a verified source")
        if len(set(self.allowed_levels)) != len(self.allowed_levels):
            raise ValueError("allowed_levels must be unique")
        return self


class EligibilityPolicy(BaseModel):
    """Reviewed facts for one exact target; coverage is an explicit assessment."""

    model_config = ConfigDict(extra="forbid")

    competition_id: str
    edition_id: str
    track_id: str | None = None
    coverage: PolicyCoverage
    coverage_note: str
    source: SourceMetadata
    constraints: list[EducationLevelConstraint] = Field(default_factory=list)

    @field_validator("competition_id", "edition_id", "track_id", "coverage_note")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "EligibilityPolicy":
        if self.source.source_type is not SourceType.OFFICIAL:
            raise ValueError("policy requires an official source")
        if self.source.verification_status is not VerificationStatus.VERIFIED:
            raise ValueError("policy requires a verified source")
        if self.coverage is PolicyCoverage.COMPLETE and not self.constraints:
            raise ValueError("complete policy requires explicit constraints")
        targets = {
            EligibilityScope.COMPETITION: self.competition_id,
            EligibilityScope.EDITION: self.edition_id,
            EligibilityScope.TRACK: self.track_id,
        }
        seen: set[str] = set()
        for constraint in self.constraints:
            if constraint.rule_id in seen or constraint.rule_id == "policy-coverage-incomplete":
                raise ValueError("duplicate or reserved rule_id")
            if constraint.target_id != targets[constraint.scope]:
                raise ValueError("constraint target does not match policy")
            seen.add(constraint.rule_id)
        return self
