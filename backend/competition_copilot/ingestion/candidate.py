"""Provisional competition records awaiting separate human review."""

from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.ingestion.models import RawCompetitionData


class CandidateStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    """A recorded issue, without running validation or changing candidate state."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    field: str | None = None
    severity: IssueSeverity


class CompetitionCandidate(BaseModel):
    """Keep raw and provisional parsed data outside the official collection."""

    model_config = ConfigDict(extra="forbid")

    id: str
    raw_data: RawCompetitionData
    competition: Competition | None = None
    edition: CompetitionEdition | None = None
    tracks: list[CompetitionTrack] = Field(default_factory=list)
    status: CandidateStatus = CandidateStatus.PENDING
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    created_at: AwareDatetime
    reviewed_at: AwareDatetime | None = None
    review_note: str | None = None

    @field_validator("id")
    @classmethod
    def require_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must not be blank")
        return value
