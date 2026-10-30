"""Explicit student intent mutations and read-only competition workspace joins."""

from typing import Literal

from pydantic import model_validator

from competition_copilot.application.competition_detail import CompetitionDetailQuery
from competition_copilot.application.planning_workspace import (
    PlanningWorkspaceQuery,
    TimeReference,
)
from competition_copilot.application.profile_freshness import (
    ProfileFreshness,
    resolve_profile_freshness,
)
from competition_copilot.application.profiles import (
    GetProfileQuery,
    ProfileActorBinding,
)
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.skill_gap import SkillGapDecision
from competition_copilot.repositories.competition import (
    CompetitionRepository,
    RepositoryEntityNotFoundError,
)
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileValue,
    StudentProfileRepository,
)
from competition_copilot.repositories.student_competition import (
    DerivedResultReadStore,
    DerivedResultReference,
    MyCompetitionTarget,
    RelationshipReference,
    RelationshipSnapshot,
    RelationshipState,
    RetainedDerivedResult,
    StudentCompetitionRepository,
    canonical_json,
    content_digest,
)


class MyCompetitionQuery(GetProfileQuery):
    target: MyCompetitionTarget


class MyCompetitionCommand(GetProfileQuery):
    operation: Literal["add", "update", "remove"]
    target: MyCompetitionTarget
    state: RelationshipState = "SAVED"
    expected_reference: RelationshipReference | None = None

    @model_validator(mode="after")
    def explicit_state_update(self):
        if self.operation == "update" and "state" not in self.model_fields_set:
            raise ValueError("State update requires an explicitly supplied state")
        return self


class MyPlanSelection(MyCompetitionQuery):
    plan_ref: PlanReference


class MyPlanSelectionResult(ProfileValue):
    selected: DerivedResultReference


class MyPlanSelector:
    def __init__(self, results, plans, lineage, actor):
        self.results, self.plans, self.lineage, self.actor = results, plans, lineage, actor

    def select(self, command: MyPlanSelection) -> MyPlanSelectionResult:
        authorize(self.actor, command.student_id)
        sequence = self.results.next_sequence()
        ref = command.plan_ref
        if ref.student_id != command.student_id or MyCompetitionTarget(**ref.target.model_dump()) != command.target:
            raise ProfileError("MY_COMPETITION_INVALID_REFERENCE")
        try:
            plan = self.plans.resolve(ref)
            if PlanReference.from_plan(plan) != ref:
                raise ValueError("Plan mismatch")
        except ValueError as exc:
            raise ProfileError("MY_COMPETITION_INVALID_REFERENCE") from exc
        selected = DerivedResultReference(result_ref_id=f"selected-plan:{ref.content_digest}:{sequence}",
            student_id=command.student_id, target=command.target, kind="PLAN_REFERENCE",
            content_digest=content_digest(ref.model_dump(mode="json")))
        self.results.retain_and_select(RetainedDerivedResult(reference=selected,
            payload_json=canonical_json(ref.model_dump(mode="json")),
            input_profile_ref=self.lineage.read(ref), execution_sequence=sequence))
        return MyPlanSelectionResult(selected=selected)


class MyCompetitionMutationResult(ProfileValue):
    snapshot: RelationshipSnapshot
    removed: bool
    persistence_boundary: Literal["HOST_MEMORY"] = "HOST_MEMORY"


class DisplayIdentity(ProfileValue):
    competition_name: str | None
    edition_name: str | None
    track_name: str | None


class DerivedSummary(ProfileValue):
    availability: Literal["NOT_ANALYZED", "NOT_SELECTED", "AVAILABLE", "UNAVAILABLE", "INVALID_REFERENCE"]
    status: str | None = None
    label: str
    result_ref: DerivedResultReference | None = None
    plan_ref: PlanReference | None = None
    profile_freshness: ProfileFreshness
    audit_json: str | None = None


class MyPlanningSummary(ProfileValue):
    availability: Literal["AVAILABLE", "PROVIDER_UNAVAILABLE", "PROFILE_UNAVAILABLE", "INVALID_REFERENCE"]
    confirmed_constraints_count: int | None = None
    pending_confirmations_count: int | None = None
    has_advisory: bool | None = None


class MyTimeSummary(ProfileValue):
    availability: Literal["VERIFIED", "OFFICIAL_CANDIDATE", "UNKNOWN", "PROVIDER_UNAVAILABLE"]
    references: tuple[TimeReference, ...] = ()


def time_summary(detail):
    """Project endpoint evidence from the existing detail, independent of Profile/Plan."""
    references = []
    edition = detail.selected_edition
    if edition:
        for section in ("registration", "competition"):
            window = getattr(edition, section + "_window")
            for endpoint in ("start", "end"):
                field = section + "_" + endpoint
                value = getattr(window, endpoint + "_at") if window else None
                provenance = next((p for p in detail.provenance if p.section == "time_windows"
                    and p.source.verification_status.value == "verified"
                    and any(t.field == field for t in p.temporal)), None)
                if value is not None and provenance:
                    precision = next(t.precision for t in provenance.temporal if t.field == field)
                    references.append(TimeReference(kind="VERIFIED", field=field, scope="edition", value=value,
                        source=provenance.source, observed_at=provenance.source.observed_at,
                        precision=precision, verification="verified"))
    for candidate in detail.temporal_candidates:
        if candidate.source.source_type.value == "official" and candidate.verification_status.value == "pending":
            references.append(TimeReference(kind="OFFICIAL_CANDIDATE", field=candidate.field,
                scope="track" if candidate.track_id else "edition", raw_text=candidate.raw_text,
                source=candidate.source, observed_at=candidate.source.observed_at,
                precision=candidate.precision, verification="pending", candidate=candidate))
    references.sort(key=lambda t: (t.field, t.kind, t.raw_text or ""))
    availability = "VERIFIED" if any(t.kind == "VERIFIED" for t in references) else (
        "OFFICIAL_CANDIDATE" if references else "UNKNOWN")
    return MyTimeSummary(availability=availability, references=tuple(references))


class NextActionProjection(ProfileValue):
    policy_version: Literal["next-action-v1"] = "next-action-v1"
    kind: Literal["DETAIL", "PROFILE", "ELIGIBILITY", "SKILL_GAP", "PLAN", "WORKSPACE", "EVIDENCE"]
    label: str
    reason_code: str
    target: MyCompetitionTarget


def next_action(target, *, target_available, profile_available, eligibility, skill_gap, plan):
    if not target_available:
        kind, label, reason = "DETAIL", "查看赛事详情", "TARGET_UNAVAILABLE"
    elif not profile_available:
        kind, label, reason = "PROFILE", "完善个人画像", "CURRENT_PROFILE_UNAVAILABLE"
    elif eligibility.availability == "NOT_ANALYZED":
        kind, label, reason = "ELIGIBILITY", "判断参赛资格", "ELIGIBILITY_NOT_ANALYZED"
    elif eligibility.availability != "AVAILABLE" or eligibility.status in ("unknown", "ineligible"):
        kind, label, reason = "EVIDENCE", "查看资格依据", "ELIGIBILITY_REVIEW_REQUIRED"
    elif eligibility.profile_freshness.status != "CURRENT":
        kind, label, reason = "ELIGIBILITY", "重新判断参赛资格", "ELIGIBILITY_PROFILE_NOT_CURRENT"
    elif skill_gap.availability == "NOT_ANALYZED":
        kind, label, reason = "SKILL_GAP", "分析技能差距", "SKILL_GAP_NOT_ANALYZED"
    elif skill_gap.availability != "AVAILABLE":
        kind, label, reason = "EVIDENCE", "查看分析依据", "SKILL_GAP_UNAVAILABLE"
    elif skill_gap.profile_freshness.status != "CURRENT":
        kind, label, reason = "SKILL_GAP", "重新分析技能差距", "SKILL_GAP_PROFILE_NOT_CURRENT"
    elif plan.availability == "NOT_SELECTED":
        kind, label, reason = "PLAN", "生成备赛计划", "PLAN_NOT_SELECTED"
    elif plan.availability != "AVAILABLE":
        kind, label, reason = "EVIDENCE", "查看计划引用", "PLAN_REFERENCE_UNAVAILABLE"
    elif plan.profile_freshness.status == "STALE":
        kind, label, reason = "WORKSPACE", "查看较早计划 / 重新生成", "PLAN_PROFILE_STALE"
    elif plan.profile_freshness.status == "UNKNOWN":
        kind, label, reason = "WORKSPACE", "查看计划依据", "PLAN_PROFILE_UNKNOWN"
    else:
        kind, label, reason = "WORKSPACE", "查看备赛工作区", "PLAN_PROFILE_CURRENT"
    return NextActionProjection(kind=kind, label=label, reason_code=reason, target=target)


class MyCompetitionProjection(ProfileValue):
    relationship_ref: RelationshipReference
    student_id: StableId
    target: MyCompetitionTarget
    relationship_state: RelationshipState
    display_identity: DisplayIdentity
    eligibility_summary: DerivedSummary
    skill_gap_summary: DerivedSummary
    plan_summary: DerivedSummary
    planning_summary: MyPlanningSummary
    time_summary: MyTimeSummary
    next_action: NextActionProjection
    section_availability: tuple[str, ...]
    persistence_boundary: Literal["HOST_MEMORY"] = "HOST_MEMORY"
    audit: RelationshipSnapshot

    @model_validator(mode="after")
    def exact_identity(self):
        if (self.relationship_ref != self.audit.relationship_ref or self.student_id != self.relationship_ref.student_id
                or self.target != self.relationship_ref.target or self.relationship_state != self.audit.relationship.state
                or self.next_action.target != self.target):
            raise ValueError("My Competition projection identity mismatch")
        for kind, summary in (("ELIGIBILITY", self.eligibility_summary), ("SKILL_GAP", self.skill_gap_summary),
                              ("PLAN_REFERENCE", self.plan_summary)):
            if summary.result_ref and (summary.result_ref.student_id, summary.result_ref.target) != (self.student_id, self.target):
                raise ValueError("Summary identity mismatch")
            if summary.availability == "AVAILABLE" and (summary.result_ref is None or summary.result_ref.kind != kind):
                raise ValueError("Available summary needs an exact selected result")
        if self.plan_summary.availability == "AVAILABLE" and self.plan_summary.plan_ref is None:
            raise ValueError("Available Plan summary needs an exact Plan reference")
        return self


class MyCompetitionsProjection(ProfileValue):
    student_id: StableId
    competitions: tuple[MyCompetitionProjection, ...]
    persistence_boundary: Literal["HOST_MEMORY"] = "HOST_MEMORY"

    @model_validator(mode="after")
    def student_scope(self):
        if any(item.student_id != self.student_id for item in self.competitions):
            raise ValueError("My Competitions student mismatch")
        return self


def authorize(actor, student_id):
    if student_id not in actor.permitted_student_ids:
        raise ProfileError("MY_COMPETITION_FORBIDDEN")


def relationship_access(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except (OSError, RuntimeError) as exc:
        raise ProfileError("MY_COMPETITION_REPOSITORY_UNAVAILABLE") from exc


class MyCompetitionEditor:
    def __init__(self, relationships: StudentCompetitionRepository, competitions: CompetitionRepository,
                 actor: ProfileActorBinding, *, clock):
        self.relationships, self.competitions, self.actor, self.clock = relationships, competitions, actor, clock

    def mutate(self, command: MyCompetitionCommand) -> MyCompetitionMutationResult:
        authorize(self.actor, command.student_id)
        if command.operation == "add":
            if command.expected_reference is not None:
                raise ProfileError("MY_COMPETITION_INVALID_REFERENCE")
            t = command.target
            try:
                self.competitions.get_competition(t.competition_id)
                edition = self.competitions.get_edition(t.edition_id)
                track = self.competitions.get_track(t.track_id) if t.track_id else None
                if edition.competition_id != t.competition_id or (track and track.edition_id != t.edition_id):
                    raise ProfileError("MY_COMPETITION_INVALID_TARGET")
            except RepositoryEntityNotFoundError as exc:
                raise ProfileError("MY_COMPETITION_INVALID_TARGET") from exc
            snapshot = relationship_access(self.relationships.add, command.student_id, t, command.state, now=self.clock())
        else:
            ref = command.expected_reference
            if ref is None or ref.student_id != command.student_id or ref.target != command.target:
                raise ProfileError("MY_COMPETITION_INVALID_REFERENCE")
            snapshot = relationship_access(self.relationships.get_exact, command.student_id, command.target)
            if snapshot is None:
                raise ProfileError("MY_COMPETITION_NOT_FOUND")
            if command.operation == "remove":
                relationship_access(self.relationships.remove, ref)
            else:
                snapshot = relationship_access(self.relationships.replace_state, ref, command.state, now=self.clock())
        return MyCompetitionMutationResult(snapshot=snapshot, removed=command.operation == "remove")


class MyCompetitionsReader:
    def __init__(self, relationships: StudentCompetitionRepository, results: DerivedResultReadStore,
                 profiles: StudentProfileRepository, actor: ProfileActorBinding, *, details, planning, plans):
        self.relationships, self.results, self.profiles, self.actor = relationships, results, profiles, actor
        self.details, self.planning, self.plans = details, planning, plans

    def read(self, query: GetProfileQuery) -> MyCompetitionsProjection:
        authorize(self.actor, query.student_id)
        snapshots = relationship_access(self.relationships.list_for_student, query.student_id)
        profile = self.profiles.get(query.student_id)
        return MyCompetitionsProjection(student_id=query.student_id,
            competitions=tuple(self._project(s, profile) for s in snapshots))

    def get(self, query: MyCompetitionQuery) -> MyCompetitionProjection:
        authorize(self.actor, query.student_id)
        snapshot = relationship_access(self.relationships.get_exact, query.student_id, query.target)
        if snapshot is None:
            raise ProfileError("MY_COMPETITION_NOT_FOUND")
        return self._project(snapshot, self.profiles.get(query.student_id))

    def _summary(self, student, target, kind, current):
        unknown = resolve_profile_freshness(None, current, student_id=student)
        try:
            ref = self.results.selected(student, target, kind)
        except (OSError, RuntimeError):
            return DerivedSummary(availability="UNAVAILABLE", label="结果读取服务暂不可用", profile_freshness=unknown)
        if ref is None:
            return DerivedSummary(availability="NOT_SELECTED" if kind == "PLAN_REFERENCE" else "NOT_ANALYZED",
                label={"ELIGIBILITY": "尚未判断", "SKILL_GAP": "尚未分析", "PLAN_REFERENCE": "尚未关联正式计划"}[kind],
                profile_freshness=unknown)
        try:
            if (ref.student_id, ref.target, ref.kind) != (student, target, kind):
                raise ValueError("Selected result identity mismatch")
            result = self.results.resolve(ref)
            if result is None:
                return DerivedSummary(availability="UNAVAILABLE", label="结果正文不可用", result_ref=ref,
                    profile_freshness=unknown)
            result = type(result).model_validate_json(result.model_dump_json())
            if result.reference != ref:
                raise ValueError("Retained result identity mismatch")
            freshness = resolve_profile_freshness(result.input_profile_ref, current, student_id=student)
            plan_ref = None
            if kind == "ELIGIBILITY":
                status = EligibilityDecision.model_validate_json(result.payload_json).status.value
                label = {"eligible": "符合已声明资格规则", "ineligible": "不满足已声明资格规则", "unknown": "资格待确认"}[status]
            elif kind == "SKILL_GAP":
                status = SkillGapDecision.model_validate_json(result.payload_json).gap_status.value
                label = {"gap_identified": "存在正式分析确认的技能差距", "no_gap": "当前分析未发现技能差距", "undetermined": "暂无法判断"}[status]
            else:
                plan_ref = PlanReference.model_validate_json(result.payload_json)
                plan = self.plans.resolve(plan_ref)
                if PlanReference.from_plan(plan) != plan_ref:
                    raise ValueError("Plan reference mismatch")
                input_ref = self.planning.lineage.read(plan_ref)
                if input_ref is not None and result.input_profile_ref is not None and input_ref != result.input_profile_ref:
                    raise ValueError("Plan input lineage mismatch")
                freshness = resolve_profile_freshness(input_ref, current, student_id=student)
                status = plan.status.value
                label = {"draft": "草案", "active": "进行中", "completed": "已完成",
                    "cancelled": "已取消", "superseded": "已被替代"}[status] + f" v{plan.version}"
            return DerivedSummary(availability="AVAILABLE", status=status, label=label, result_ref=ref,
                plan_ref=plan_ref, profile_freshness=freshness, audit_json=result.payload_json)
        except (ValueError, LookupError):
            return DerivedSummary(availability="INVALID_REFERENCE", label="结果引用不可用", result_ref=ref,
                profile_freshness=unknown)
        except (OSError, RuntimeError):
            return DerivedSummary(availability="UNAVAILABLE", label="结果读取服务暂不可用", result_ref=ref,
                profile_freshness=unknown)

    def _project(self, snapshot, profile):
        r, target = snapshot.relationship, snapshot.relationship.target()
        current = profile.profile_ref if profile else None
        summaries = [self._summary(r.student_id, target, kind, current)
                     for kind in ("ELIGIBILITY", "SKILL_GAP", "PLAN_REFERENCE")]
        eligibility, gap, plan = summaries
        display = DisplayIdentity(competition_name=None, edition_name=None, track_name=None)
        times = MyTimeSummary(availability="PROVIDER_UNAVAILABLE")
        issues, valid_target = [], True
        try:
            detail = self.details.read(CompetitionDetailQuery(**target.model_dump()))
            display = DisplayIdentity(competition_name=detail.competition.name,
                edition_name=detail.selected_edition.name if detail.selected_edition else None,
                track_name=detail.selected_track.name if detail.selected_track else None)
            times = time_summary(detail)
        except RepositoryEntityNotFoundError:
            valid_target = False
            issues.append("TARGET_UNAVAILABLE")
        except Exception:
            valid_target = False
            issues.append("PROVIDER_UNAVAILABLE")
        planning = MyPlanningSummary(availability="PROFILE_UNAVAILABLE" if profile is None else "PROVIDER_UNAVAILABLE")
        if valid_target and profile:
            try:
                if plan.availability == "INVALID_REFERENCE":
                    planning = MyPlanningSummary(availability="INVALID_REFERENCE")
                else:
                    workspace = self.planning.read(PlanningWorkspaceQuery(student_id=r.student_id,
                        **target.model_dump(), plan_ref=plan.plan_ref))
                    if workspace.current_profile_ref != current:
                        raise ValueError("Workspace profile snapshot changed during read")
                    planning = MyPlanningSummary(availability="AVAILABLE",
                        confirmed_constraints_count=len(workspace.confirmed_constraints),
                        pending_confirmations_count=len(workspace.pending_confirmations),
                        has_advisory=bool(workspace.preparation_suggestions))
                    references = workspace.time_references
                    kind = "VERIFIED" if any(t.kind == "VERIFIED" for t in references) else (
                        "OFFICIAL_CANDIDATE" if references else "UNKNOWN")
                    times = MyTimeSummary(availability=kind, references=references)
            except Exception:
                issues.append("PLANNING_PROVIDER_UNAVAILABLE")
        return MyCompetitionProjection(relationship_ref=snapshot.relationship_ref, student_id=r.student_id,
            target=target, relationship_state=r.state, display_identity=display,
            eligibility_summary=eligibility, skill_gap_summary=gap, plan_summary=plan,
            planning_summary=planning, time_summary=times,
            next_action=next_action(target, target_available=valid_target, profile_available=profile is not None,
                eligibility=eligibility, skill_gap=gap, plan=plan),
            section_availability=tuple(issues), audit=snapshot)
