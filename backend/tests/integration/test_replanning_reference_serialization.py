"""Reuse real P8 COMAP chain, retaining typed source_item/evidence URLs."""

import socket
from datetime import timedelta

import pytest
from pydantic import HttpUrl

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservedInstant,
    SnapshotDiff,
    SnapshotReference,
    WindowEndpointChange,
)
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.plan_revision_service import (
    PlanRevisionResult,
    PlanRevisionService,
)
from competition_copilot.domain.replanning import (
    EventImpactAnalysis,
    PlanReference,
    ReplanningDecision,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.replanning_input import ReplanningInput
from competition_copilot.domain.source_metadata import SourceMetadata
from tests.integration.test_p8_real_planning_integration import (
    BaselineCompetitionPlanBuilder,
    PlanningInputDeriver,
    SkillGapEngine,
    run_pipeline,
)
from tests.integration.test_p8_real_planning_integration import (
    offline_read_only_data_boundary as offline_read_only_data_boundary,
)
from tests.integration.test_p8_real_planning_integration import (
    real_inputs as real_inputs,
)


@pytest.fixture(autouse=True)
def reject_dns(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Typed URL compatibility must never resolve URL over network")
    monkeypatch.setattr(socket, "getaddrinfo", fail)


@pytest.mark.parametrize("known_student", [True, False])
def test_real_sourced_comap_plan_reference_analyzer_and_lineage(real_inputs, known_student):
    services = SkillGapEngine(), PlanningInputDeriver(), BaselineCompetitionPlanBuilder()
    context, _, _, plan = run_pipeline(real_inputs, known_student, services)
    original = plan.model_dump_json()
    item = next(need.source_item for need in plan.planning_needs if need.source_item is not None)
    url = item.requirement.presence_evidence[0].source.source_url
    assert isinstance(url, HttpUrl)
    assert plan.model_dump_json() and item.requirement.presence_evidence
    reference = PlanReference.from_plan(plan)
    parsed = CompetitionPlan.model_validate_json(original)
    reconstructed = CompetitionPlan(**plan.model_dump())
    assert reference == PlanReference.from_plan(parsed) == PlanReference.from_plan(reconstructed)
    assert PlanReference.model_validate_json(reference.model_dump_json()) == reference
    t0 = plan.updated_at
    observed, evaluated, decided = (t0 + timedelta(hours=n) for n in (1, 2, 3))
    source = SourceMetadata(source_url="https://example.invalid/test-only-sourced-plan-window",
        source_type="manual", observed_at=observed, verification_status="verified")
    target = CompetitionTarget(competition_id=plan.competition_id, edition_id=plan.edition_id)
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="test-only-sourced-before", target=target, observed_at=t0),
        after=SnapshotReference(snapshot_id="test-only-sourced-after", target=target, observed_at=observed),
        changes=(WindowEndpointChange(field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=observed, sources=(source,)),
            after=ObservedInstant(state="known_value", value=evaluated, sources=(source,))),),
    )
    event = CompetitionEventEngine().interpret(diff, detected_at=observed)[0]
    analyzer = CompetitionEventImpactAnalyzer()
    first = analyzer.analyze(event, context.student_profile, plan, evaluated_at=evaluated)
    second = analyzer.analyze(event, context.student_profile, parsed, evaluated_at=evaluated)
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert first.plan == reference and first.outcome == "undetermined"
    assert "plan_dependency_not_represented" in first.reason_codes
    assert all(e.plan_id == plan.id and e.event_id == event.id for e in first.evidence)
    decision = ReplanningDecisionService().decide((first,), plan, evaluated_at=decided)
    assert decision.impacts[0].plan == reference and decision.trigger_event_ids == (event.id,)
    assert decision.outcome == "undetermined"
    supplied = ReplanningInput(before=plan, decision=decision, supplied_at=decided, status="unresolved")
    receipt = PlanRevisionService().revise(plan, supplied, executed_at=decided)
    assert receipt.after == plan and receipt.plan_diff.changes == ()
    assert receipt.plan_diff.status_change is None and receipt.plan_diff.decision == decision
    for model, model_type in ((first, EventImpactAnalysis), (decision, ReplanningDecision),
                              (supplied, ReplanningInput), (receipt, PlanRevisionResult)):
        parsed_output = model_type.model_validate_json(model.model_dump_json())
        assert parsed_output == model and parsed_output.model_dump_json() == model.model_dump_json()
    assert PlanReference.from_plan(plan).model_dump_json() == reference.model_dump_json()
    assert plan.model_dump_json() == original and plan.planning_needs[0].source_item is not None
