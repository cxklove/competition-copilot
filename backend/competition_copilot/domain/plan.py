from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from competition_copilot.domain.skill_gap import (
    SkillGapItem,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirementCoverage,
    SkillRequirementTarget,
)
from competition_copilot.domain.temporal import TimeWindow


class _PlanningSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach_input(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated planning snapshot instead")
        return super().model_copy(deep=deep)


class PlanningNeedType(str, Enum):
    SKILL_IMPROVEMENT = "skill_improvement"
    UNCERTAINTY_RESOLUTION = "uncertainty_resolution"


class SkillGapPlanningAudit(_PlanningSnapshot):
    """Small supplied P7 decision projection, not a second gap evaluation.

    Caller retains the original decision and supplies its exact target, coverage,
    overall status and reasons. Need-local SkillGapItem snapshots retain source
    facts/evidence without embedding a complete decision in every need.
    """

    target: SkillRequirementTarget
    coverage: SkillRequirementCoverage
    gap_status: SkillGapStatus
    reason_codes: tuple[SkillGapReasonCode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_projection(self) -> Self:
        reasons = set(self.reason_codes)
        if len(reasons) != len(self.reason_codes):
            raise ValueError("source reason codes must be unique")
        for coverage, reason in (
            (SkillRequirementCoverage.PARTIAL, SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE),
            (SkillRequirementCoverage.MISSING, SkillGapReasonCode.REQUIREMENT_DATA_MISSING),
        ):
            if (self.coverage is coverage) != (reason in reasons):
                raise ValueError("source coverage and reasons conflict")
        if self.coverage is SkillRequirementCoverage.MISSING and (
            self.gap_status is not SkillGapStatus.UNDETERMINED
            or reasons != {SkillGapReasonCode.REQUIREMENT_DATA_MISSING}
        ):
            raise ValueError("missing requirements remain undetermined")
        if self.gap_status is SkillGapStatus.NO_GAP and (
            self.coverage is not SkillRequirementCoverage.COMPLETE
            or reasons != {SkillGapReasonCode.REQUIREMENT_SATISFIED}
        ):
            raise ValueError("NO_GAP projection must retain confirmed complete satisfaction")
        has_gap_reason = SkillGapReasonCode.SKILL_BELOW_REQUIREMENT in reasons
        if (self.gap_status is SkillGapStatus.GAP_IDENTIFIED) != has_gap_reason:
            raise ValueError("source gap status and reasons conflict")
        if self.gap_status is SkillGapStatus.UNDETERMINED and not reasons.intersection({
            SkillGapReasonCode.REQUIREMENT_DATA_MISSING,
            SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,
            SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,
            SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,
        }):
            raise ValueError("undetermined source needs an uncertainty reason")
        return self


class PlanningNeed(_PlanningSnapshot):
    """Supplied action purpose, justified by P7 facts; never compares skill levels."""

    id: str = Field(strict=True, min_length=1)
    kind: PlanningNeedType
    reason_codes: tuple[SkillGapReasonCode, ...] = Field(min_length=1)
    source_item: SkillGapItem | None = None

    @field_validator("id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("need id must not be blank")
        return value

    @model_validator(mode="after")
    def check_source(self) -> Self:
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("need reason codes must be unique")
        if self.source_item is not None:
            if self.reason_codes != self.source_item.reason_codes:
                raise ValueError("need must preserve exact item reasons")
            expected = (
                SkillGapItemStatus.GAP if self.kind is PlanningNeedType.SKILL_IMPROVEMENT
                else SkillGapItemStatus.UNKNOWN
            )
            if self.source_item.status is not expected:
                raise ValueError("need kind conflicts with confirmed P7 item status")
        elif (
            self.kind is not PlanningNeedType.UNCERTAINTY_RESOLUTION
            or self.reason_codes not in (
                (SkillGapReasonCode.REQUIREMENT_DATA_MISSING,),
                (SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,),
            )
        ):
            raise ValueError("only coverage uncertainty needs may omit a source item")
        return self


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class PlanMilestone(_PlanningSnapshot):
    """Immutable milestone; purpose derives from its referenced PlanningNeed.

    source_need_id=None retains P1 general/manual milestone semantics, without
    claiming a P7-backed skill action. Timing may be absent or partially known.
    """

    id: str
    title: str
    description: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    estimated_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    dependency_ids: tuple[str, ...] = ()
    status: MilestoneStatus = MilestoneStatus.PENDING
    source_need_id: str | None = None

    @field_validator("id", "title", "description", "source_need_id")
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
    def normalize_dependency_ids(cls, dependency_ids: tuple[str, ...]) -> tuple[str, ...]:
        normalized = []
        seen = set()
        for dependency_id in dependency_ids:
            stripped = dependency_id.strip()
            if not stripped:
                raise ValueError("dependency_ids must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return tuple(normalized)

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


class CompetitionPlan(_PlanningSnapshot):
    """Immutable initial plan for an exact edition or track.

    Existing timestamps/version/status remain supplied metadata, not replanning.
    Target existence and parent relationships are validated by the caller; this
    model checks exact agreement with the supplied P7 target. An audit can be
    retained with no needs/milestones. No dates, priorities or actions are inferred.
    """

    id: str
    student_id: str
    competition_id: str
    edition_id: str
    track_id: str | None = None
    planning_horizon: TimeWindow | None = None
    skill_gap_audit: SkillGapPlanningAudit | None = None
    planning_needs: tuple[PlanningNeed, ...] = ()
    status: PlanStatus = PlanStatus.DRAFT
    version: int = Field(default=1, strict=True, ge=1)
    milestones: tuple[PlanMilestone, ...] = ()
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "student_id", "competition_id", "edition_id", "track_id")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("planning_horizon", mode="before")
    @classmethod
    def revalidate_horizon(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, TimeWindow) else value

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

    @model_validator(mode="after")
    def check_planning_sources(self) -> Self:
        needs = {need.id: need for need in self.planning_needs}
        if len(needs) != len(self.planning_needs):
            raise ValueError("planning needs must not contain duplicate ids")
        audit = self.skill_gap_audit
        if self.planning_needs and audit is None:
            raise ValueError("planning needs require a supplied P7 audit")
        if audit is not None:
            target = audit.target
            if (self.competition_id, self.edition_id, self.track_id) != (
                target.competition_id, target.edition_id, target.track_id
            ):
                raise ValueError("plan target does not match P7 audit target")
            for need in self.planning_needs:
                if not set(need.reason_codes).issubset(audit.reason_codes):
                    raise ValueError("planning need reasons absent from P7 audit")
                if (
                    need.kind is PlanningNeedType.SKILL_IMPROVEMENT
                    and audit.gap_status is not SkillGapStatus.GAP_IDENTIFIED
                ):
                    raise ValueError("skill improvement requires confirmed P7 gap")
        for milestone in self.milestones:
            if milestone.source_need_id is not None and milestone.source_need_id not in needs:
                raise ValueError("milestone references unknown planning need")
            if self.planning_horizon is not None:
                for instant in (milestone.start_at, milestone.due_at):
                    if instant is None:
                        continue
                    start = self.planning_horizon.start_at
                    end = self.planning_horizon.end_at
                    if (start is not None and instant < start) or (end is not None and instant > end):
                        raise ValueError("milestone timing outside explicit planning horizon")
        return self
