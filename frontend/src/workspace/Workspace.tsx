import { useState } from 'react';
import type { FormEvent } from 'react';
import { useConversation } from './useConversation.ts';
import type { InvocationClient } from './useConversation.ts';
import { workflowLabel } from './state.ts';
import { HitlPanel } from './HitlPanel.tsx';
import { ResultPanel } from '../results/ResultPanel.tsx';
import type { ArtifactReader } from '../results/artifacts.ts';

const errors = {
  TRANSPORT_ERROR: '连接未完成，请检查后重试。请求不会自动重发。',
  RUNTIME_ERROR: 'Runtime 未能完成调用，请稍后重试。',
  CONTRACT_ERROR: '无法解析 Runtime 响应，本次内容未作为有效回复展示。',
  ABORTED: '请求已取消；这不代表业务操作已撤销。',
};
const continuationErrors = {
  TRANSPORT_ERROR: '续接连接未确认完成。',
  RUNTIME_ERROR: 'Runtime 未返回已确认的续接结果。',
  CONTRACT_ERROR: '无法解析续接响应，本次内容未作为有效回复展示。',
  ABORTED: '续接请求已取消等待；这不代表业务操作已撤销。',
};
const examples = ['有哪些适合我的竞赛？', '帮我检查参赛资格', '我该如何准备比赛？'];
const newRequestId = () => crypto.randomUUID();

export function Workspace({
  client,
  nextRequestId = newRequestId,
  now,
  readArtifacts,
}: {
  client: InvocationClient;
  nextRequestId?: () => string;
  now?: () => string;
  readArtifacts?: ArtifactReader;
}) {
  const { state, submit, retry, startNew, clarify, decide } = useConversation(
    client,
    nextRequestId,
    now,
  );
  const [input, setInput] = useState('');
  const [studentId, setStudentId] = useState('');
  const pending = state.uiStatus === 'SUBMITTING';
  const response = state.response;
  const needs = response?.outcome === 'NEEDS_CLARIFICATION';
  const waits = response?.outcome === 'WAITING_FOR_APPROVAL';
  const locked = pending || needs || waits || state.continuationUnconfirmed;

  function send(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || locked) return;
    void submit(input, studentId);
    setInput('');
  }

  return (
    <div className="app-shell">
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
          FAKE · 演示环境
        </span>
      </header>
      <main id="workspace" className="workspace">
        <div className="workspace-heading">
          <p className="eyebrow">COMPETITION WORKSPACE</p>
          <h1>把竞赛目标，变成下一步。</h1>
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
                      <p>{entry.content}</p>
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
              />
            )}
            {state.error && (
              <div className="error-surface" role="alert">
                <strong>{state.error}</strong>
                <p>
                  {state.continuationUnconfirmed
                    ? continuationErrors[state.error]
                    : errors[state.error]}
                </p>
                {state.continuationUnconfirmed ? (
                  <p>
                    续接请求未确认完成，执行状态可能未知。请重新检查当前状态后再操作；此处不重发续接请求。
                  </p>
                ) : (
                  <button type="button" onClick={() => void retry()} disabled={pending}>
                    重试此请求
                  </button>
                )}
              </div>
            )}
            <form className="composer" onSubmit={send}>
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
              <p className="composer-hint" id="composer-hint">
                {needs || waits
                  ? '请使用上方对应的补充信息或明确批准/拒绝控件。普通文字不会自动产生批准决定。'
                  : 'Enter 换行，Ctrl / ⌘ + Enter 发送。演示回复为预设内容，不代表真实业务判断。'}
              </p>
            </form>
          </section>
          <aside className="workflow-panel" aria-label="工作流与结果">
            <section aria-labelledby="workflow-title">
              <p className="eyebrow">CURRENT WORKFLOW</p>
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
                  <p>{response.clarification?.question}</p>
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
      </main>
      <footer className="page-footer">
        Competition Copilot<span>明确输入 · 结构化状态 · 可追溯决策</span>
      </footer>
    </div>
  );
}
