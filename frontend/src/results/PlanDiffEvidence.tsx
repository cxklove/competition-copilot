import type { ReactNode } from 'react';
import type { AgentResponse } from '../runtime/generated/contracts.ts';
import type { PlanDiff, SourceMetadata } from './generated/artifacts.ts';
import { SourceGroups } from './SourceGroups.tsx';
import { isControlledDemo } from './SourceMetadata.tsx';
import { planStatus } from './SemanticResults.tsx';

export function PlanDiffEvidence({
  diffs,
  response,
  sources = [],
  audit,
}: {
  diffs: readonly PlanDiff[];
  response?: AgentResponse;
  sources?: readonly SourceMetadata[];
  audit?: ReactNode;
}) {
  const allSources = [
    ...diffs.flatMap((diff) => diff.decision.impacts.map((impact) => impact.event.source)),
    ...sources,
  ];
  const controlled = allSources.some((source) => isControlledDemo(source.source_url));
  const refs = response?.audit?.results ?? [];
  // Approval wording requires the backend's completed revision and explicit
  // approval/authority audit refs, never user text, a click or a changed status.
  const approved =
    response?.outcome === 'COMPLETED' &&
    response.intent === 'REQUEST_PLAN_REVISION' &&
    ['APPROVAL_REQUEST', 'APPROVAL_RESPONSE', 'AUTHORITY'].every((kind) =>
      refs.some((ref) => ref.kind === kind),
    );
  return (
    <>
      <details className="plan-diff-evidence">
        <summary>查看决策依据</summary>
        {diffs.map((diff, index) => (
          <ol key={index} aria-label="触发事件">
            {diff.decision.impacts.map((impact) => (
              <li key={impact.event.id}>
                <p>
                  {isControlledDemo(impact.event.source.source_url)
                    ? '模拟赛事变化'
                    : '已返回赛事变化记录'}
                </p>
                {impact.reason_codes.includes('target_track_removed') ? (
                  <p>当前目标赛道发生变化</p>
                ) : impact.event.event_type === 'track_membership_changed' ? (
                  <p>赛事赛道成员信息发生变化</p>
                ) : (
                  <p>赛事信息发生变化，具体内容见审计记录。</p>
                )}
                <p>
                  {impact.outcome === 'affects_plan'
                    ? '当前计划受到影响'
                    : impact.outcome === 'no_plan_impact'
                      ? '当前计划未受影响（沿用返回结论）'
                      : '当前计划是否受到影响尚无法确认'}
                </p>
              </li>
            ))}
            <li>
              {diff.decision.outcome === 'replan'
                ? '系统判断需要重新规划'
                : diff.decision.outcome === 'keep_current_plan'
                  ? '系统判断保持当前计划'
                  : '系统尚无法确定是否需要调整计划'}
            </li>
            {approved && diff.decision.outcome === 'replan' && (
              <li>用户批准调整（本次结果包含审批与授权记录）</li>
            )}
            <li>
              {diff.status_change
                ? `实际 PlanDiff：${planStatus(diff.status_change.before_status)} → ${planStatus(diff.status_change.after_status)}`
                : diff.changes?.length
                  ? '实际 PlanDiff：后端已返回里程碑集合变更'
                  : '实际 PlanDiff：未声明变化'}
            </li>
          </ol>
        ))}
      </details>
      <details className="plan-diff-sources">
        <summary>{controlled ? '查看演示数据来源' : '查看赛事变化来源'}</summary>
        {controlled && (
          <>
            <h5>演示数据来源</h5>
            <p>类型：受控演示数据</p>
            <p>本次变化仅用于展示事件驱动重规划能力，不代表 Huawei 官方真实发生该变化。</p>
          </>
        )}
        <SourceGroups sources={allSources} />
      </details>
      <details className="plan-diff-audit">
        <summary>查看高级审计信息</summary>
        <details>
          <summary>结果引用（{refs.length}）</summary>
          <ul aria-label="结果引用">
            {refs.map((ref, index) => (
              <li key={index}>
                {ref.kind} · {ref.ref_id}
              </li>
            ))}
          </ul>
        </details>
        <ul aria-label="重规划证据引用">
          {diffs.flatMap((diff) =>
            diff.decision.impacts.flatMap((impact) =>
              impact.evidence.map((entry, index) => (
                <li key={`${impact.event.id}-${index}`}>
                  事件 {entry.event_id} · 方案 {entry.plan_id} · 字段{' '}
                  {entry.source_change_fields?.join(', ')}
                </li>
              )),
            ),
          )}
        </ul>
        {audit ?? <pre>{JSON.stringify(diffs, null, 2)}</pre>}
      </details>
    </>
  );
}
