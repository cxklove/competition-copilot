import { useState } from 'react';
import type {
  ClarificationRequest,
  ClarificationValues,
  PlanReference,
} from '../runtime/generated/contracts.ts';
import schemas from '../runtime/generated/contracts.json' with { type: 'json' };
import { clarificationFields } from './interactions.ts';
import type { PublicInteraction } from './interactions.ts';
import type { InteractionResult } from './useConversation.ts';
import { clarificationLabels, intentLabels } from './clarificationPresentation.ts';

export function ClarificationPanel({
  proposal,
  interaction,
  disabled,
  plans = [],
  clarify,
}: {
  proposal: ClarificationRequest;
  interaction: PublicInteraction | null;
  disabled: boolean;
  plans?: readonly PlanReference[];
  clarify: (token: string, values: ClarificationValues) => Promise<InteractionResult>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const locked = disabled || !interaction;
  const unsupported = proposal.fields.some((field) => !clarificationFields[field]);
  const choices = [
    ...new Map(
      [...(interaction?.context?.plan_ref ? [interaction.context.plan_ref] : []), ...plans].map(
        (ref) => [JSON.stringify(ref), ref],
      ),
    ).values(),
  ];
  const update = (key: string, value: string) =>
    setValues((previous) => ({ ...previous, [key]: value }));
  const advanced = proposal.fields.some(
    (field) =>
      field === 'CAPABILITY_ARGUMENTS' ||
      field === 'CAPABILITY_INVOCATION' ||
      (field === 'PLAN' && !choices.length),
  );
  const contextLabels = {
    student_id: '当前学生',
    competition_id: '当前赛事',
    edition_id: '当前届次',
    track_id: '当前赛道',
  } as const;
  function advancedInput(field: string, label: string) {
    return (
      <details
        className="advanced-clarification"
        onToggle={(event) => {
          const expanded = event.currentTarget.open;
          setOpen((prior) => ({ ...prior, [field]: expanded }));
        }}
      >
        <summary>查看高级输入{field === 'STUDENT_PROFILE' ? '（学生画像）' : ''}</summary>
        {open[field] && (
          <div className="clarification-field">
            <label htmlFor={`advanced-${proposal.clarification_id}-${field}`}>
              {label}（JSON）
            </label>
            <textarea
              id={`advanced-${proposal.clarification_id}-${field}`}
              rows={4}
              value={values[`${field}_JSON`] ?? ''}
              onChange={(e) => update(`${field}_JSON`, e.target.value)}
            />
          </div>
        )}
      </details>
    );
  }
  if (proposal.reason === 'MISSING_STUDENT_PROFILE') {
    return (
      <section className="hitl-panel" aria-label="画像不可用">
        <h3>请先确认个人画像</h3>
        <p>当前学生画像不可用。请确认已选择当前学生，并在“我的能力”中查看画像后重新发起操作。</p>
        <a href="#/profile">前往我的能力</a>
      </section>
    );
  }
  return (
    <section className="hitl-panel" aria-labelledby="clarification-title">
      <h3 id="clarification-title">补充所需信息</h3>
      <p>还需要补充一些信息</p>
      <p>为了继续完成当前操作，系统需要确认本次分析所需的信息。</p>
      {interaction?.context && (
        <dl className="context-summary">
          {Object.entries(contextLabels).flatMap(([key, label]) => {
            const value = interaction.context?.[key as keyof typeof contextLabels];
            return value
              ? [
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>,
                ]
              : [];
          })}
        </dl>
      )}
      {advanced && (
        <div className="clarification-limit">
          <strong>需要补充高级参数</strong>
          <p>
            当前操作需要额外结构化信息，普通界面暂无法安全生成。请主动展开高级输入；不会根据已有标识猜测业务参数。
          </p>
        </div>
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
              const json = values[`${field}_JSON`] ?? '';
              if (field === 'STUDENT_PROFILE' && !json.trim()) {
                if (!raw.trim()) throw new Error('required');
                answers.student = {
                  id: raw,
                  ...(values.STUDENT_EDUCATION
                    ? { education_level: values.STUDENT_EDUCATION }
                    : {}),
                };
              } else if (field === 'PLAN' && !json.trim() && choices.length) {
                const selected = raw === '' ? undefined : choices[Number(raw)];
                if (!selected) throw new Error('required');
                answers.plan_ref = selected;
              } else if (field === 'CAPABILITY_ARGUMENTS' || config.json) {
                if (!json.trim()) throw new Error('required');
                const parsed: unknown = JSON.parse(json);
                answers[config.key] = field === 'CAPABILITY_ARGUMENTS' ? json : parsed;
              } else {
                if (!raw.trim()) throw new Error('required');
                answers[config.key] = raw;
              }
            }
            void clarify(interaction!.token, answers as ClarificationValues).then((result) => {
              if (!result.accepted) setError(result.error ?? '交互已失效。');
            });
          } catch {
            setError('请完整填写本次请求的信息；高级输入需使用合法的结构化内容。');
          }
        }}
      >
        <fieldset disabled={locked || unsupported}>
          <legend>本次需要填写的信息</legend>
          {proposal.fields.map((field) => {
            const config = clarificationFields[field];
            if (!config) return <p key={field}>当前操作需要服务端可信上下文，不能在浏览器生成。</p>;
            const id = `clarify-${proposal.clarification_id}-${field}`;
            if (
              field === 'CAPABILITY_ARGUMENTS' ||
              field === 'CAPABILITY_INVOCATION' ||
              (field === 'PLAN' && !choices.length)
            )
              return <div key={field}>{advancedInput(field, clarificationLabels[field]!)}</div>;
            return (
              <div className="clarification-field" key={field}>
                <label htmlFor={id}>
                  {field === 'EDITION' && proposal.options?.some((option) => option.field === field)
                    ? '届次'
                    : clarificationLabels[field]}
                </label>
                {proposal.options?.some((option) => option.field === field) ? (
                  <select
                    id={id}
                    required
                    value={values[field] ?? ''}
                    onChange={(e) => update(field, e.target.value)}
                  >
                    <option value="" disabled>
                      {field === 'EDITION' ? '请选择届次' : '请选择'}
                    </option>
                    {proposal.options
                      .filter((option) => option.field === field)
                      .map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                  </select>
                ) : field === 'INTENT' ? (
                  <select
                    id={id}
                    required
                    value={values[field] ?? ''}
                    onChange={(e) => update(field, e.target.value)}
                  >
                    <option value="" disabled>
                      请选择意图
                    </option>
                    {schemas.AgentArtsInvocationEnvelope.$defs.AgentIntent.enum.map((value) => (
                      <option key={value} value={value}>
                        {intentLabels[value as keyof typeof intentLabels]}
                      </option>
                    ))}
                  </select>
                ) : field === 'PLAN' ? (
                  <select
                    id={id}
                    required
                    value={values[field] ?? ''}
                    onChange={(e) => update(field, e.target.value)}
                  >
                    <option value="" disabled>
                      请选择已有计划
                    </option>
                    {choices.map((ref, index) => (
                      <option key={JSON.stringify(ref)} value={String(index)}>
                        {ref.plan_id} · 版本 {ref.version}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    required={field !== 'STUDENT_PROFILE' || !values.STUDENT_PROFILE_JSON?.trim()}
                    value={values[field] ?? ''}
                    onChange={(e) => update(field, e.target.value)}
                  />
                )}
                {field === 'STUDENT_PROFILE' && (
                  <>
                    <label htmlFor={`${id}-education`}>学历（仅填写已确认信息）</label>
                    <select
                      id={`${id}-education`}
                      value={values.STUDENT_EDUCATION ?? ''}
                      onChange={(e) => update('STUDENT_EDUCATION', e.target.value)}
                    >
                      <option value="">暂不提供</option>
                      <option value="undergraduate">本科生</option>
                      <option value="graduate">研究生</option>
                    </select>
                    {advancedInput(field, '完整学生画像')}
                  </>
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
        只提交本次要求的字段。标识是否匹配、是否存在冲突，仍由 Runtime/Core
        验证。提交不表示信息已被确认或流程已完成。
      </p>
      <details className="clarification-audit">
        <summary>高级详情</summary>
        <pre>{JSON.stringify(proposal, null, 2)}</pre>
      </details>
    </section>
  );
}
