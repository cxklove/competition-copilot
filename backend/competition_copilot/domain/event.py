from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

from competition_copilot.domain.source_metadata import SourceMetadata


class CompetitionEventType(str, Enum):
    REGISTRATION_OPENED = "registration_opened"
    REGISTRATION_CLOSED = "registration_closed"
    DEADLINE_CHANGED = "deadline_changed"
    MATERIAL_UPDATED = "material_updated"
    RULE_UPDATED = "rule_updated"
    TRACK_UPDATED = "track_updated"
    RESULT_PUBLISHED = "result_published"
    OTHER = "other"


class CompetitionEvent(BaseModel):
    """A recorded competition change with its source and observation time."""

    model_config = ConfigDict(extra="forbid")

    id: str
    competition_id: str
    edition_id: str
    event_type: CompetitionEventType
    occurred_at: datetime | None = None
    observed_at: datetime
    source: SourceMetadata
    description: str | None = None

    @field_validator("id", "competition_id", "edition_id", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must be timezone-aware")
        return value
