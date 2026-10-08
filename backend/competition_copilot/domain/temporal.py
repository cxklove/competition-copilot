from datetime import datetime, timezone
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class TimeWindow(BaseModel):
    """A time interval whose endpoints may be unknown."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.start_at.astimezone(timezone.utc)
            > self.end_at.astimezone(timezone.utc)
        ):
            raise ValueError("start_at must be before or equal to end_at")
        return self
