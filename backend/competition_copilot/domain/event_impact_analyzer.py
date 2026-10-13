"""Deterministic Event-to-Plan impact only; no replanning or hidden facts."""

from datetime import datetime

from pydantic import AwareDatetime, TypeAdapter

from competition_copilot.domain.digital_twin import ObservationState
from competition_copilot.domain.event import CompetitionEvent, CompetitionEventType
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    ImpactOutcome,
    PlanReference,
    ReplanningEvidence,
    ReplanningReasonCode,
    ScopeState,
)
from competition_copilot.domain.student import StudentProfile


class CompetitionEventImpactAnalyzer:
    """Use supplied P10 lineage and exact P8 target, never milestone/profile prose.

    P11.1 explicitly treats target membership addition/removal as positive impact.
    Whole-plan target impact identifies no individual milestone dependency.
    Missing represented dependency remains unresolved, including windows with dates.
    """

    def analyze(
        self, event: CompetitionEvent, student: StudentProfile, plan: CompetitionPlan,
        *, evaluated_at: datetime,
    ) -> EventImpactAnalysis:
        for value, expected in (
            (event, CompetitionEvent), (student, StudentProfile), (plan, CompetitionPlan),
        ):
            if not isinstance(value, expected):
                raise TypeError(f"Expected validated {expected.__name__}")
        event = CompetitionEvent.model_validate(event)
        # StudentProfile is mutable and does not revalidate model instances.
        # Validate a detached projection instead; retain only identity in output.
        student = StudentProfile.model_validate(student.model_dump())
        plan = CompetitionPlan.model_validate(plan)
        if not isinstance(evaluated_at, datetime):
            raise TypeError("evaluated_at must be an explicit aware datetime")
        evaluated_at = TypeAdapter(AwareDatetime).validate_python(evaluated_at)
        if student.id != plan.student_id:
            raise ValueError("Student identity must match the supplied Plan")
        if event.source_diff is None:
            raise ValueError("Impact requires a P10 Diff-backed Event")

        target = event.target
        mismatch = (
            target.competition_id != plan.competition_id
            or target.edition_id != plan.edition_id
            or (target.track_id is not None and plan.track_id is not None
                and target.track_id != plan.track_id)
        )
        outcome = ImpactOutcome.UNDETERMINED
        reason = ReplanningReasonCode.PLAN_DEPENDENCY_NOT_REPRESENTED
        if mismatch:
            outcome = ImpactOutcome.NO_PLAN_IMPACT
            reason = ReplanningReasonCode.TARGET_MISMATCH
        elif event.event_type == CompetitionEventType.OBSERVATION_COVERAGE_CHANGED:
            reason = ReplanningReasonCode.OBSERVATION_ONLY_EVENT
        elif event.event_type == CompetitionEventType.TRACK_MEMBERSHIP_CHANGED:
            change = event.source_changes[0]
            before, after = change.before.value or (), change.after.value or ()
            track = plan.track_id
            if track is not None:
                if track in before and track not in after:
                    outcome = ImpactOutcome.AFFECTS_PLAN
                    reason = ReplanningReasonCode.TARGET_TRACK_REMOVED
                elif track not in before and track in after:
                    outcome = ImpactOutcome.AFFECTS_PLAN
                    reason = ReplanningReasonCode.PLAN_DEPENDENCY_MATCHED
                elif (
                    change.before.state == ObservationState.KNOWN_VALUE
                    and change.after.state == ObservationState.KNOWN_VALUE
                    and track in before and track in after
                ):
                    outcome = ImpactOutcome.NO_PLAN_IMPACT
                    reason = ReplanningReasonCode.UNRELATED_TRACK_CHANGE

        # Normal frozen constructor validates target/outcome/reason/evidence.
        return EventImpactAnalysis(
            event=event, plan=PlanReference.from_plan(plan), student_id=student.id,
            evaluated_at=evaluated_at, outcome=outcome, reason_codes=(reason,),
            scope=AffectedPlanScope(
                plan_id=plan.id,
                state=ScopeState.UNRESOLVED if outcome == ImpactOutcome.UNDETERMINED else ScopeState.KNOWN,
                whole_plan=outcome == ImpactOutcome.AFFECTS_PLAN,
            ),
            evidence=(ReplanningEvidence(
                event_id=event.id, plan_id=plan.id,
                source_change_fields=event.source_change_fields,
            ),),
        )
