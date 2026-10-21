"""Versioned WHAT-to-propose policy. No authorization, execution, IO or LLM.

Inputs are already authoritative P10/P11 results. Checking their typed lineage
for policy applicability never generates a new Event, Impact or Decision.
"""

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.event import CompetitionEventType
from competition_copilot.domain.plan import CompetitionPlan, PlanStatus
from competition_copilot.domain.replanning import (
    ImpactOutcome,
    PlanReference,
    ReplanningDecision,
    ReplanningOutcome,
    ReplanningReasonCode,
    ScopeState,
)
from competition_copilot.domain.replanning_input import replanning_decision_fingerprint

POLICY_ID = "target-track-removed-cancel-v1"


class _PreparationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value):
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(self, *, update=None, deep=False):
        if update is not None:
            raise TypeError("Construct a validated preparation snapshot")
        return super().model_copy(deep=deep)


def _identity(prefix: str, value: BaseModel) -> str:
    return prefix + sha256(json.dumps(value.model_dump(mode="json"), sort_keys=True,
                                     separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


class PreparationReference(_PreparationModel):
    kind: Literal["EVENT", "IMPACT", "DECISION", "SCOPE", "PLAN"]
    ref_id: StableId


class ProposedPlanOperation(_PreparationModel):
    """Specification only, deliberately not a P11 executable instruction."""

    policy_id: Literal["target-track-removed-cancel-v1"] = POLICY_ID
    expected_plan: PlanReference
    source_decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: Literal["update_plan_status"] = "update_plan_status"
    field: Literal["status"] = "status"
    before_value: Literal[PlanStatus.DRAFT, PlanStatus.ACTIVE]
    after_value: Literal[PlanStatus.CANCELLED] = PlanStatus.CANCELLED

    @property
    def id(self) -> str:
        return _identity("proposed-plan-operation-v1:", self)


def _supported(plan: CompetitionPlan, decision: ReplanningDecision) -> bool:
    reference = PlanReference.from_plan(plan)
    if (plan.track_id is None or plan.status not in (PlanStatus.DRAFT, PlanStatus.ACTIVE)
        or decision.outcome != ReplanningOutcome.REPLAN
        or decision.scope.state != ScopeState.KNOWN or not decision.scope.whole_plan
        or decision.scope.plan_id != plan.id):
        return False
    confirmed = []
    for impact in decision.impacts:
        if (impact.plan != reference or impact.student_id != plan.student_id
            or impact.event.target != reference.target
            or impact.outcome == ImpactOutcome.UNDETERMINED):
            return False
        if impact.outcome == ImpactOutcome.AFFECTS_PLAN:
            if (ReplanningReasonCode.TARGET_TRACK_REMOVED not in impact.reason_codes
                or impact.event.event_type != CompetitionEventType.TRACK_MEMBERSHIP_CHANGED):
                return False
            # Typed EventImpactAnalysis already proves this removal. Retain/check
            # that exact lineage, never reinterpret another change as removal.
            membership = impact.event.source_changes[0]
            if (plan.track_id not in (membership.before.value or ())
                or plan.track_id in (membership.after.value or ())
                or not any("track_membership" in e.source_change_fields for e in impact.evidence)):
                return False
            confirmed.append(impact)
    return bool(confirmed)


def _references(plan: CompetitionPlan, decision: ReplanningDecision) -> tuple[PreparationReference, ...]:
    fingerprint = replanning_decision_fingerprint(decision)
    reference = PlanReference.from_plan(plan)
    refs = [PreparationReference(kind="PLAN", ref_id=reference.plan_id + "/" + reference.content_digest),
            PreparationReference(kind="DECISION", ref_id=fingerprint),
            PreparationReference(kind="SCOPE", ref_id=fingerprint + "#/scope")]
    for index, impact in enumerate(decision.impacts):
        refs.extend((PreparationReference(kind="EVENT", ref_id=impact.event.id),
                     PreparationReference(kind="IMPACT", ref_id=fingerprint + f"#/impacts/{index}")))
    return tuple(refs)


class PlanRevisionProposal(_PreparationModel):
    """Complete retained preparation context, with zero execution authority."""

    policy_id: Literal["target-track-removed-cancel-v1"] = POLICY_ID
    before: CompetitionPlan
    decision: ReplanningDecision
    prepared_at: AwareDatetime
    operation: ProposedPlanOperation
    reason_codes: tuple[Literal["target_track_removed"], ...] = ("target_track_removed",)
    evidence_refs: tuple[PreparationReference, ...]
    message: Literal["target-track-removed-cancel-v1: exact target track removed; whole-plan REPLAN; cancellation proposed only, explicit approval required."] = (
        "target-track-removed-cancel-v1: exact target track removed; whole-plan REPLAN; cancellation proposed only, explicit approval required.")

    @property
    def id(self) -> str:
        return _identity("plan-revision-proposal-v1:", self)

    @model_validator(mode="after")
    def bind_policy(self) -> Self:
        if not _supported(self.before, self.decision):
            raise ValueError("Unsupported or mismatched instruction preparation context")
        expected = ProposedPlanOperation(expected_plan=PlanReference.from_plan(self.before),
            source_decision_fingerprint=replanning_decision_fingerprint(self.decision),
            before_value=self.before.status)
        if (self.operation != expected or self.reason_codes != ("target_track_removed",)
            or self.evidence_refs != _references(self.before, self.decision)):
            raise ValueError("Proposal must retain exact policy operation and evidence bindings")
        if self.prepared_at < max(self.decision.evaluated_at, self.before.updated_at):
            raise ValueError("Preparation cannot precede Plan/Decision")
        return self


class InstructionPreparationStatus(StrEnum):
    PREPARED = "PREPARED"
    UNSUPPORTED = "UNSUPPORTED"


class InstructionPreparationResult(_PreparationModel):
    status: InstructionPreparationStatus
    policy_id: Literal["target-track-removed-cancel-v1"] = POLICY_ID
    proposal: PlanRevisionProposal | None = None
    reason_codes: tuple[Literal["target_track_removed", "NO_SUPPORTED_INSTRUCTION_POLICY"], ...]
    evidence_refs: tuple[PreparationReference, ...]

    @model_validator(mode="after")
    def bind_result(self) -> Self:
        if self.status == InstructionPreparationStatus.PREPARED:
            if (self.proposal is None or self.reason_codes != self.proposal.reason_codes
                or self.evidence_refs != self.proposal.evidence_refs):
                raise ValueError("Prepared result must retain its proposal audit")
        elif self.proposal is not None or self.reason_codes != ("NO_SUPPORTED_INSTRUCTION_POLICY",):
            raise ValueError("Unsupported result cannot contain a proposed operation")
        return self


class TargetTrackRemovedCancellationPolicy:
    policy_id = POLICY_ID

    def prepare(self, plan: CompetitionPlan, decision: ReplanningDecision, *,
                prepared_at: datetime) -> InstructionPreparationResult:
        plan = CompetitionPlan.model_validate(plan.model_dump())
        decision = ReplanningDecision.model_validate(decision.model_dump())
        prepared_at = TypeAdapter(AwareDatetime).validate_python(prepared_at)
        refs = _references(plan, decision)
        if not _supported(plan, decision):
            return InstructionPreparationResult(status="UNSUPPORTED",
                reason_codes=("NO_SUPPORTED_INSTRUCTION_POLICY",), evidence_refs=refs)
        proposal = PlanRevisionProposal(before=plan, decision=decision, prepared_at=prepared_at,
            operation=ProposedPlanOperation(expected_plan=PlanReference.from_plan(plan),
                source_decision_fingerprint=replanning_decision_fingerprint(decision), before_value=plan.status),
            evidence_refs=refs)
        return InstructionPreparationResult(status="PREPARED", proposal=proposal,
            reason_codes=proposal.reason_codes, evidence_refs=refs)
