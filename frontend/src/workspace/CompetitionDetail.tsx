import { useEffect, useRef, useState } from 'react';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { CompetitionDetailProjection } from '../results/generated/artifacts.ts';
import type { InvocationClient } from './useConversation.ts';
import type { ReadRecord } from './competitionSession.ts';
import { detailFacts } from './competitionData.ts';
import { ErrorPresentation, errorDetails } from '../results/ErrorPresentation.tsx';
import type { ErrorDetails } from '../results/ErrorPresentation.tsx';
import { SourceGroups } from '../results/SourceGroups.tsx';
import { isControlledDemo } from '../results/SourceMetadata.tsx';
import { SkillGapResults } from '../results/SemanticResults.tsx';

export type DetailTarget = { editionId?: string; trackId?: string };
const tabs = ['赛事概览', '参赛资格', '技能要求', '时间节点', '赛道', '证据来源', '变化历史'];
const levelLabels: Record<string, string> = {
  unknown: '尚未明确',
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
  expert: '专家',
};

export function CompetitionDetail({
  id,
  active,
  records,
  client,
  context,
  disabled,
  onBusy,
  open,
  select,
}: {
  id: string;
  active: boolean;
  records: readonly ReadRecord[];
  client: InvocationClient;
  context: AgentContext;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  open: (id: string | null) => void;
  select: (id: string, message?: string, target?: DetailTarget) => void;
}) {
  const [target, setTarget] = useState<DetailTarget>({});
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorDetails | null>(null);
  const attempts = useRef(new Set<string>());
  const busy = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const query = {
    competition_id: id,
    ...(target.editionId ? { edition_id: target.editionId } : {}),
    ...(target.trackId ? { track_id: target.trackId } : {}),
  };
  const queryKey = JSON.stringify(query);
  const record = records.findLast((r) =>
    r.artifacts.some(
      (a) =>
        a.model === 'CompetitionDetailProjection' &&
        a.value.query.competition_id === id &&
        (a.value.query.edition_id ?? undefined) === target.editionId &&
        (a.value.query.track_id ?? undefined) === target.trackId,
    ),
  );
  const artifact = record?.artifacts.find((a) => a.model === 'CompetitionDetailProjection');
  const detail: CompetitionDetailProjection | undefined = artifact?.value;
  const facts = detailFacts(records, id, {
    ...context,
    competition_id: id,
    edition_id: target.editionId,
    track_id: target.trackId,
  });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
      onBusy(false);
    };
  }, []);
  async function read() {
    if (busy.current || disabled) return;
    busy.current = true;
    attempts.current.add(queryKey);
    setLoading(true);
    setError(null);
    onBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const result = await client.exchange(
        {
          request: {
            request_id: `detail-${crypto.randomUUID()}`,
            user_message: '查看赛事详情',
            intent: 'GET_COMPETITION_DETAILS',
            context: query,
          },
        },
        { signal: abort.signal },
      );
      if (mounted.current && result.response?.outcome !== 'COMPLETED')
        setError(
          result.response?.error ?? { code: 'DETAIL_READ_FAILED', message: '赛事详情读取未完成。' },
        );
    } catch (failure) {
      if (mounted.current) setError(errorDetails(failure));
    } finally {
      busy.current = false;
      if (mounted.current) {
        setLoading(false);
        onBusy(false);
      }
    }
  }
  useEffect(() => {
    if (active && !detail && !attempts.current.has(queryKey) && !disabled && !loading) void read();
  }, [active, queryKey, detail, disabled, loading]);
  function choose(next: DetailTarget) {
    setTarget(next);
    setError(null);
    select(id, undefined, next);
  }
  const policy = detail?.eligibility_policy;
  const requirements = detail?.skill_requirements;
  const sources = detail
    ? [
        ...detail.provenance.map((p) => p.source),
        ...(policy ? [policy.source, ...(policy.constraints ?? []).map((c) => c.source)] : []),
        ...(requirements?.requirement_set.requirements?.flatMap((r) =>
          [...r.presence_evidence, ...(r.evidence ?? [])].flatMap((e) =>
            e.source ? [e.source] : [],
          ),
        ) ?? []),
      ]
    : [];
  return (
    <div className="competition-center competition-detail">
      <button type="button" onClick={() => open(null)}>
        返回赛事中心
      </button>
      {loading && <p role="status">正在加载赛事信息...</p>}
      {error && (
        <div role="alert">
          <h2>暂时无法加载赛事信息</h2>
          <ErrorPresentation error={error} />
        </div>
      )}
      {!detail && !loading && !error && <p>暂无已验证的赛事详情，可重新读取正式记录。</p>}
      <button type="button" disabled={disabled || loading} onClick={() => void read()}>
        重新读取详情
      </button>
      {detail && (
        <>
          <header className="page-intro">
            <h1>{detail.competition.name}</h1>
            <p>
              {detail.selected_edition?.name ?? '尚未选择届次'}
              {detail.selected_track && ` · ${detail.selected_track.name}`}
            </p>
            <p>来源核验状态和观察时间见证据来源；时间信息不作推断。</p>
            {detail.provenance
              .filter((p) => p.section === 'competition')
              .slice(0, 1)
              .map((p) => (
                <p key={p.source.source_url}>
                  赛事来源：{p.source.verification_status === 'verified' ? '已核验' : '尚未核验'} ·
                  来源观察时间：{p.source.observed_at}
                </p>
              ))}
          </header>
          <div className="competition-search">
            <label>
              届次
              <select
                value={target.editionId ?? ''}
                disabled={disabled || loading}
                onChange={(e) => choose(e.target.value ? { editionId: e.target.value } : {})}
              >
                <option value="">请选择届次</option>
                {detail.editions.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            {detail.selected_edition && (
              <label>
                赛道
                <select
                  value={target.trackId ?? ''}
                  disabled={disabled || loading}
                  onChange={(e) =>
                    choose({
                      editionId: target.editionId,
                      ...(e.target.value ? { trackId: e.target.value } : {}),
                    })
                  }
                >
                  <option value="">不指定赛道</option>
                  {(detail.tracks ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="competition-action-bar">
            <button
              type="button"
              disabled={disabled || loading}
              onClick={() => select(id, undefined, target)}
            >
              设为当前赛事
            </button>
            {['判断参赛资格', '分析技能差距', '生成备赛计划'].map((message) => (
              <button
                key={message}
                type="button"
                disabled={disabled || loading}
                onClick={() => select(id, message, target)}
              >
                {message}
              </button>
            ))}
          </div>
          <p className="panel-note">
            分析操作进入 Copilot，由用户明确提交；详情读取不执行资格或技能差距分析。
          </p>
          <div className="competition-tabs" role="tablist" aria-label="赛事详情">
            {tabs.map((label, index) => (
              <button
                key={label}
                id={`detail-tab-${index}`}
                type="button"
                role="tab"
                aria-selected={tab === index}
                aria-controls="detail-panel"
                tabIndex={tab === index ? 0 : -1}
                onClick={() => setTab(index)}
                onKeyDown={(e) => {
                  const next =
                    e.key === 'ArrowRight'
                      ? (index + 1) % tabs.length
                      : e.key === 'ArrowLeft'
                        ? (index + tabs.length - 1) % tabs.length
                        : e.key === 'Home'
                          ? 0
                          : e.key === 'End'
                            ? tabs.length - 1
                            : null;
                  if (next !== null) {
                    e.preventDefault();
                    setTab(next);
                    (
                      e.currentTarget.parentElement?.querySelectorAll('button')[
                        next
                      ] as HTMLButtonElement
                    )?.focus();
                  }
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <section
            className="dashboard-card competition-tabpanel"
            id="detail-panel"
            role="tabpanel"
            aria-labelledby={`detail-tab-${tab}`}
            tabIndex={0}
          >
            {tab === 0 && (
              <>
                <h2>赛事概览</h2>
                <p>{detail.competition.description ?? '暂无已核验的赛事说明信息'}</p>
                <p>届次：{detail.selected_edition?.name ?? '尚未选择'}</p>
                <p>赛道：{detail.selected_track?.name ?? '尚未指定'}</p>
                <p>
                  {detail.selected_edition
                    ? `已返回 ${(detail.tracks ?? []).length} 条赛道记录，不代表现实中确认无其他赛道。`
                    : '选择届次后读取赛道与时间信息。'}
                </p>
                <p>主办信息及赛事状态：当前正式字段暂未提供。</p>
              </>
            )}
            {tab === 1 && (
              <>
                <h2>官方资格规则事实</h2>
                <p>以下仅表示当前已审核政策覆盖范围，不宣称覆盖赛事所有资格规则。</p>
                {policy ? (
                  <>
                    <p>
                      覆盖状态：
                      {policy.coverage === 'partial' ? '部分已审核' : '当前政策声明完整覆盖'}
                    </p>
                    <p>{policy.coverage_note}</p>
                    {(policy.constraints ?? []).map((c) => (
                      <article key={c.rule_id}>
                        <p>{c.evidence_text}</p>
                        <p>
                          规则适用教育层级：
                          {c.allowed_levels
                            .map(
                              (level) =>
                                ({ undergraduate: '本科生', graduate: '研究生', unknown: '未知' })[
                                  level
                                ] ?? level,
                            )
                            .join('、')}
                        </p>
                      </article>
                    ))}
                  </>
                ) : (
                  <p>当前暂无可读取的已审核资格规则。</p>
                )}
                <h2>当前用户资格</h2>
                {facts.eligibility ? (
                  <p>
                    {
                      { eligible: '资格已确认', ineligible: '当前资格受限', unknown: '尚无法确认' }[
                        facts.eligibility.status
                      ]
                    }
                  </p>
                ) : (
                  <p>尚未分析你的参赛资格。</p>
                )}
              </>
            )}
            {tab === 2 && (
              <>
                <h2>技能要求</h2>
                {requirements ? (
                  <>
                    <p>需求版本：{requirements.requirement_version}</p>
                    <p>
                      覆盖状态：
                      {
                        {
                          partial: '部分已核验',
                          complete: '完整覆盖声明',
                          missing: '暂无技能要求数据',
                        }[requirements.requirement_set.coverage]
                      }
                    </p>
                    <p>{requirements.requirement_set.coverage_note}</p>
                    {(requirements.requirement_set.requirements ?? []).map((r) => (
                      <article key={r.skill_id}>
                        <h3>
                          {requirements.skills.find((s) => s.id === r.skill_id)?.name ?? r.skill_id}
                        </h3>
                        <p>
                          {r.requirement_type === 'required'
                            ? '已确认需要该技能'
                            : '已返回期望技能要求'}
                        </p>
                        <p>
                          {r.required_level === null
                            ? '所需能力等级暂未明确'
                            : `所需能力等级：${levelLabels[r.required_level] ?? r.required_level}`}
                        </p>
                        <details>
                          <summary>查看赛事要求依据</summary>
                          {r.presence_evidence.map((e, i) => (
                            <p key={i}>{e.message}</p>
                          ))}
                          <SourceGroups
                            sources={[...r.presence_evidence, ...(r.evidence ?? [])].flatMap((e) =>
                              e.source ? [e.source] : [],
                            )}
                          />
                        </details>
                      </article>
                    ))}
                  </>
                ) : (
                  <p>当前暂无与所选届次和赛道精确匹配的已审核技能要求数据。</p>
                )}
                <h2>个人技能差距</h2>
                {facts.skillGap ? (
                  <SkillGapResults result={facts.skillGap} />
                ) : (
                  <p>尚未进行个人技能差距分析。</p>
                )}
              </>
            )}
            {tab === 3 && (
              <>
                <h2>时间节点</h2>
                {(['registration_window', 'competition_window'] as const).map((field) => {
                  const window = detail.selected_edition?.[field];
                  return (
                    <article key={field}>
                      <h3>{field === 'registration_window' ? '报名时间' : '比赛时间'}</h3>
                      <p>开始：{window?.start_at ?? '时间暂未确认'}</p>
                      <p>结束：{window?.end_at ?? '时间暂未确认'}</p>
                    </article>
                  );
                })}
                <p>提交时间：暂未提供</p>
                <p>观察时间不是截止日期，系统不会自动推断日期。</p>
              </>
            )}
            {tab === 4 && (
              <>
                <h2>赛道</h2>
                {(detail.tracks ?? []).length ? (
                  (detail.tracks ?? []).map((t) => (
                    <article key={t.id}>
                      <h3>{t.name}</h3>
                      <p>{t.description ?? '暂无已审核的赛道说明'}</p>
                      {t.source && <SourceGroups sources={[t.source]} />}
                      <button
                        type="button"
                        disabled={disabled || loading}
                        onClick={() => choose({ editionId: target.editionId, trackId: t.id })}
                      >
                        选择此赛道：{t.name}
                      </button>
                    </article>
                  ))
                ) : (
                  <p>暂无可展示的赛道记录，不代表赛事确认没有赛道。</p>
                )}
              </>
            )}
            {tab === 5 && (
              <>
                <h2>证据来源</h2>
                {sources.length ? (
                  <SourceGroups sources={sources} />
                ) : (
                  <p>暂无来源元数据，不从官方网站链接推断核验状态。</p>
                )}
              </>
            )}
            {tab === 6 && (
              <>
                <h2>完整赛事变化历史</h2>
                <p>暂未提供完整赛事变化历史</p>
                <p>系统当前没有持久化赛事事件历史记录。</p>
                <h2>当前会话中的赛事变化证据</h2>
                {facts.events.length ? (
                  facts.events.map((event) => (
                    <article key={event.id}>
                      <h3>
                        {event.event_type === 'track_membership_changed'
                          ? '赛道成员发生变化'
                          : '已记录赛事变化'}
                      </h3>
                      {isControlledDemo(event.source.source_url) && (
                        <p>模拟赛事变化 / 演示数据，不代表官方真实发生变化。</p>
                      )}
                      <p>{event.description}</p>
                      <p>观察时间：{event.observed_at}</p>
                      <SourceGroups sources={[event.source]} />
                    </article>
                  ))
                ) : (
                  <p>当前会话暂无与所选目标精确匹配的赛事变化证据。</p>
                )}
              </>
            )}
          </section>
          <details className="competition-audit">
            <summary>查看高级审计信息</summary>
            <pre>
              {JSON.stringify(
                {
                  projection: detail,
                  result: record?.response,
                  artifacts: record?.artifacts,
                  session_evidence: facts.audit,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </div>
  );
}
