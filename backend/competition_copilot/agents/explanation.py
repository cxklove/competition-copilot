"""Bounded explanation projection/rendering. Domain results remain authoritative.

The model composes a structured draft using supplied sentence variants. Arbitrary
paraphrases are deliberately rejected: this validator is not a natural-language
fact checker. Neither context construction nor generation calls a capability.
"""

import json
from enum import Enum, StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel

from competition_copilot.agents.capabilities import AgentCapabilityResult, EventBatch
from competition_copilot.agents.contracts import (
    AgentContract,
    AgentIntent,
    AuditReferences,
    CapabilityId,
    ResultReference,
    WorkflowStatus,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.application.my_competitions import (
    MyCompetitionMutationResult,
    MyCompetitionProjection,
    MyCompetitionsProjection,
    MyPlanSelectionResult,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.digital_twin import (
    CompetitionSnapshot,
    SnapshotDiff,
    StableId,
)
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.plan_revision_service import PlanRevisionResult
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingResult,
)
from competition_copilot.domain.replanning import (
    EventImpactAnalysis,
    PlanReference,
    ReplanningDecision,
    ReplanningEvidence,
)
from competition_copilot.domain.skill_gap import SkillGapDecision
from competition_copilot.domain.source_metadata import SourceMetadata


class EvidenceKind(StrEnum):
    REASON_CODE = "REASON_CODE"
    SOURCE = "SOURCE"
    DOMAIN_EVIDENCE = "DOMAIN_EVIDENCE"
    PLAN_DIFF = "PLAN_DIFF"
    APPROVAL_AUDIT = "APPROVAL_AUDIT"
    UNCERTAINTY = "UNCERTAINTY"


class GroundingEvidence(AgentContract):
    id: StableId
    kind: EvidenceKind
    reference: ResultReference
    reason_code: StableId | None = None
    source: SourceMetadata | None = None
    code: str | None = None
    field: str | None = None
    value: str | int | float | bool | None = None
    event_id: StableId | None = None
    plan_id: StableId | None = None
    milestone_ids: tuple[StableId, ...] = ()
    source_change_fields: tuple[StableId, ...] = ()


class ExplanationFact(AgentContract):
    id: StableId
    statements: tuple[StableId, ...]


class ExplanationContext(AgentContract):
    request_id: StableId
    intent: AgentIntent
    capability: CapabilityId | None
    workflow_outcome: WorkflowStatus
    result_type: StableId
    authoritative_status: StableId
    primary_ref: ResultReference
    result_refs: tuple[ResultReference, ...]
    reason_codes: tuple[StableId, ...]
    evidence: tuple[GroundingEvidence, ...]
    facts: tuple[ExplanationFact, ...]
    summary_options: tuple[StableId, ...]
    uncertainty_statement: StableId | None
    plan_refs: tuple[PlanReference, ...] = ()


class ExplanationPoint(AgentContract):
    fact_id: StableId
    text: StableId


class ExplanationDraft(AgentContract):
    """No decision, score, status, authority, operation or new citation payload."""
    result_ref: ResultReference
    summary: StableId
    key_points: tuple[ExplanationPoint, ...]
    uncertainty_statement: StableId | None
    evidence_refs: tuple[StableId, ...]
    source_refs: tuple[StableId, ...]
    reason_codes: tuple[StableId, ...]


class ExplanationModel(Protocol):
    def explain(self, context: ExplanationContext) -> ExplanationDraft:
        ...


class ExplanationRendering(AgentContract):
    message: StableId
    model_used: bool
    fallback_reason: Literal["NO_MODEL", "MODEL_ERROR", "INVALID_DRAFT", "CONTEXT_LIMIT"] | None = None
    events: tuple[StableId, ...]


def _value(value):
    return value.value if isinstance(value, Enum) else value


def _quoted(value):
    """Literal artifact data, never instructions or inferred business claims."""
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _resolve(data, pointer):
    """Resolve only existing Facade audit pointers, never fetch an artifact/URL."""
    node = data
    for part in pointer.split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, BaseModel) and key in type(node).model_fields:
            node = getattr(node, key)
        elif isinstance(node, (list, tuple)):
            node = node[int(key)]
        else:
            return None
    return node


def _grounding(audit, receipt):
    items = {}
    for reason in audit.reasons:
        item = GroundingEvidence(id="REASON_CODE:" + reason.result.kind.value + ":" + reason.result.ref_id + ":" + reason.reason_code,
            kind="REASON_CODE", reference=reason.result, reason_code=reason.reason_code)
        items[item.id] = item
    for ref in audit.results:
        if ref.kind not in ("SOURCE", "EVIDENCE", "PLAN_DIFF", "APPROVAL_REQUEST", "APPROVAL_RESPONSE", "AUTHORITY"):
            continue
        source, code, field, value = None, None, None, None
        lineage = {}
        if receipt is not None and ref.ref_id.startswith(receipt.result_ref.ref_id + "#/data/"):
            pointer = ref.ref_id[len(receipt.result_ref.ref_id + "#/data/"):]
            try:
                node = _resolve(receipt.data, pointer)
            except (KeyError, IndexError, ValueError):
                node = None
            if isinstance(node, SourceMetadata):
                source = node
            if isinstance(node, Evidence):
                # External/free prose is not an approved sentence. Keep structured
                # rule evidence and provenance; no raw messages/profile dumps.
                code, field, value = node.code, node.field, node.value
            if isinstance(node, ReplanningEvidence):
                lineage = {"event_id": node.event_id, "plan_id": node.plan_id,
                    "milestone_ids": node.milestone_ids, "source_change_fields": node.source_change_fields}
        kind = ("SOURCE" if ref.kind == "SOURCE" else "PLAN_DIFF" if ref.kind == "PLAN_DIFF" else
                "DOMAIN_EVIDENCE" if ref.kind == "EVIDENCE" else "APPROVAL_AUDIT")
        item = GroundingEvidence(id=ref.kind.value + ":" + ref.ref_id, kind=kind,
            reference=ref, source=source, code=code, field=field, value=value, **lineage)
        items[item.id] = item
    return tuple(items[key] for key in sorted(items))


def build_explanation_context(state: AgentState, receipt: AgentCapabilityResult | None = None) -> ExplanationContext:
    """Explicit typed projection; no full Domain object dump or business rules.

    Recommendation/Plan details have fixed display limits, preserving producer
    order and exact omitted counts. All audit references remain available. An
    oversized context never reaches the model (see generate_explanation).
    """
    facts, uncertainty, plans, extra_refs = [], [], [], []
    audit = state.audit
    if receipt is not None:
        audit = AuditReferences(results=tuple({(r.kind, r.ref_id): r for r in
            (*audit.results, *receipt.audit.results)}.values()), reasons=tuple({
                (r.result.kind, r.result.ref_id, r.reason_code): r for r in
                (*audit.reasons, *receipt.audit.reasons)}.values()))
    capability = receipt.capability if receipt is not None else (state.invocation.capability if state.invocation else None)
    outcome = WorkflowStatus.COMPLETED if receipt is not None else state.status
    primary = receipt.result_ref if receipt is not None else ResultReference(
        kind="APPROVAL_REQUEST", ref_id=state.approval_request.approval_request_id)
    status, result_type, title = "SUCCESS", "CapabilityResult", "能力执行"

    def fact(key, text):
        facts.append(ExplanationFact(id=key, statements=(text, "记录显示：" + text)))

    def plan(reference, label):
        plans.append(reference)
        fact(label, f"{label}：Plan {_quoted(reference.plan_id)}，版本 {reference.version}。")

    def decision(value):
        extra_refs.extend(ResultReference(kind="EVENT", ref_id=e) for e in value.trigger_event_ids)
        fact("replanning", "重规划决定：" + value.outcome.value.upper() + "；决定本身不表示已修改计划。")
        fact("scope", f"影响范围：{value.scope.state.value.upper()}；whole_plan={value.scope.whole_plan}。")
        if value.outcome == "undetermined" or value.scope.state != "known":
            uncertainty.append("重规划结论或原始影响范围存在未确定信息")
        for i, impact in enumerate(value.impacts):
            fact(f"trigger.{i}", f"触发事件 {_quoted(impact.event.id)}；Impact={impact.outcome.value.upper()}。")

    data = receipt.data if receipt is not None else None
    if receipt is None:
        pending = state.approval_request
        if pending is None:
            raise ValueError("An authoritative result or approval interaction is required")
        result_type = "ApprovalRequest"
        status = "REJECTED" if state.approval_response and state.approval_response.decision == "REJECT" else "WAITING_FOR_APPROVAL"
        title = "用户审批"
        extra_refs.extend((primary, pending.decision_ref, pending.affected_scope_ref,
                           pending.proposed_input_ref, *pending.instruction_refs))
        if pending.resolution_ref:
            extra_refs.append(pending.resolution_ref)
        if status == "WAITING_FOR_APPROVAL":
            fact("approval", "需要你的明确确认才能执行；当前尚未执行修改。")
        else:
            fact("approval", "你已拒绝此次修改；未执行 mutation，未生成新的 PlanDiff。")
        fact("operation", "拟议操作（请求原文）：" + _quoted(pending.summary))
        plan(pending.before_plan, "before")
        fact("decision_ref", "ReplanningDecision 引用：" + _quoted(pending.decision_ref.ref_id))
        fact("scope_ref", "AffectedPlanScope 引用：" + _quoted(pending.affected_scope_ref.ref_id))
    elif isinstance(data, EligibilityDecision):
        result_type, status, title = "EligibilityDecision", data.status.value.upper(), "资格检查"
        for i, rule in enumerate(data.rule_evaluations[:10]):
            fact(f"rule.{i}", f"规则 {_quoted(rule.rule_id)}：{rule.status.value.upper()}；reason={rule.reason_code.value}。")
        if data.status == "unknown":
            uncertainty.append("资格信息不足，UNKNOWN 不表示可以参赛")
        elif any(rule.status == "unknown" for rule in data.rule_evaluations):
            uncertainty.append("部分资格信息未确定；已确定的 " + status + " 结论不变")
    elif isinstance(data, RecommendationRankingResult):
        result_type, status, title = "RecommendationRankingResult", "RANKED", "推荐结果"
        for bucket in ("confirmed", "uncertain", "blocked"):
            entries = getattr(data, bucket)
            fact(bucket, f"{bucket}：{len(entries)} 个结果；沿用 P6 原有 bucket 和顺序。")
            for i, entry in enumerate(entries[:5]):
                evaluation = entry if bucket == "blocked" else entry.evaluation
                target = evaluation.candidate
                rank = None if bucket == "blocked" else entry.rank
                fact(f"{bucket}.{i}", f"{bucket}；rank={rank}；target=" +
                    _quoted((target.competition_id, target.edition_id, target.track_id)) +
                    f"；score={evaluation.suitability_score}。")
            if len(entries) > 5:
                fact(bucket + ".omitted", f"{bucket} 其余 {len(entries) - 5} 个结果未在解释中展开。")
        if data.uncertain or any(e.evaluation.suitability_score is None for e in (*data.confirmed, *data.uncertain)):
            uncertainty.append("推荐中存在资格或评分未确定的信息；uncertain 不等于 confirmed")
    elif isinstance(data, SkillGapDecision):
        result_type, status, title = "SkillGapDecision", data.gap_status.value.upper(), "技能差距"
        fact("coverage", "需求覆盖：" + data.requirements.coverage.value.upper() + "。")
        extra_refs.extend(ResultReference(kind="EVIDENCE", ref_id=receipt.result_ref.ref_id +
            f"#/data/audit_evidence/{i}") for i in range(len(data.audit_evidence)))
        for i, item in enumerate(data.items[:10]):
            fact(f"skill.{i}", f"技能 {_quoted(item.requirement.skill_id)}：{item.status.value.upper()}；student_level=" +
                 _quoted(_value(item.student_level)) + "；required_level=" + _quoted(_value(item.requirement.required_level)) + "。")
        if data.gap_status == "undetermined" or data.requirements.coverage != "complete" or any(i.status == "unknown" for i in data.items):
            uncertainty.append("技能/需求信息不足或覆盖不完整，不能推断未证实的技能差距")
    elif isinstance(data, CompetitionPlan):
        result_type, status, title = "CompetitionPlan", data.status.value.upper(), "备赛计划"
        plan(PlanReference.from_plan(data), "plan")
        fact("inventory", f"实际 PlanningNeeds={len(data.planning_needs)}，Milestones={len(data.milestones)}。")
        if data.planning_horizon is not None:
            fact("horizon", f"实际 horizon：{data.planning_horizon.start_at} 至 {data.planning_horizon.end_at}。")
        for i, need in enumerate(data.planning_needs[:10]):
            fact(f"need.{i}", f"PlanningNeed {_quoted(need.id)}：{need.kind.value}。")
        for i, milestone in enumerate(data.milestones[:10]):
            fact(f"milestone.{i}", f"Milestone {_quoted(milestone.id)}；source_need={_quoted(milestone.source_need_id)}；due_at={milestone.due_at}。")
        if any(m.start_at is None or m.due_at is None for m in data.milestones):
            uncertainty.append("部分里程碑时间未提供，不推断日期或 deadline")
        if data.skill_gap_audit and (data.skill_gap_audit.gap_status == "undetermined" or data.skill_gap_audit.coverage != "complete"):
            uncertainty.append("计划保留原技能/需求不确定性；未提供的时间不作推断")
    elif isinstance(data, EventImpactAnalysis):
        result_type, status, title = "EventImpactAnalysis", data.outcome.value.upper(), "计划影响"
        plan(data.plan, "plan")
        fact("event", "事件引用：" + _quoted(data.event.id))
        extra_refs.append(ResultReference(kind="EVENT", ref_id=data.event.id))
        fact("category", "事件类别：" + str(_value(data.event.category)))
        if data.outcome == "undetermined" or data.scope.state != "known":
            uncertainty.append("计划影响或范围尚未确定，不能解释为无影响")
    elif isinstance(data, ReplanningDecision):
        result_type, status, title = "ReplanningDecision", data.outcome.value.upper(), "重规划决定"
        decision(data)
        if data.outcome == "keep_current_plan":
            fact("keep", "决定保留当前计划；本次未执行计划修改。")
    elif isinstance(data, PlanRevisionResult):
        result_type, status, title = "PlanRevisionResult", (
            "REVISION_COMPLETED" if data.plan_diff.decision.outcome == "replan"
            else data.plan_diff.decision.outcome.value.upper()), "计划修订"
        diff = data.plan_diff
        extra_refs.extend((ResultReference(kind="PLAN_DIFF", ref_id=receipt.result_ref.ref_id + "#/data/plan_diff"),
                           ResultReference(kind="REPLANNING_INPUT", ref_id=data.replanning_input.id)))
        plan(PlanReference.from_plan(diff.before), "before")
        plan(PlanReference.from_plan(diff.after), "after")
        decision(diff.decision)
        if diff.decision.outcome != "replan":
            fact("no_revision", "此次未执行计划修改；before/after 保持一致。")
        if diff.status_change is not None:
            fact("status_change", f"实际 PlanDiff：status {diff.status_change.before_status.value} -> {diff.status_change.after_status.value}。")
        fact("milestone_change", f"实际 PlanDiff milestone 批次={len(diff.changes)}；只描述该 Diff 记录的修改。")
        for i, instruction in enumerate(data.replanning_input.instructions[:10]):
            fact(f"revision.{i}", f"已授权 milestone {_quoted(instruction.target_milestone_id)}：due_at {instruction.expected_before.due_at} -> {instruction.after.due_at}。")
        if data.replanning_input.plan_status_instruction:
            fact("authority", "此次修订的 approval_ref：" + _quoted(data.replanning_input.plan_status_instruction.authority.approval_ref))
    elif isinstance(data, SnapshotDiff):
        result_type, status, title = "SnapshotDiff", "DIFF_RECORDED", "赛事快照差异"
        fact("snapshots", f"快照 {_quoted(data.before.snapshot_id)} -> {_quoted(data.after.snapshot_id)}。")
        for i, change in enumerate(data.changes):
            fact(f"change.{i}", f"{change.field}：{change.kind.value}；{change.before.state.value} -> {change.after.state.value}。")
            if change.kind == "observation_state_changed":
                uncertainty.append("观测覆盖变化不是赛事事实删除，也不表示取消")
    elif isinstance(data, CompetitionSnapshot):
        result_type, status, title = "CompetitionSnapshot", "SNAPSHOT_RECORDED", "赛事快照"
        fact("snapshot", f"快照 {_quoted(data.snapshot_id)}；观测于 {data.observed_at.isoformat()}。")
        for name in ("registration_window", "competition_window", "track_membership"):
            observation = getattr(data.dynamic_state, name)
            fact(name, f"{name}：{observation.state.value}。")
            if observation.state == "unknown":
                uncertainty.append("未观测事实仍为 UNKNOWN，不能视为不存在")
    elif isinstance(data, (MyCompetitionsProjection, MyCompetitionProjection, MyCompetitionMutationResult, MyPlanSelectionResult)):
        result_type, status, title = type(data).__name__, "READ_OR_SELF_MUTATION_RECORDED", "我的赛事"
        fact("workspace", "我的赛事操作已返回；关系与业务分析结果分别展示。")
    elif isinstance(data, EventBatch):
        result_type, status, title = "EventBatch", "EVENTS_RECORDED", "赛事事件"
        for i, event in enumerate(data.events[:10]):
            fact(f"event.{i}", f"事件 {_quoted(event.id)}：{event.event_type.value}；category={_value(event.category)}。")
            if event.category == "observation_change":
                uncertainty.append("观测覆盖变化不是赛事事实变更或取消")
    else:
        # Six P4 read envelopes: select IDs only, never rules/private payloads.
        result_type, title = type(data).__name__, "赛事读取"
        collections = {"competitions": "competition", "editions": "edition", "tracks": "track"}
        for field, singular in collections.items():
            if field in type(data).model_fields:
                entries = getattr(data, field)
                fact(field, f"返回 {len(entries)} 个 {singular}。")
                for i, entity in enumerate(entries[:10]):
                    fact(f"{field}.{i}", f"{singular} ID：{_quoted(entity.id)}。")
            elif singular in type(data).model_fields:
                fact(singular, f"{singular} ID：{_quoted(getattr(data, singular).id)}。")
    label = {"ELIGIBLE": "符合资格", "INELIGIBLE": "不符合资格", "UNKNOWN": "信息不足",
        "NO_GAP": "未发现差距", "GAP_IDENTIFIED": "已识别差距", "UNDETERMINED": "尚未确定",
        "KEEP_CURRENT_PLAN": "保留当前计划", "NO_PLAN_IMPACT": "无计划影响",
        "REPLAN": "需要重规划，尚不代表执行", "WAITING_FOR_APPROVAL": "等待明确批准",
        "REJECTED": "已拒绝，未执行修改", "REVISION_COMPLETED": "修订已执行"}.get(status, status)
    summaries = (f"{title}结果：{status}（{label}）。", f"本次{title}结论为 {status}（{label}）。")
    audit = AuditReferences(results=tuple({(r.kind, r.ref_id): r for r in
        (*audit.results, *extra_refs)}.values()), reasons=audit.reasons)
    uncertainty_statement = "不确定性：" + "；".join(dict.fromkeys(uncertainty)) + "。" if uncertainty else None
    grounding = _grounding(audit, receipt)
    if uncertainty_statement:
        grounding = (*grounding, GroundingEvidence(id="UNCERTAINTY:" + primary.ref_id,
            kind="UNCERTAINTY", reference=primary, value=uncertainty_statement))
    return ExplanationContext(request_id=state.request.request_id, intent=state.intent,
        capability=capability, workflow_outcome=outcome, result_type=result_type,
        authoritative_status=status, primary_ref=primary, result_refs=audit.results,
        reason_codes=tuple(sorted({r.reason_code for r in audit.reasons})),
        evidence=grounding, facts=tuple(facts), summary_options=summaries,
        uncertainty_statement=uncertainty_statement,
        plan_refs=tuple({(p.plan_id, p.version, p.content_digest): p for p in plans}.values()))


class ExplanationGroundingValidator:
    """Exact allowlists, not speculative keyword checks on arbitrary prose."""
    @staticmethod
    def validate(context: ExplanationContext, draft: ExplanationDraft) -> ExplanationDraft:
        draft = ExplanationDraft.model_validate(draft)
        if draft.result_ref != context.primary_ref or draft.summary not in context.summary_options:
            raise ValueError("Unsupported result or conclusion")
        if tuple(p.fact_id for p in draft.key_points) != tuple(f.id for f in context.facts):
            raise ValueError("Facts/order must preserve the authoritative projection")
        if any(p.text not in f.statements for p, f in zip(draft.key_points, context.facts, strict=True)):
            raise ValueError("Unsupported statement")
        if draft.uncertainty_statement != context.uncertainty_statement:
            raise ValueError("Required uncertainty must be preserved")
        if draft.reason_codes != context.reason_codes:
            raise ValueError("Unsupported or omitted reason code")
        for ids, allowed in ((draft.evidence_refs, {e.id for e in context.evidence}),
                             (draft.source_refs, {e.id for e in context.evidence if e.kind == "SOURCE"})):
            if len(ids) != len(set(ids)) or not set(ids).issubset(allowed):
                raise ValueError("Unknown evidence/source reference")
        if context.evidence and not draft.evidence_refs:
            raise ValueError("Evidence citation required")
        if any(e.kind == "SOURCE" for e in context.evidence) and not draft.source_refs:
            raise ValueError("Source citation required")
        return draft


def _render(context, summary, points, uncertainty):
    lines = [summary, *points]
    if uncertainty:
        lines.append(uncertainty)
    if context.reason_codes:
        lines.append("原因代码：" + ", ".join(context.reason_codes))
    lines.append("结果引用：" + context.primary_ref.ref_id)
    evidence = [e.reference.ref_id for e in context.evidence if e.kind == "DOMAIN_EVIDENCE"]
    if evidence:
        lines.append("证据引用：" + ", ".join(dict.fromkeys(evidence[:3])))
    sources = [e for e in context.evidence if e.kind == "SOURCE"]
    for item in sources[:3]:
        source = item.source
        lines.append("来源引用：" + item.reference.ref_id + ("；" + str(source.source_url) +
            f"；type={source.source_type.value}；verification={source.verification_status.value}；observed_at={source.observed_at.isoformat()}"
            if source else ""))
    return "\n".join(lines)


def deterministic_explanation(context: ExplanationContext) -> str:
    """Capability-specific facts/status above supply all fallback templates."""
    return _render(context, context.summary_options[0], [f.statements[0] for f in context.facts],
                   context.uncertainty_statement)


def generate_explanation(context: ExplanationContext, model: ExplanationModel | None) -> ExplanationRendering:
    events = ["explanation_context_built"]
    reason = "NO_MODEL"
    if model is not None and len(context.model_dump_json().encode("utf-8")) > 65536:
        reason = "CONTEXT_LIMIT"
    elif model is not None:
        events.append("explanation_model_called")
        try:
            # Give even a malicious injected fake only a detached immutable value.
            raw = model.explain(ExplanationContext.model_validate_json(context.model_dump_json()))
        except Exception:
            reason = "MODEL_ERROR"
        else:
            try:
                draft = ExplanationGroundingValidator.validate(context, raw)
            except Exception:
                reason = "INVALID_DRAFT"
            else:
                return ExplanationRendering(message=_render(context, draft.summary,
                    [p.text for p in draft.key_points], draft.uncertainty_statement),
                    model_used=True, events=tuple((*events, "explanation_grounding_passed")))
    return ExplanationRendering(message=deterministic_explanation(context), model_used=False,
        fallback_reason=reason, events=tuple((*events, "explanation_fallback_used")))
