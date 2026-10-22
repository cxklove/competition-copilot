import { useMemo } from 'react';
import type { AgentResponse } from '../runtime/generated/contracts.ts';
import { validateArtifacts } from './artifacts.ts';
import type { ArtifactReader, LinkedArtifact } from './artifacts.ts';
import { ReasonList } from './ReasonList.tsx';
import { EvidenceList } from './EvidenceList.tsx';
import { SourceLink, SourceMetadata } from './SourceMetadata.tsx';
import { PlanDiffView } from './PlanDiffView.tsx';
import { PlanDiffEvidence } from './PlanDiffEvidence.tsx';
import { ErrorPresentation } from './ErrorPresentation.tsx';
import {
  RecommendationCard,
  RecommendationResults,
  SkillGapResults,
  PlanTimeline,
} from './SemanticResults.tsx';

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
      <details>
        <summary>高级详情</summary>
        <code>{status}</code>
      </details>
      {uncertain && <p>返回结果保留不确定性，不能据此认定符合、不符合或已完成判断。</p>}
    </div>
  );
}
function ArtifactView({ artifact }: { artifact: LinkedArtifact }) {
  switch (artifact.model) {
    case 'CompetitionDetailProjection':
      return (
        <>
          <h4>{artifact.value.competition.name}</h4>
          <p>{artifact.value.selected_edition?.name ?? '尚未选择届次'}</p>
          <p>{artifact.value.selected_track?.name ?? '尚未指定赛道'}</p>
          <details>
            <summary>查看赛事读取详情</summary>
            <pre>{JSON.stringify(artifact.value, null, 2)}</pre>
          </details>
        </>
      );
    case 'EligibilityDecision': {
      const result = artifact.value;
      return (
        <>
          <BusinessStatus status={result.status} />
          <p>
            竞赛：{result.competition_id} · 届次：{result.edition_id}
            {result.track_id && ` · 赛道：${result.track_id}`}
          </p>
          <details>
            <summary>查看决策依据</summary>
            <ReasonList codes={result.reason_codes} />
          </details>
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
    case 'RecommendationEvaluation':
      return <RecommendationCard result={artifact.value} />;
    case 'SkillGapDecision':
      return (
        <>
          <BusinessStatus status={artifact.value.gap_status} />
          <SkillGapResults result={artifact.value} />
        </>
      );
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
    case 'ListCompetitionsOutput':
    case 'GetCompetitionOutput': {
      const competitions =
        artifact.model === 'ListCompetitionsOutput'
          ? artifact.value.competitions
          : [artifact.value.competition];
      return (
        <ul aria-label="赛事结果">
          {competitions.map((item) => (
            <li key={item.id}>
              <strong>{item.name}</strong>
              <p>竞赛 ID：{item.id}</p>
              {item.description && <p>{item.description}</p>}
              {item.official_url && <SourceLink url={item.official_url} />}
            </li>
          ))}
        </ul>
      );
    }
    case 'CompetitionPlan':
      return <PlanTimeline plan={artifact.value} />;
    case 'RecommendationRankingResult':
      return <RecommendationResults result={artifact.value} />;
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
  const diffs = resolved.artifacts.filter((artifact) => artifact.model === 'PlanDiff');
  if (diffs.length) {
    const sources = resolved.artifacts.flatMap((artifact) =>
      artifact.model === 'SourceMetadata'
        ? [artifact.value]
        : artifact.model === 'Evidence' && artifact.value.source
          ? [artifact.value.source]
          : [],
    );
    return (
      <div className="result-summary grounded-results">
        <h3>回复已就绪</h3>
        {diffs.map((artifact) => (
          <PlanDiffView key={artifact.ref.ref_id} diff={artifact.value} includeDetails={false} />
        ))}
        <PlanDiffEvidence
          diffs={diffs.map((artifact) => artifact.value)}
          sources={sources}
          response={response}
          audit={<pre>{JSON.stringify({ response, artifacts: resolved.artifacts }, null, 2)}</pre>}
        />
        <details className="semantic-raw">
          <summary>查看原始回复</summary>
          <p>{response.message}</p>
        </details>
      </div>
    );
  }
  const ranking = resolved.artifacts.find(
    (artifact) => artifact.model === 'RecommendationRankingResult',
  );
  const evaluation = resolved.artifacts.find(
    (artifact) => artifact.model === 'RecommendationEvaluation',
  );
  if (ranking || evaluation) {
    // Associated Evidence/Source artifacts belong to this same recommendation
    // delivery. Retain every validated body/ref once in the shared audit, rather
    // than rendering dozens of unrelated-looking disclosures beside the cards.
    const audit = <pre>{JSON.stringify({ response, artifacts: resolved.artifacts }, null, 2)}</pre>;
    return (
      <div className="result-summary grounded-results">
        {ranking ? (
          <RecommendationResults result={ranking.value} audit={audit} />
        ) : (
          evaluation && (
            <>
              <h3>推荐结果</h3>
              <RecommendationCard result={evaluation.value} />
              <details className="recommendation-audit">
                <summary>查看高级审计信息</summary>
                {audit}
              </details>
            </>
          )
        )}
        <details className="recommendation-raw">
          <summary>查看原始回复</summary>
          <p>{response.message}</p>
        </details>
      </div>
    );
  }
  const skillGap = resolved.artifacts.find((artifact) => artifact.model === 'SkillGapDecision');
  const plan = resolved.artifacts.find((artifact) => artifact.model === 'CompetitionPlan');
  if (skillGap || plan) {
    const audit = <pre>{JSON.stringify({ response, artifacts: resolved.artifacts }, null, 2)}</pre>;
    return (
      <div className="result-summary grounded-results">
        {skillGap ? (
          <SkillGapResults result={skillGap.value} audit={audit} />
        ) : (
          plan && <PlanTimeline plan={plan.value} audit={audit} />
        )}
        <details className="semantic-raw">
          <summary>查看原始回复</summary>
          <p>{response.message}</p>
        </details>
      </div>
    );
  }
  const audit = response.audit;
  const hasPrimary = resolved.artifacts.some(
    (artifact) => artifact.model !== 'Evidence' && artifact.model !== 'SourceMetadata',
  );
  const visibleArtifacts = hasPrimary
    ? resolved.artifacts.filter(
        (artifact) => artifact.model !== 'Evidence' && artifact.model !== 'SourceMetadata',
      )
    : resolved.artifacts;
  return (
    <div className="result-summary grounded-results">
      <h3>{response.outcome === 'FAILED' ? 'Agent 未完成请求' : '回复已就绪'}</h3>
      <p>说明见对话正文；以下只展示返回的结构化数据与引用。</p>
      {response.error && <ErrorPresentation error={response.error} />}
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
      {visibleArtifacts.map((artifact) => (
        <section
          className="result-artifact"
          key={`${artifact.ref.kind}:${artifact.ref.ref_id}`}
          aria-label={`结果 ${artifact.ref.ref_id}`}
        >
          <ArtifactView artifact={artifact} />
        </section>
      ))}
      <details className="audit-details">
        <summary>查看高级审计信息</summary>
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
        <details>
          <summary>结果引用（{audit?.results?.length ?? 0}）</summary>
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
        </details>
        {!audit?.results?.some((ref) => ref.kind === 'EVIDENCE') && !resolved.artifacts.length && (
          <p>无可用证据正文。</p>
        )}
        <pre>{JSON.stringify({ response, artifacts: resolved.artifacts }, null, 2)}</pre>
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
