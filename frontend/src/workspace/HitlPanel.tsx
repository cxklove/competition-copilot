import { useState } from 'react';
import { ClarificationPanel } from './ClarificationPanel.tsx';
import type { PlanReference } from '../runtime/generated/contracts.ts';
import type {
  AgentResponse,
  ApprovalDecision,
  ClarificationValues,
} from '../runtime/generated/contracts.ts';
import type { PublicInteraction } from './interactions.ts';
import type { InteractionResult } from './useConversation.ts';

export function HitlPanel({
  response,
  interaction,
  disabled,
  clarify,
  decide,
  plans,
}: {
  response: AgentResponse;
  interaction: PublicInteraction | null;
  disabled: boolean;
  plans?: readonly PlanReference[];
  clarify: (token: string, values: ClarificationValues) => Promise<InteractionResult>;
  decide: (token: string, decision: ApprovalDecision) => Promise<InteractionResult>;
}) {
  const [error, setError] = useState('');
  const locked = disabled || !interaction;
  if (response.outcome === 'NEEDS_CLARIFICATION' && response.clarification) {
    return (
      <ClarificationPanel
        proposal={response.clarification}
        interaction={interaction}
        disabled={disabled}
        plans={plans}
        clarify={clarify}
      />
    );
  }
  if (response.outcome !== 'WAITING_FOR_APPROVAL' || !response.approval_request) return null;
  const proposal = response.approval_request;
  const plan = proposal.before_plan;
  const rows: [string, string][] = [
    ['操作', proposal.action],
    ['请求 ID', proposal.source_request_id],
    ['批准请求 ID', proposal.approval_request_id],
    ['调用 ID', proposal.invocation_id],
    ['目标方案', plan.plan_id],
    ['学生 ID', plan.student_id],
    ['方案版本', String(plan.version)],
    ['方案指纹', plan.content_digest],
    ['方案时间', plan.updated_at],
    ['目标竞赛', plan.target.competition_id],
    ['目标届次', plan.target.edition_id],
    ...(plan.target.track_id ? [['目标赛道', plan.target.track_id] as [string, string]] : []),
    ['范围引用', proposal.affected_scope_ref.ref_id],
    ['决策引用', proposal.decision_ref.ref_id],
    ['输入引用', proposal.proposed_input_ref.ref_id],
    ...(proposal.resolution_ref
      ? [['范围解析引用', proposal.resolution_ref.ref_id] as [string, string]]
      : []),
    ['指令引用', proposal.instruction_refs.map((ref) => ref.ref_id).join(', ')],
    ['理由代码', (proposal.audit.reasons ?? []).map((ref) => ref.reason_code).join(', ')],
    [
      '依据引用',
      (proposal.audit.results ?? [])
        .filter((ref) => ref.kind === 'EVIDENCE')
        .map((ref) => ref.ref_id)
        .join(', '),
    ],
  ];
  return (
    <section className="hitl-panel" aria-labelledby="approval-title">
      <h3 id="approval-title">请明确批准或拒绝</h3>
      <p>{proposal.summary}</p>
      <dl className="approval-context">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {proposal.proposed_after_plan && (
        <p>
          提议方案引用：{proposal.proposed_after_plan.plan_id} · 版本{' '}
          {proposal.proposed_after_plan.version}
        </p>
      )}
      <p className="hitl-note">
        以上为返回的提案与引用；未提供的影响内容不会在此推断。点击仅发送你的决定，须等待 Runtime
        确认结果。
      </p>
      <div className="approval-actions">
        <button
          type="button"
          className="approve-button"
          disabled={locked}
          onClick={() => {
            setError('');
            void decide(interaction!.token, 'APPROVE').then((result) => {
              if (!result.accepted) setError(result.error ?? '交互已失效。');
            });
          }}
        >
          APPROVE · 批准提案
        </button>
        <button
          type="button"
          className="reject-button"
          disabled={locked}
          onClick={() => {
            setError('');
            void decide(interaction!.token, 'REJECT').then((result) => {
              if (!result.accepted) setError(result.error ?? '交互已失效。');
            });
          }}
        >
          REJECT · 拒绝提案
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
