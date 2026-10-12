"""Deterministic one-need/one-milestone structure; no scheduling or gap mapping."""

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from competition_copilot.domain.plan import (
    CompetitionPlan,
    PlanMilestone,
    PlanningNeed,
    PlanningNeedType,
    SkillGapPlanningAudit,
    SkillRequirementTarget,
)
from competition_copilot.domain.temporal import TimeWindow


def _machine_fields(value: Any) -> Any:
    """Identity uses supplied structured facts, excluding evidence display prose.

    This is serialization only: no source status/level/reason is interpreted.
    PlanningNeed has no title/description; its nested evidence has message text.
    """
    if isinstance(value, dict):
        return {key: _machine_fields(item) for key, item in value.items() if key != "message"}
    if isinstance(value, list):
        return [_machine_fields(item) for item in value]
    return value


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


class BaselineCompetitionPlanBuilder:
    """Consume P8 needs directly; retain order and generate unscheduled DRAFT.

    Target is the existing P8.1 audit target type, reused through plan.py. No P7
    service/decision/status/reason imports or reinterpretation occurs here.
    Source audit is required by CompetitionPlan for nonempty needs. Caller passes
    the matching P8.2 needs/audit pair and validates real target parent relations.
    """

    def build(
        self,
        *,
        target: SkillRequirementTarget,
        planning_needs: tuple[PlanningNeed, ...],
        student_id: str,
        created_at: datetime,
        source_audit: SkillGapPlanningAudit | None = None,
        planning_horizon: TimeWindow | None = None,
    ) -> CompetitionPlan:
        if not isinstance(target, SkillRequirementTarget):
            raise TypeError("target must be a validated planning target")
        target = SkillRequirementTarget.model_validate(target)
        if not isinstance(planning_needs, tuple) or any(
            not isinstance(need, PlanningNeed) for need in planning_needs
        ):
            raise TypeError("planning_needs must be an immutable tuple of PlanningNeed")
        needs = tuple(PlanningNeed.model_validate(need) for need in planning_needs)
        # P8.2 IDs encode exact machine target identity. Validate that binding
        # without reading a P7 status/reason or deriving any new need semantics.
        # General/manual P8.1 IDs have no embedded target; their supplied audit
        # remains the target binding checked by CompetitionPlan below.
        for need in needs:
            if need.id.startswith("planning-need:"):
                identity = json.loads(need.id.removeprefix("planning-need:"))
                if not isinstance(identity, list) or len(identity) != 6:
                    raise ValueError("invalid canonical planning need identity")
                if identity[:3] != [target.competition_id, target.edition_id, target.track_id]:
                    raise ValueError("planning need target does not match builder target")
        if source_audit is not None:
            if not isinstance(source_audit, SkillGapPlanningAudit):
                raise TypeError("source_audit must be a validated planning audit")
            source_audit = SkillGapPlanningAudit.model_validate(source_audit)
        if planning_horizon is not None:
            if not isinstance(planning_horizon, TimeWindow):
                raise TypeError("planning_horizon must be a TimeWindow snapshot")
            planning_horizon = TimeWindow.model_validate(planning_horizon.model_dump())
        if not isinstance(student_id, str) or not student_id.strip():
            raise ValueError("student_id must be a nonblank identity")
        student_id = student_id.strip()
        if not isinstance(created_at, datetime) or created_at.utcoffset() is None:
            raise ValueError("created_at must be an explicitly supplied timezone-aware datetime")

        plan_id = "baseline-plan-v1:" + _digest({
            "target": target.model_dump(mode="json"),
            "student_id": student_id,
            "created_at": created_at.isoformat(),
            "needs": [_machine_fields(need.model_dump(mode="json")) for need in needs],
            "audit": source_audit.model_dump(mode="json") if source_audit is not None else None,
            "horizon": planning_horizon.model_dump(mode="json") if planning_horizon is not None else None,
        })
        milestones = []
        for need in needs:
            if need.kind is PlanningNeedType.SKILL_IMPROVEMENT:
                title = "Address confirmed skill improvement need: " + need.source_item.requirement.skill_id
            elif need.kind is PlanningNeedType.UNCERTAINTY_RESOLUTION:
                title = (
                    "Resolve competition requirement uncertainty" if need.source_item is None
                    else "Resolve planning uncertainty for skill: " + need.source_item.requirement.skill_id
                )
            else:
                raise ValueError("unsupported PlanningNeedType")
            milestones.append(PlanMilestone(
                id="baseline-milestone-v1:" + _digest((plan_id, need.id)),
                title=title,
                source_need_id=need.id,
            ))
        # Normal P8.1 validation enforces target/audit agreement, duplicate IDs
        # and source references. Any error fails the whole build, without fallback.
        return CompetitionPlan(
            id=plan_id,
            student_id=student_id,
            competition_id=target.competition_id,
            edition_id=target.edition_id,
            track_id=target.track_id,
            planning_horizon=planning_horizon,
            skill_gap_audit=source_audit,
            planning_needs=needs,
            milestones=tuple(milestones),
            created_at=created_at,
            updated_at=created_at,
        )
