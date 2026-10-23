import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useConversation } from './useConversation.ts';
import type { InvocationClient } from './useConversation.ts';
import { workflowLabel } from './state.ts';
import { HitlPanel } from './HitlPanel.tsx';
import { ResultPanel } from '../results/ResultPanel.tsx';
import { ErrorPresentation } from '../results/ErrorPresentation.tsx';
import type { ArtifactReader } from '../results/artifacts.ts';
import type { PlanReference } from '../runtime/generated/contracts.ts';
import { collectPlanChoices, planChoiceKey } from './plans.ts';
import type { PlanChoice } from './plans.ts';
import { actionHint, guidedActions } from './actions.ts';
import type { GuidedAction } from './actions.ts';
import type { WorkspaceSnapshot } from './sessionPresentation.ts';
import type { CompetitionSelection } from './CompetitionCenter.tsx';

const examples = ['有哪些适合我的竞赛？', '帮我检查参赛资格', '我该如何准备比赛？'];
const newRequestId = () => crypto.randomUUID();

export function Workspace({
  client,
  nextRequestId = newRequestId,
  now,
  readArtifacts,
  localPlan,
  runtimeLabel = 'FAKE · 演示环境',
  invocationNote = '演示回复为预设内容，不代表真实业务判断。',
  embedded = false,
  onSnapshot,
  contextSelection,
  externalBusy = false,
}: {
  client: InvocationClient;
  nextRequestId?: () => string;
  now?: () => string;
  readArtifacts?: ArtifactReader;
  localPlan?: PlanReference;
  runtimeLabel?: string;
  invocationNote?: string;
  embedded?: boolean;
  onSnapshot?: (snapshot: WorkspaceSnapshot) => void;
  contextSelection?: CompetitionSelection;
  externalBusy?: boolean;
}) {
  const { state, presentationError, submit, retry, startNew, clarify, decide } = useConversation(
    client,
    nextRequestId,
    now,
  );
  const [input, setInput] = useState('');
  const [studentId, setStudentId] = useState('');
  const [competitionId, setCompetitionId] = useState('');
  const [editionId, setEditionId] = useState('');
  const [trackId, setTrackId] = useState('');
  const [useLocalPlan, setUseLocalPlan] = useState(false);
  const [plans, setPlans] = useState<PlanChoice[]>([]);
  const [selectedPlanKey, setSelectedPlanKey] = useState('');
  const selectedPlan = plans.find((plan) => planChoiceKey(plan.reference) === selectedPlanKey);
  const pending = state.uiStatus === 'SUBMITTING';
  const response = state.response;
  const needs = response?.outcome === 'NEEDS_CLARIFICATION';
  const waits = response?.outcome === 'WAITING_FOR_APPROVAL';
  const locked = pending || needs || waits || state.continuationUnconfirmed || externalBusy;

  const handledSelection = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!contextSelection || handledSelection.current === contextSelection.sequence) return;
    handledSelection.current = contextSelection.sequence;
    if (competitionId.trim() !== contextSelection.competitionId) {
      setCompetitionId(contextSelection.competitionId);
      setEditionId('');
      setTrackId('');
    }
    if ('editionId' in contextSelection) {
      setEditionId(contextSelection.editionId ?? '');
      setTrackId(contextSelection.trackId ?? '');
    }
    if (contextSelection.message) setInput(`请${contextSelection.message}。`);
    if (contextSelection.action && !locked) {
      const scope = explicitContext();
      scope.competition_id = contextSelection.competitionId;
      delete scope.edition_id;
      delete scope.track_id;
      if (contextSelection.editionId) scope.edition_id = contextSelection.editionId;
      if (contextSelection.trackId) scope.track_id = contextSelection.trackId;
      void submit(
        contextSelection.action.message,
        studentId,
        scope,
        contextSelection.action.intent,
      );
      setInput('');
    }
  }, [contextSelection]);

  useEffect(() => {
    onSnapshot?.({
      context: {
        ...(studentId.trim() ? { student_id: studentId.trim() } : {}),
        ...(competitionId.trim() ? { competition_id: competitionId.trim() } : {}),
        ...(editionId.trim() ? { edition_id: editionId.trim() } : {}),
        ...(trackId.trim() ? { track_id: trackId.trim() } : {}),
        ...(selectedPlan
          ? { plan_ref: selectedPlan.reference }
          : useLocalPlan && localPlan
            ? { plan_ref: localPlan }
            : {}),
      },
      selectedPlan: selectedPlan ?? (useLocalPlan && localPlan ? { reference: localPlan } : null),
      recentResponse: state.entries.findLast((entry) => entry.response)?.response ?? null,
      pendingApproval: waits ? response.approval_request : null,
      pending,
      continuationUnconfirmed: state.continuationUnconfirmed,
      interactionPending: !!(needs || waits || state.continuationUnconfirmed),
    });
  }, [
    onSnapshot,
    studentId,
    competitionId,
    editionId,
    trackId,
    selectedPlan,
    useLocalPlan,
    localPlan,
    state.entries,
    waits,
    response,
    pending,
    state.continuationUnconfirmed,
  ]);

  useEffect(() => {
    if (!response || !readArtifacts) return;
    try {
      const received = collectPlanChoices(response, readArtifacts(response));
      if (!received.length) return;
      setPlans((previous) => {
        const choices = new Map(previous.map((plan) => [planChoiceKey(plan.reference), plan]));
        for (const plan of received) choices.set(planChoiceKey(plan.reference), plan);
        return [...choices.values()];
      });
    } catch {
      // Invalid hosting artifacts never create selectable references.
    }
  }, [response, readArtifacts]);

  function explicitContext() {
    return {
      ...(competitionId.trim() ? { competition_id: competitionId.trim() } : {}),
      ...(editionId.trim() ? { edition_id: editionId.trim() } : {}),
      ...(trackId.trim() ? { track_id: trackId.trim() } : {}),
      ...(selectedPlan
        ? { plan_ref: selectedPlan.reference }
        : useLocalPlan && localPlan
          ? { plan_ref: localPlan }
          : {}),
    };
  }

  function send(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || locked) return;
    void submit(input, studentId, explicitContext());
    setInput('');
  }

  const hasSelectedPlan = !!(selectedPlan || (useLocalPlan && localPlan));
  const hasTarget = !!(competitionId.trim() && editionId.trim());
  function sendAction(action: GuidedAction) {
    if (locked || actionHint(action, hasTarget, hasSelectedPlan)) return;
    void submit(action.message, studentId, explicitContext(), action.intent);
  }

  const Content = embedded ? 'section' : 'main';
  return (
    <div className={embedded ? 'copilot-workspace' : 'app-shell'}>
      {!embedded && (
        <header className="product-header">
          <a className="brand" href="#workspace">
            <span className="brand-mark" aria-hidden="true">
              C<span>·</span>C
            </span>
            <span>
              Competition Copilot<small>竞赛决策与成长助手</small>
            </span>
          </a>
          <span className="runtime-badge">
            <span aria-hidden="true" />
            {runtimeLabel}
          </span>
        </header>
      )}
      <Content
        id="workspace"
        className="workspace"
        aria-label={embedded ? 'Copilot 工作区' : undefined}
      >
        <div className="workspace-heading">
          {!embedded && <p className="eyebrow">COMPETITION WORKSPACE</p>}
          <h1>{embedded ? 'Copilot' : '把竞赛目标，变成下一步。'}</h1>
          <p>从一个问题开始，梳理你的参赛与备赛方向。</p>
        </div>
        <div className={`workspace-grid${response?.outcome === 'COMPLETED' ? ' has-result' : ''}`}>
          <section className="conversation" aria-labelledby="conversation-title">
            <div className="section-heading">
              <h2 id="conversation-title">对话</h2>
              <button type="button" onClick={startNew} disabled={pending}>
                开始新请求
              </button>
            </div>
            <div className="timeline" aria-busy={pending}>
              {state.entries.length === 0 ? (
                <div className="empty-state">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                    <circle cx="24" cy="24" r="19" stroke="currentColor" />
                    <path d="m30 18-4 9-8 3 3-8 9-4Z" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="24" cy="24" r="2" fill="currentColor" />
                  </svg>
                  <h3>从一个问题开始</h3>
                  <p>你可以询问赛事发现、参赛资格、推荐、技能差距或备赛规划。</p>
                  <div className="example-prompts">
                    {examples.map((text) => (
                      <button key={text} type="button" onClick={() => setInput(text)}>
                        {text}
                        <span aria-hidden="true">↗</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <ol className="message-list" aria-label="对话记录" aria-live="polite">
                  {state.entries.map((entry) => (
                    <li
                      key={entry.id}
                      className={`message message-${entry.role.toLowerCase()}`}
                      data-request-id={entry.requestId}
                    >
                      <div className="message-role">
                        {entry.role === 'USER'
                          ? '你'
                          : entry.role === 'AGENT'
                            ? 'Competition Copilot'
                            : '状态'}
                      </div>
                      {entry.role === 'AGENT' &&
                      entry.response?.outcome === 'NEEDS_CLARIFICATION' ? (
                        <details>
                          <summary>查看原始回复</summary>
                          <p>{entry.content}</p>
                        </details>
                      ) : entry.role === 'AGENT' &&
                        readArtifacts &&
                        entry.response &&
                        ['GET_RECOMMENDATIONS', 'ANALYZE_SKILL_GAP', 'BUILD_PLAN'].includes(
                          entry.response.intent,
                        ) &&
                        entry.response.outcome === 'COMPLETED' &&
                        entry.requestId === response?.request_id ? (
                        <p>
                          {entry.response.intent === 'GET_RECOMMENDATIONS'
                            ? '推荐候选已返回，请查看推荐结果。'
                            : entry.response.intent === 'ANALYZE_SKILL_GAP'
                              ? '技能分析已返回，请查看技能差距分析。'
                              : '计划已返回，请查看备赛计划。'}
                        </p>
                      ) : entry.role === 'AGENT' && entry.response && readArtifacts ? (
                        <details>
                          <summary>查看原始回复</summary>
                          <p>{entry.content}</p>
                        </details>
                      ) : (
                        <p>{entry.content}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
              {pending && (
                <p className="loading" role="status">
                  <span className="loading-dot" aria-hidden="true" />
                  正在等待回复…
                </p>
              )}
            </div>
            {(needs || waits) && response && (
              <HitlPanel
                key={state.interaction?.token ?? 'inactive-interaction'}
                response={response}
                interaction={state.interaction}
                disabled={pending || state.continuationUnconfirmed}
                clarify={clarify}
                decide={decide}
                plans={[...plans.map((plan) => plan.reference), ...(localPlan ? [localPlan] : [])]}
              />
            )}
            {state.error && (
              <div className="error-surface" role="alert">
                <ErrorPresentation
                  error={presentationError ?? { code: state.error, message: state.error }}
                  category={state.error}
                />
                {state.continuationUnconfirmed ? (
                  <p>
                    续接请求未确认完成，执行状态可能未知。请重新检查当前状态后再操作；此处不重发续接请求。
                  </p>
                ) : presentationError?.message ===
                  'NO_TARGET_CONSISTENT_REPLANNING_INPUT' ? null : (
                  <button type="button" onClick={() => void retry()} disabled={pending}>
                    重试此请求
                  </button>
                )}
              </div>
            )}
            <form className="composer" onSubmit={send}>
              {contextSelection?.message && (
                <p className="context-summary">
                  已从赛事详情选择当前赛事。请补充必要信息，再使用“{contextSelection.message}
                  ”快捷操作继续；尚未提交。
                </p>
              )}
              {externalBusy && <p role="status">正在获取赛事数据，请等待当前只读请求完成。</p>}
              <fieldset className="guided-actions" disabled={locked}>
                <legend>快捷操作</legend>
                <div className="guided-action-buttons">
                  {guidedActions.map((action) => {
                    const hint = actionHint(action, hasTarget, hasSelectedPlan);
                    return (
                      <button
                        key={action.intent}
                        type="button"
                        disabled={!!hint}
                        aria-describedby={
                          hint
                            ? action.intent === 'REQUEST_PLAN_REVISION'
                              ? 'plan-action-hint'
                              : 'target-action-hint'
                            : undefined
                        }
                        onClick={() => sendAction(action)}
                      >
                        {action.label}
                      </button>
                    );
                  })}
                </div>
                {!hasTarget && <p id="target-action-hint">请先选择比赛和届次。</p>}
                {!hasSelectedPlan && <p id="plan-action-hint">请先生成或选择一个计划。</p>}
              </fieldset>
              <label htmlFor="request-text">你的问题</label>
              <textarea
                id="request-text"
                rows={3}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={locked}
                placeholder="例如：我想参加竞赛，应该从哪里开始？"
                aria-describedby="composer-hint"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    e.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="composer-actions">
                <div className="context-field">
                  <label htmlFor="student-id">
                    学生 ID <span>可选 · 显式上下文</span>
                  </label>
                  <input
                    id="student-id"
                    value={studentId}
                    onChange={(e) => setStudentId(e.target.value)}
                    disabled={locked}
                    placeholder="不填写则不附加学生身份"
                  />
                </div>
                <button className="send-button" type="submit" disabled={locked || !input.trim()}>
                  {pending ? '提交中…' : '发送请求'}
                  <span aria-hidden="true">↑</span>
                </button>
              </div>
              <details className="local-context">
                <summary>本地调用的显式上下文</summary>
                <label htmlFor="competition-id">竞赛 ID</label>
                <input
                  id="competition-id"
                  value={competitionId}
                  disabled={locked}
                  required={!!editionId.trim()}
                  onChange={(e) => setCompetitionId(e.target.value)}
                />
                <label htmlFor="edition-id">届次 ID</label>
                <input
                  id="edition-id"
                  value={editionId}
                  disabled={locked}
                  onChange={(e) => setEditionId(e.target.value)}
                />
                <label htmlFor="track-id">赛道 ID（可选）</label>
                <input
                  id="track-id"
                  value={trackId}
                  disabled={locked}
                  onChange={(event) => setTrackId(event.target.value)}
                />
                <label htmlFor="selected-plan">当前计划 / 选择计划</label>
                <select
                  id="selected-plan"
                  value={selectedPlanKey}
                  disabled={locked}
                  onChange={(event) => {
                    setSelectedPlanKey(event.target.value);
                    setUseLocalPlan(false);
                  }}
                >
                  <option value="">未选择生成的计划</option>
                  {plans.map((plan) => (
                    <option
                      key={planChoiceKey(plan.reference)}
                      value={planChoiceKey(plan.reference)}
                    >
                      {plan.reference.plan_id} · 版本 {plan.reference.version} · {plan.status} ·{' '}
                      {plan.reference.target.competition_id} / {plan.reference.target.edition_id} /{' '}
                      {plan.reference.target.track_id ?? 'edition-level'}
                    </option>
                  ))}
                </select>
                <p>
                  选择计划不表示批准，也不会生成事件、影响或修订指令。缺少匹配的重规划输入时，修订请求会被拒绝。
                  计划选择仅保留在当前页面；服务端重启后需重新生成计划。
                  赛道移除演示使用人工受控观察，不代表官方真的移除了赛道。
                </p>
                {localPlan && (
                  <>
                    <label>
                      <input
                        type="checkbox"
                        checked={useLocalPlan}
                        disabled={locked}
                        onChange={(e) => {
                          setUseLocalPlan(e.target.checked);
                          setSelectedPlanKey('');
                        }}
                      />
                      使用本地受控修订示例方案（非真实赛事变化）
                    </label>
                    <p>
                      方案引用：{localPlan.plan_id} · 版本 {localPlan.version} · 学生{' '}
                      {localPlan.student_id}
                    </p>
                    <p>选择仅提供公开 PlanRef，不表示批准。修订示例请清空不匹配的学生/赛事字段。</p>
                  </>
                )}
              </details>
              <p className="composer-hint" id="composer-hint">
                {needs || waits
                  ? '请使用上方对应的补充信息或明确批准/拒绝控件。普通文字不会自动产生批准决定。'
                  : `Enter 换行，Ctrl / ⌘ + Enter 发送。${invocationNote}`}
              </p>
            </form>
          </section>
          <aside className="workflow-panel" aria-label="工作流与结果">
            <section aria-labelledby="workflow-title">
              {!embedded && <p className="eyebrow">CURRENT WORKFLOW</p>}
              <h2 id="workflow-title">工作流状态</h2>
              <p className={`workflow-status ${pending ? 'is-pending' : ''}`} role="status">
                {workflowLabel(state)}
              </p>
              <p className="panel-note">
                {pending
                  ? '本地提交中，尚未获得 Agent workflow 结果。'
                  : '状态来自已验证的结构化回复；不会根据回复文字猜测。'}
              </p>
            </section>
            <section className="result-slot" aria-labelledby="result-title">
              <h2 id="result-title">当前结果</h2>
              {needs ? (
                <div className="interaction-shell">
                  <h3>需要补充信息</h3>
                  <p>请按表单补充本次操作所需的信息；不能安全填写的参数可在高级输入中查看。</p>
                  <span>
                    {state.continuationUnconfirmed
                      ? '续接结果未确认'
                      : pending
                        ? '补充信息已发送，等待回复'
                        : '请填写本次要求的字段'}
                  </span>
                </div>
              ) : waits ? (
                <div className="interaction-shell">
                  <h3>等待用户确认</h3>
                  <p>{response.approval_request?.summary}</p>
                  <span>
                    {state.continuationUnconfirmed
                      ? '执行状态未确认，不能断言是否已执行'
                      : pending
                        ? '决定已发送，等待 Runtime 确认'
                        : '尚未发送批准或拒绝决定'}
                  </span>
                </div>
              ) : response ? (
                <ResultPanel response={response} readArtifacts={readArtifacts} />
              ) : (
                <p className="panel-note">发送问题后，在这里查看当前请求的状态与结果摘要。</p>
              )}
            </section>
            <p className="session-note">
              仅保留当前页面会话
              <br />
              刷新后清空，不作为业务记录。
              <br />
              开始新请求不表示批准、拒绝或撤销旧请求。
            </p>
          </aside>
        </div>
      </Content>
      {!embedded && (
        <footer className="page-footer">
          Competition Copilot<span>明确输入 · 结构化状态 · 可追溯决策</span>
        </footer>
      )}
    </div>
  );
}
