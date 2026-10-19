import { useMemo } from 'react';
import type { AgentResponse } from '../runtime/generated/contracts.ts';
import { validateArtifacts } from './artifacts.ts';
import type { ArtifactReader, LinkedArtifact } from './artifacts.ts';
import { ReasonList } from './ReasonList.tsx';
import { EvidenceList } from './EvidenceList.tsx';
import { SourceLink, SourceMetadata } from './SourceMetadata.tsx';
import { PlanDiffView } from './PlanDiffView.tsx';

const statuses: Record<string, string> = {
  eligible: '符合已声明资格规则',
  ineligible: '不符合已声明资格规则',
  unknown: '信息不足，资格无法确定',
  undetermined: '信息不足，无法确定',
  no_gap: '未发现已声明技能差距',
  gap_identified: '存在已确认技能差距',
  keep_current_plan: '保持当前方案',
  replan: '需要重规划',
  recommended: '建议考虑',
  not_recommended: '未推荐',
  eligibility_blocked: '资格条件阻断',
  eligibility_uncertain: '资格条件尚不确定',
  suitability_undetermined: '适配程度尚无法确定',
};
export function BusinessStatus({ status }: { status: string }) {
  const uncertain = [
    'unknown',
    'undetermined',
    'eligibility_uncertain',
    'suitability_undetermined',
  ].includes(status);
  return (
    <div className={uncertain ? 'business-status is-uncertain' : 'business-status'}>
      <strong>{statuses[status] ?? status}</strong>
      <code>{status}</code>
      {uncertain && <p>返回结果保留不确定性，不能据此认定符合、不符合或已完成判断。</p>}
    </div>
  );
}
function ArtifactView({ artifact }: { artifact: LinkedArtifact }) {
  switch (artifact.model) {
    case 'EligibilityDecision': {
      const result = artifact.value;
      return (
        <>
          <BusinessStatus status={result.status} />
          <p>
            竞赛：{result.competition_id} · 届次：{result.edition_id}
            {result.track_id && ` · 赛道：${result.track_id}`}
          </p>
          <ReasonList codes={result.reason_codes} />
          <EvidenceList evidence={result.evidence ?? []} />
          <details>
            <summary>逐项规则结果</summary>
            <ul>
              {result.rule_evaluations?.map((rule) => (
                <li key={rule.rule_id}>
                  {rule.rule_id} · {rule.scope} · {rule.target_id}
                  <p>{rule.message}</p>
                  <BusinessStatus status={rule.status} />
                </li>
              ))}
            </ul>
          </details>
        </>
      );
    }
    case 'RecommendationEvaluation': {
      const result = artifact.value;
      return (
        <>
          <BusinessStatus status={result.status} />
          <p>
            候选：{result.candidate.competition_id} · {result.candidate.edition_id} ·{' '}
            {result.candidate.track_id}
          </p>
          {result.suitability_score != null && <p>后端适配分：{result.suitability_score}</p>}
          <ReasonList codes={result.reason_codes} />
          <EvidenceList evidence={result.evidence ?? []} />
          <ul aria-label="评分分项">
            {result.score_components?.map((part) => (
              <li key={part.component_id}>
                {part.component_id} · {part.score}
                <p>{part.message}</p>
                <code>{part.reason_code}</code>
                <EvidenceList evidence={part.evidence} />
              </li>
            ))}
          </ul>
        </>
      );
    }
    case 'SkillGapDecision': {
      const result = artifact.value;
      return (
        <>
          <BusinessStatus status={result.gap_status} />
          <p>
            竞赛：{result.target.competition_id} · 届次：{result.target.edition_id}
          </p>
          <p>要求覆盖：{result.requirements.coverage}</p>
          <p>{result.requirements.coverage_note}</p>
          <ReasonList codes={result.reason_codes} />
          <EvidenceList evidence={result.audit_evidence} />
          <ul aria-label="技能结果">
            {result.items?.map((item) => (
              <li key={item.requirement.skill_id}>
                <strong>{item.requirement.skill_id}</strong>
                <p>返回状态：{item.status}</p>
                <p>
                  学生水平：{item.student_level ?? '未提供'} · 要求：
                  {item.requirement.required_level ?? '未指定'}
                </p>
                <ReasonList codes={item.reason_codes} />
                <EvidenceList
                  evidence={[
                    ...(item.requirement.presence_evidence ?? []),
                    ...(item.requirement.evidence ?? []),
                    ...(item.student_evidence ?? []),
                  ]}
                />
              </li>
            ))}
          </ul>
        </>
      );
    }
    case 'PlanDiff':
      return (
        <>
          <BusinessStatus status={artifact.value.decision.outcome} />
          <PlanDiffView diff={artifact.value} />
        </>
      );
    case 'Evidence':
      return <EvidenceList evidence={[artifact.value]} />;
    case 'SourceMetadata':
      return <SourceMetadata source={artifact.value} />;
  }
}

export function ResultPanel({
  response,
  readArtifacts,
}: {
  response: AgentResponse;
  readArtifacts?: ArtifactReader;
}) {
  const resolved = useMemo(() => {
    try {
      return {
        artifacts: validateArtifacts(
          response,
          response.outcome === 'COMPLETED' ? readArtifacts?.(response) : undefined,
        ),
        invalid: false,
      };
    } catch {
      return { artifacts: [], invalid: true };
    }
  }, [response, readArtifacts]);
  // HITL is rendered by P14.3; no final artifact/PlanDiff while awaiting a decision.
  if (response.outcome !== 'COMPLETED' && response.outcome !== 'FAILED') return null;
  const audit = response.audit;
  return (
    <div className="result-summary grounded-results">
      <h3>{response.outcome === 'FAILED' ? 'Agent 未完成请求' : '回复已就绪'}</h3>
      <p>说明见对话正文；以下只展示返回的结构化数据与引用。</p>
      {response.error && (
        <p>
          {response.error.code} · {response.error.message}
        </p>
      )}
      {resolved.invalid && (
        <p role="alert">
          ARTIFACT_CONTRACT_ERROR：结果正文与当前请求/引用或公开结构不一致，未展示正文。
        </p>
      )}
      {!resolved.artifacts.length && (
        <p className="unavailable">
          未提供可展示的业务结果正文；不会从说明推断业务状态或计算方案差异。
        </p>
      )}
      {resolved.artifacts.map((artifact) => (
        <section
          className="result-artifact"
          key={`${artifact.ref.kind}:${artifact.ref.ref_id}`}
          aria-label={`结果 ${artifact.ref.ref_id}`}
        >
          <h4>{artifact.ref.kind}</h4>
          <p className="artifact-identity">结果引用：{artifact.ref.ref_id}</p>
          <ArtifactView artifact={artifact} />
        </section>
      ))}
      <details className="audit-details">
        <summary>理由与结果引用</summary>
        <p>请求 ID：{response.request_id}</p>
        <ul aria-label="关联理由">
          {audit?.reasons?.map((reason, index) => (
            <li key={index}>
              <p>
                关联结果：{reason.result.kind} · {reason.result.ref_id}
              </p>
              <ReasonList codes={[reason.reason_code]} />
            </li>
          ))}
        </ul>
        {!audit?.reasons?.length && <p>未提供理由代码。</p>}
        <ul aria-label="结果引用">
          {audit?.results?.map((ref) => (
            <li key={`${ref.kind}:${ref.ref_id}`}>
              {ref.kind} · {ref.kind === 'SOURCE' ? <SourceLink url={ref.ref_id} /> : ref.ref_id}
              {['SOURCE', 'EVIDENCE', 'PLAN_DIFF'].includes(ref.kind) &&
                !resolved.artifacts.some(
                  (a) => a.ref.kind === ref.kind && a.ref.ref_id === ref.ref_id,
                ) && <span> · 仅有引用，正文/元数据未提供</span>}
            </li>
          ))}
        </ul>
        {!audit?.results?.some((ref) => ref.kind === 'EVIDENCE') && !resolved.artifacts.length && (
          <p>无可用证据正文。</p>
        )}
        <ul aria-label="方案引用">
          {response.plan_refs?.map((plan) => (
            <li key={`${plan.plan_id}:${plan.version}:${plan.content_digest}`}>
              {plan.plan_id} · 版本 {plan.version} · {plan.student_id}
              <p>指纹：{plan.content_digest}</p>
              <p>
                目标：{plan.target.competition_id} · {plan.target.edition_id} ·{' '}
                {plan.target.track_id}
              </p>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
