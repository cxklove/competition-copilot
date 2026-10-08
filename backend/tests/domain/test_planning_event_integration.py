import json
from datetime import datetime, timedelta, timezone

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import DecisionResult, DecisionStatus, Evidence
from competition_copilot.domain.event import CompetitionEvent, CompetitionEventType
from competition_copilot.domain.plan import (
    CompetitionPlan,
    MilestoneStatus,
    PlanMilestone,
    PlanStatus,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.student import EducationLevel, StudentProfile


def test_planning_event_and_decision_models_form_an_in_memory_scenario() -> None:
    student = StudentProfile(id="student-1", education_level=EducationLevel.GRADUATE)
    competition = Competition(id="huawei-ict", name="Huawei ICT Competition")
    source = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.MANUAL,
        observed_at=datetime(2026, 10, 9, 20, tzinfo=timezone(timedelta(hours=8))),
        verification_status=VerificationStatus.VERIFIED,
    )
    edition = CompetitionEdition(
        id="huawei-ict-2026",
        competition_id=competition.id,
        year=2026,
        name="2026 edition",
        source=source,
    )
    track = CompetitionTrack(
        id="huawei-ict-2026-innovation",
        edition_id=edition.id,
        name="Innovation",
        source=source,
    )
    review_rules = PlanMilestone(
        id="review-rules",
        title="Review rules",
        start_at=datetime(2026, 10, 8, 9, tzinfo=timezone.utc),
        due_at=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
    )
    prepare_proposal = PlanMilestone(
        id="prepare-proposal",
        title="Prepare proposal",
        start_at=datetime(2026, 10, 9, 9, tzinfo=timezone.utc),
        due_at=datetime(2026, 10, 15, 18, tzinfo=timezone.utc),
        dependency_ids=[review_rules.id],
    )
    plan = CompetitionPlan(
        id="plan-1",
        student_id=student.id,
        competition_id=competition.id,
        edition_id=edition.id,
        milestones=[review_rules, prepare_proposal],
        created_at=datetime(2026, 10, 8, 8, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 8, 8, tzinfo=timezone.utc),
    )
    plan_before_event = plan.model_dump(mode="json")
    event = CompetitionEvent(
        id="deadline-change-1",
        competition_id=competition.id,
        edition_id=edition.id,
        event_type=CompetitionEventType.DEADLINE_CHANGED,
        occurred_at=datetime(2026, 10, 9, 10, tzinfo=timezone.utc),
        observed_at=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        source=source,
        description="Deadline change recorded for this edition.",
    )
    evidence = Evidence(
        code="deadline-change-recorded",
        message="A deadline change event was recorded.",
        source=source,
        field="event_type",
        value=event.event_type.value,
    )
    decision = DecisionResult(
        status=DecisionStatus.UNKNOWN,
        reason_codes=["no-rule-evaluated"],
        evidence=[evidence],
    )

    assert edition.competition_id == competition.id == "huawei-ict"
    assert track.edition_id == edition.id == "huawei-ict-2026"
    assert track.id == "huawei-ict-2026-innovation"
    assert plan.student_id == student.id == "student-1"
    assert plan.competition_id == event.competition_id == competition.id
    assert plan.edition_id == event.edition_id == edition.id
    assert [milestone.id for milestone in plan.milestones] == [
        review_rules.id,
        prepare_proposal.id,
    ]
    assert prepare_proposal.dependency_ids == [review_rules.id]
    assert evidence.source is source
    assert decision.evidence == [evidence]

    for value in (
        source.observed_at,
        review_rules.start_at,
        review_rules.due_at,
        prepare_proposal.start_at,
        prepare_proposal.due_at,
        plan.created_at,
        plan.updated_at,
        event.occurred_at,
        event.observed_at,
    ):
        assert value is not None
        assert value.utcoffset() is not None

    for model in (
        student,
        competition,
        edition,
        track,
        source,
        evidence,
        decision,
        review_rules,
        prepare_proposal,
        plan,
        event,
    ):
        payload = model.model_dump(mode="json")
        assert json.loads(json.dumps(payload)) == payload
        assert type(model).model_validate(payload) == model

    assert plan.model_dump(mode="json") == plan_before_event
    assert plan.status is PlanStatus.DRAFT
    assert plan.version == 1
    assert [milestone.status for milestone in plan.milestones] == [
        MilestoneStatus.PENDING,
        MilestoneStatus.PENDING,
    ]
    assert decision.status is DecisionStatus.UNKNOWN
    assert decision.reason_codes == ["no-rule-evaluated"]
