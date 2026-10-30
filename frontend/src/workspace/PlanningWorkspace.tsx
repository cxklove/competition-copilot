import { AddMyCompetitionButton } from './MyCompetitions.tsx';
import { useEffect, useRef, useState } from 'react';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { PlanningWorkspaceProjection } from '../results/generated/artifacts.ts';
import { parseOriginalPlan, validateArtifacts } from '../results/artifacts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import { SourceMetadata } from '../results/SourceMetadata.tsx';
import { PlanTimeline, planStatus } from '../results/SemanticResults.tsx';
import type { InvocationClient } from './useConversation.ts';
import { guidedActions } from './actions.ts';
import type { GuidedAction } from './actions.ts';
import { planChoiceKey } from './plans.ts';

const freshness = {
  CURRENT: '基于当前画像',
  STALE: '基于较早画像',
  UNKNOWN: '画像版本未记录，无法确认',
};
const scopeName = { competition: '赛事级依据', edition: '届次级依据', track: '赛道级依据' };
const levels: Record<string, string> = {
  unknown: '尚未明确',
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
};

export function PlanningWorkspaceView({
  value,
  act,
  detail,
  profile,
}: {
  value: PlanningWorkspaceProjection;
  act: (action: GuidedAction) => void;
  detail: () => void;
  profile: () => void;
}) {
  const constraints = value.confirmed_constraints;
  const tasks = value.preparation_suggestions;
  const pending = value.pending_confirmations;
  const times = value.time_references;
  const original = value.plan_original_json ? parseOriginalPlan(value.plan_original_json) : null;
  const verified = new Set(times.filter((t) => t.kind === 'VERIFIED').map((t) => t.field));
  const visibleTimes = times.filter(
    (t) =>
      t.kind === 'VERIFIED' ||
      (!verified.has(t.field) &&
        (t.field.includes('_') || ![...verified].some((f) => f.startsWith(t.field + '_')))),
  );
  return (
    <div className="planning-workspace">
      <section className="profile-section" aria-label="备赛概览">
        <h2>备赛概览</h2>
        <p>
          {value.competition_name}
          {value.edition_name ? ` / ${value.edition_name}` : ''}
          {value.track_name ? ` / ${value.track_name}` : ''}
        </p>
        <AddMyCompetitionButton target={value.target} />
        {value.plan_summary ? (
          <>
            <p>
              计划状态：{planStatus(value.plan_summary.status)} · 版本 {value.plan_summary.version}
            </p>
            <p
              className={`profile-freshness freshness-${value.plan_freshness.status.toLowerCase()}`}
            >
              {freshness[value.plan_freshness.status]}
            </p>
          </>
        ) : (
          <p>尚未生成或选择正式备赛计划</p>
        )}
        <p>
          当前画像每周可投入：
          {value.profile_context.weekly_available_hours == null
            ? '尚未填写'
            : `${value.profile_context.weekly_available_hours} 小时 / 周`}
        </p>
        {value.profile_context.weekly_available_hours === 0 && (
          <p>当前每周可投入时间为 0 小时，可先在个人画像中调整时间投入。</p>
        )}
        {!!value.profile_context.goals.length && (
          <p>个人目标：{value.profile_context.goals.join('、')}</p>
        )}
        {!!value.profile_context.interests.length && (
          <p>兴趣：{value.profile_context.interests.join('、')}</p>
        )}
        <p>
          已确认约束：{constraints.length} 项 · 推荐准备：{tasks.length} 项 · 待确认：
          {pending.length} 项
        </p>
        <p>以下是当前读取的赛事资料，不代表计划生成时的历史资料。</p>
      </section>
      <section className="profile-section" aria-label="已确认约束">
        <h2>已确认约束</h2>
        {!constraints.length && <p>当前范围暂无可展示的已核验约束。</p>}
        {constraints.map((c) => (
          <article className="analysis-summary" key={c.constraint_id}>
            <h3>{c.label}</h3>
            <p>{c.type === 'skill_level' ? (levels[c.value] ?? c.value) : c.value}</p>
            <p>{scopeName[c.scope]} · 已核验</p>
            <SourceMetadata source={c.source} />
          </article>
        ))}
      </section>
      <section className="profile-section" aria-label="推荐准备任务">
        <h2>推荐准备任务</h2>
        <p>基于本次读取的当前画像。这些建议独立于正式计划，不属于旧 Plan 正文。</p>
        {!tasks.length && <p>暂无当前精确范围的准备建议；不会根据赛事名称猜测技能要求。</p>}
        {tasks.map((task) => (
          <article className="analysis-summary" key={task.task_id}>
            <span className="semantic-chip">建议</span>
            <h3>{task.title}</h3>
            <p>{task.description}</p>
            <p>
              建议依据：赛事已核验涉及{' '}
              {constraints.find(
                (c) => c.type === 'skill_identity' && c.field === task.source_basis.skill_id,
              )?.value ?? task.source_basis.skill_id}
              ；
              {task.source_basis.profile_skill_state === 'recorded'
                ? '当前画像已记录该技能'
                : task.source_basis.profile_skill_state === 'missing'
                  ? '画像尚未记录该技能，不代表没有能力'
                  : '已记录该技能，等级尚未评定'}
              。
            </p>
          </article>
        ))}
      </section>
      <section className="profile-section" aria-label="待确认事项">
        <h2>待确认事项</h2>
        {!pending.length && <p>当前读取范围没有列出的待确认事项，不代表覆盖全部官方要求。</p>}
        <ul>
          {pending.map((p) => (
            <li key={p.confirmation_id}>
              {p.title} · {scopeName[p.scope]}
            </li>
          ))}
        </ul>
      </section>
      <section className="profile-section" aria-label="时间参考">
        <h2>时间参考</h2>
        {!visibleTimes.length && <p>当前资料中暂未发现可靠时间信息。</p>}
        {visibleTimes.map((t, i) => (
          <article className="analysis-summary" key={i}>
            <h3>{t.kind === 'VERIFIED' ? '正式时间 · 已核验' : '官方已公布 · 待核验'}</h3>
            <p>{scopeName[t.scope]}</p>
            {t.kind === 'VERIFIED' ? (
              <p>
                {
                  (
                    {
                      registration_start: '报名开始',
                      registration_end: '报名结束',
                      competition_start: '比赛开始',
                      competition_end: '比赛结束',
                    } as Record<string, string>
                  )[t.field]
                }
                ：<time dateTime={t.value ?? ''}>{t.value}</time>
              </p>
            ) : (
              <>
                <p>官方原文：{t.raw_text}</p>
                <p>
                  信息粒度：
                  {(
                    {
                      DATE: '日期',
                      DATETIME: '日期和时间',
                      MONTH: '月份',
                      TEXT_ONLY: '原文',
                    } as Record<string, string>
                  )[t.precision] ?? t.precision}
                </p>
                <p>时间原文尚未形成可用于计划和自动决策的结构化时间事实。</p>
              </>
            )}
            <SourceMetadata source={t.source} />
          </article>
        ))}
      </section>
      <section className="profile-section" aria-label="计划原文与审计">
        <h2>计划原文 / 审计</h2>
        {value.plan_original_json ? (
          <details>
            <summary>查看完整正式计划与依赖</summary>
            {original && <PlanTimeline plan={original} />}
            <pre>{value.plan_original_json}</pre>
          </details>
        ) : (
          <p>尚未选择正式计划。</p>
        )}
        <details>
          <summary>查看读取与建议依据审计</summary>
          <pre>{JSON.stringify(value, null, 2)}</pre>
        </details>
      </section>
      <section className="profile-section" aria-label="备赛操作">
        <h2>下一步</h2>
        <button disabled={!value.target.edition_id} onClick={() => act(guidedActions[3])}>
          {value.plan_ref ? '重新生成计划' : '生成备赛计划'}
        </button>
        <button disabled={!value.target.edition_id} onClick={() => act(guidedActions[2])}>
          重新分析技能差距
        </button>
        <button onClick={detail}>查看赛事详情</button>
        <button onClick={profile}>完善个人画像</button>
      </section>
    </div>
  );
}

export function PlanningWorkspace({
  active,
  context,
  client,
  readArtifacts,
  disabled,
  profileToken,
  act,
  detail,
  profile,
  center,
}: {
  active: boolean;
  context: AgentContext;
  client: InvocationClient;
  readArtifacts?: ArtifactReader;
  disabled: boolean;
  profileToken: string;
  act: (a: GuidedAction) => void;
  detail: () => void;
  profile: () => void;
  center: () => void;
}) {
  const key = JSON.stringify([context, profileToken]);
  const latest = useRef({ client, context, readArtifacts });
  latest.current = { client, context, readArtifacts };
  const [reload, setReload] = useState(0);
  const [state, setState] = useState<{
    key: string;
    value?: PlanningWorkspaceProjection;
    error?: string;
  }>({ key: '' });
  useEffect(() => {
    if (
      !active ||
      disabled ||
      !latest.current.context.student_id ||
      !latest.current.context.competition_id
    )
      return;
    const selected = latest.current;
    let alive = true;
    const controller = new AbortController();
    setState({ key });
    void (async () => {
      try {
        const result = await selected.client.exchange(
          {
            request: {
              request_id: `planning-workspace-${crypto.randomUUID()}`,
              user_message: '查看备赛工作区',
              intent: 'GET_PLANNING_WORKSPACE',
              context: selected.context,
            },
          },
          { signal: controller.signal },
        );
        if (result.response?.outcome !== 'COMPLETED') {
          const identity = `${result.response?.error?.code ?? ''} ${result.response?.error?.message ?? ''}`;
          throw new Error(
            identity.includes('PLAN_REFERENCE_UNAVAILABLE')
              ? 'PLAN_REFERENCE_UNAVAILABLE'
              : 'READ_UNAVAILABLE',
          );
        }
        const value = validateArtifacts(
          result.response,
          selected.readArtifacts?.(result.response),
        ).find((a) => a.model === 'PlanningWorkspaceProjection');
        if (
          value?.model !== 'PlanningWorkspaceProjection' ||
          value.value.student_id !== selected.context.student_id ||
          value.value.target.competition_id !== selected.context.competition_id ||
          (value.value.target.edition_id ?? null) !== (selected.context.edition_id ?? null) ||
          (value.value.target.track_id ?? null) !== (selected.context.track_id ?? null) ||
          !!value.value.plan_ref !== !!selected.context.plan_ref ||
          (value.value.plan_ref &&
            selected.context.plan_ref &&
            planChoiceKey(value.value.plan_ref) !== planChoiceKey(selected.context.plan_ref))
        )
          throw new Error('IDENTITY_MISMATCH');
        if (alive) setState({ key, value: value.value });
      } catch (failure) {
        if (alive)
          setState({ key, error: failure instanceof Error ? failure.message : 'READ_UNAVAILABLE' });
      }
    })();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [key, active, disabled, reload]);
  if (!active) return null;
  return (
    <section>
      <h1>备赛计划</h1>
      {!context.competition_id ? (
        <>
          <p>尚未选择当前赛事</p>
          <button onClick={center}>前往赛事中心</button>
        </>
      ) : !context.student_id ? (
        <>
          <p>尚未选择当前学生</p>
          <button onClick={profile}>完善个人画像</button>
        </>
      ) : (
        <>
          {!context.edition_id && <p>尚未选择届次，请在赛事详情中明确选择。</p>}
          <button disabled={disabled} onClick={() => setReload((v) => v + 1)}>
            刷新备赛资料
          </button>
          {state.key !== key || (!state.value && !state.error) ? (
            <p role="status">正在读取备赛资料…</p>
          ) : state.error ? (
            <p role="alert">
              {state.error === 'PLAN_REFERENCE_UNAVAILABLE'
                ? '所选计划引用不可读取，请重新选择计划。'
                : '备赛资料读取失败，请检查所选学生、赛事范围和计划引用后重新读取。'}
            </p>
          ) : (
            state.value && (
              <PlanningWorkspaceView
                value={state.value}
                act={act}
                detail={detail}
                profile={profile}
              />
            )
          )}
        </>
      )}
    </section>
  );
}
