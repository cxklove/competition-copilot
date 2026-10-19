import type { PlanDiff, PlanMilestone } from './generated/artifacts.ts';
import { ReasonList } from './ReasonList.tsx';
import { SourceMetadata } from './SourceMetadata.tsx';

function Milestones({ items }: { items: PlanMilestone[] }) {
  return items.length ? (
    <ul>
      {items.map((item) => (
        <li key={item.id}>
          <strong>{item.title}</strong>
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
        </li>
      ))}
    </ul>
  ) : (
    <p>此集合为空。</p>
  );
}
export function PlanDiffView({ diff }: { diff: PlanDiff }) {
  return (
    <section className="plan-diff" aria-label="方案变更">
      <h4>方案变更 · 后端提供的 PlanDiff</h4>
      <p>决策：{diff.decision.outcome}</p>
      <div className="before-after">
        <div>
          <h5>变更前</h5>
          <p>
            {diff.before.id} · 版本 {diff.before.version}
          </p>
          <p>状态：{diff.before.status}</p>
        </div>
        <div>
          <h5>变更后</h5>
          <p>
            {diff.after.id} · 版本 {diff.after.version}
          </p>
          <p>状态：{diff.after.status}</p>
        </div>
      </div>
      {diff.status_change && (
        <p>
          方案状态：{diff.status_change.before_status} → {diff.status_change.after_status}
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
      <h5>触发与理由</h5>
      <ReasonList codes={diff.decision.reason_codes} />
      <ul aria-label="触发事件">
        {diff.decision.impacts.map((impact) => (
          <li key={impact.event.id}>
            <p>事件：{impact.event.id}</p>
            <p>
              影响：{impact.outcome} · 范围：{impact.scope.state}
            </p>
            <SourceMetadata source={impact.event.source} />
            <ReasonList codes={impact.reason_codes} />
            <ul aria-label="重规划证据引用">
              {impact.evidence.map((item, index) => (
                <li key={index}>
                  事件 {item.event_id} · 方案 {item.plan_id} · 字段{' '}
                  {item.source_change_fields?.join(', ') || '未提供'}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <p>
        Diff 评估时间：<time dateTime={diff.evaluated_at}>{diff.evaluated_at}</time>
      </p>
    </section>
  );
}
