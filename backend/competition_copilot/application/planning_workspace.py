"""Read-side preparation advice. Never writes a Plan or evaluates a decision."""

import hashlib
import json
from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field, model_validator

from competition_copilot.application.competition_detail import (
    CompetitionDetailQuery,
    CompetitionDetailReader,
    DetailAvailability,
)
from competition_copilot.application.plans import PlanRegistry
from competition_copilot.application.profile_freshness import (
    DerivedProfileBinding,
    ProfileFreshness,
    resolve_profile_freshness,
)
from competition_copilot.application.profile_skills import (
    SkillCatalogQuery,
    SkillCatalogReader,
)
from competition_copilot.application.profiles import ProfileActorBinding
from competition_copilot.application.temporal_evidence import TemporalCandidateSnapshot
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileReference,
    ProfileValue,
    StudentProfileProjection,
    StudentProfileRepository,
)


def _identity(prefix, value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return prefix + ":" + hashlib.sha256(raw.encode()).hexdigest()


class PlanInputLineageReader(Protocol):
    def read(self, reference: PlanReference) -> ProfileReference | None: ...


class MappedPlanInputLineageReader:
    def __init__(self, bindings: Mapping[str, DerivedProfileBinding]):
        self.bindings = bindings

    def read(self, reference: PlanReference) -> ProfileReference | None:
        matches = {b.input_profile_ref for b in self.bindings.values()
                   if b.kind == "CompetitionPlan" and b.plan_ref == reference}
        if len(matches) > 1:
            raise ValueError("Conflicting exact Plan input lineage")
        return next(iter(matches)) if matches else None


class PlanningWorkspaceQuery(CompetitionDetailQuery):
    student_id: str = Field(min_length=1)
    plan_ref: PlanReference | None = None


class WorkspaceEvidence(ProfileValue):
    code: str
    message: str
    field: str | None
    value_json: str
    source: SourceMetadata | None


def _evidence(facts):
    return tuple(WorkspaceEvidence(code=e.code, message=e.message, field=e.field,
        value_json=json.dumps(e.model_dump(mode="json")["value"], sort_keys=True, ensure_ascii=False),
        source=e.source) for e in facts)


class ConfirmedConstraint(ProfileValue):
    constraint_id: str
    type: Literal["skill_identity", "skill_level", "eligibility", "time"]
    field: str
    label: str
    value: str
    scope: Literal["competition", "edition", "track"]
    source: SourceMetadata
    evidence: tuple[WorkspaceEvidence, ...] = ()
    verification: Literal["verified"] = "verified"

    @model_validator(mode="after")
    def verified_source(self):
        if self.source.verification_status is not VerificationStatus.VERIFIED:
            raise ValueError("Constraint requires verified source")
        return self


class PreparationBasis(ProfileValue):
    profile_ref: ProfileReference
    skill_id: str
    profile_skill_state: Literal["recorded", "missing", "unknown"]
    requirement_version: str
    requirement_target: CompetitionDetailQuery
    evidence: tuple[WorkspaceEvidence, ...]


class AdvisoryPreparationTask(ProfileValue):
    task_id: str
    template_id: str
    policy_version: Literal["preparation-advisory-v1"] = "preparation-advisory-v1"
    title: str
    description: str
    advisory: Literal[True] = True
    related_skill_ids: tuple[str, ...]
    target: CompetitionDetailQuery
    profile_ref: ProfileReference
    source_basis: PreparationBasis
    suggested_sequence: int = Field(ge=1)

    @model_validator(mode="after")
    def exact_basis(self):
        if (self.profile_ref != self.source_basis.profile_ref or self.target != self.source_basis.requirement_target
                or self.related_skill_ids != (self.source_basis.skill_id,)):
            raise ValueError("Advisory source binding mismatch")
        expected = _identity("advisory", {"template": self.template_id, "policy": self.policy_version,
            "target": self.target.model_dump(mode="json"), "basis": self.source_basis.model_dump(mode="json")})
        if self.task_id != expected:
            raise ValueError("Advisory content identity mismatch")
        return self


class PreparationAdvisoryPolicy:
    policy_version = "preparation-advisory-v1"

    def prepare(self, profile: StudentProfileProjection, target: CompetitionDetailQuery,
                artifact: SkillRequirementSetEnvelope | None, names: Mapping[str, str]):
        if artifact is None:
            return ()
        t = artifact.requirement_set.target
        if (t.competition_id, t.edition_id, t.track_id) != (target.competition_id, target.edition_id, target.track_id):
            raise ValueError("Advisory requirement scope mismatch")
        skills = {s.skill_id: s for s in profile.skills}
        tasks = []
        for requirement in sorted(artifact.requirement_set.requirements, key=lambda r: r.skill_id):
            skill = skills.get(requirement.skill_id)
            state = "missing" if skill is None else "unknown" if skill.level is SkillLevel.UNKNOWN else "recorded"
            basis = PreparationBasis(profile_ref=profile.profile_ref, skill_id=requirement.skill_id,
                profile_skill_state=state, requirement_version=artifact.requirement_version,
                requirement_target=target, evidence=_evidence(requirement.presence_evidence))
            name = names[requirement.skill_id]  # Catalog failure is never a guessed name.
            if state == "missing":
                templates = (("record", f"建议补充 {name} 技能画像", "尚未记录不代表没有能力；可先了解相关能力要求。"),)
            elif state == "unknown":
                templates = (("assess", f"建议进行 {name} 能力自评", "已记录该技能，等级尚未评定；可完成一次基础练习并记录自评。"),)
            elif requirement.skill_id == "mathematical-modeling":
                templates = (
                    ("model-case", "建议完成一次完整数学建模案例训练", "自主练习完整建模流程；不表示存在技能差距或赛事规定了训练任务。"),
                    ("model-review", "建议复盘模型选择与结果评价", "记录模型选择、假设、验证与复盘过程。"),
                    ("model-tools", "建议整理建模工具和个人模板", "整理可复用的个人工具与练习记录；不是官方材料要求。"))
            else:
                templates = (("practice", f"建议开展 {name} 案例练习", "自主练习并复盘相关技能；不判断等级达标或能力不足。"),)
            for template, title, description in templates:
                identity = {"template": template, "policy": self.policy_version,
                    "target": target.model_dump(mode="json"), "basis": basis.model_dump(mode="json")}
                tasks.append(AdvisoryPreparationTask(task_id=_identity("advisory", identity),
                    template_id=template, title=title, description=description,
                    related_skill_ids=(requirement.skill_id,), target=target,
                    profile_ref=profile.profile_ref, source_basis=basis, suggested_sequence=len(tasks) + 1))
        return tuple(sorted(tasks, key=lambda t: (t.suggested_sequence, t.task_id))[:6])


class PendingConfirmation(ProfileValue):
    confirmation_id: str
    type: Literal["requirement", "profile", "time", "plan_need", "policy"]
    title: str
    description: str
    scope: Literal["competition", "edition", "track"]
    source_basis: tuple[WorkspaceEvidence, ...] = ()
    reason_codes: tuple[str, ...]


class TimeReference(ProfileValue):
    kind: Literal["VERIFIED", "OFFICIAL_CANDIDATE"]
    field: Literal["registration", "competition", "registration_start", "registration_end", "competition_start", "competition_end"]
    scope: Literal["edition", "track"]
    value: AwareDatetime | None = None
    raw_text: str | None = None
    source: SourceMetadata
    observed_at: AwareDatetime
    precision: Literal["minute", "second", "DATETIME", "DATE", "MONTH", "TEXT_ONLY"]
    verification: VerificationStatus
    candidate: TemporalCandidateSnapshot | None = None

    @model_validator(mode="after")
    def temporal_authority(self):
        if self.kind == "VERIFIED":
            if (self.value is None or self.candidate is not None or self.raw_text is not None
                    or self.verification is not VerificationStatus.VERIFIED
                    or self.source.verification_status is not VerificationStatus.VERIFIED
                    or self.field in ("registration", "competition") or self.precision not in ("minute", "second")):
                raise ValueError("Verified time reference requires structured endpoint evidence")
        else:
            c = self.candidate
            if (c is None or self.value is not None or self.source.source_type is not SourceType.OFFICIAL
                    or self.verification is not VerificationStatus.PENDING
                    or c.verification_status is not VerificationStatus.PENDING
                    or (self.field, self.raw_text, self.precision, self.source, self.observed_at, self.scope) != (
                        c.field, c.raw_text, c.precision, c.source, c.source.observed_at, "track" if c.track_id else "edition")):
                raise ValueError("Candidate reference must preserve pending evidence without a structured value")
        return self


class WorkspacePlanSummary(ProfileValue):
    plan_id: str
    version: int
    status: str


class WorkspaceProfileContext(ProfileValue):
    weekly_available_hours: float | None
    goals: tuple[str, ...]
    interests: tuple[str, ...]
    persistence_boundary: Literal["HOST_MEMORY"] = "HOST_MEMORY"


class WorkspaceAvailability(ProfileValue):
    detail: DetailAvailability
    plan: Literal["AVAILABLE", "NOT_SELECTED"]
    profile: Literal["AVAILABLE"] = "AVAILABLE"
    suggestions: Literal["AVAILABLE", "NO_EXACT_REQUIREMENT"]


class PlanningWorkspaceProjection(ProfileValue):
    schema_version: Literal["1.0"] = "1.0"
    student_id: str
    target: CompetitionDetailQuery
    competition_name: str
    edition_name: str | None
    track_name: str | None
    plan_summary: WorkspacePlanSummary | None
    plan_ref: PlanReference | None
    plan_input_profile_ref: ProfileReference | None
    plan_freshness: ProfileFreshness
    current_profile_ref: ProfileReference
    profile_context: WorkspaceProfileContext
    confirmed_constraints: tuple[ConfirmedConstraint, ...]
    preparation_suggestions: tuple[AdvisoryPreparationTask, ...]
    pending_confirmations: tuple[PendingConfirmation, ...]
    time_references: tuple[TimeReference, ...]
    section_availability: WorkspaceAvailability
    plan_original_json: str | None

    @model_validator(mode="after")
    def identity_binding(self):
        if self.current_profile_ref.student_id != self.student_id:
            raise ValueError("Workspace profile identity mismatch")
        if self.plan_ref and (self.plan_ref.student_id, self.plan_ref.target.competition_id,
                self.plan_ref.target.edition_id, self.plan_ref.target.track_id) != (
                self.student_id, self.target.competition_id, self.target.edition_id, self.target.track_id):
            raise ValueError("Workspace Plan identity mismatch")
        if any(t.profile_ref != self.current_profile_ref or t.target != self.target
               or t.source_basis.profile_ref != t.profile_ref for t in self.preparation_suggestions):
            raise ValueError("Workspace advisory binding mismatch")
        if self.plan_freshness.current_profile_ref != self.current_profile_ref or self.plan_freshness.input_profile_ref != self.plan_input_profile_ref:
            raise ValueError("Workspace freshness binding mismatch")
        return self


class PlanningWorkspaceReader:
    def __init__(self, profiles: StudentProfileRepository, plans: PlanRegistry,
                 lineage: PlanInputLineageReader, details: CompetitionDetailReader,
                 catalog: SkillCatalogReader, actor: ProfileActorBinding):
        self.profiles, self.plans, self.lineage = profiles, plans, lineage
        self.details, self.catalog, self.actor = details, catalog, actor
        self.advisory = PreparationAdvisoryPolicy()

    def read(self, query: PlanningWorkspaceQuery) -> PlanningWorkspaceProjection:
        if query.student_id not in self.actor.permitted_student_ids:
            raise ProfileError("PROFILE_EDIT_FORBIDDEN")
        profile = self.profiles.get(query.student_id)
        if profile is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        target = CompetitionDetailQuery(competition_id=query.competition_id,
            edition_id=query.edition_id, track_id=query.track_id)
        plan, input_ref = None, None
        if query.plan_ref:
            r = query.plan_ref
            if (r.student_id, r.target.competition_id, r.target.edition_id, r.target.track_id) != (
                    query.student_id, query.competition_id, query.edition_id, query.track_id):
                raise ProfileError("PLANNING_IDENTITY_MISMATCH")
            try:
                plan = self.plans.resolve(r)
            except ValueError as exc:
                raise ProfileError("PLAN_REFERENCE_UNAVAILABLE") from exc
            if PlanReference.from_plan(plan) != r:
                raise ProfileError("PLANNING_IDENTITY_MISMATCH")
            input_ref = self.lineage.read(r)
            if input_ref and input_ref.student_id != query.student_id:
                raise ProfileError("PLANNING_IDENTITY_MISMATCH")
        detail = self.details.read(target)
        names = {s.skill_id: s.name for s in self.catalog.read(SkillCatalogQuery()).skills}
        constraints, pending, times = [], [], []
        scope = "track" if query.track_id else "edition" if query.edition_id else "competition"

        def confirm(kind, field, label, value, source, evidence=(), fact_scope=None):
            constraints.append(ConfirmedConstraint(constraint_id=_identity("constraint",
                [target.model_dump(mode="json"), field, value, source.model_dump(mode="json")]),
                type=kind, field=field, label=label, value=value, scope=fact_scope or scope,
                source=source, evidence=_evidence(evidence)))

        def wait(kind, key, title, reason, facts=(), fact_scope=None):
            pending.append(PendingConfirmation(confirmation_id=_identity("confirmation",
                [target.model_dump(mode="json"), kind, key]), type=kind, title=title,
                description=title, scope=fact_scope or scope, source_basis=_evidence(facts),
                reason_codes=(reason,) if isinstance(reason, str) else reason))

        artifact = detail.skill_requirements
        if artifact:
            for requirement in sorted(artifact.requirement_set.requirements, key=lambda r: r.skill_id):
                name = names[requirement.skill_id]
                presence = requirement.presence_evidence
                confirm("skill_identity", requirement.skill_id, "已核验相关技能", name, presence[0].source, presence)
                if requirement.required_level is None:
                    wait("requirement", requirement.skill_id, f"{name} 所需能力等级尚未明确",
                         "REQUIREMENT_PROFICIENCY_UNSPECIFIED", presence)
                else:
                    facts = requirement.evidence
                    confirm("skill_level", requirement.skill_id + ".required_level", name + " 等级要求",
                        requirement.required_level.value, facts[0].source, facts)
                skill = next((s for s in profile.skills if s.skill_id == requirement.skill_id), None)
                if skill is None:
                    wait("profile", requirement.skill_id, f"尚未记录 {name} 技能", "STUDENT_SKILL_RECORD_MISSING")
                elif skill.level is SkillLevel.UNKNOWN:
                    wait("profile", requirement.skill_id, f"{name} 已记录，等级尚未评定", "STUDENT_SKILL_LEVEL_UNKNOWN")
            if artifact.requirement_set.coverage.value != "complete":
                wait("requirement", "coverage", "当前技能要求覆盖仍不完整",
                     "REQUIREMENT_DATA_MISSING" if artifact.requirement_set.coverage.value == "missing" else "PARTIAL_REQUIREMENT_COVERAGE")
        else:
            wait("requirement", "coverage", "暂无当前范围的已审核技能要求" if query.edition_id else "请选择届次后查看技能要求",
                 "NO_EXACT_REQUIREMENT" if query.edition_id else "NOT_REQUESTED")
        if detail.eligibility_policy:
            for rule in sorted(detail.eligibility_policy.constraints, key=lambda r: r.rule_id):
                if rule.source.verification_status is VerificationStatus.VERIFIED:
                    confirm("eligibility", rule.rule_id, "已核验参赛规则", rule.evidence_text,
                            rule.source, fact_scope=rule.scope.value)
            if detail.eligibility_policy.coverage.value != "complete":
                wait("policy", "coverage", "当前资格规则覆盖仍不完整", "PARTIAL_POLICY_COVERAGE")
        else:
            wait("policy", "coverage", "暂无当前范围的已审核资格规则" if query.edition_id else "请选择届次后查看资格规则",
                 "NO_EXACT_POLICY" if query.edition_id else "NOT_REQUESTED")
        edition = detail.selected_edition
        if edition is None:
            wait("time", "edition", "请选择届次后查看时间信息", "NOT_REQUESTED", fact_scope="edition")
        for section, label in (("registration", "报名"), ("competition", "比赛")):
            if edition is None:
                break
            window = getattr(edition, section + "_window") if edition else None
            for endpoint, text in (("start", "开始"), ("end", "结束")):
                field = section + "_" + endpoint
                instant = getattr(window, endpoint + "_at") if window else None
                provenance = next((p for p in detail.provenance if p.section == "time_windows"
                    and p.source.verification_status is VerificationStatus.VERIFIED
                    and any(t.field == field for t in p.temporal)), None)
                if instant is not None and provenance:
                    precision = next(t.precision for t in provenance.temporal if t.field == field)
                    confirm("time", field, label + text, instant.isoformat(), provenance.source, fact_scope="edition")
                    times.append(TimeReference(kind="VERIFIED", field=field, scope="edition", value=instant,
                        source=provenance.source, observed_at=provenance.source.observed_at,
                        precision=precision, verification=VerificationStatus.VERIFIED))
                else:
                    wait("time", field, f"正式{label}{text}时间尚未确认" if edition else "请选择届次后查看时间信息",
                         "VERIFIED_TIME_UNAVAILABLE" if edition else "NOT_REQUESTED", fact_scope="edition")
        for candidate in sorted(detail.temporal_candidates, key=lambda c: c.candidate_id):
            if candidate.source.source_type is SourceType.OFFICIAL and candidate.verification_status is VerificationStatus.PENDING:
                times.append(TimeReference(kind="OFFICIAL_CANDIDATE", field=candidate.field,
                    scope="track" if candidate.track_id else "edition", raw_text=candidate.raw_text,
                    source=candidate.source, observed_at=candidate.source.observed_at,
                    precision=candidate.precision, verification=candidate.verification_status, candidate=candidate))
        if plan:
            for need in plan.planning_needs:
                if need.kind.value == "uncertainty_resolution":
                    wait("plan_need", need.id, "原计划待确认事项：" + (
                        names.get(need.source_item.requirement.skill_id, need.source_item.requirement.skill_id)
                        if need.source_item else "赛事要求覆盖"), tuple(r.value for r in need.reason_codes),
                        need.source_item.requirement.presence_evidence if need.source_item else ())
        return PlanningWorkspaceProjection(student_id=query.student_id, target=target,
            competition_name=detail.competition.name, edition_name=edition.name if edition else None,
            track_name=detail.selected_track.name if detail.selected_track else None,
            plan_summary=WorkspacePlanSummary(plan_id=plan.id, version=plan.version, status=plan.status.value) if plan else None,
            plan_ref=query.plan_ref, plan_input_profile_ref=input_ref,
            plan_freshness=resolve_profile_freshness(input_ref, profile.profile_ref, student_id=query.student_id),
            current_profile_ref=profile.profile_ref,
            profile_context=WorkspaceProfileContext(weekly_available_hours=profile.weekly_available_hours,
                goals=profile.goals, interests=profile.interests),
            confirmed_constraints=tuple(sorted(constraints, key=lambda c: (c.type, c.field, c.constraint_id))),
            preparation_suggestions=self.advisory.prepare(profile, target, artifact, names),
            pending_confirmations=tuple(sorted(pending, key=lambda p: (p.type, p.confirmation_id))),
            time_references=tuple(sorted(times, key=lambda t: (t.field, t.kind, t.raw_text or ""))),
            section_availability=WorkspaceAvailability(detail=detail.availability,
                plan="AVAILABLE" if plan else "NOT_SELECTED", suggestions="AVAILABLE" if artifact else "NO_EXACT_REQUIREMENT"),
            plan_original_json=plan.model_dump_json() if plan else None)
