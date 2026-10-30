import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { AgentContext, MyCompetitionCommand } from '../runtime/generated/contracts.ts';
import type {
  MyCompetitionProjection,
  MyCompetitionTarget,
} from '../results/generated/artifacts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import type { InvocationClient } from './useConversation.ts';

const stateLabels = { SAVED: '已关注', PREPARING: '准备中' };
const freshness = {
  CURRENT: '基于当前画像',
  STALE: '基于较早画像',
  UNKNOWN: '画像版本未记录，无法确认',
};
export const targetKey = (target: MyCompetitionTarget) =>
  JSON.stringify([target.competition_id, target.edition_id, target.track_id ?? null]);

export function myCompetitionError(message: string): string {
  if (message.includes('REPOSITORY_UNAVAILABLE')) return '赛事关系存储暂不可用，请稍后重试。';
  if (message.includes('VERSION_CONFLICT')) return '赛事关系已发生变化，请重新加载后再操作。';
  if (message.includes('ALREADY_EXISTS')) return '该届次和赛道已加入我的赛事，请重新加载。';
  if (message.includes('FORBIDDEN')) return '当前操作者无权访问该学生的赛事集合。';
  if (message.includes('INVALID_TARGET')) return '赛事范围不可用，请重新选择届次和赛道。';
  if (message.includes('NOT_FOUND')) return '该赛事关系已不存在，请重新加载。';
  if (message.includes('INVALID_REFERENCE')) return '引用已不可用，请重新加载后再操作。';
  return '暂时无法读取或保存我的赛事，请检查 Runtime 连接后重试。';
}

type MyCompetitionsState = {
  student?: string | null;
  items: MyCompetitionProjection[];
  loading: boolean;
  busy: boolean;
  error: string;
  refresh: () => void;
  mutate: (command: MyCompetitionCommand) => Promise<void>;
  editions: (competitionId: string) => Promise<{ id: string; name: string }[]>;
};
const MyCompetitionsContext = createContext<MyCompetitionsState | null>(null);

export function MyCompetitionsProvider({
  children,
  context,
  client,
  readArtifacts,
  disabled,
  token,
  active = true,
}: {
  children: ReactNode;
  context: AgentContext;
  client: InvocationClient;
  readArtifacts?: ArtifactReader;
  disabled: boolean;
  token: string;
  active?: boolean;
}) {
  const student = context.student_id;
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ student: string; items: MyCompetitionProjection[] }>();
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const latest = useRef({ client, readArtifacts, student });
  latest.current = { client, readArtifacts, student };
  const refresh = () => setRevision((r) => r + 1);
  useEffect(() => {
    if (!active || !student || disabled) return;
    const selected = latest.current;
    const controller = new AbortController();
    let alive = true;
    setLoading(true);
    setError('');
    void (async () => {
      try {
        const result = await selected.client.exchange(
          {
            request: {
              request_id: `my-competitions-${crypto.randomUUID()}`,
              intent: 'GET_MY_COMPETITIONS',
              user_message: '查看我的赛事',
              context: { student_id: student },
            },
          },
          { signal: controller.signal },
        );
        if (result.response?.outcome !== 'COMPLETED') throw new Error(JSON.stringify(result));
        const artifact = validateArtifacts(
          result.response,
          selected.readArtifacts?.(result.response),
        ).find((a) => a.model === 'MyCompetitionsProjection');
        if (
          artifact?.model !== 'MyCompetitionsProjection' ||
          artifact.value.student_id !== student ||
          artifact.value.competitions.some((item) => item.student_id !== student)
        )
          throw new Error('RESULT_IDENTITY_MISMATCH');
        if (alive) setData({ student, items: artifact.value.competitions });
      } catch (error) {
        if (alive) setError(myCompetitionError(String(error)));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [student, disabled, token, revision, active]);
  async function mutate(command: MyCompetitionCommand) {
    if (!student || disabled || inFlight.current || command.student_id !== student) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const intent = {
        add: 'ADD_MY_COMPETITION',
        update: 'UPDATE_MY_COMPETITION',
        remove: 'REMOVE_MY_COMPETITION',
      } as const;
      const result = await client.exchange({
        request: {
          request_id: `my-competition-${crypto.randomUUID()}`,
          intent: intent[command.operation],
          user_message: '管理我的赛事',
          context: { student_id: student },
          my_competition_command: command,
        },
      });
      if (result.response?.outcome !== 'COMPLETED') throw new Error(JSON.stringify(result));
      const mutation = validateArtifacts(result.response, readArtifacts?.(result.response)).find(
        (a) => a.model === 'MyCompetitionMutationResult',
      );
      if (
        mutation?.model !== 'MyCompetitionMutationResult' ||
        mutation.value.snapshot.relationship.student_id !== student ||
        targetKey(mutation.value.snapshot.relationship_ref.target) !== targetKey(command.target)
      )
        throw new Error('RESULT_IDENTITY_MISMATCH');
      refresh();
    } catch (error) {
      setError(myCompetitionError(String(error)));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  async function editions(competitionId: string) {
    const result = await client.exchange({
      request: {
        request_id: `edition-choices-${crypto.randomUUID()}`,
        intent: 'GET_COMPETITION_DETAILS',
        user_message: '读取可选择届次',
        context: { student_id: student, competition_id: competitionId },
      },
    });
    if (result.response?.outcome !== 'COMPLETED') throw new Error('EDITION_CHOICES_UNAVAILABLE');
    const artifact = validateArtifacts(result.response, readArtifacts?.(result.response)).find(
      (a) => a.model === 'CompetitionDetailProjection',
    );
    if (
      artifact?.model !== 'CompetitionDetailProjection' ||
      artifact.value.competition.id !== competitionId
    )
      throw new Error('EDITION_CHOICES_UNAVAILABLE');
    return artifact.value.editions.map((edition) => ({ id: edition.id, name: edition.name }));
  }
  return (
    <MyCompetitionsContext.Provider
      value={{
        student,
        items: data && data.student === student ? data.items : [],
        loading,
        busy: busy || disabled,
        error,
        refresh,
        mutate,
        editions,
      }}
    >
      {children}
    </MyCompetitionsContext.Provider>
  );
}

export function AddMyCompetitionButton({
  target,
}: {
  target: { competition_id: string; edition_id?: string | null; track_id?: string | null };
}) {
  const state = useContext(MyCompetitionsContext);
  const [hint, setHint] = useState('');
  const [editions, setEditions] = useState<{ id: string; name: string }[] | null>(null);
  const [edition, setEdition] = useState('');
  useEffect(() => {
    setEditions(null);
    setEdition('');
    setHint('');
  }, [target.competition_id, target.edition_id]);
  if (!state) return null;
  const exact = target.edition_id
    ? {
        competition_id: target.competition_id,
        edition_id: target.edition_id,
        track_id: target.track_id ?? null,
      }
    : null;
  const selected =
    exact ??
    (edition
      ? { competition_id: target.competition_id, edition_id: edition, track_id: null }
      : null);
  const existing =
    selected && state.items.find((item) => targetKey(item.target) === targetKey(selected));
  return (
    <span className="my-competition-add">
      <button
        type="button"
        disabled={!state.student || state.busy || state.loading || !!existing}
        onClick={() => {
          if (!exact) {
            setHint('请先选择届次，再加入我的赛事。');
            void state
              .editions(target.competition_id)
              .then(setEditions)
              .catch(() => setHint('届次读取不可用，请到赛事详情重新读取。'));
            return;
          }
          void state.mutate({
            operation: 'add',
            student_id: state.student!,
            target: exact,
            state: 'SAVED',
          });
        }}
      >
        {existing ? stateLabels[existing.relationship_state] : '加入我的赛事'}
      </button>
      {hint && <span role="status">{hint}</span>}
      {!exact && editions && (
        <span>
          <label>
            请选择届次
            <select value={edition} onChange={(e) => setEdition(e.target.value)}>
              <option value="">请选择届次</option>
              {editions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!edition || state.busy || state.loading || !!existing}
            onClick={() =>
              void state.mutate({
                operation: 'add',
                student_id: state.student!,
                target: {
                  competition_id: target.competition_id,
                  edition_id: edition,
                  track_id: null,
                },
                state: 'SAVED',
              })
            }
          >
            确认加入
          </button>
        </span>
      )}
      {state.error && <span role="status">{state.error}</span>}
    </span>
  );
}

export function MyCompetitionsPage({
  active,
  setCurrent,
  detail,
  act,
  browse,
  recommend,
  workspace,
}: {
  active: boolean;
  setCurrent: (item: MyCompetitionProjection) => void;
  detail: (item: MyCompetitionProjection) => void;
  act: (item: MyCompetitionProjection) => void;
  browse: () => void;
  recommend: () => void;
  workspace?: (item: MyCompetitionProjection) => void;
}) {
  const state = useContext(MyCompetitionsContext);
  const [filter, setFilter] = useState<'ALL' | 'SAVED' | 'PREPARING'>('ALL');
  const [confirm, setConfirm] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<string | null>(null);
  if (!active || !state) return null;
  const items = state.items.filter(
    (item) => filter === 'ALL' || item.relationship_state === filter,
  );
  return (
    <section aria-label="我的赛事工作区">
      <h1>我的赛事</h1>
      <p>当前本地演示关系仅保存在运行中的服务内，服务重启后不会保留。</p>
      {!state.student ? (
        <p>尚未选择当前学生</p>
      ) : (
        <>
          <div role="group" aria-label="赛事关系筛选">
            {(['ALL', 'PREPARING', 'SAVED'] as const).map((value) => (
              <button
                type="button"
                key={value}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
              >
                {value === 'ALL' ? '全部' : stateLabels[value]}
              </button>
            ))}
          </div>
          <button type="button" disabled={state.loading || state.busy} onClick={state.refresh}>
            重新加载我的赛事
          </button>
          {state.error && <p role="alert">{state.error}</p>}
          {state.loading && <p role="status">正在读取我的赛事…</p>}
          {!state.loading && !state.error && !state.items.length && (
            <div>
              <p>还没有加入任何赛事</p>
              <button type="button" onClick={browse}>
                浏览赛事
              </button>
              <button type="button" onClick={recommend}>
                查看赛事推荐
              </button>
            </div>
          )}
          {items.map((item) => (
            <article className="analysis-summary" key={item.relationship_ref.relationship_id}>
              <h2>{item.display_identity.competition_name ?? '赛事资料不可用'}</h2>
              <p>
                {item.display_identity.edition_name ?? '届次资料不可用'}
                {item.display_identity.track_name && ` / ${item.display_identity.track_name}`}
              </p>
              <p>状态：{stateLabels[item.relationship_state]}</p>
              {(
                [
                  ['资格', item.eligibility_summary],
                  ['技能差距', item.skill_gap_summary],
                  ['计划', item.plan_summary],
                ] as const
              ).map(([label, summary]) => (
                <div key={label}>
                  <p>
                    {label}：{summary.label}
                  </p>
                  {summary.availability === 'AVAILABLE' && (
                    <p
                      className={`profile-freshness freshness-${summary.profile_freshness.status.toLowerCase()}`}
                    >
                      {freshness[summary.profile_freshness.status]}
                    </p>
                  )}
                </div>
              ))}
              {item.planning_summary.availability === 'AVAILABLE' && (
                <p>
                  已确认约束：{item.planning_summary.confirmed_constraints_count} 项 · 待确认：
                  {item.planning_summary.pending_confirmations_count} 项 · 准备建议：
                  {item.planning_summary.has_advisory ? '有' : '暂无'}
                </p>
              )}
              <p>
                时间：
                {
                  {
                    VERIFIED: '有已核验正式时间',
                    OFFICIAL_CANDIDATE: '官方已公布 · 待核验',
                    UNKNOWN: '正式时间尚未确认',
                    PROVIDER_UNAVAILABLE: '时间资料暂不可用',
                  }[item.time_summary.availability]
                }
              </p>
              {(item.time_summary.references ?? []).map((time, index) => (
                <p key={`${time.field}-${index}`}>
                  {time.kind === 'VERIFIED'
                    ? '正式时间 · 已核验'
                    : '时间参考 · 官方已公布 · 待核验'}
                  ：{time.value ?? time.raw_text}
                </p>
              ))}
              <button
                type="button"
                disabled={state.busy}
                onClick={() =>
                  item.next_action.kind === 'EVIDENCE'
                    ? setEvidence(item.relationship_ref.relationship_id)
                    : act(item)
                }
              >
                {item.next_action.label}
              </button>
              <button type="button" disabled={state.busy} onClick={() => setCurrent(item)}>
                设为当前赛事
              </button>
              {workspace && item.planning_summary.availability === 'AVAILABLE' && (
                <button type="button" disabled={state.busy} onClick={() => workspace(item)}>
                  查看备赛工作区
                </button>
              )}
              <button type="button" onClick={() => detail(item)}>
                查看详情
              </button>
              <button
                type="button"
                disabled={state.busy}
                onClick={() =>
                  void state.mutate({
                    operation: 'update',
                    student_id: item.student_id,
                    target: item.target,
                    state: item.relationship_state === 'SAVED' ? 'PREPARING' : 'SAVED',
                    expected_reference: item.relationship_ref,
                  })
                }
              >
                {item.relationship_state === 'SAVED' ? '开始准备' : '改为已关注'}
              </button>
              <button
                type="button"
                disabled={state.busy}
                onClick={() => setConfirm(item.relationship_ref.relationship_id)}
              >
                移出我的赛事
              </button>
              {confirm === item.relationship_ref.relationship_id && (
                <div role="group" aria-label="移出确认">
                  <p>移出只删除赛事关系，已有分析和计划继续保留。</p>
                  <button
                    type="button"
                    disabled={state.busy}
                    onClick={() => {
                      setConfirm(null);
                      void state.mutate({
                        operation: 'remove',
                        student_id: item.student_id,
                        target: item.target,
                        expected_reference: item.relationship_ref,
                      });
                    }}
                  >
                    确认移出
                  </button>
                  <button type="button" onClick={() => setConfirm(null)}>
                    取消
                  </button>
                </div>
              )}
              <details open={evidence === item.relationship_ref.relationship_id || undefined}>
                <summary>高级审计 / 分析依据</summary>
                <pre>{JSON.stringify(item, null, 2)}</pre>
              </details>
            </article>
          ))}
        </>
      )}
    </section>
  );
}
