"""Local demo composition, real authorities and optional prepared cloud proposals.

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
from competition_copilot.application.controlled_plan_observation import (
    ControlledPlanObservation,
    ControlledPlanRevisionPreparer,
)
from competition_copilot.application.plans import PlanRegistry
from competition_copilot.application.recommendation import (
    RecommendationContextAssembler,
)
from competition_copilot.application.skill_gap_inputs import prepare_skill_gap_context
from competition_copilot.application.student_skill_evidence import (
    StudentSkillEvidenceDeclaration,
    prepare_student_skill_evidence,
)
from competition_copilot.composition import build_seed_agent
from competition_copilot.domain.recommendation import RecommendationCandidate
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.replanning_input import ReplanningInput
from competition_copilot.domain.student import StudentProfile
from competition_copilot.domain.verified_skill_overlap import VerifiedSkillOverlapScorer
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
    ReplanningInputUnavailable,
)
from competition_copilot.integrations.local_runtime.plans import InMemoryPlanRegistry
from competition_copilot.integrations.local_runtime.projection import presentation


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
        self.on_retain = None
        self.on_resume = None

    def prepare_request(self, request):
        if request != self.frame.state.request:
            raise ValueError("Request binding mismatch")
        return self.frame

    def retain(self, handle, frame):
        if self.on_retain:
            frame = self.on_retain(frame)
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
        if self.on_resume:
            self.on_resume(prior, reply)
        values = {field: reply}
        if prior.state.status == "WAITING_FOR_APPROVAL":
            # Actor and exact current Plan come ONLY from the authorized local
            # host. A handle, cookie, browser role or decision does not supply them.
            values.update(approved_by_ref="local-development-operator",
                          current_plan=self.current_plan(prior.state.approval_request.before_plan),
                          executed_at=self.clock())
        return HumanResume(**values)


def create_local_host(root, *, clock=lambda: datetime.now(timezone.utc), cloud_models=None,
                      plan_registry: PlanRegistry | None = None):
    controlled = json.loads((root / "data/local_runtime/controlled_revision.json").read_text(encoding="utf-8"))
    source = ReplanningInput.model_validate(controlled["proposal"])
    registry = plan_registry if plan_registry is not None else InMemoryPlanRegistry()
    registry.register(source.before)
    profiles = {level: StudentProfile(id="local-" + level,
                **({"education_level": level} if level != "unknown" else {}))
                for level in ("undergraduate", "graduate", "unknown")}
    profiles = {value.id: value for value in profiles.values()}
    # Explicit synthetic local fixture, never inferred from candidates or an LLM.
    demo = json.loads((root / "data/local_runtime/recommendation_demo.json").read_text(encoding="utf-8"))
    if demo["fixture_kind"] != "LOCAL DEMO FIXTURE":
        raise ValueError("Expected explicit local demo fixture")
    demo_profile = StudentProfile(**demo["profile"])
    if demo_profile.id in profiles:
        raise ValueError("Demo profile must not replace existing profiles")
    profiles[demo_profile.id] = demo_profile
    declarations = tuple(StudentSkillEvidenceDeclaration.model_validate(item)
                         for item in demo.get("student_skill_evidence", []))
    student_evidence = {demo_profile.id: prepare_student_skill_evidence(demo_profile, declarations)}
    repository = JsonSeedCompetitionRepository(root / "data/seed")
    requirements = JsonSkillRequirementProvider(root / "data/skill_requirements")
    observation = ControlledPlanObservation.model_validate_json(
        (root / "data/local_runtime/generated_huawei_observation.json").read_bytes())
    revision_preparer = ControlledPlanRevisionPreparer(repository, observation)

    def factory(request):
        nonce = secrets.token_urlsafe(16)
        args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=nonce + "/arguments")
        frame = GraphInput(state=AgentState(request=request), clarification_id=nonce + "/question",
            result_ref=ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/result"),
            routing_invocation_id=nonce + "/invocation", routing_arguments_ref=args,
            arguments_json=json.dumps({"artifact_ref": args.model_dump(mode="json"), "payload": {}}),
            approval_request_id=nonce + "/approval", interaction_created_at=clock())
        bindings = Bindings(frame, clock=clock, current_plan=lambda reference:
                            PlanReference.from_plan(registry.get_current(reference.plan_id)))
        if cloud_models is None and request.intent is None:
            model = OfflineIntentModel(request)
        else:
            from competition_copilot.integrations.local_runtime.prepared_intent import (
                PreparedIntentModel,
                retain_competition_choices,
            )

            model = PreparedIntentModel(cloud_models.intent if cloud_models else None, request)
        composition = build_seed_agent(seed_directory=root / "data/seed", policy_directory=root / "data/eligibility",
            inputs=bindings, scoring=RecommendationScoringEngine([WeightedSuitabilityScorer(VerifiedSkillOverlapScorer())]),
            intent_model=model,
            explanation_model=cloud_models.explanation if cloud_models else None,
            human_interpreter=cloud_models.human_interpreter if cloud_models else None,
            requirement_provider=requirements)
        if cloud_models is not None or request.intent is not None:
            # Natural-language routing calls the provider once; explicit actions
            # call it zero times. Both use the same preparation/validation path.
            model.prepare(composition.facade, frame)
            bindings.on_resume = model.observe_resume
            bindings.on_retain = lambda pending: retain_competition_choices(model, composition.facade, pending)
            capability = model.preparation_capability
        else:
            capability = model.proposal.candidate_capability
        context = request.context
        student = profiles.get(context.student_id)
        payload = {}
        if capability == "get_competition_details":
            payload = {key: value for key, value in {
                "competition_id": context.competition_id, "edition_id": context.edition_id,
                "track_id": context.track_id,
            }.items() if value is not None}
        if capability in ("get_competition", "check_eligibility"):
            payload = {key: value for key, value in {
                "competition_id": context.competition_id,
                **({"edition_id": context.edition_id, "track_id": context.track_id,
                    "student": student.model_dump(mode="json") if student else None}
                   if capability == "check_eligibility" else {}),
            }.items() if value is not None}
        # Existing P4 read inputs come only from explicit context, never the
        # model's asserted targets. Unprepared capabilities remain core-validated.
        for selected, name in (
            ("list_competition_editions", "competition_id"),
            ("get_competition_edition", "edition_id"),
            ("list_edition_tracks", "edition_id"),
            ("get_competition_track", "track_id"),
        ):
            if capability == selected and getattr(context, name) is not None:
                payload = {name: getattr(context, name)}
        if capability in ("analyze_skill_gap", "build_plan") and student and context.competition_id and context.edition_id:
            skill = prepare_skill_gap_context(repository, requirements, student,
                context.competition_id, context.edition_id, context.track_id,
                student_evidence.get(student.id, ()))
            payload = {"context": skill.model_dump(mode="json")}
        if capability == "revise_plan":
            if context.plan_ref:
                selected = registry.resolve(context.plan_ref)
                if PlanReference.from_plan(registry.get_current(selected.id)) != context.plan_ref:
                    raise ValueError("Stale selected Plan")
                if selected != source.before:
                    owner = profiles.get(selected.student_id)
                    if owner is None:
                        raise ReplanningInputUnavailable()
                    prepared = revision_preparer.prepare(selected, owner, observed_at=frame.interaction_created_at)
                    if prepared is None:
                        raise ReplanningInputUnavailable()
                    frame = GraphInput(**{**frame.model_dump(), "prepared_revision": prepared.proposal})
                    payload = {"before": selected.model_dump(mode="json")}
                else:
                    payload = {"before": source.before.model_dump(mode="json"),
                               "replanning_input": source.model_dump(mode="json"), "executed_at": clock().isoformat()}
            else:
                payload = {"before": source.before.model_dump(mode="json"),
                           "replanning_input": source.model_dump(mode="json"), "executed_at": clock().isoformat()}
        frame = GraphInput(**{**frame.model_dump(), "arguments_json": json.dumps({
            "artifact_ref": args.model_dump(mode="json"), "payload": payload})})
        bindings.frame = frame
        if capability == "get_recommendations" and student and context.competition_id and context.edition_id:
            from competition_copilot.integrations.local_runtime.recommendation import (
                FacadeEligibilityEvaluator,
            )
            contexts = RecommendationContextAssembler(repository, FacadeEligibilityEvaluator(
                composition.facade, request_id=request.request_id, namespace=nonce), requirements).assemble(
                    student, anchor=RecommendationCandidate(competition_id=context.competition_id,
                        edition_id=context.edition_id, track_id=context.track_id))
            payload = {"contexts": [candidate.model_dump(mode="json") for candidate in contexts]}
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
                registry.replace_current(PlanReference.from_plan(receipt.data.plan_diff.before),
                    receipt.data.after, plan_diff=receipt.data.plan_diff)
            if receipt.status == "SUCCESS" and receipt.capability == "build_plan":
                registry.register(receipt.data)
            return receipt

        composition.facade.execute = record  # Observe the same Facade, never replace its decisions.
        return LocalSession(AgentArtsRuntimeAdapter(composition.agent, bindings), bindings.retain,
                            lambda response: presentation(response, receipts))

    return LocalInvocationHost(factory, plan_registry=registry)
