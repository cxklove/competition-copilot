"""Controlled P11.1 scope/action evolution; normal constructors, no decision service."""

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
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2, T3 = T1 + timedelta(days=1), T1 + timedelta(days=2)
TARGET = CompetitionTarget(competition_id="competition", edition_id="edition")
SOURCE = SourceMetadata(
    source_url="https://example.invalid/mixed-contract", source_type="manual",
    observed_at=T1, verification_status="verified",
)
PLAN = CompetitionPlan(
    id="plan", student_id="student", competition_id="competition", edition_id="edition",
    track_id="a", created_at=T1, updated_at=T1,
    milestones=tuple(PlanMilestone(id=mid, title="Supplied milestone") for mid in ("m1", "m2", "m3")),
)


def analysis(kind, *, mids=(), whole=True, partial=False, key="one"):
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
            after=ObservedTrackMembership(
                state="known_value", value=("b",) if kind == "affected" else ("a", "b"),
                sources=(SOURCE,),
            ),
        )
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=TARGET, observed_at=T1),
        after=SnapshotReference(snapshot_id="after-" + key, target=TARGET, observed_at=T2),
        changes=(change,),
    )
    source = CompetitionEventEngine().interpret(diff, detected_at=T2)[0]
    result = CompetitionEventImpactAnalyzer().analyze(source, StudentProfile(id="student"), PLAN, evaluated_at=T2)
    if kind != "affected":
        return result
    # Supplied reference evidence for Contract construction; no milestone guess
    # or automatic scope derivation is performed by a P11.3 service.
    return EventImpactAnalysis(**{
        **result.model_dump(),
        "scope": AffectedPlanScope(
            plan_id=PLAN.id, state="partially_resolved" if partial else "known",
            whole_plan=whole, milestone_ids=mids,
        ),
        "evidence": (ReplanningEvidence(
            event_id=source.id, plan_id=PLAN.id, milestone_ids=mids,
            source_change_fields=source.source_change_fields,
        ),),
    })


def decision(impacts, *, outcome="replan", state="known", mids=(), whole=True,
             reasons=("confirmed_plan_impact",), **overrides):
    return ReplanningDecision(**{
        "impacts": impacts, "evaluated_at": T3, "outcome": outcome,
        "scope": AffectedPlanScope(plan_id=PLAN.id, state=state, milestone_ids=mids, whole_plan=whole),
        "reason_codes": reasons, **overrides,
    })


@pytest.mark.parametrize("state,whole,mids,remainder", [
    ("known", False, (), False),
    ("known", False, ("m1", "m2"), False),
    ("known", True, (), False),
    ("unresolved", False, (), True),
    ("partially_resolved", False, ("m1",), True),
    ("partially_resolved", True, (), True),
])
def test_four_scope_meanings_are_immutable_machine_distinct_and_json_stable(state, whole, mids, remainder):
    scope = AffectedPlanScope(plan_id="plan", state=state, whole_plan=whole, milestone_ids=mids)
    assert scope.has_unresolved_remainder == remainder
    assert AffectedPlanScope.model_validate_json(scope.model_dump_json()) == scope
    assert "has_unresolved_remainder" not in scope.model_dump()  # state is the only mechanism
    with pytest.raises(ValidationError):
        scope.state = "known"


def test_original_scope_payloads_parse_without_new_required_fields():
    for state in ("known", "unresolved"):
        payload = {"plan_id": "plan", "state": state, "whole_plan": False, "milestone_ids": []}
        assert AffectedPlanScope(**payload).model_dump(mode="json") == payload


@pytest.mark.parametrize("fields", [
    {"state": "partially_resolved"},
    {"state": "unresolved", "milestone_ids": ("m1",)},
    {"state": "unresolved", "whole_plan": True},
    {"state": "known", "has_unresolved_remainder": True},
])
def test_known_empty_with_unresolved_claim_or_inconsistent_state_rejects(fields):
    with pytest.raises(ValidationError):
        AffectedPlanScope(plan_id="plan", **fields)


def test_partial_milestone_refs_are_unique_canonical_not_set_order():
    first = AffectedPlanScope(plan_id="plan", state="partially_resolved", milestone_ids=("m2", "m1"))
    second = AffectedPlanScope(plan_id="plan", state="partially_resolved", milestone_ids=("m1", "m2"))
    assert first.model_dump_json() == second.model_dump_json()
    with pytest.raises(ValidationError):
        AffectedPlanScope(plan_id="plan", state="partially_resolved", milestone_ids=("m1", "m1"))


def test_block_reproduction_known_milestone_plus_uncertain_yields_replan_with_full_lineage():
    affected = analysis("affected", mids=("m1",), whole=False)
    uncertain = analysis("uncertain")
    result = decision(
        (affected, uncertain), state="partially_resolved", whole=False, mids=("m1",),
        reasons=("confirmed_impact_with_unresolved_remainder",),
    )
    assert result.outcome == "replan"
    assert result.scope.has_unresolved_remainder
    assert result.scope.milestone_ids == ("m1",)
    assert set(result.trigger_event_ids) == {affected.event.id, uncertain.event.id}
    assert {item.outcome.value for item in result.impacts} == {"affects_plan", "undetermined"}
    assert all(item.evidence for item in result.impacts)


def test_block_reproduction_whole_plan_impact_and_uncertainty_are_preserved():
    result = decision(
        (analysis("affected"), analysis("uncertain")), state="partially_resolved",
        reasons=("confirmed_impact_with_unresolved_remainder",),
    )
    assert result.scope.whole_plan and result.scope.has_unresolved_remainder


def test_multiple_known_scope_union_with_unresolved_remainder_is_valid_supplied_result():
    impacts = (
        analysis("affected", mids=("m1", "m2"), whole=False, key="one"),
        analysis("affected", mids=("m2", "m3"), whole=False, key="two"),
        analysis("uncertain"),
    )
    result = decision(
        impacts, state="partially_resolved", whole=False, mids=("m3", "m1", "m2"),
        reasons=("confirmed_impact_with_unresolved_remainder",),
    )
    assert result.scope.milestone_ids == ("m1", "m2", "m3")


def test_confirmed_partial_impact_replans_even_without_separate_uncertain_analysis():
    result = decision(
        (analysis("affected", mids=("m1",), whole=False, partial=True),),
        state="partially_resolved", mids=("m1",), whole=False,
        reasons=("confirmed_impact_with_unresolved_remainder",),
    )
    assert result.scope.has_unresolved_remainder


@pytest.mark.parametrize("kinds,outcome", [
    (("negative",), "keep_current_plan"),
    (("negative", "negative"), "keep_current_plan"),
    (("uncertain",), "undetermined"),
    (("negative", "uncertain"), "undetermined"),
    (("affected",), "replan"),
    (("affected", "negative"), "replan"),
])
def test_pure_cases_and_precedence_compatible_supplied_constructors(kinds, outcome):
    impacts = tuple(analysis(kind, key=str(index)) for index, kind in enumerate(kinds))
    result = decision(
        impacts, outcome=outcome, whole=outcome == "replan",
        state="unresolved" if outcome == "undetermined" else "known",
        reasons=({"replan": ("confirmed_plan_impact",),
                  "undetermined": ("impact_undetermined",),
                  "keep_current_plan": ("no_plan_impact",)}[outcome]),
    )
    assert result.outcome == outcome
    assert ReplanningDecision.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("kinds,outcome", [
    (("negative",), "replan"),
    (("uncertain",), "replan"),
    (("negative", "uncertain"), "replan"),
    (("uncertain",), "keep_current_plan"),
    (("affected",), "keep_current_plan"),
    (("affected", "uncertain"), "keep_current_plan"),
    (("affected",), "undetermined"),
    (("affected", "uncertain"), "undetermined"),
    (("negative",), "undetermined"),
])
def test_outcomes_that_violate_confirmed_uncertain_negative_precedence_reject(kinds, outcome):
    impacts = tuple(analysis(kind, key=str(index)) for index, kind in enumerate(kinds))
    with pytest.raises(ValidationError):
        decision(
            impacts, outcome=outcome, whole=outcome == "replan",
            state="unresolved" if outcome == "undetermined" else "known",
            reasons=({"replan": ("confirmed_plan_impact",),
                      "undetermined": ("impact_undetermined",),
                      "keep_current_plan": ("no_plan_impact",)}[outcome]),
        )


@pytest.mark.parametrize("overrides", [
    {"state": "known"},
    {"mids": ()},
    {"mids": ("m1", "m2")},
    {"whole": True},
    {"reasons": ("no_plan_impact",)},
    {"reasons": ("confirmed_plan_impact",)},
    {"reasons": ("confirmed_impact_with_unresolved_remainder", "no_plan_impact")},
])
def test_mixed_replan_cannot_drop_known_refs_uncertainty_or_claim_irrelevant(overrides):
    arguments = {
        "state": "partially_resolved", "mids": ("m1",), "whole": False,
        "reasons": ("confirmed_impact_with_unresolved_remainder",), **overrides,
    }
    with pytest.raises(ValidationError):
        decision((analysis("affected", mids=("m1",), whole=False), analysis("uncertain")), **arguments)


def test_order_independence_input_preservation_serialization_and_semantic_scope_difference():
    affected = analysis("affected", mids=("m1",), whole=False)
    uncertain = analysis("uncertain")
    negative = analysis("negative")
    impacts = (affected, uncertain, negative)
    original = tuple(item.model_dump_json() for item in impacts)
    arguments = {
        "state": "partially_resolved", "whole": False, "mids": ("m1",),
        "reasons": ("confirmed_impact_with_unresolved_remainder", "confirmed_plan_impact"),
    }
    first = decision(impacts, **arguments)
    second = decision(tuple(reversed(impacts)), **arguments)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.trigger_event_ids == tuple(sorted(item.event.id for item in impacts))
    assert original == tuple(item.model_dump_json() for item in impacts)
    assert ReplanningDecision.model_validate(first.model_dump(mode="json")) == first
    resolved = decision((affected,), mids=("m1",), whole=False)
    assert resolved.model_dump_json() != first.model_dump_json()
    for obj in (first, first.scope, first.impacts[0], first.impacts[0].evidence[0]):
        with pytest.raises(ValidationError):
            obj.extra = "mutation"


def test_duplicates_empty_input_and_unsupported_milestone_claims_reject():
    affected = analysis("affected")
    for impacts in ((), (affected, affected)):
        with pytest.raises(ValidationError):
            decision(impacts)
    with pytest.raises(ValidationError):
        analysis("affected", mids=("missing",), whole=False)
    with pytest.raises(ValidationError):
        EventImpactAnalysis(**{
            **affected.model_dump(),
            "scope": AffectedPlanScope(plan_id="plan", state="known", milestone_ids=("m1",)),
        })  # milestone claim lacks reference evidence


def test_old_resolved_replan_reason_remains_valid_but_mixed_claim_requires_mixed_reason():
    affected = analysis("affected")
    assert decision((affected,), reasons=("structural_revision_supported",)).outcome == "replan"
    with pytest.raises(ValidationError):
        decision((affected,), reasons=("confirmed_impact_with_unresolved_remainder",))
    with pytest.raises(ValidationError):
        decision((affected, analysis("uncertain")), state="partially_resolved", reasons=("structural_revision_supported",))
