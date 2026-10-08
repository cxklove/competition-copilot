from datetime import datetime, timezone
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class PlanMilestone(BaseModel):
    """A task or milestone recorded in a competition plan."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    estimated_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    dependency_ids: list[str] = Field(default_factory=list)
    status: MilestoneStatus = MilestoneStatus.PENDING

    @field_validator("id", "title", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("start_at", "due_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must be timezone-aware")
        return value

    @field_validator("dependency_ids")
    @classmethod
    def normalize_dependency_ids(cls, dependency_ids: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for dependency_id in dependency_ids:
            stripped = dependency_id.strip()
            if not stripped:
                raise ValueError("dependency_ids must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def check_dates_and_dependencies(self) -> Self:
        if (
            self.start_at is not None
            and self.due_at is not None
            and self.start_at.astimezone(timezone.utc)
            > self.due_at.astimezone(timezone.utc)
        ):
            raise ValueError("start_at must be before or equal to due_at")
        if self.id in self.dependency_ids:
            raise ValueError("dependency_ids must not contain own id")
        return self


class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class CompetitionPlan(BaseModel):
    """A versioned preparation plan for a student and competition edition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    student_id: str
    competition_id: str
    edition_id: str
    status: PlanStatus = PlanStatus.DRAFT
    version: int = Field(default=1, strict=True, ge=1)
    milestones: list[PlanMilestone] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "student_id", "competition_id", "edition_id")
    @classmethod
    def strip_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def check_dates_and_milestone_ids(self) -> Self:
        if self.updated_at.astimezone(timezone.utc) < self.created_at.astimezone(
            timezone.utc
        ):
            raise ValueError("updated_at must be after or equal to created_at")

        seen = set()
        for milestone in self.milestones:
            if milestone.id in seen:
                raise ValueError("milestones must not contain duplicate ids")
            seen.add(milestone.id)
        return self
