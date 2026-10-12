import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.plan import (
    CompetitionPlan,
    MilestoneStatus,
    PlanMilestone,
    PlanStatus,
)

MINIMAL_PLAN = {
    "id": "plan-1",
    "student_id": "student-1",
    "competition_id": "competition-1",
    "edition_id": "edition-1",
    "created_at": datetime(2026, 10, 8, 9, tzinfo=timezone.utc),
    "updated_at": datetime(2026, 10, 8, 9, tzinfo=timezone.utc),
}


def test_minimal_plan_defaults_to_draft_version_one_and_no_milestones() -> None:
    plan = CompetitionPlan(**MINIMAL_PLAN)

    assert plan.id == "plan-1"
    assert plan.student_id == "student-1"
    assert plan.competition_id == "competition-1"
    assert plan.edition_id == "edition-1"
    assert plan.status is PlanStatus.DRAFT
    assert plan.version == 1
    assert plan.milestones == ()
    assert plan.created_at == MINIMAL_PLAN["created_at"]
    assert plan.updated_at == MINIMAL_PLAN["updated_at"]


def test_complete_plan() -> None:
    milestones = [
        PlanMilestone(id="task-1", title="Read the rules"),
        PlanMilestone(
            id="task-2",
            title="Build prototype",
            dependency_ids=["task-1"],
            status=MilestoneStatus.IN_PROGRESS,
        ),
    ]
    created_at = datetime(2026, 10, 8, 9, tzinfo=timezone(timedelta(hours=8)))
    updated_at = datetime(2026, 10, 9, 18, tzinfo=timezone(timedelta(hours=8)))
    plan = CompetitionPlan(
        id="  plan-1  ",
        student_id="  student-1  ",
        competition_id="  competition-1  ",
        edition_id="  edition-1  ",
        status=PlanStatus.ACTIVE,
        version=2,
        milestones=milestones,
        created_at=created_at,
        updated_at=updated_at,
    )

    assert (plan.id, plan.student_id, plan.competition_id, plan.edition_id) == (
        "plan-1",
        "student-1",
        "competition-1",
        "edition-1",
    )
    assert plan.status is PlanStatus.ACTIVE
    assert plan.version == 2
    assert plan.milestones == tuple(milestones)
    assert plan.created_at == created_at
    assert plan.updated_at == updated_at


@pytest.mark.parametrize("field", ["id", "student_id", "competition_id", "edition_id"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_blank_identity_fields_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CompetitionPlan.model_validate({**MINIMAL_PLAN, field: value})


@pytest.mark.parametrize("status", list(PlanStatus))
def test_all_plan_statuses_are_accepted(status: PlanStatus) -> None:
    assert CompetitionPlan(**{**MINIMAL_PLAN, "status": status}).status is status


def test_unknown_plan_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="status"):
        CompetitionPlan(**{**MINIMAL_PLAN, "status": "pending"})


def test_explicit_version_one_is_accepted() -> None:
    assert CompetitionPlan(**{**MINIMAL_PLAN, "version": 1}).version == 1


@pytest.mark.parametrize("version", [0, -1, True, 1.5, "1"])
def test_invalid_version_is_rejected(version: object) -> None:
    with pytest.raises(ValidationError, match="version"):
        CompetitionPlan.model_validate({**MINIMAL_PLAN, "version": version})


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_naive_plan_datetime_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CompetitionPlan.model_validate(
            {**MINIMAL_PLAN, field: datetime(2026, 10, 8, 9)}
        )


def test_updated_at_can_equal_created_at() -> None:
    plan = CompetitionPlan(**MINIMAL_PLAN)

    assert plan.updated_at == plan.created_at


def test_update_order_uses_absolute_time() -> None:
    plan = CompetitionPlan(
        **{
            **MINIMAL_PLAN,
            "created_at": datetime(
                2026, 10, 8, 12, tzinfo=timezone(timedelta(hours=8))
            ),
            "updated_at": datetime(2026, 10, 8, 5, tzinfo=timezone.utc),
        }
    )

    assert plan.updated_at > plan.created_at


def test_updated_before_created_is_rejected() -> None:
    with pytest.raises(ValidationError, match="updated_at must be after"):
        CompetitionPlan(
            **{
                **MINIMAL_PLAN,
                "created_at": datetime(2026, 10, 9, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 10, 8, tzinfo=timezone.utc),
            }
        )


def test_duplicate_milestone_ids_are_rejected_after_trimming() -> None:
    with pytest.raises(ValidationError, match="duplicate ids"):
        CompetitionPlan(
            **{
                **MINIMAL_PLAN,
                "milestones": [
                    PlanMilestone(id=" task-1 ", title="Read the rules"),
                    PlanMilestone(id="task-1", title="Read the rules again"),
                ],
            }
        )


def test_references_and_dependencies_are_not_looked_up() -> None:
    plan = CompetitionPlan(
        **{
            **MINIMAL_PLAN,
            "student_id": "not-yet-stored",
            "competition_id": "unknown-competition",
            "edition_id": "unknown-edition",
            "milestones": [
                PlanMilestone(
                    id="task-1", title="Build prototype", dependency_ids=["unknown-task"]
                )
            ],
        }
    )

    assert plan.student_id == "not-yet-stored"
    assert plan.milestones[0].dependency_ids == ("unknown-task",)


def test_status_and_version_are_not_changed_by_milestones() -> None:
    plan = CompetitionPlan(
        **{
            **MINIMAL_PLAN,
            "milestones": [
                PlanMilestone(
                    id="task-1", title="Read the rules", status=MilestoneStatus.COMPLETED
                )
            ],
        }
    )

    assert plan.status is PlanStatus.DRAFT
    assert plan.version == 1


def test_default_milestone_lists_are_independent() -> None:
    first = CompetitionPlan(**MINIMAL_PLAN)
    second = CompetitionPlan(**MINIMAL_PLAN)

    with pytest.raises(AttributeError):
        first.milestones.append(PlanMilestone(id="task-1", title="Read the rules"))

    assert second.milestones == ()


def test_plan_serialization() -> None:
    plan = CompetitionPlan(
        **{
            **MINIMAL_PLAN,
            "milestones": [PlanMilestone(id="task-1", title="Read the rules")],
        }
    )
    expected = {
        "id": "plan-1",
        "student_id": "student-1",
        "competition_id": "competition-1",
        "edition_id": "edition-1",
        "track_id": None,
        "planning_horizon": None,
        "skill_gap_audit": None,
        "planning_needs": [],
        "status": "draft",
        "version": 1,
        "milestones": [
            {
                "id": "task-1",
                "title": "Read the rules",
                "description": None,
                "start_at": None,
                "due_at": None,
                "estimated_hours": None,
                "dependency_ids": [],
                "status": "pending",
                "source_need_id": None,
            }
        ],
        "created_at": "2026-10-08T09:00:00Z",
        "updated_at": "2026-10-08T09:00:00Z",
    }

    assert plan.model_dump(mode="json") == expected
    assert json.loads(plan.model_dump_json()) == expected


def test_plan_model_validate_round_trip() -> None:
    original = CompetitionPlan(
        **{
            **MINIMAL_PLAN,
            "status": PlanStatus.ACTIVE,
            "version": 3,
            "milestones": [
                PlanMilestone(id="task-1", title="Read the rules"),
                PlanMilestone(
                    id="task-2",
                    title="Build prototype",
                    dependency_ids=["task-1"],
                    status=MilestoneStatus.IN_PROGRESS,
                ),
            ],
        }
    )

    restored = CompetitionPlan.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.status is PlanStatus.ACTIVE
    assert isinstance(restored.milestones[0], PlanMilestone)
