import { planStatus } from '../results/SemanticResults.tsx';
import { useCompetitionName } from '../results/competitionNames.tsx';
import { intentLabels } from './clarificationPresentation.ts';
import { initialState, workflowLabel } from './state.ts';
import type { WorkspaceSnapshot } from './sessionPresentation.ts';

export function CurrentContext({
  session,
  openCompetition,
}: {
  session: WorkspaceSnapshot | null;
  openCompetition?: () => void;
}) {
  const context = session?.context;
  const name = useCompetitionName();
  return (
    <section className="dashboard-card" aria-labelledby="context-title">
      <h2 id="context-title">当前上下文</h2>
      <p className="panel-note">来自本页显式输入与计划选择；输入仍需服务端核验。</p>
      <dl className="context-overview">
        <div>
          <dt>学生</dt>
          <dd>{context?.student_id ? '已填写学生引用（待核验）' : '尚未指定学生'}</dd>
        </div>
        <div>
          <dt>赛事</dt>
          <dd>{context?.competition_id ? name(context.competition_id) : '当前没有选中的赛事'}</dd>
        </div>
        <div>
          <dt>届次</dt>
          <dd>{context?.edition_id ? '已指定届次' : '尚未指定届次'}</dd>
        </div>
        <div>
          <dt>赛道</dt>
          <dd>{context?.track_id ? '已指定赛道' : '未指定赛道'}</dd>
        </div>
        <div>
          <dt>当前计划</dt>
          <dd>
            {session?.selectedPlan
              ? `已选择版本 v${session.selectedPlan.reference.version}`
              : '尚未选择计划'}
          </dd>
        </div>
      </dl>
      {openCompetition && (
        <button type="button" onClick={openCompetition}>
          {context?.competition_id ? '查看当前赛事' : '浏览赛事'}
        </button>
      )}
      <details className="context-technical">
        <summary>查看技术详情</summary>
        <pre>{JSON.stringify(context ?? {}, null, 2)}</pre>
      </details>
    </section>
  );
}

export function Dashboard({
  session,
  openCopilot,
  openCompetition,
}: {
  session: WorkspaceSnapshot | null;
  openCopilot: () => void;
  openCompetition?: () => void;
}) {
  const name = useCompetitionName();
  const selected = session?.selectedPlan;
  const recent = session?.recentResponse;
  const approval = session?.pendingApproval;
  return (
    <div className="dashboard">
      <header className="page-intro">
        <p className="page-kicker">你的竞赛工作台</p>
        <h1>首页</h1>
        <p>欢迎来到 Competition Copilot。从了解自己和赛事开始，把选择变成下一步。</p>
        <span className="semantic-chip">
          {session?.context.student_id ? '本页已指定学生引用' : '尚未指定当前学生'}
        </span>
      </header>
      {session?.pending && (
        <p role="status">正在处理 Copilot 中的请求，可返回查看进展。切换页面不会重新提交。</p>
      )}
      <div className="dashboard-grid">
        <CurrentContext session={session} openCompetition={openCompetition} />
        <section className="dashboard-card" aria-labelledby="current-plan-title">
          <h2 id="current-plan-title">当前计划</h2>
          {selected ? (
            <>
              <p>{name(selected.reference.target.competition_id)}</p>
              <p>计划版本：v{selected.reference.version}</p>
              <p>
                计划状态：
                <span className="semantic-chip">
                  {selected.status ? planStatus(selected.status) : '暂无状态记录'}
                </span>
              </p>
              <p className="panel-note">
                显示当前显式选择的版本，不保证是服务端最新版本。服务端仍会检查过期引用。
              </p>
            </>
          ) : (
            <div className="product-empty">
              <h3>当前没有计划</h3>
              <p>选择赛事并生成第一版备赛计划，再显式选择后，计划会显示在这里。</p>
            </div>
          )}
          <button type="button" onClick={openCopilot}>
            {selected ? '在 Copilot 中查看计划' : '打开 Copilot 生成计划'}
          </button>
        </section>
        <section className="dashboard-card" aria-labelledby="recent-result-title">
          <h2 id="recent-result-title">最近结果 / 最近决策</h2>
          {recent ? (
            <>
              <p>{intentLabels[recent.intent]}</p>
              <span className="semantic-chip">
                {workflowLabel({ ...initialState, response: recent })}
              </span>
              <p className="panel-note">
                仅展示本页最近一次已验证回复。业务结论与证据请在 Copilot 查看。
              </p>
            </>
          ) : (
            <div className="product-empty">
              <h3>还没有决策记录</h3>
              <p>完成一次赛事查询或分析后，最近结果会显示在这里。</p>
            </div>
          )}
          <button type="button" onClick={openCopilot}>
            查看 Copilot 记录
          </button>
        </section>
        {approval && (
          <section
            className="dashboard-card approval-notice"
            aria-labelledby="pending-approval-title"
          >
            <h2 id="pending-approval-title">待你确认</h2>
            <p>当前计划有一项后端返回的调整建议，尚不能视为已执行。</p>
            {session?.continuationUnconfirmed ? (
              <p>审批续接结果未确认，请返回检查当前状态。</p>
            ) : (
              <p>请查看影响范围与依据，再明确批准或拒绝。</p>
            )}
            <button type="button" onClick={openCopilot}>
              返回处理审批
            </button>
          </section>
        )}
        <section className="dashboard-card next-action" aria-labelledby="next-action-title">
          <h2 id="next-action-title">下一步</h2>
          <p>
            {approval
              ? '返回当前工作流，查看待确认的计划调整。'
              : !session?.context.competition_id
                ? 'Competition Copilot 可以帮助你发现赛事、判断资格并制定备赛计划。'
                : selected
                  ? '查看当前计划及其依据，或在 Copilot 中继续讨论下一步。'
                  : '在 Copilot 中补充信息，判断资格、分析技能差距或生成备赛计划。'}
          </p>
          <button type="button" onClick={openCopilot}>
            打开 Copilot
          </button>
        </section>
      </div>
      <p className="product-session-note">
        当前页面会话 · 无后台持续状态承诺。刷新清空页面选择；本地服务重启后，生成计划不持久化。
      </p>
    </div>
  );
}
