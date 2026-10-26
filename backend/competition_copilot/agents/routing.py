"""Provider-neutral proposals and deterministic routing guards, no business rules."""

import json
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, Self

from pydantic import Field, model_validator

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    CapabilityAccess,
    CapabilityMetadata,
)
from competition_copilot.agents.contracts import (
    AgentContract,
    AgentIntent,
    AgentRequest,
    CapabilityId,
    CapabilityInvocationRequest,
    ClarificationReason,
    ContextField,
    ResultReference,
)
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.replanning import PlanReference


class RoutingAmbiguity(StrEnum):
    NONE = "NONE"
    INTENT = "INTENT"
    TARGET = "TARGET"
    CONFLICT = "CONFLICT"
    MULTI_STEP = "MULTI_STEP"


class ProposedTargets(AgentContract):
    student_id: StableId | None = None
    competition_id: StableId | None = None
    edition_id: StableId | None = None
    track_id: StableId | None = None
    plan_id: StableId | None = None


class IntentRoutingProposal(AgentContract):
    """Untrusted interaction metadata, never arguments, approval or Domain truth."""

    intent: AgentIntent
    candidate_capability: CapabilityId | None
    ambiguity: RoutingAmbiguity
    missing_context: tuple[ContextField, ...]
    targets: ProposedTargets = Field(default_factory=ProposedTargets)


def explicit_intent_proposal(request: AgentRequest) -> IntentRoutingProposal | None:
    """Translate a user action to an untrusted proposal, not an invocation.

    Unsupported explicit operations stay unsupported; they never fall back to
    text/model inference. The normal routing validator still admits execution.
    """
    if request.intent is None:
        return None
    capability = {
        AgentIntent.GET_PROFILE_ANALYSES: CapabilityId.GET_PROFILE_ANALYSES,
        AgentIntent.GET_PROFILE: CapabilityId.GET_PROFILE,
        AgentIntent.GET_SKILL_CATALOG: CapabilityId.GET_SKILL_CATALOG,
        AgentIntent.ADD_PROFILE_SKILL: CapabilityId.ADD_PROFILE_SKILL,
        AgentIntent.UPDATE_PROFILE_SKILL: CapabilityId.UPDATE_PROFILE_SKILL,
        AgentIntent.REMOVE_PROFILE_SKILL: CapabilityId.REMOVE_PROFILE_SKILL,

        AgentIntent.UPDATE_PROFILE: CapabilityId.UPDATE_PROFILE,
        AgentIntent.GET_COMPETITION_DETAILS: CapabilityId.GET_COMPETITION_DETAILS,
        AgentIntent.CHECK_ELIGIBILITY: CapabilityId.CHECK_ELIGIBILITY,
        AgentIntent.GET_RECOMMENDATIONS: CapabilityId.GET_RECOMMENDATIONS,
        AgentIntent.ANALYZE_SKILL_GAP: CapabilityId.ANALYZE_SKILL_GAP,
        AgentIntent.BUILD_PLAN: CapabilityId.BUILD_PLAN,
        AgentIntent.REQUEST_PLAN_REVISION: CapabilityId.REVISE_PLAN,
    }.get(request.intent)
    return IntentRoutingProposal(intent=request.intent, candidate_capability=capability,
                                 ambiguity=RoutingAmbiguity.NONE, missing_context=())


class RoutingCapability(AgentContract):
    capability: CapabilityId
    description: StableId
    access: CapabilityAccess
    requires_explicit_approval: bool
    required_fields: tuple[StableId, ...]


def required_fields(metadata: CapabilityMetadata) -> tuple[str, ...]:
    schema = json.loads(metadata.input_schema_json)
    payload = schema["properties"]["payload"]
    if "$ref" in payload:
        payload = schema["$defs"][payload["$ref"].split("/")[-1]]
    return tuple(payload.get("required", ()))


def routing_catalog(facade: AgentCapabilityFacade) -> tuple[RoutingCapability, ...]:
    return tuple(RoutingCapability(
        capability=m.capability, description=m.description, access=m.access,
        requires_explicit_approval=m.requires_explicit_approval,
        required_fields=required_fields(m),
    ) for m in facade.list_capabilities())


class IntentModelInput(AgentContract):
    request: AgentRequest
    catalog: tuple[RoutingCapability, ...]


class IntentModel(Protocol):
    def propose(self, value: IntentModelInput) -> IntentRoutingProposal:
        """Return structured output; consumer always revalidates it as untrusted."""
        ...


class RoutingValidationStatus(StrEnum):
    READY = "READY"
    CLARIFICATION = "CLARIFICATION"
    REJECTED = "REJECTED"


class RoutingReason(StrEnum):
    VALIDATED = "VALIDATED"
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    AMBIGUITY = "AMBIGUITY"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INCOMPATIBLE_CAPABILITY = "INCOMPATIBLE_CAPABILITY"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"


class RoutingValidationResult(AgentContract):
    status: RoutingValidationStatus
    reason: RoutingReason
    invocation: CapabilityInvocationRequest | None = None
    missing_context: tuple[ContextField, ...] = ()
    clarification_reason: ClarificationReason | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.status == RoutingValidationStatus.READY) != (self.invocation is not None):
            raise ValueError("Only validated routing has an invocation")
        if self.status == RoutingValidationStatus.CLARIFICATION:
            if not self.missing_context or self.clarification_reason is None:
                raise ValueError("Clarification requires fields and a typed reason")
        elif self.missing_context or self.clarification_reason is not None:
            raise ValueError("Clarification requires fields and a typed reason")
        return self


# Safety policy, not workflow planning: an intent may admit several capabilities.
INTENT_CAPABILITIES = MappingProxyType({
    AgentIntent.GET_PROFILE_ANALYSES: (CapabilityId.GET_PROFILE_ANALYSES,),
    AgentIntent.GET_PROFILE: (CapabilityId.GET_PROFILE,),
    AgentIntent.GET_SKILL_CATALOG: (CapabilityId.GET_SKILL_CATALOG,),
    AgentIntent.ADD_PROFILE_SKILL: (CapabilityId.ADD_PROFILE_SKILL,),
    AgentIntent.UPDATE_PROFILE_SKILL: (CapabilityId.UPDATE_PROFILE_SKILL,),
    AgentIntent.REMOVE_PROFILE_SKILL: (CapabilityId.REMOVE_PROFILE_SKILL,),

    AgentIntent.UPDATE_PROFILE: (CapabilityId.UPDATE_PROFILE,),
    AgentIntent.DISCOVER_COMPETITIONS: (CapabilityId.LIST_COMPETITIONS,),
    AgentIntent.GET_COMPETITION_DETAILS: (
        CapabilityId.GET_COMPETITION_DETAILS,
        CapabilityId.GET_COMPETITION, CapabilityId.LIST_EDITIONS, CapabilityId.GET_EDITION,
        CapabilityId.LIST_TRACKS, CapabilityId.GET_TRACK,
    ),
    AgentIntent.CHECK_ELIGIBILITY: (CapabilityId.CHECK_ELIGIBILITY,),
    AgentIntent.GET_RECOMMENDATIONS: (
        CapabilityId.CHECK_ELIGIBILITY, CapabilityId.GET_RECOMMENDATIONS,
    ),
    AgentIntent.ANALYZE_SKILL_GAP: (CapabilityId.ANALYZE_SKILL_GAP,),
    AgentIntent.BUILD_PLAN: (CapabilityId.BUILD_PLAN,),
    AgentIntent.CHECK_COMPETITION_CHANGES: (
        CapabilityId.BUILD_COMPETITION_SNAPSHOT, CapabilityId.DIFF_COMPETITION_SNAPSHOT,
        CapabilityId.DERIVE_COMPETITION_EVENTS,
    ),
    AgentIntent.EXPLAIN_REPLANNING: (
        CapabilityId.ANALYZE_EVENT_IMPACT, CapabilityId.DECIDE_REPLANNING,
    ),
    AgentIntent.REQUEST_PLAN_REVISION: (CapabilityId.REVISE_PLAN,),
    AgentIntent.APPROVE_PLAN_REVISION: (),
    AgentIntent.REJECT_PLAN_REVISION: (),
    AgentIntent.UNKNOWN: (),
})

FIELD_NAMES = MappingProxyType({
    "student": ContextField.STUDENT_PROFILE, "student_id": ContextField.STUDENT_PROFILE,
    "competition_id": ContextField.COMPETITION, "edition_id": ContextField.EDITION,
    "track_id": ContextField.TRACK, "plan": ContextField.PLAN, "before": ContextField.PLAN,
})


IDENTITY_FIELDS = ("student_id", "competition_id", "edition_id", "track_id", "plan_id")


def _merge_trusted_identities(*sources: dict) -> dict[str, str]:
    resolved = {}
    for source in sources:
        for name in IDENTITY_FIELDS:
            value = source.get(name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                # Malformed values establish no identity. The unchanged typed
                # argument boundary rejects them as INVALID_ARGUMENTS, not conflict.
                continue
            if name in resolved and resolved[name] != value:
                raise ValueError("Conflicting trusted identity")
            resolved[name] = value
    return {name: resolved[name] for name in IDENTITY_FIELDS if name in resolved}


def _project_trusted_payload(payload: dict) -> dict[str, str]:
    """Bounded projection of existing input contracts, not recursive key search."""
    nodes = [payload]
    for key in ("target", "candidate", "context", "plan", "before", "source_decision"):
        node = payload.get(key)
        if isinstance(node, dict):
            nodes.append(node)
            if isinstance(node.get("target"), dict):
                nodes.append(node["target"])
    for node in tuple(nodes):
        requirements = node.get("requirements")
        if isinstance(requirements, dict) and isinstance(requirements.get("target"), dict):
            nodes.append(requirements["target"])
    projections = list(nodes)
    for node in nodes:
        for key, identity in (
            ("student", "student_id"), ("student_profile", "student_id"),
            ("competition", "competition_id"), ("edition", "edition_id"), ("track", "track_id"),
        ):
            value = node.get(key)
            if isinstance(value, dict):
                projections.append({identity: value.get("id")})
    for key in ("plan", "before"):
        value = payload.get(key)
        if isinstance(value, dict):
            projections.append({"plan_id": value.get("id")})
    return _merge_trusted_identities(*projections)


def _anchored_recommendations(request, payload, capability):
    return (capability == CapabilityId.GET_RECOMMENDATIONS
            and request.context.plan_ref is None
            and isinstance(payload.get("contexts"), list) and len(payload["contexts"]) > 1)


def _resolve_trusted_context(request: AgentRequest, payload: dict, *,
                             capability=None) -> tuple[dict[str, str], ...]:
    """Caller-only canonical identity scopes; proposal values are never sources.

    P6 contexts describe distinct recommendation candidates, so different candidate
    targets remain separate scopes. Every context must describe the same student.
    Outer identities constrain each scope. For a P6 multi-candidate batch only,
    an optional caller target constrains membership instead of excluding alternatives.
    Plan-bound requests retain the original exact-target checks.
    """
    outer = request.context.model_dump(mode="json")
    plan = request.context.plan_ref
    plan_ids = {} if plan is None else {
        "plan_id": plan.plan_id, "student_id": plan.student_id,
        **plan.target.model_dump(mode="json"),
    }
    base = _merge_trusted_identities(outer, plan_ids, _project_trusted_payload(payload))
    contexts = payload.get("contexts", [])
    if not isinstance(contexts, list) or any(not isinstance(item, dict) for item in contexts):
        raise ValueError("Invalid trusted contexts")
    if _anchored_recommendations(request, payload, capability):
        # Recommendation ranks a pool even when no current target is selected.
        # Never let payload-level identities override the caller. Only candidate
        # scopes may differ; their own projections must remain internally coherent.
        base = {name: value for name, value in base.items()
                if name not in ("competition_id", "edition_id", "track_id")}
    scopes = [_merge_trusted_identities(base, _project_trusted_payload(item)) for item in contexts]
    if not scopes:
        scopes = [base]
    # A batch of recommendation candidates belongs to one student, not mixed users.
    _merge_trusted_identities(*({"student_id": scope.get("student_id")} for scope in scopes))
    if _anchored_recommendations(request, payload, capability):
        if any("plan_id" in scope for scope in scopes) or not any(
            all(scope.get(name) == outer.get(name)
                for name in ("competition_id", "edition_id", "track_id")
                if outer.get(name) is not None) for scope in scopes
        ):
            raise ValueError("Recommendation anchor missing or plan scope supplied")
    return tuple(sorted(scopes, key=lambda scope: tuple(scope.items())))


def context_conflicts(request: AgentRequest, payload: dict, targets: ProposedTargets, *,
                      capability=None) -> bool:
    try:
        scopes = _resolve_trusted_context(request, payload, capability=capability)
    except ValueError:
        return True
    # A proposal target is an assertion about caller context, never a new source.
    # Without an explicit anchor it must match every scope. With an anchor,
    # candidate assertions must match that caller anchor, never select an alternative.
    for name, value in targets.model_dump().items():
        if value is None:
            continue
        if (_anchored_recommendations(request, payload, capability)
                and name in ("competition_id", "edition_id", "track_id")):
            if getattr(request.context, name) != value:
                return True
        elif any(scope.get(name) != value for scope in scopes):
            return True
    return False


class RoutingProposalValidator:
    def __init__(self, facade: AgentCapabilityFacade):
        self._facade = facade
        self._metadata = {m.capability: m for m in facade.list_capabilities()}

    def validate(self, proposal: IntentRoutingProposal, request: AgentRequest, *,
                 invocation_id: StableId | None, arguments_ref: ResultReference | None,
                 arguments: dict | None) -> RoutingValidationResult:
        proposal = IntentRoutingProposal.model_validate(proposal)

        def reject(reason):
            return RoutingValidationResult(status="REJECTED", reason=reason)

        def clarify(reason, fields, category=ClarificationReason.MISSING_REQUIRED_CONTEXT):
            return RoutingValidationResult(status="CLARIFICATION", reason=reason,
                missing_context=tuple(sorted(set(fields), key=lambda f: f.value)),
                clarification_reason=category)

        if proposal.intent == AgentIntent.UNKNOWN:
            return clarify(RoutingReason.UNKNOWN_INTENT, (ContextField.INTENT,),
                           ClarificationReason.AMBIGUOUS_INTENT)
        capability = self._metadata.get(proposal.candidate_capability)
        if capability is None:
            return reject(RoutingReason.UNSUPPORTED_CAPABILITY)
        if capability.capability not in INTENT_CAPABILITIES[proposal.intent]:
            return reject(RoutingReason.INCOMPATIBLE_CAPABILITY)
        # A model-originated mutation is never executable in P12.4, even with a
        # caller approval response. The existing explicit structured path is separate.
        explicit_profile_edit = (
            capability.capability == CapabilityId.UPDATE_PROFILE
            and request.intent == AgentIntent.UPDATE_PROFILE
            and proposal.intent == AgentIntent.UPDATE_PROFILE
            and request.profile_update is not None)
        explicit_skill_edit = (
            request.skill_command is not None and request.intent == proposal.intent
            and capability.capability.value == request.skill_command.operation + "_profile_skill")
        if (capability.access == CapabilityAccess.MUTATING or capability.requires_explicit_approval) and not (explicit_profile_edit or explicit_skill_edit):
            return clarify(RoutingReason.APPROVAL_REQUIRED, (ContextField.APPROVAL_CONTEXT,),
                           ClarificationReason.MISSING_APPROVAL_CONTEXT)
        payload = arguments.get("payload") if isinstance(arguments, dict) else None
        if payload is not None and not isinstance(payload, dict):
            return reject(RoutingReason.INVALID_ARGUMENTS)
        if context_conflicts(request, payload or {}, proposal.targets,
                             capability=proposal.candidate_capability):
            return reject(RoutingReason.CONTEXT_CONFLICT)
        if proposal.ambiguity != RoutingAmbiguity.NONE:
            category = (ClarificationReason.AMBIGUOUS_TARGET
                        if proposal.ambiguity in (RoutingAmbiguity.TARGET, RoutingAmbiguity.CONFLICT)
                        else ClarificationReason.AMBIGUOUS_INTENT)
            return clarify(RoutingReason.AMBIGUITY, (ContextField.INTENT,), category)
        missing = list(proposal.missing_context)
        if payload is None or arguments_ref is None or invocation_id is None:
            missing.append(ContextField.CAPABILITY_ARGUMENTS)
        else:
            missing.extend(FIELD_NAMES.get(name, ContextField.CAPABILITY_ARGUMENTS)
                           for name in required_fields(capability)
                           if payload.get(name) is None)
        if missing:
            return clarify(RoutingReason.MISSING_CONTEXT, missing)
        try:
            invocation = CapabilityInvocationRequest(
                invocation_id=invocation_id, source_request_id=request.request_id,
                intent=proposal.intent, capability=capability.capability,
                arguments_ref=arguments_ref,
            )
            checked = self._facade.validate_arguments(invocation, arguments)
            if request.context.plan_ref:
                for name in ("plan", "before"):
                    plan = getattr(checked.payload, name, None)
                    if plan is not None and PlanReference.from_plan(plan) != request.context.plan_ref:
                        return reject(RoutingReason.CONTEXT_CONFLICT)
        except (ValueError, TypeError):
            return reject(RoutingReason.INVALID_ARGUMENTS)
        return RoutingValidationResult(status="READY", reason="VALIDATED", invocation=invocation)
