import { useState } from 'react';
import type {
  AgentResponse,
  ApprovalDecision,
  ClarificationValues,
} from '../runtime/generated/contracts.ts';
import schemas from '../runtime/generated/contracts.json' with { type: 'json' };
import { clarificationFields } from './interactions.ts';
import type { PublicInteraction } from './interactions.ts';
import type { InteractionResult } from './useConversation.ts';

export function HitlPanel({
  response,
  interaction,
  disabled,
  clarify,
  decide,
}: {
  response: AgentResponse;
  interaction: PublicInteraction | null;
  disabled: boolean;
  clarify: (token: string, values: ClarificationValues) => Promise<InteractionResult>;
  decide: (token: string, decision: ApprovalDecision) => Promise<InteractionResult>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const locked = disabled || !interaction;
  if (response.outcome === 'NEEDS_CLARIFICATION' && response.clarification) {
    const proposal = response.clarification;
    const unsupported = proposal.fields.some((field) => !clarificationFields[field]);
    return (
      <section className="hitl-panel" aria-labelledby="clarification-title">
        <h3 id="clarification-title">补充所需信息</h3>
        <p>{proposal.question}</p>
        {interaction?.context && (
          <p className="context-summary">
            原请求上下文：
            {Object.entries(interaction.context)
              .filter(
                ([key, value]) => value != null && key !== 'plan_ref' && key !== 'profile_ref',
              )
              .map(([key, value]) => `${key}: ${value}`)
              .join(' · ') || '未提供标识字段'}
          </p>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (locked || unsupported) return;
            setError('');
            try {
              const answers: Record<string, unknown> = {};
              for (const field of proposal.fields) {
                const config = clarificationFields[field]!;
                const raw = values[field] ?? '';
                if (!raw.trim()) throw new Error('required');
                answers[config.key] = config.json ? JSON.parse(raw) : raw;
              }
              void clarify(interaction!.token, answers as ClarificationValues).then((result) => {
                if (!result.accepted) setError(result.error ?? '交互已失效。');
              });
            } catch {
              setError('请完整填写所请求字段；JSON 项须使用合法的结构化对象。');
            }
          }}
        >
          <fieldset disabled={locked || unsupported}>
            <legend>本次需要填写的字段</legend>
            {proposal.fields.map((field) => {
              const config = clarificationFields[field];
              const id = `clarify-${proposal.clarification_id}-${field}`;
              if (!config)
                return (
                  <p key={field} className="unsupported-field">
                    {field} 需要服务端可信上下文，不能在浏览器生成。
                  </p>
                );
              return (
                <div className="clarification-field" key={field}>
                  <label htmlFor={id}>
                    {config.label}
                    <small>{field}</small>
                  </label>
                  {field === 'INTENT' ? (
                    <select
                      id={id}
                      value={values[field] ?? ''}
                      required
                      onChange={(e) => setValues({ ...values, [field]: e.target.value })}
                    >
                      <option value="" disabled>
                        请选择意图
                      </option>
                      {schemas.AgentArtsInvocationEnvelope.$defs.AgentIntent.enum.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  ) : config.json || field === 'CAPABILITY_ARGUMENTS' ? (
                    <textarea
                      id={id}
                      rows={3}
                      required
                      value={values[field] ?? ''}
                      onChange={(e) => setValues({ ...values, [field]: e.target.value })}
                    />
                  ) : (
                    <input
                      id={id}
                      required
                      value={values[field] ?? ''}
                      onChange={(e) => setValues({ ...values, [field]: e.target.value })}
                    />
                  )}
                </div>
              );
            })}
            <button className="send-button" type="submit" disabled={locked || unsupported}>
              提交补充信息
            </button>
          </fieldset>
        </form>
        {error && <p role="alert">{error}</p>}
        <p className="hitl-note">
          只提交本次要求的字段。标识是否匹配、是否存在冲突，仍由 Runtime/Core 验证。
        </p>
      </section>
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
