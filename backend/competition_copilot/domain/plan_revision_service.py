"""Mechanical, atomic execution of approved milestone updates only."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter, model_validator

from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone
from competition_copilot.domain.replanning import (
    PlanDiff,
    PlanMilestonesChange,
    ReplanningOutcome,
    revised_plan_identity,
)
from competition_copilot.domain.replanning_input import (
    ReplanningInput,
    ReplanningInputStatus,
)


class PlanRevisionResult(BaseModel):
    """Execution receipt retains approval payload alongside frozen Diff lineage.

    No second Plan model: after is the existing CompetitionPlan in plan_diff.
    Partial input is not executed; unresolved no-op retains its Decision outcome.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")
    replanning_input: ReplanningInput
    plan_diff: PlanDiff

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @property
    def after(self) -> CompetitionPlan:
        return self.plan_diff.after

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        if update is not None:
            raise TypeError("Construct a validated execution receipt")
        return super().model_copy(deep=deep)

    @model_validator(mode="after")
    def bind_execution(self) -> Self:
        source, diff = self.replanning_input, self.plan_diff
        if source.before != diff.before or source.decision != diff.decision:
            raise ValueError("Receipt must retain exact input Plan and Decision")
        if diff.evaluated_at < source.supplied_at:
            raise ValueError("Execution cannot precede input supply")
        if source.decision.outcome == ReplanningOutcome.REPLAN:
            if source.status != ReplanningInputStatus.EXECUTABLE:
                raise ValueError("Only fully executable REPLAN can produce a revision receipt")
            approved = {item.target_milestone_id: item.after for item in source.instructions}
            expected = tuple(approved.get(item.id, item) for item in source.before.milestones)
            if diff.after.milestones != expected or diff.after.updated_at != diff.evaluated_at:
                raise ValueError("Actual result must match all approved updates and execution time")
            inventory = {item.id for item in diff.after.milestones}
            if any(not set(item.dependency_ids).issubset(inventory) for item in diff.after.milestones):
                raise ValueError("Final dependencies must reference existing milestones")
        elif diff.after != source.before or diff.changes:
            raise ValueError("Non-REPLAN execution must preserve exact Plan")
        return self


class PlanRevisionService:
    """Input carries Decision, Scope, impacts and explicit authority transitively.

    Does not reinterpret Events, recompute decisions, authenticate approvals or
    call Planner. PARTIALLY_EXECUTABLE is deliberately rejected, never applied.
    """

    def revise(
        self, before: CompetitionPlan, replanning_input: ReplanningInput,
        *, executed_at: datetime,
    ) -> PlanRevisionResult:
        if not isinstance(before, CompetitionPlan) or not isinstance(replanning_input, ReplanningInput):
            raise TypeError("Supply typed CompetitionPlan and ReplanningInput")
        before = CompetitionPlan.model_validate(before)
        source = ReplanningInput.model_validate(replanning_input)
        if source.before != before:
            raise ValueError("Input must bind exact current Plan identity/version/content")
        if not isinstance(executed_at, datetime):
            raise TypeError("executed_at must be an explicitly supplied aware datetime")
        instant = TypeAdapter(AwareDatetime).validate_python(executed_at).astimezone(timezone.utc)
        if instant < source.supplied_at:
            raise ValueError("Execution cannot precede supplied input")
        after = before
        if source.decision.outcome == ReplanningOutcome.REPLAN:
            if source.status != ReplanningInputStatus.EXECUTABLE:
                raise ValueError("REPLAN requires fully executable input; partial/unresolved reject")
            # Revalidated contract restricts each supplied after to due_at only.
            updates = {item.target_milestone_id: item.after.due_at for item in source.instructions}
            milestones = tuple(
                PlanMilestone(**{**item.model_dump(), "due_at": updates[item.id]})
                if item.id in updates else item
                for item in before.milestones
            )
            inventory = {item.id for item in milestones}
            if any(not set(item.dependency_ids).issubset(inventory) for item in milestones):
                raise ValueError("Final dependency reference does not exist")
            after = CompetitionPlan(**{
                **before.model_dump(), "milestones": milestones,
                "id": revised_plan_identity(before, milestones),
                "version": before.version + 1, "updated_at": instant,
            })
        # Actual validated states, not instruction intent, determine the Diff.
        changes = (() if before.milestones == after.milestones else (
            PlanMilestonesChange(before=before.milestones, after=after.milestones),
        ))
        diff = PlanDiff(before=before, after=after, decision=source.decision,
                        evaluated_at=instant, changes=changes)
        return PlanRevisionResult(replanning_input=source, plan_diff=diff)
