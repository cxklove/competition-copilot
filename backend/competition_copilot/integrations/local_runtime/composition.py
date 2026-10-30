"""Local demo composition, real authorities and optional prepared cloud proposals.

No HTTP, SDK, production credentials or replacement business rules. Prepared
arguments are caller-owned context; only the unchanged P12 graph authorizes use.
"""

import json
import secrets
from datetime import datetime, timezone
from types import MappingProxyType

from competition_copilot.agents.contracts import ResultReference
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.human_contracts import (
    ApprovalResponse,
    HumanMessage,
    HumanResume,
)
from competition_copilot.agents.routing import (
    IntentRoutingProposal,
    PendingArgumentPreparation,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.application.competition_detail import CompetitionDetailReader
from competition_copilot.application.controlled_plan_observation import (
    ControlledPlanObservation,
    ControlledPlanRevisionPreparer,
)
from competition_copilot.application.my_competitions import (
    MyCompetitionEditor,
    MyCompetitionsReader,
    MyPlanSelector,
)
from competition_copilot.application.planning_workspace import (
    MappedPlanInputLineageReader,
    PlanningWorkspaceReader,
)
from competition_copilot.application.plans import PlanRegistry
from competition_copilot.application.profile_freshness import (
    DerivedProfileBinding,
    ProfileAnalysesReader,
)
from competition_copilot.application.profile_skills import (
    SkillCatalogReader,
    StudentSkillEditor,
)
from competition_copilot.application.profiles import (
    ProfileActorBinding,
    StudentProfileEditor,
    StudentProfileReader,
)
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
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.repositories.student_memory import (
    InMemoryStudentProfileRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.infrastructure.student_competition_memory import (
    InMemoryDerivedResultReadStore,
    InMemoryStudentCompetitionRepository,
)
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter
from competition_copilot.integrations.local_runtime.hosting import (
    LocalInvocationHost,
    LocalSession,
    ReplanningInputUnavailable,
)
from competition_copilot.integrations.local_runtime.plans import InMemoryPlanRegistry
from competition_copilot.integrations.local_runtime.projection import presentation
from competition_copilot.repositories.student_competition import (
    DerivedResultReference,
    MyCompetitionTarget,
    RetainedDerivedResult,
    canonical_json,
    content_digest,
)


class OfflineIntentModel:
    """Bounded demo intent proposal only, never eligibility/score/consent truth."""

    def __init__(self, request):
        text = request.user_message.casefold()
        intent, capability = "DISCOVER_COMPETITIONS", "list_competitions"
        for tokens, selected in (
            (("我的赛事", "正在准备哪些"), ("GET_MY_COMPETITIONS", "get_my_competitions")),
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
        self.on_resolved = None

    def prepare_resolved(self, frame):
        return self.on_resolved(frame) if self.on_resolved else frame

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
                      plan_registry: PlanRegistry | None = None, permitted_profile_ids=None):
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
    profile_repository = InMemoryStudentProfileRepository(profiles.values(), created_at=clock(),
        evidence={demo_profile.id: prepare_student_skill_evidence(demo_profile, declarations)})
    actor = ProfileActorBinding(actor_id="local-development-operator",
        permitted_student_ids=tuple(profiles) if permitted_profile_ids is None else tuple(permitted_profile_ids))
    profile_reader = StudentProfileReader(profile_repository, actor)
    profile_editor = StudentProfileEditor(profile_repository, actor, clock=clock)
    del profiles  # Fixture bootstrap is not a second authoritative store.

    repository = JsonSeedCompetitionRepository(root / "data/seed")
    from competition_copilot.infrastructure.temporal_evidence_json import (
        JsonTemporalEvidenceProvider,
    )

    temporal_evidence = JsonTemporalEvidenceProvider(
        root / "data/temporal_evidence/candidates.json", root, repository)
    requirements = JsonSkillRequirementProvider(root / "data/skill_requirements")
    skill_catalog = SkillCatalogReader(requirements)
    skill_editor = StudentSkillEditor(profile_repository, actor, clock=clock, catalog=skill_catalog)
    observation = ControlledPlanObservation.model_validate_json(
        (root / "data/local_runtime/generated_huawei_observation.json").read_bytes())
    revision_preparer = ControlledPlanRevisionPreparer(repository, observation)

    relationship_repository = InMemoryStudentCompetitionRepository()
    derived_results = InMemoryDerivedResultReadStore()
    relationship_editor = MyCompetitionEditor(relationship_repository, repository, actor, clock=clock)
    profile_inputs = {}
    planning_workspace = PlanningWorkspaceReader(profile_repository, registry,
        MappedPlanInputLineageReader(MappingProxyType(profile_inputs)),
        CompetitionDetailReader(repository, JsonEligibilityPolicyProvider(root / "data/eligibility"),
            requirements, repository, temporal_evidence), skill_catalog, actor)
    profile_analyses = ProfileAnalysesReader(profile_repository, actor, MappingProxyType(profile_inputs))

    my_competitions = MyCompetitionsReader(relationship_repository, derived_results, profile_repository, actor,
        details=CompetitionDetailReader(repository, JsonEligibilityPolicyProvider(root / "data/eligibility"),
            requirements, repository, temporal_evidence), planning=planning_workspace, plans=registry)
    plan_selector = MyPlanSelector(derived_results, registry, MappedPlanInputLineageReader(profile_inputs), actor)

    def factory(request):
        execution_sequence = derived_results.next_sequence()
        # Capture repository profile state before even the routing admission
        # preflight computes missing fields; target completeness is independent.
        context = request.context
        profile_record = profile_repository.get_record(context.student_id)
        profile_snapshot = profile_record.profile if profile_record else None
        student = profile_snapshot.domain_profile() if profile_snapshot else None
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
            my_competitions=my_competitions, my_competition_editor=relationship_editor, my_plan_selector=plan_selector,
            inputs=bindings, scoring=RecommendationScoringEngine([WeightedSuitabilityScorer(VerifiedSkillOverlapScorer())]),
            intent_model=model,
            explanation_model=cloud_models.explanation if cloud_models and request.intent not in ("GET_MY_COMPETITIONS", "GET_MY_COMPETITION", "ADD_MY_COMPETITION", "UPDATE_MY_COMPETITION", "REMOVE_MY_COMPETITION", "SELECT_MY_COMPETITION_PLAN", "GET_PLANNING_WORKSPACE", "GET_PROFILE_ANALYSES", "GET_PROFILE", "UPDATE_PROFILE", "GET_SKILL_CATALOG", "ADD_PROFILE_SKILL", "UPDATE_PROFILE_SKILL", "REMOVE_PROFILE_SKILL") else None,
            human_interpreter=cloud_models.human_interpreter if cloud_models else None,
            requirement_provider=requirements, temporal_evidence=temporal_evidence,
            profile_reader=profile_reader, profile_editor=profile_editor,
            planning_workspace=planning_workspace, skill_catalog=skill_catalog, skill_editor=skill_editor, profile_analyses=profile_analyses,
            resume_preparer=bindings.prepare_resolved)
        if cloud_models is not None or request.intent is not None:
            # Natural-language routing calls the provider once; explicit actions
            # call it zero times. Both use the same preparation/validation path.
            model.prepare(composition.facade, frame)
            bindings.on_resume = model.observe_resume
            bindings.on_retain = lambda pending: retain_competition_choices(model, composition.facade, pending)
            capability = model.preparation_capability
        else:
            capability = model.proposal.candidate_capability
        def prepare_exact_target(selected_frame):
            """Resolve independent profile and target inputs before schema-level missing checks.

            A retained clarification uses this same captured profile/evidence/ref;
            a new request captures a new repository snapshot. No inferred target.
            """
            selected = selected_frame.state.request.context
            missing = []
            if student is None:
                missing.append("STUDENT_PROFILE")
            if selected.competition_id is None:
                missing.append("COMPETITION")
            elif selected.edition_id is None:
                missing.append("EDITION")
            if missing:
                return {}, PendingArgumentPreparation(capability=capability, fields=tuple(missing),
                    profile_ref=profile_snapshot.profile_ref if profile_snapshot else None,
                    reason="MISSING_STUDENT_PROFILE" if student is None else "MISSING_REQUIRED_CONTEXT")
            skill = prepare_skill_gap_context(repository, requirements, student,
                selected.competition_id, selected.edition_id, selected.track_id,
                profile_record.evidence)
            prepared_payload = {"context": skill.model_dump(mode="json")}
            if capability == "build_plan":
                # Same real P7 prerequisite; no synthetic decision or Domain change.
                from competition_copilot.agents.contracts import (
                    CapabilityInvocationRequest,
                )

                invocation = CapabilityInvocationRequest(invocation_id=nonce + "/skill-prerequisite",
                    source_request_id=request.request_id, intent="ANALYZE_SKILL_GAP",
                    capability="analyze_skill_gap", arguments_ref=args)
                prerequisite = composition.facade.execute(invocation,
                    {"artifact_ref": args.model_dump(mode="json"), "payload": prepared_payload},
                    result_ref=ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/skill-result"))
                if prerequisite.status != "SUCCESS":
                    raise ValueError("P7 prerequisite unavailable")
                prepared_payload = {"source_decision": prerequisite.data.model_dump(mode="json"),
                    "student_id": student.id, "created_at": clock().isoformat()}
            return prepared_payload, None

        payload = {}
        if capability in ("get_my_competitions", "get_my_competition", "select_my_competition_plan"):
            payload = {"student_id": context.student_id} if context.student_id else {}
            if capability != "get_my_competitions" and context.competition_id and context.edition_id:
                payload["target"] = {"competition_id": context.competition_id, "edition_id": context.edition_id, "track_id": context.track_id}
            if capability == "select_my_competition_plan" and context.plan_ref:
                payload["plan_ref"] = context.plan_ref.model_dump(mode="json")
        if capability in ("add_my_competition", "update_my_competition", "remove_my_competition") and request.my_competition_command:
            payload = request.my_competition_command.model_dump(mode="json")
        if capability == "get_planning_workspace":
            payload = {k: v for k, v in {"student_id": context.student_id,
                "competition_id": context.competition_id, "edition_id": context.edition_id,
                "track_id": context.track_id,
                "plan_ref": context.plan_ref.model_dump(mode="json") if context.plan_ref else None}.items() if v is not None}
        if capability == "get_profile_analyses":
            payload = {"student_id": context.student_id, "result_ref_ids": request.profile_result_refs or (),
                       "competition_id": context.competition_id, "edition_id": context.edition_id,
                       "track_id": context.track_id,
                       "plan_ref": context.plan_ref.model_dump(mode="json") if context.plan_ref else None}
        if capability in ("get_profile", "update_profile"):
            payload = {"student_id": context.student_id} if context.student_id else {}
            if capability == "update_profile" and request.profile_update is not None:
                payload.update(update=request.profile_update.model_dump(mode="json"), request_id=request.request_id)
        if capability in ("add_profile_skill", "update_profile_skill", "remove_profile_skill"):
            payload = {"student_id": context.student_id} if context.student_id else {}
            if request.skill_command is not None:
                payload.update(command=request.skill_command.model_dump(mode="json"), request_id=request.request_id)
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
        if capability in ("analyze_skill_gap", "build_plan"):
            def target_choices(selected_frame, pending):
                if pending is None or "EDITION" not in pending.fields:
                    return ()
                from competition_copilot.agents.contracts import (
                    CapabilityInvocationRequest,
                )
                from competition_copilot.agents.human_contracts import (
                    ClarificationOption,
                )

                choice_ref = ResultReference(kind="TOOL_RESULT", ref_id=nonce + "/edition-choices")
                choice_args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=choice_ref.ref_id + "/arguments")
                result = composition.facade.execute(CapabilityInvocationRequest(
                    invocation_id=choice_ref.ref_id + "/invoke", source_request_id=request.request_id,
                    intent="GET_COMPETITION_DETAILS", capability="list_competition_editions",
                    arguments_ref=choice_args),
                    {"artifact_ref": choice_args.model_dump(mode="json"), "payload": {
                        "competition_id": selected_frame.state.request.context.competition_id}},
                    result_ref=choice_ref)
                if result.status != "SUCCESS":
                    raise ValueError("Edition choices unavailable")
                return tuple(ClarificationOption(field="EDITION", value=item.id, label=item.name,
                    source_ref=choice_ref) for item in result.data.editions)

            payload, pending = prepare_exact_target(frame)
            frame = GraphInput(**{**frame.model_dump(), "pending_preparation": pending,
                "clarification_options": target_choices(frame, pending)})

            def resume_target(resolved):
                nonlocal payload
                payload, pending = prepare_exact_target(resolved)
                return GraphInput(**{**resolved.model_dump(), "pending_preparation": pending,
                    "clarification_options": target_choices(resolved, pending),
                    "arguments_json": json.dumps({"artifact_ref": args.model_dump(mode="json"),
                                                   "payload": payload})})

            bindings.on_resolved = resume_target
        if capability == "revise_plan":
            if context.plan_ref:
                selected = registry.resolve(context.plan_ref)
                if PlanReference.from_plan(registry.get_current(selected.id)) != context.plan_ref:
                    raise ValueError("Stale selected Plan")
                if selected != source.before:
                    owner_snapshot = profile_repository.get(selected.student_id)
                    owner = owner_snapshot.domain_profile() if owner_snapshot else None
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
        if capability == "get_recommendations" and student:
            from competition_copilot.integrations.local_runtime.recommendation import (
                FacadeEligibilityEvaluator,
            )
            contexts = RecommendationContextAssembler(repository, FacadeEligibilityEvaluator(
                composition.facade, request_id=request.request_id, namespace=nonce), requirements).assemble(
                    student, anchor=(RecommendationCandidate(competition_id=context.competition_id,
                        edition_id=context.edition_id, track_id=context.track_id)
                        if context.competition_id and context.edition_id else None))
            payload = {"contexts": [candidate.model_dump(mode="json") for candidate in contexts]}
            bindings.frame = GraphInput(**{**frame.model_dump(), "arguments_json": json.dumps({
                "artifact_ref": args.model_dump(mode="json"), "payload": payload})})
        receipts = []
        execute = composition.facade.execute

        def record(*values, **kwargs):
            receipt = execute(*values, **kwargs)
            receipts.append(receipt)
            if (receipt.status == "SUCCESS" and profile_snapshot
                    and isinstance(values[1], dict)
                    and values[1].get("payload") == payload
                    and receipt.capability in (
                "get_recommendations", "analyze_skill_gap", "build_plan")):
                target = receipt.data.target if receipt.capability == "analyze_skill_gap" else receipt.data
                profile_inputs[receipt.result_ref.ref_id] = DerivedProfileBinding(
                    kind=type(receipt.data).__name__,
                    competition_id=target.competition_id if receipt.capability != "get_recommendations" else None,
                    edition_id=target.edition_id if receipt.capability != "get_recommendations" else None,
                    track_id=target.track_id if receipt.capability != "get_recommendations" else None,
                    plan_ref=PlanReference.from_plan(receipt.data) if receipt.capability == "build_plan" else None,
                    result_ref_id=receipt.result_ref.ref_id, input_profile_ref=profile_snapshot.profile_ref,
                    plan_id=receipt.data.id if receipt.capability == "build_plan" else None,
                    plan_version=receipt.data.version if receipt.capability == "build_plan" else None)
            if receipt.status == "SUCCESS" and receipt.capability == "revise_plan":
                registry.replace_current(PlanReference.from_plan(receipt.data.plan_diff.before),
                    receipt.data.after, plan_diff=receipt.data.plan_diff)
            if receipt.status == "SUCCESS" and receipt.capability == "build_plan":
                registry.register(receipt.data)
            # Only the successfully invoked top-level action selects a result.
            # P6/P8 prerequisites are deliberately not promoted to user selections.
            kinds = {"check_eligibility": "ELIGIBILITY", "analyze_skill_gap": "SKILL_GAP", "build_plan": "PLAN_REFERENCE"}
            if (receipt.status == "SUCCESS" and receipt.capability == capability
                    and receipt.capability in kinds and profile_snapshot
                    and receipt.invocation_id == frame.routing_invocation_id):
                body = PlanReference.from_plan(receipt.data) if capability == "build_plan" else receipt.data
                t = body.target if capability != "check_eligibility" else body
                target = MyCompetitionTarget(competition_id=t.competition_id, edition_id=t.edition_id, track_id=t.track_id)
                ref = DerivedResultReference(result_ref_id=receipt.result_ref.ref_id, student_id=profile_snapshot.student_id,
                    target=target, kind=kinds[capability], content_digest=content_digest(body.model_dump(mode="json")))
                derived_results.retain_and_select(RetainedDerivedResult(reference=ref,
                    payload_json=canonical_json(body.model_dump(mode="json")),
                    input_profile_ref=profile_snapshot.profile_ref, execution_sequence=execution_sequence))
            return receipt

        composition.facade.execute = record  # Observe the same Facade, never replace its decisions.
        return LocalSession(AgentArtsRuntimeAdapter(composition.agent, bindings), bindings.retain,
                            lambda response: presentation(response, receipts))

    host = LocalInvocationHost(factory, plan_registry=registry)
    host.relationship_repository = relationship_repository
    host.derived_result_store = derived_results
    host.profile_repository = profile_repository
    host.profile_input_bindings = MappingProxyType(profile_inputs)
    return host
