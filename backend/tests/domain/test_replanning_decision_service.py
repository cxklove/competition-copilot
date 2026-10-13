"""P11.3 synthesis only; supplied milestone scopes are controlled Contract fixtures."""

import itertools
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservedInstant,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
    TrackMembershipChange,
    WindowEndpointChange,
)
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    ReplanningDecision,
    ReplanningEvidence,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2, T3 = T1 + timedelta(days=1), T1 + timedelta(days=2)
SOURCE = SourceMetadata(
    source_url="https://example.invalid/decision-fixture", source_type="manual",
    observed_at=T1, verification_status="verified",
)


def plan(**overrides):
    return CompetitionPlan(**{
        "id": "plan", "student_id": "student", "competition_id": "competition",
        "edition_id": "edition", "track_id": "a", "created_at": T1, "updated_at": T1,
        "milestones": tuple(PlanMilestone(id=mid, title="Caller supplied task") for mid in ("m1", "m2", "m3")),
        **overrides,
    })


def analysis(kind, *, key="one", current=None, mids=(), whole=True, partial=False):
    current = current or plan()
    target = CompetitionTarget(competition_id=current.competition_id, edition_id=current.edition_id)
    if kind == "uncertain":
        change = WindowEndpointChange(
            field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=T1, sources=(SOURCE,)),
            after=ObservedInstant(state="known_value", value=T2, sources=(SOURCE,)),
        )
    else:
        change = TrackMembershipChange(
            field="track_membership", kind="value_changed",
            before=ObservedTrackMembership(state="known_value", value=("a",), sources=(SOURCE,)),
            after=ObservedTrackMembership(state="known_value", value=("b",) if kind == "affected" else ("a", "b"), sources=(SOURCE,)),
        )
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id="after-" + key, target=target, observed_at=T2),
        changes=(change,),
    )
    event = CompetitionEventEngine().interpret(diff, detected_at=T2)[0]
    result = CompetitionEventImpactAnalyzer().analyze(event, StudentProfile(id=current.student_id), current, evaluated_at=T2)
    if kind != "affected" or (whole and not mids and not partial):
        return result
    return EventImpactAnalysis(**{
        **result.model_dump(),
        "scope": AffectedPlanScope(
            plan_id=current.id, state="partially_resolved" if partial else "known",
            whole_plan=whole, milestone_ids=mids,
        ),
        "evidence": (ReplanningEvidence(
            event_id=event.id, plan_id=current.id, milestone_ids=mids,
            source_change_fields=event.source_change_fields,
        ),),
    })


def decide(impacts, current=None, *, time=T3):
    return ReplanningDecisionService().decide(impacts, current or plan(), evaluated_at=time)


@pytest.mark.parametrize("kinds,outcome,state,reason", [
    (("negative", "negative"), "keep_current_plan", "known", "no_plan_impact"),
    (("affected",), "replan", "known", "confirmed_plan_impact"),
    (("uncertain",), "undetermined", "unresolved", "impact_undetermined"),
    (("negative", "uncertain"), "undetermined", "unresolved", "impact_undetermined"),
    (("affected", "negative"), "replan", "known", "confirmed_plan_impact"),
    (("affected", "uncertain"), "replan", "partially_resolved", "confirmed_impact_with_unresolved_remainder"),
    (("affected", "negative", "uncertain"), "replan", "partially_resolved", "confirmed_impact_with_unresolved_remainder"),
])
def test_precedence_scope_reason_and_all_lineage(kinds, outcome, state, reason):
    impacts = tuple(analysis(kind, key=str(index)) for index, kind in enumerate(kinds))
    result = decide(impacts)
    assert result.outcome == outcome
    assert result.scope.state == state
    assert tuple(code.value for code in result.reason_codes) == (reason,)
    assert result.scope.whole_plan == (outcome == "replan")
    assert result.scope.milestone_ids == ()
    assert result.trigger_event_ids == tuple(sorted(item.event.id for item in impacts))
    assert result.impacts == tuple(sorted(impacts, key=lambda item: item.event.id))
    assert result.impacts[0].plan.plan_id == result.scope.plan_id == "plan"
    assert ReplanningDecision.model_validate_json(result.model_dump_json()) == result
    assert ReplanningDecision.model_validate(result.model_dump(mode="json")) == result


@pytest.mark.parametrize("with_uncertain", [False, True])
def test_known_scope_union_with_or_without_unresolved_remainder(with_uncertain):
    impacts = (
        analysis("affected", key="a", mids=("m1", "m2"), whole=False),
        analysis("affected", key="b", mids=("m2", "m3"), whole=False),
    )
    if with_uncertain:
        impacts += (analysis("uncertain"),)
    result = decide(impacts)
    assert result.scope.milestone_ids == ("m1", "m2", "m3")
    assert result.scope.has_unresolved_remainder == with_uncertain
    assert not result.scope.whole_plan
    assert result.scope.state == ("partially_resolved" if with_uncertain else "known")


def test_known_milestone_and_whole_plan_markers_survive_uncertainty():
    known = analysis("affected", mids=("m1",), whole=False)
    uncertain = analysis("uncertain")
    result = decide((known, uncertain))
    assert result.scope.milestone_ids == ("m1",)
    assert result.scope.has_unresolved_remainder
    whole = analysis("affected", key="whole")
    result = decide((whole, known, uncertain))
    assert result.scope.whole_plan and result.scope.has_unresolved_remainder
    assert result.scope.milestone_ids == ("m1",)


def test_partial_confirmed_scope_remains_partial_without_an_uncertain_analysis():
    result = decide((analysis("affected", mids=("m1",), whole=False, partial=True),))
    assert result.outcome == "replan"
    assert result.scope.state == "partially_resolved"
    assert result.scope.milestone_ids == ("m1",)


def test_known_empty_is_distinct_from_pure_unresolved():
    keep = decide((analysis("negative"),))
    unknown = decide((analysis("uncertain"),))
    assert keep.scope.milestone_ids == unknown.scope.milestone_ids == ()
    assert keep.scope.state != unknown.scope.state
    assert not keep.scope.has_unresolved_remainder
    assert unknown.scope.has_unresolved_remainder


@pytest.mark.parametrize("override", [
    {"id": "another"}, {"student_id": "another"}, {"edition_id": "another"},
    {"track_id": "b"}, {"version": 2}, {"updated_at": T2},
    {"milestones": (PlanMilestone(id="m1", title="Changed content same Plan ID"),)},
])
def test_exact_caller_plan_context_conflicts_reject(override):
    first = analysis("uncertain")
    with pytest.raises(ValueError, match="exact supplied Plan"):
        decide((first,), plan(**override))


def test_impacts_from_different_plans_reject_without_cross_plan_aggregation():
    with pytest.raises(ValueError, match="exact supplied Plan"):
        decide((analysis("uncertain"), analysis("uncertain", current=plan(id="other"), key="other")))


def test_exact_duplicates_are_batch_local_normalized_not_cross_call_suppressed():
    a, b = analysis("affected"), analysis("uncertain")
    service = ReplanningDecisionService()
    expected = service.decide((a, b), plan(), evaluated_at=T3)
    repeated = service.decide((a, a, b, b), plan(), evaluated_at=T3)
    assert repeated.model_dump_json() == expected.model_dump_json()
    assert service.decide((a, b), plan(), evaluated_at=T3) == expected
    assert len(repeated.impacts) == 2


def test_same_trigger_id_conflicting_analysis_content_rejects_normal_constructors():
    original = analysis("affected")
    changed_time = EventImpactAnalysis(**{**original.model_dump(), "evaluated_at": T3})
    changed_scope = analysis("affected", mids=("m1",), whole=False)
    assert original.event.id == changed_time.event.id == changed_scope.event.id
    for conflict in (changed_time, changed_scope):
        with pytest.raises(ValueError, match="conflicting analyses"):
            decide((original, conflict))
        with pytest.raises(ValueError, match="conflicting analyses"):
            decide((conflict, original))


def test_order_independence_canonical_lineage_and_input_preservation():
    impacts = (analysis("affected"), analysis("negative"), analysis("uncertain"))
    current = plan()
    before = (tuple(item.model_dump_json() for item in impacts), current.model_dump_json())
    outputs = {decide(order, current).model_dump_json() for order in itertools.permutations(impacts)}
    assert len(outputs) == 1
    assert before == (tuple(item.model_dump_json() for item in impacts), current.model_dump_json())
    result = decide(impacts)
    for obj in (result, result.scope, result.impacts[0], result.impacts[0].evidence[0]):
        with pytest.raises(ValidationError):
            obj.extra = "mutation"
    with pytest.raises(TypeError):
        result.model_copy(update={})


def test_equivalent_aware_instants_have_canonical_representation_not_first_input_wins():
    original = analysis("uncertain")
    equivalent = EventImpactAnalysis(**{
        **original.model_dump(),
        "evaluated_at": original.evaluated_at.astimezone(timezone(timedelta(hours=8))),
    })
    assert original == equivalent
    assert original.model_dump_json() != equivalent.model_dump_json()
    assert decide((original, equivalent)).model_dump_json() == decide((equivalent, original)).model_dump_json()


def test_no_impact_reanalysis_or_milestone_prose_guessing(monkeypatch):
    current = plan(milestones=(PlanMilestone(id="m1", title="报名 deadline track competition"),))
    supplied = analysis("uncertain", current=current)

    def forbidden(*args, **kwargs):
        pytest.fail("Decision service must not rerun impact or Event mapping")

    monkeypatch.setattr(CompetitionEventImpactAnalyzer, "analyze", forbidden)
    monkeypatch.setattr(CompetitionEventEngine, "interpret", forbidden)
    result = decide((supplied,), current)
    assert result.outcome == "undetermined"
    assert result.scope.milestone_ids == ()


@pytest.mark.parametrize("time", [T1, T3.replace(tzinfo=None)])
def test_explicit_time_must_be_aware_and_not_precede_analyses(time):
    with pytest.raises(ValidationError):
        decide((analysis("negative"),), time=time)


def test_empty_mutable_untyped_inputs_and_missing_time_reject():
    supplied = analysis("uncertain")
    with pytest.raises(ValueError, match="Empty"):
        decide(())
    with pytest.raises(TypeError):
        decide([supplied])
    with pytest.raises(TypeError):
        decide((supplied.model_dump(),))
    with pytest.raises(TypeError):
        ReplanningDecisionService().decide((supplied,), plan())
    with pytest.raises(TypeError):
        ReplanningDecisionService().decide((supplied,), plan().model_dump(), evaluated_at=T3)
