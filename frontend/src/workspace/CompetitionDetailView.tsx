import type { Dispatch, SetStateAction } from 'react';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { CompetitionDetailProjection } from '../results/generated/artifacts.ts';
import { ErrorPresentation } from '../results/ErrorPresentation.tsx';
import type { ErrorDetails } from '../results/ErrorPresentation.tsx';
import { SkillGapResults } from '../results/SemanticResults.tsx';
import { isControlledDemo } from '../results/SourceMetadata.tsx';
import { SourceGroups } from '../results/SourceGroups.tsx';
import type { ReadRecord } from './competitionSession.ts';
import type { detailFacts } from './competitionData.ts';
import type { DetailTarget } from './CompetitionDetail.tsx';
import { guidedActions } from './actions.ts';
import type { GuidedAction } from './actions.ts';
import {
  cachedDetail,
  CompetitionEvidenceCenter,
  CompetitionTimeline,
  DataAvailabilitySummary,
  SourceStatus,
  verificationLabel,
  windowSummary,
} from './competitionPresentation.tsx';

const tabs = ['赛事概览', '参赛资格', '技能要求', '时间节点', '赛道', '证据来源', '变化历史'];
const levels: Record<string, string> = {
  unknown: '尚未明确',
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
  expert: '专家',
};
const actions = guidedActions.filter((a) =>
  ['CHECK_ELIGIBILITY', 'ANALYZE_SKILL_GAP', 'BUILD_PLAN'].includes(a.intent),
);

export function CompetitionDetailView({
  detail,
  facts,
  context,
  records,
  record,
  target,
  tab,
  setTab,
  choose,
  loading,
  disabled,
  error,
  read,
  open,
  select,
}: {
  detail?: CompetitionDetailProjection;
  facts: ReturnType<typeof detailFacts>;
  context: AgentContext;
  records: readonly ReadRecord[];
  record?: ReadRecord;
  target: DetailTarget;
  tab: number;
  setTab: Dispatch<SetStateAction<number>>;
  choose: (target: DetailTarget) => void;
  loading: boolean;
  disabled: boolean;
  error: ErrorDetails | null;
  read: () => Promise<void>;
  open: (id: string | null) => void;
  select: (id: string, message?: string, target?: DetailTarget, action?: GuidedAction) => void;
}) {
  const policy = detail?.eligibility_policy;
  const requirements = detail?.skill_requirements;
  const locked = disabled || loading;
  function act(intent: string) {
    const action = actions.find((a) => a.intent === intent);
    if (detail && action && !locked) select(detail.competition.id, action.label, target, action);
  }
  const scopeSources = detail?.selected_track
    ? detail.selected_track.source
      ? [detail.selected_track.source]
      : []
    : detail?.selected_edition
      ? detail.selected_edition.source
        ? [detail.selected_edition.source]
        : []
      : (detail?.provenance.filter((p) => p.section === 'competition').map((p) => p.source) ?? []);
  return (
    <div className="competition-center competition-detail">
      <div className="detail-toolbar">
        <button type="button" onClick={() => open(null)}>
          返回赛事中心
        </button>
        <button type="button" disabled={locked} onClick={() => void read()}>
          重新读取详情
        </button>
      </div>
      {loading && <p role="status">正在加载赛事信息...</p>}
      {error && (
        <div className="error-surface" role="alert">
          <h2>暂时无法加载赛事信息</h2>
          <ErrorPresentation error={error} />
        </div>
      )}
      {!detail && !loading && !error && (
        <div className="detail-empty">
          <h1>暂无已验证的赛事详情</h1>
          <p>可重新读取正式记录；不会从页面名称补造赛事数据。</p>
        </div>
      )}
      {detail && (
        <>
          <header className="detail-hero">
            <p className="page-kicker">赛事档案 · 用有依据的信息作出选择</p>
            <h1>{detail.competition.name}</h1>
            <nav className="scope-breadcrumb" aria-label="赛事层级">
              <span>{detail.competition.name}</span>
              <span aria-hidden="true">/</span>
              <span>{detail.selected_edition?.name ?? '尚未选择届次'}</span>
              <span aria-hidden="true">/</span>
              <span>{detail.selected_track?.name ?? '尚未选择赛道'}</span>
            </nav>
            {detail.competition.description && (
              <p className="detail-description">{detail.competition.description}</p>
            )}
            <SourceStatus
              sources={scopeSources}
              label={
                detail.selected_track
                  ? '当前赛道来源'
                  : detail.selected_edition
                    ? '当前届次来源'
                    : '赛事来源'
              }
            />
            <div className="competition-action-bar">
              <button
                type="button"
                disabled={locked}
                onClick={() => select(detail.competition.id, undefined, target)}
              >
                设为当前赛事
              </button>
              {actions.map((a) => (
                <button
                  type="button"
                  key={a.intent}
                  disabled={locked}
                  onClick={() => act(a.intent)}
                >
                  {a.label}
                </button>
              ))}
            </div>
            <p className="panel-note">
              选择分析操作后将在 Copilot 中继续；如果需要补充信息，系统会向你确认。
            </p>
          </header>
          <div className="detail-layout">
            <aside className="current-scope dashboard-card" aria-label="当前范围">
              <h2>当前范围</h2>
              <dl>
                <dt>赛事</dt>
                <dd>{detail.competition.name}</dd>
                <dt>届次</dt>
                <dd>{detail.selected_edition?.name ?? '尚未选择届次'}</dd>
                <dt>赛道</dt>
                <dd>{detail.selected_track?.name ?? '尚未选择赛道（可保持届次级分析）'}</dd>
                <dt>当前学生</dt>
                <dd>
                  {context.student_id ? '已指定学生引用，分析时由服务端校验' : '尚未指定学生'}
                </dd>
                <dt>当前计划</dt>
                <dd>
                  {context.plan_ref
                    ? `已选择计划版本 v${context.plan_ref.version}`
                    : '尚未选择计划'}
                </dd>
              </dl>
              <p className="panel-note">选择范围不改变资格结果、计划版本或审批状态。</p>
            </aside>
            <section className="detail-selection dashboard-card" aria-label="选择分析范围">
              <h2>选择届次与赛道</h2>
              <p>赛事 → 届次 → 赛道。只按你的明确选择读取，不默认选择最新届次或第一条赛道。</p>
              <div className="competition-search">
                <label>
                  届次
                  <select
                    value={target.editionId ?? ''}
                    disabled={locked}
                    onChange={(e) => choose(e.target.value ? { editionId: e.target.value } : {})}
                  >
                    <option value="">请选择届次</option>
                    {detail.editions.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.name} · {e.year} · {verificationLabel(e.source)}
                      </option>
                    ))}
                  </select>
                </label>
                {detail.selected_edition && (
                  <label>
                    赛道
                    <select
                      value={target.trackId ?? ''}
                      disabled={locked}
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
                          {t.name} · {verificationLabel(t.source)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {detail.selected_edition ? (
                <p>
                  {windowSummary(detail.selected_edition.registration_window)}（报名） ·{' '}
                  {windowSummary(detail.selected_edition.competition_window)}（比赛）
                </p>
              ) : detail.editions.length ? (
                <div className="edition-options">
                  {detail.editions.map((e) => (
                    <article key={e.id}>
                      <h3>{e.name}</h3>
                      <p>
                        {e.year} · {verificationLabel(e.source)}
                      </p>
                      <p>报名：{windowSummary(e.registration_window)}</p>
                      <p>比赛：{windowSummary(e.competition_window)}</p>
                      <button
                        type="button"
                        disabled={locked}
                        onClick={() => choose({ editionId: e.id })}
                      >
                        查看此届次：{e.name}
                      </button>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="detail-empty">
                  暂无可读取届次记录。当前仅展示赛事层级资料，不推断届次或赛道。
                </p>
              )}
            </section>
          </div>
          <div className="competition-tabs" role="tablist" aria-label="赛事详情">
            {tabs.map((label, i) => (
              <button
                type="button"
                key={label}
                id={`detail-tab-${i}`}
                role="tab"
                aria-selected={tab === i}
                aria-controls="detail-panel"
                tabIndex={tab === i ? 0 : -1}
                onClick={() => setTab(i)}
                onKeyDown={(e) => {
                  const next =
                    e.key === 'ArrowRight'
                      ? (i + 1) % tabs.length
                      : e.key === 'ArrowLeft'
                        ? (i + tabs.length - 1) % tabs.length
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
                <div className="overview-grid">
                  <section className="detail-section">
                    <h3>基本信息</h3>
                    <dl>
                      <dt>赛事</dt>
                      <dd>{detail.competition.name}</dd>
                      <dt>当前届次</dt>
                      <dd>{detail.selected_edition?.name ?? '尚未选择届次'}</dd>
                      <dt>当前赛道</dt>
                      <dd>{detail.selected_track?.name ?? '尚未选择赛道'}</dd>
                    </dl>
                    <p>
                      {detail.competition.description ??
                        '暂无已审核的赛事说明。可先查看正式来源和可读取届次。'}
                    </p>
                  </section>
                  <DataAvailabilitySummary detail={detail} />
                  <section className="detail-section">
                    <h3>官方来源与核验</h3>
                    <p>核验状态仅适用于相应来源与范围。</p>
                    <SourceStatus sources={scopeSources} label="当前范围来源" />
                    <button type="button" onClick={() => setTab(5)}>
                      浏览证据中心
                    </button>
                  </section>
                  <section className="detail-section">
                    <h3>建议下一步</h3>
                    <p>先确认规则和技能要求，再按需分析自己的情况。</p>
                    <button type="button" onClick={() => setTab(1)}>
                      查看参赛规则
                    </button>
                    <button type="button" onClick={() => setTab(2)}>
                      查看技能要求
                    </button>
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => act('CHECK_ELIGIBILITY')}
                    >
                      判断我的参赛资格
                    </button>
                  </section>
                </div>
              </>
            )}
            {tab === 1 && (
              <div className="decision-sections">
                <section className="detail-section">
                  <h2>官方参赛规则</h2>
                  <p>以下仅表示当前已审核政策覆盖范围，不宣称覆盖赛事所有资格规则。</p>
                  {policy ? (
                    <>
                      <div className="coverage-note">
                        <strong>
                          {policy.coverage === 'partial'
                            ? '当前规则覆盖不完整'
                            : '当前政策声明完整覆盖'}
                        </strong>
                        <p>{policy.coverage_note}</p>
                        {policy.coverage === 'partial' && (
                          <p>系统仅展示当前已审核规则，不代表全部官方资格要求。</p>
                        )}
                      </div>
                      {(policy.constraints ?? []).map((c) => (
                        <article key={c.rule_id}>
                          <h3>学历要求</h3>
                          <p>{c.evidence_text}</p>
                          <p>
                            规则适用教育层级：
                            {c.allowed_levels
                              .map(
                                (l) =>
                                  ({
                                    undergraduate: '本科生',
                                    graduate: '研究生',
                                    unknown: '未知',
                                  })[l] ?? l,
                              )
                              .join('、')}
                          </p>
                          <p className="panel-note">
                            规则范围：
                            {c.scope === 'competition'
                              ? '赛事'
                              : c.scope === 'edition'
                                ? '届次'
                                : '赛道'}
                            层级
                          </p>
                          <details>
                            <summary>查看规则依据</summary>
                            <SourceGroups sources={[c.source]} />
                          </details>
                        </article>
                      ))}
                    </>
                  ) : (
                    <div className="detail-empty">
                      <h3>{detail.selected_edition ? '暂无已审核资格规则' : '尚未选择届次'}</h3>
                      <p>
                        当前暂无可读取的已审核资格规则。请选择精确范围查看；不从其他范围继承规则。
                      </p>
                    </div>
                  )}
                </section>
                <section className="detail-section">
                  <h2>我的资格判断</h2>
                  {facts.eligibility ? (
                    <p className="business-status">
                      {
                        {
                          eligible: '资格已确认',
                          ineligible: '当前资格受限',
                          unknown: '尚无法确认',
                        }[facts.eligibility.status]
                      }
                    </p>
                  ) : (
                    <p>尚未分析你的参赛资格。</p>
                  )}
                  <p>只展示与当前学生、届次和赛道精确匹配的已有结果。</p>
                  <button type="button" disabled={locked} onClick={() => act('CHECK_ELIGIBILITY')}>
                    判断我的参赛资格
                  </button>
                </section>
              </div>
            )}
            {tab === 2 && (
              <>
                <section className="detail-section">
                  <h2>赛事技能要求</h2>
                  {requirements ? (
                    <>
                      <div className="coverage-note">
                        <strong>
                          覆盖状态：
                          {
                            {
                              partial: '部分已核验',
                              complete: '完整覆盖声明',
                              missing: '暂无技能要求数据',
                            }[requirements.requirement_set.coverage]
                          }
                        </strong>
                        <p>{requirements.requirement_set.coverage_note}</p>
                      </div>
                      <div className="requirement-grid">
                        {(requirements.requirement_set.requirements ?? []).map((r) => (
                          <article key={r.skill_id}>
                            <h3>
                              {requirements.skills.find((s) => s.id === r.skill_id)?.name ??
                                '技能名称尚未提供'}
                            </h3>
                            <span className="semantic-chip">
                              {r.requirement_type === 'required'
                                ? '已确认需要该技能'
                                : '期望具备的技能'}
                            </span>
                            <p>
                              {r.required_level === null
                                ? '所需能力等级暂未明确'
                                : `所需能力等级：${levels[r.required_level] ?? r.required_level}`}
                            </p>
                            <p>
                              本项属于当前
                              {requirements.requirement_set.coverage === 'partial'
                                ? '部分已核验'
                                : '已返回'}
                              要求集；不表示个人已满足。
                            </p>
                            <details>
                              <summary>查看技能要求来源</summary>
                              {r.presence_evidence.map((e, i) => (
                                <p key={i}>{e.message}</p>
                              ))}
                              <SourceGroups
                                sources={[...r.presence_evidence, ...(r.evidence ?? [])].flatMap(
                                  (e) => (e.source ? [e.source] : []),
                                )}
                              />
                            </details>
                          </article>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="detail-empty">
                      <h3>{detail.selected_edition ? '暂无精确技能要求' : '尚未选择届次'}</h3>
                      <p>当前暂无与所选届次和赛道精确匹配的已审核技能要求数据。</p>
                      <p>不会把届次级要求自动应用到赛道，也不会运行个人技能分析来补赛事资料。</p>
                    </div>
                  )}
                </section>
                <section className="detail-section">
                  <h2>我的技能差距</h2>
                  {facts.skillGap ? (
                    <SkillGapResults result={facts.skillGap} />
                  ) : (
                    <p>尚未进行个人技能差距分析。</p>
                  )}
                  <button type="button" disabled={locked} onClick={() => act('ANALYZE_SKILL_GAP')}>
                    分析我的技能差距
                  </button>
                </section>
              </>
            )}
            {tab === 3 && <CompetitionTimeline detail={detail} />}
            {tab === 4 && (
              <>
                <h2>赛事赛道</h2>
                <p>以下为当前届次的正式赛道记录；尚未查询的赛道规则保持未知。</p>
                <div className="track-grid">
                  {(detail.tracks ?? []).map((t) => {
                    const exact = cachedDetail(records, detail.competition.id, {
                      editionId: detail.selected_edition?.id,
                      trackId: t.id,
                    });
                    return (
                      <article
                        key={t.id}
                        className={detail.selected_track?.id === t.id ? 'is-selected' : ''}
                      >
                        <h3>{t.name}</h3>
                        {detail.selected_track?.id === t.id && (
                          <span className="semantic-chip">当前选择</span>
                        )}
                        <p>{t.description ?? '暂无已审核的赛道说明'}</p>
                        <p>赛道来源：{verificationLabel(t.source)}</p>
                        <p>
                          精确资格规则：
                          {!exact
                            ? '尚未读取该范围'
                            : exact.eligibility_policy
                              ? exact.eligibility_policy.coverage === 'partial'
                                ? '部分已审核'
                                : '已有审核政策'
                              : '暂无精确范围数据'}
                        </p>
                        <p>
                          精确技能要求：
                          {!exact
                            ? '尚未读取该范围'
                            : exact.skill_requirements
                              ? '已有审核要求'
                              : '暂无精确范围数据'}
                        </p>
                        <button
                          type="button"
                          disabled={locked}
                          onClick={() =>
                            choose({ editionId: detail.selected_edition?.id, trackId: t.id })
                          }
                        >
                          选择此赛道：{t.name}
                        </button>
                      </article>
                    );
                  })}
                </div>
                {!(detail.tracks ?? []).length && (
                  <div className="detail-empty">
                    <h3>{detail.selected_edition ? '暂无可展示的赛道记录' : '尚未选择届次'}</h3>
                    <p>不代表赛事确认没有赛道；可保持届次级范围或查看来源。</p>
                  </div>
                )}
              </>
            )}
            {tab === 5 && <CompetitionEvidenceCenter detail={detail} />}
            {tab === 6 && (
              <>
                <h2>赛事变化历史</h2>
                <div className="detail-empty">
                  <strong>暂未提供完整赛事变化历史</strong>
                  <p>当前版本尚未持久化全部 CompetitionEvent；当前会话证据不等于完整历史。</p>
                </div>
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
                        <p className="coverage-note">
                          模拟赛事变化 / 演示数据，不代表官方真实发生变化。
                        </p>
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
          {tab !== 0 && (
            <section className="detail-next dashboard-card">
              <h2>建议下一步</h2>
              <p>选择现有操作，提交后由 Backend 核验所需信息。</p>
              {!facts.eligibility && (
                <button type="button" disabled={locked} onClick={() => act('CHECK_ELIGIBILITY')}>
                  前往资格分析
                </button>
              )}
              {!facts.skillGap && (
                <button type="button" disabled={locked} onClick={() => act('ANALYZE_SKILL_GAP')}>
                  前往技能差距分析
                </button>
              )}
              {detail.selected_edition && (
                <button type="button" disabled={locked} onClick={() => act('BUILD_PLAN')}>
                  开始生成备赛计划
                </button>
              )}
            </section>
          )}
          <details className="competition-audit">
            <summary>查看高级审计信息</summary>
            <pre>
              {JSON.stringify(
                {
                  projection: detail,
                  result: record?.response,
                  artifacts: record?.artifacts,
                  context,
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
