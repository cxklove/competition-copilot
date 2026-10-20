"""Local development composition, real authorities and offline intent proposals.

No HTTP, SDK, production credentials or replacement business rules. Prepared
arguments are caller-owned context; only the unchanged P12 graph authorizes use.
"""

import json
import secrets
from datetime import datetime, timezone

from competition_copilot.agents.contracts import ResultReference
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.human_contracts import (
    ApprovalResponse,
    HumanMessage,
    HumanResume,
)
from competition_copilot.agents.routing import IntentRoutingProposal
from competition_copilot.agents.state import AgentState
from competition_copilot.composition import build_seed_agent
from competition_copilot.domain.recommendation import RecommendationContext
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.replanning_input import ReplanningInput
from competition_copilot.domain.skill_gap import SkillGapContext
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter
from competition_copilot.integrations.local_runtime.hosting import (
    LocalInvocationHost,
    LocalSession,
)
from competition_copilot.integrations.local_runtime.projection import presentation


class MissingScorer:
    component_id = "local-unconfigured-signal"

    def evaluate(self, context):
        return None  # No invented suitability score; P6 owns missing-signal semantics.


class OfflineIntentModel:
    """Bounded demo intent proposal only, never eligibility/score/consent truth."""

    def __init__(self, request):
        text = request.user_message.casefold()
        intent, capability = "DISCOVER_COMPETITIONS", "list_competitions"
        for tokens, selected in (
            (("revision", "调整", "修订"), ("REQUEST_PLAN_REVISION", "revise_plan")),
            (("eligibility", "资格"), ("CHECK_ELIGIBILITY", "check_eligibility")),
            (("recommend", "推荐"), ("GET_RECOMMENDATIONS", "get_recommendations")),
            (("skill", "技能"), ("ANALYZE_SKILL_GAP", "analyze_skill_gap")),
            (("plan", "计划"), ("BUILD_PLAN", "build_plan")),
            (("detail", "详情"), ("GET_COMPETITION_DETAILS", "get_competition")),
        ):
            if any(token in text for token in tokens):
                intent, capability = selected
                break
        self.proposal = IntentRoutingProposal(intent=intent, candidate_capability=capability,
                                             ambiguity="NONE", missing_context=())

    def propose(self, value):
        if self.proposal.candidate_capability == "revise_plan" and value.request.context.plan_ref is None:
            return IntentRoutingProposal(**{**self.proposal.model_dump(), "missing_context": ("PLAN",)})
        return self.proposal


class Bindings:
    def __init__(self, frame, *, clock, current_plan):
        self.frame = frame
        self.clock, self.current_plan = clock, current_plan
        self.handle, self.pending = None, None

    def prepare_request(self, request):
        if request != self.frame.state.request:
            raise ValueError("Request binding mismatch")
        return self.frame

    def retain(self, handle, frame):
        self.handle, self.pending = handle, frame.model_dump_json()

    def resolve_continuation(self, reference):
        if self.handle is None or not secrets.compare_digest(reference, self.handle):
            raise ValueError("Continuation binding mismatch")
        self.handle = None
        return GraphInput.model_validate_json(self.pending)

    def prepare_resume(self, prior, reply):
        field = "approval" if isinstance(reply, ApprovalResponse) else "message" if isinstance(reply, HumanMessage) else "clarification"
        if reply.source_request_id != prior.state.request.request_id:
            raise ValueError("Reply belongs to another request")
        values = {field: reply}
        if prior.state.status == "WAITING_FOR_APPROVAL":
            # Actor and exact current Plan come ONLY from the authorized local
            # host. A handle, cookie, browser role or decision does not supply them.
            values.update(approved_by_ref="local-development-operator",
                          current_plan=self.current_plan(), executed_at=self.clock())
        return HumanResume(**values)


def create_local_host(root, *, clock=lambda: datetime.now(timezone.utc)):
    controlled = json.loads((root / "data/local_runtime/controlled_revision.json").read_text(encoding="utf-8"))
    source = ReplanningInput.model_validate(controlled["proposal"])
    current = {source.before.id: PlanReference.from_plan(source.before)}
    profiles = {level: StudentProfile(id="local-" + level,
                **({"education_level": level} if level != "unknown" else {}))
                for level in ("undergraduate", "graduate", "unknown")}
    profiles = {value.id: value for value in profiles.values()}
    repository = JsonSeedCompetitionRepository(root / "data/seed")
    requirements = JsonSkillRequirementProvider(root / "data/skill_requirements")

    def factory(request):
        model = OfflineIntentModel(request)
        capability = model.proposal.candidate_capability
        context = request.context
        student = profiles.get(context.student_id)
        payload = {}
        if capability in ("get_competition", "check_eligibility"):
            payload = {key: value for key, value in {
                "competition_id": context.competition_id,
                **({"edition_id": context.edition_id, "track_id": context.track_id,
                    "student": student.model_dump(mode="json") if student else None}
                   if capability == "check_eligibility" else {}),
            }.items() if value is not None}
        if capability in ("analyze_skill_gap", "build_plan") and student and context.competition_id and context.edition_id:
            skill = SkillGapContext(student_profile=student,
                competition=repository.get_competition(context.competition_id),
                edition=repository.get_edition(context.edition_id),
                track=repository.get_track(context.track_id) if context.track_id else None,
                requirements=requirements.get_requirements(context.competition_id, context.edition_id, context.track_id))
            payload = {"context": skill.model_dump(mode="json")}
        if capability == "revise_plan":
            if context.plan_ref and (context.plan_ref != PlanReference.from_plan(source.before)
                                     or context.plan_ref != current[source.before.id]):
                raise ValueError("Unknown local controlled Plan")
            payload = {"before": source.before.model_dump(mode="json"),
                       "replanning_input": source.model_dump(mode="json"), "executed_at": clock().isoformat()}
        nonce = secrets.token_urlsafe(16)
        args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=nonce + "/arguments")
        frame = GraphInput(state=AgentState(request=request), clarification_id=nonce + "/question",
            result_ref=ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/result"),
            routing_invocation_id=nonce + "/invocation", routing_arguments_ref=args,
            arguments_json=json.dumps({"artifact_ref": args.model_dump(mode="json"), "payload": payload}),
            approval_request_id=nonce + "/approval", interaction_created_at=clock())
        bindings = Bindings(frame, clock=clock, current_plan=lambda: current[source.before.id])
        composition = build_seed_agent(seed_directory=root / "data/seed", policy_directory=root / "data/eligibility",
            inputs=bindings, scoring=RecommendationScoringEngine([WeightedSuitabilityScorer(MissingScorer())]),
            intent_model=model)  # P12.6 deterministic grounded fallback, no external model.
        if capability == "get_recommendations" and student and context.competition_id and context.edition_id:
            from competition_copilot.agents.contracts import CapabilityInvocationRequest
            eligibility = composition.facade.execute(CapabilityInvocationRequest(
                invocation_id=nonce + "/eligibility-prerequisite", source_request_id=request.request_id,
                intent="CHECK_ELIGIBILITY", capability="check_eligibility", arguments_ref=args),
                {"artifact_ref": args.model_dump(mode="json"), "payload": {
                    "student": student.model_dump(mode="json"), "competition_id": context.competition_id,
                    "edition_id": context.edition_id, "track_id": context.track_id}},
                result_ref=ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/eligibility-result"))
            if eligibility.status != "SUCCESS":
                raise ValueError("P5 prerequisite unavailable")
            candidate = RecommendationContext(student_profile=student,
                candidate={"competition_id": context.competition_id, "edition_id": context.edition_id, "track_id": context.track_id},
                competition=repository.get_competition(context.competition_id), edition=repository.get_edition(context.edition_id),
                track=repository.get_track(context.track_id) if context.track_id else None,
                eligibility_decision=eligibility.data)
            payload = {"contexts": [candidate.model_dump(mode="json")]}
            bindings.frame = GraphInput(**{**frame.model_dump(), "arguments_json": json.dumps({
                "artifact_ref": args.model_dump(mode="json"), "payload": payload})})
        if capability == "build_plan" and "context" in payload:
            # Real P7 prerequisite through the same Facade, not browser-computed truth.
            from competition_copilot.agents.contracts import CapabilityInvocationRequest
            invocation = CapabilityInvocationRequest(invocation_id=nonce + "/skill-prerequisite",
                source_request_id=request.request_id, intent="ANALYZE_SKILL_GAP", capability="analyze_skill_gap", arguments_ref=args)
            prerequisite = composition.facade.execute(invocation,
                {"artifact_ref": args.model_dump(mode="json"), "payload": payload},
                result_ref=ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/skill-result"))
            if prerequisite.status != "SUCCESS":
                raise ValueError("P7 prerequisite unavailable")
            payload = {"source_decision": prerequisite.data.model_dump(mode="json"),
                       "student_id": student.id, "created_at": clock().isoformat()}
            bindings.frame = GraphInput(**{**frame.model_dump(), "arguments_json": json.dumps({
                "artifact_ref": args.model_dump(mode="json"), "payload": payload})})
        receipts = []
        execute = composition.facade.execute

        def record(*values, **kwargs):
            receipt = execute(*values, **kwargs)
            receipts.append(receipt)
            if receipt.status == "SUCCESS" and receipt.capability == "revise_plan":
                current[source.before.id] = PlanReference.from_plan(receipt.data.after)
            return receipt

        composition.facade.execute = record  # Observe the same Facade, never replace its decisions.
        return LocalSession(AgentArtsRuntimeAdapter(composition.agent, bindings), bindings.retain,
                            lambda response: presentation(response, receipts))

    return LocalInvocationHost(factory)
