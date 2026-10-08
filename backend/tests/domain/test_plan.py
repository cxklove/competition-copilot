import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.plan import MilestoneStatus, PlanMilestone


def test_minimal_milestone() -> None:
    milestone = PlanMilestone(id="  task-1  ", title="  Read the rules  ")

    assert milestone.id == "task-1"
    assert milestone.title == "Read the rules"
    assert milestone.description is None
    assert milestone.start_at is None
    assert milestone.due_at is None
    assert milestone.estimated_hours is None
    assert milestone.dependency_ids == []
    assert milestone.status is MilestoneStatus.PENDING


def test_complete_milestone() -> None:
    start_at = datetime(2026, 10, 8, 9, tzinfo=timezone(timedelta(hours=8)))
    due_at = datetime(2026, 10, 9, 18, tzinfo=timezone(timedelta(hours=8)))
    milestone = PlanMilestone(
        id="task-2",
        title="Build prototype",
        description="  Implement the first version.  ",
        start_at=start_at,
        due_at=due_at,
        estimated_hours=12.5,
        dependency_ids=["task-1"],
        status=MilestoneStatus.IN_PROGRESS,
    )

    assert milestone.description == "Implement the first version."
    assert milestone.start_at == start_at
    assert milestone.due_at == due_at
    assert milestone.estimated_hours == 12.5
    assert milestone.dependency_ids == ["task-1"]
    assert milestone.status is MilestoneStatus.IN_PROGRESS


@pytest.mark.parametrize("field", ["id", "title"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_blank_id_or_title_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        PlanMilestone.model_validate(
            {"id": "task-1", "title": "Read the rules", field: value}
        )


@pytest.mark.parametrize("description", ["", " \t\n "])
def test_blank_description_is_rejected(description: str) -> None:
    with pytest.raises(ValidationError, match="description"):
        PlanMilestone(id="task-1", title="Read the rules", description=description)


@pytest.mark.parametrize("field", ["start_at", "due_at"])
def test_naive_datetime_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        PlanMilestone.model_validate(
            {"id": "task-1", "title": "Read the rules", field: datetime(2026, 10, 8)}
        )


def test_dates_compare_absolute_time_across_timezones() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone(timedelta(hours=8)))
    due_at = datetime(2026, 10, 8, 5, tzinfo=timezone.utc)

    assert PlanMilestone(
        id="task-1", title="Read the rules", start_at=start_at, due_at=due_at
    ).due_at == due_at


def test_equal_start_and_due_are_allowed() -> None:
    instant = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    milestone = PlanMilestone(
        id="task-1", title="Read the rules", start_at=instant, due_at=instant
    )

    assert milestone.start_at == milestone.due_at


def test_start_after_due_is_rejected() -> None:
    with pytest.raises(ValidationError, match="start_at must be before"):
        PlanMilestone(
            id="task-1",
            title="Read the rules",
            start_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
            due_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("hours", [None, 0, 2.5])
def test_valid_estimated_hours(hours: float | None) -> None:
    milestone = PlanMilestone(
        id="task-1", title="Read the rules", estimated_hours=hours
    )

    assert milestone.estimated_hours == hours


@pytest.mark.parametrize("hours", [-0.1, float("nan"), float("inf")])
def test_invalid_estimated_hours_are_rejected(hours: float) -> None:
    with pytest.raises(ValidationError, match="estimated_hours"):
        PlanMilestone(id="task-1", title="Read the rules", estimated_hours=hours)


def test_dependency_ids_are_trimmed_deduplicated_and_ordered() -> None:
    milestone = PlanMilestone(
        id="task-3",
        title="Submit prototype",
        dependency_ids=["  task-1  ", "task-2", "task-1", "Task-1"],
    )

    assert milestone.dependency_ids == ["task-1", "task-2", "Task-1"]


@pytest.mark.parametrize("dependency_id", ["", " \t\n "])
def test_blank_dependency_id_is_rejected(dependency_id: str) -> None:
    with pytest.raises(ValidationError, match="dependency_ids"):
        PlanMilestone(
            id="task-2",
            title="Build prototype",
            dependency_ids=["task-1", dependency_id],
        )


def test_self_dependency_is_rejected_after_trimming() -> None:
    with pytest.raises(ValidationError, match="dependency_ids"):
        PlanMilestone(
            id="  task-1  ",
            title="Read the rules",
            dependency_ids=["  task-1  "],
        )


def test_dependency_existence_is_not_checked() -> None:
    milestone = PlanMilestone(
        id="task-2", title="Build prototype", dependency_ids=["not-yet-stored"]
    )

    assert milestone.dependency_ids == ["not-yet-stored"]


@pytest.mark.parametrize("status", list(MilestoneStatus))
def test_all_statuses_are_accepted(status: MilestoneStatus) -> None:
    assert PlanMilestone(id="task-1", title="Read the rules", status=status).status is (
        status
    )


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="status"):
        PlanMilestone(id="task-1", title="Read the rules", status="cancelled")


def test_serialization() -> None:
    milestone = PlanMilestone(
        id="task-2",
        title="Build prototype",
        start_at=datetime(2026, 10, 8, 9, tzinfo=timezone.utc),
        due_at=datetime(2026, 10, 9, 18, tzinfo=timezone.utc),
        estimated_hours=0,
        dependency_ids=[" task-1 ", "task-1"],
        status=MilestoneStatus.COMPLETED,
    )
    expected = {
        "id": "task-2",
        "title": "Build prototype",
        "description": None,
        "start_at": "2026-10-08T09:00:00Z",
        "due_at": "2026-10-09T18:00:00Z",
        "estimated_hours": 0.0,
        "dependency_ids": ["task-1"],
        "status": "completed",
    }

    assert milestone.model_dump(mode="json") == expected
    assert json.loads(milestone.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = PlanMilestone(
        id="task-2",
        title="Build prototype",
        description="Create a demo.",
        start_at=datetime(2026, 10, 8, 9, tzinfo=timezone(timedelta(hours=8))),
        due_at=datetime(2026, 10, 9, 18, tzinfo=timezone(timedelta(hours=8))),
        estimated_hours=12.5,
        dependency_ids=["task-1"],
        status=MilestoneStatus.IN_PROGRESS,
    )

    restored = PlanMilestone.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.status is MilestoneStatus.IN_PROGRESS
