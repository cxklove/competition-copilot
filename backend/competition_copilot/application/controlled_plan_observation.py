"""Explicit demo observation orchestration, never official competition history.

No cancellation mapping: only the reviewed instruction preparation policy decides
whether the resulting authoritative Decision supports an operation proposal.
"""

import json
from datetime import datetime
from hashlib import sha256
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.instruction_preparation import (
    PlanRevisionProposal,
    TargetTrackRemovedCancellationPolicy,
)
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    ObservedTrackMembership,
    SnapshotDiff,
)
from competition_copilot.domain.event import CompetitionEvent
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import (
    EventImpactAnalysis,
    ReplanningDecision,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.source_metadata import SourceMetadata, SourceType
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.competition import CompetitionRepository


class ControlledPlanObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_kind: Literal["CONTROLLED DEMO OBSERVATION"]
    notice: Literal["Demo-only manual scenario, not an official Huawei change."]
    target: CompetitionTarget
    before_membership: tuple[str, ...]
    after_membership: tuple[str, ...]
    source: SourceMetadata

    @model_validator(mode="after")
    def declared_demo(self) -> Self:
        if self.target.track_id is None or self.source.source_type != SourceType.MANUAL:
            raise ValueError("Controlled observation requires explicit track target and manual source")
        if (len(set(self.before_membership)) != len(self.before_membership)
            or len(set(self.after_membership)) != len(self.after_membership)):
            raise ValueError("Duplicate controlled membership")
        return self


class ControlledRevisionPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    before_snapshot: CompetitionSnapshot
    after_snapshot: CompetitionSnapshot
    source_diff: SnapshotDiff
    events: tuple[CompetitionEvent, ...]
    impacts: tuple[EventImpactAnalysis, ...]
    decision: ReplanningDecision
    proposal: PlanRevisionProposal


def _snapshot(target, state, observed_at, label):
    body = {"target": target.model_dump(mode="json"), "state": state.model_dump(mode="json"),
            "observed_at": observed_at.isoformat(), "controlled_phase": label}
    identity = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CompetitionSnapshot(snapshot_id="controlled-demo-snapshot-v1:" + identity,
        target=target, dynamic_state=state, observed_at=observed_at)


class ControlledPlanRevisionPreparer:
    def __init__(self, repository: CompetitionRepository, observation: ControlledPlanObservation):
        self.repository, self.observation = repository, observation
        self._history: dict[str, ControlledRevisionPreparation] = {}

    def history(self) -> tuple[ControlledRevisionPreparation, ...]:
        """Per-host retained manual snapshots/diff/events; no durable storage."""
        return tuple(self._history[key] for key in sorted(self._history))

    def prepare(self, plan: CompetitionPlan, student: StudentProfile, *,
                observed_at: datetime) -> ControlledRevisionPreparation | None:
        observation = self.observation
        if student.id != plan.student_id:
            raise ValueError("Controlled observation student does not own Plan")
        target = CompetitionTarget(competition_id=plan.competition_id, edition_id=plan.edition_id,
                                   track_id=plan.track_id)
        if target != observation.target:
            return None  # Configured demo observation does not apply to another target.
        track = self.repository.get_track(target.track_id)
        if track.edition_id != target.edition_id:
            raise ValueError("Controlled target track parent mismatch")
        baseline = CompetitionSnapshotBuilder(self.repository).build(CompetitionTarget(
            competition_id=target.competition_id, edition_id=target.edition_id), observed_at)
        if set(baseline.dynamic_state.track_membership.value or ()) != set(observation.before_membership):
            raise ValueError("Controlled before observation does not match Repository membership")
        # Exact track scope is independently declared by the reviewed demo input.
        # These are NEW manual snapshots, never relabelled official baseline facts.
        snapshots = []
        for label, members in (("before", observation.before_membership), ("after", observation.after_membership)):
            state = CompetitionDynamicState(**{**baseline.dynamic_state.model_dump(),
                "track_membership": ObservedTrackMembership(state="known_value", value=members,
                                                           sources=(observation.source,))})
            snapshots.append(_snapshot(target, state, observed_at, label))
        before, after = snapshots
        diff = SnapshotDiffEngine().compare(before, after)
        events = CompetitionEventEngine().interpret(diff, detected_at=observed_at)
        if not events:
            return None
        impacts = tuple(CompetitionEventImpactAnalyzer().analyze(event, student, plan,
            evaluated_at=observed_at) for event in events)
        decision = ReplanningDecisionService().decide(impacts, plan, evaluated_at=observed_at)
        result = TargetTrackRemovedCancellationPolicy().prepare(plan, decision, prepared_at=observed_at)
        if result.proposal is None:
            return None
        prepared = ControlledRevisionPreparation(before_snapshot=before, after_snapshot=after,
            source_diff=diff, events=events, impacts=impacts, decision=decision, proposal=result.proposal)
        self._history[prepared.proposal.id] = prepared
        return prepared
