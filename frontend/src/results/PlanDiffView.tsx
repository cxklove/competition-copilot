import type { PlanDiff, PlanMilestone } from './generated/artifacts.ts';
import type { ReactNode } from 'react';
import type { AgentResponse } from '../runtime/generated/contracts.ts';
import type { SourceMetadata } from './generated/artifacts.ts';
import { PlanDiffEvidence } from './PlanDiffEvidence.tsx';
import { isControlledDemo } from './SourceMetadata.tsx';
import { planStatus } from './SemanticResults.tsx';

function Milestones({ items }: { items: PlanMilestone[] }) {
  return items.length ? (
    <ul>
      {items.map((item) => (
        <li key={item.id}>
          <strong>{item.title}</strong>
          <details>
            <summary>任务详情</summary>
            <p>
              任务 ID：{item.id} · {item.status ?? '未提供状态'}
            </p>
            {item.description && <p>{item.description}</p>}
            {item.start_at && <p>开始时间：{item.start_at}</p>}
            {item.due_at && (
              <p>
                截止时间：<time dateTime={item.due_at}>{item.due_at}</time>
              </p>
            )}
            {item.estimated_hours != null && <p>预计工时：{item.estimated_hours}</p>}
            {!!item.dependency_ids?.length && <p>依赖：{item.dependency_ids.join(', ')}</p>}
            {item.source_need_id && <p>需求引用：{item.source_need_id}</p>}
          </details>
        </li>
      ))}
    </ul>
  ) : (
    <p>此集合为空。</p>
  );
}
export function PlanDiffView({
  diff,
  includeDetails = true,
  response,
  sources,
  audit,
}: {
  diff: PlanDiff;
  includeDetails?: boolean;
  response?: AgentResponse;
  sources?: readonly SourceMetadata[];
  audit?: ReactNode;
}) {
  return (
    <section className="plan-diff" aria-label="方案变更">
      <h4>方案变更 · 后端提供的 PlanDiff</h4>
      <p>
        决策：
        {diff.decision.outcome === 'replan'
          ? '需要调整计划'
          : diff.decision.outcome === 'keep_current_plan'
            ? '保持当前计划'
            : '尚无法确认是否调整'}
      </p>
      <p>
        版本：{diff.before.version} → {diff.after.version}
      </p>
      {diff.decision.reason_codes.includes('target_track_removed') && (
        <p>触发原因：目标赛道发生变化</p>
      )}
      {diff.decision.impacts.some((impact) => isControlledDemo(impact.event.source.source_url)) && (
        <p className="demo-notice">
          模拟赛事变化 / 演示数据：本次修订来自受控演示事件，不代表 Huawei 官方发生了该变化。
        </p>
      )}
      <div className="before-after">
        <div>
          <h5>变更前</h5>
          <p>版本 {diff.before.version}</p>
          <p>状态：{planStatus(diff.before.status)}</p>
        </div>
        <div>
          <h5>变更后</h5>
          <p>版本 {diff.after.version}</p>
          <p>状态：{planStatus(diff.after.status)}</p>
        </div>
      </div>
      {diff.status_change && (
        <p>
          方案状态：{planStatus(diff.status_change.before_status)} →{' '}
          {planStatus(diff.status_change.after_status)}
        </p>
      )}
      {!diff.changes?.length && !diff.status_change && (
        <p>返回的 Diff 未声明任何变化；未生成本地差异。</p>
      )}
      {(diff.changes ?? []).map((change, index) => (
        <div key={index}>
          <p>里程碑完整集合变更。契约未提供逐项新增/移除/更新分类，以下原样展示前后集合。</p>
          <div className="before-after">
            <section aria-label="变更前里程碑">
              <h5>变更前 · 包含原有任务</h5>
              <Milestones items={change.before} />
            </section>
            <section aria-label="变更后里程碑">
              <h5>变更后 · 返回的新集合</h5>
              <Milestones items={change.after} />
            </section>
          </div>
        </div>
      ))}
      {includeDetails && (
        <PlanDiffEvidence diffs={[diff]} response={response} sources={sources} audit={audit} />
      )}
      <p>
        Diff 评估时间：<time dateTime={diff.evaluated_at}>{diff.evaluated_at}</time>
      </p>
    </section>
  );
}
