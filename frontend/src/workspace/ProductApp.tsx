import { useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentProps } from 'react';
import { Workspace } from './Workspace.tsx';
import { Dashboard } from './Dashboard.tsx';
import type { WorkspaceSnapshot } from './sessionPresentation.ts';
import { CompetitionCenter } from './CompetitionCenter.tsx';
import type { CompetitionSelection } from './CompetitionCenter.tsx';
import { competitionSession } from './competitionSession.ts';
import type { ReadRecord } from './competitionSession.ts';
import { competitionsFrom } from './competitionData.ts';
import { CompetitionCatalog } from '../results/competitionNames.tsx';

const pages = [
  { id: 'home', label: '首页' },
  { id: 'competitions', label: '赛事中心' },
  { id: 'my-competitions', label: '我的赛事' },
  { id: 'profile', label: '我的能力' },
  { id: 'plans', label: '备赛计划' },
  { id: 'updates', label: '赛事动态' },
  { id: 'copilot', label: 'Copilot' },
] as const;
type Page = (typeof pages)[number]['id'];
const upcoming: Partial<Record<Page, string>> = {
  competitions: '未来在这里浏览经过核验的赛事、届次和赛道。当前可在 Copilot 中查询赛事。',
  'my-competitions': '赛事关注与持续状态管理将在后续开放。当前没有在此保存的关注列表。',
  profile: '能力画像页面将在后续开放。当前可在 Copilot 中显式提供已有学生上下文。',
  plans: '完整计划工作区将在后续开放。现有计划选择、版本、证据与变更仍在 Copilot 中查看。',
  updates: '赛事动态页面将在后续开放。这里尚未接入持续事件列表，也不代表赛事没有变化。',
};
function pageFromHash(): { page: Page; detailId: string | null } {
  const id = window.location.hash.slice(2);
  if (id.startsWith('competitions/')) {
    try {
      return {
        page: 'competitions',
        detailId: decodeURIComponent(id.slice('competitions/'.length)) || null,
      };
    } catch {
      return { page: 'competitions', detailId: null };
    }
  }
  return { page: pages.find((page) => page.id === id)?.id ?? 'home', detailId: null };
}

export function ProductApp(
  props: Omit<
    ComponentProps<typeof Workspace>,
    'embedded' | 'onSnapshot' | 'contextSelection' | 'externalBusy'
  >,
) {
  const [route, setRoute] = useState(pageFromHash);
  const page = route.page;
  const [session, setSession] = useState<WorkspaceSnapshot | null>(null);
  const [records, setRecords] = useState<ReadRecord[]>([]);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [selection, setSelection] = useState<CompetitionSelection>();
  const scoped = useMemo(
    () =>
      competitionSession(props.client, props.readArtifacts, (record) =>
        setRecords((previous) => [...previous, record]),
      ),
    [props.client, props.readArtifacts],
  );
  const competitions = useMemo(() => competitionsFrom(records), [records]);
  const blocked = !!(session?.pending || session?.interactionPending);
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const changed = () => setRoute(pageFromHash());
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  function navigate(next: Page, detailId: string | null = null) {
    const hash = `#/${next}${next === 'competitions' && detailId ? '/' + encodeURIComponent(detailId) : ''}`;
    if (window.location.hash !== hash) window.history.pushState(null, '', hash);
    setRoute({ page: next, detailId });
    main.current?.focus();
  }
  const title = pages.find((item) => item.id === page)!.label;
  return (
    <CompetitionCatalog value={competitions}>
      <div className="product-app">
        <a
          className="skip-navigation"
          href="#product-content"
          onClick={(event) => {
            event.preventDefault();
            main.current?.focus();
          }}
        >
          跳到主要内容
        </a>
        <header className="product-header">
          <a
            className="brand"
            href="#/home"
            onClick={(event) => {
              event.preventDefault();
              navigate('home');
            }}
          >
            <span className="brand-mark" aria-hidden="true">
              C<span>·</span>C
            </span>
            <span>
              Competition Copilot<small>高校竞赛全生命周期决策与成长平台</small>
            </span>
          </a>
          <div className="product-header-status">
            <span>{session?.context.student_id ? '学生上下文已填写' : '未指定学生'}</span>
            <span className="runtime-badge">{props.runtimeLabel ?? 'FAKE · 演示环境'}</span>
          </div>
        </header>
        <div className="product-layout">
          <nav className="primary-navigation" aria-label="产品导航">
            {pages.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                aria-current={page === item.id ? 'page' : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(item.id);
                }}
              >
                <span>{item.label}</span>
                {page === item.id && (
                  <span className="nav-current-marker" aria-hidden="true">
                    当前
                  </span>
                )}
              </a>
            ))}
            <p>
              当前页面会话
              <br />
              业务判断与审批由后端负责
            </p>
          </nav>
          <main id="product-content" className="product-content" ref={main} tabIndex={-1}>
            {page === 'home' && (
              <Dashboard
                session={session}
                openCopilot={() => navigate('copilot')}
                openCompetition={() =>
                  navigate('competitions', session?.context.competition_id ?? null)
                }
              />
            )}
            {page !== 'home' && page !== 'copilot' && page !== 'competitions' && (
              <section className="coming-soon" aria-labelledby="coming-soon-title">
                <p className="page-kicker">产品体验 · 后续开放</p>
                <h1 id="coming-soon-title">{title}</h1>
                <div className="product-empty">
                  <h2>即将开放</h2>
                  <p>{upcoming[page]}</p>
                  <p>本页暂不提供业务操作，不会生成或保存业务结果。</p>
                  <button type="button" onClick={() => navigate('copilot')}>
                    前往 Copilot
                  </button>
                </div>
              </section>
            )}
            <div hidden={page !== 'competitions'}>
              <CompetitionCenter
                active={page === 'competitions'}
                detailId={route.detailId}
                records={records}
                client={scoped.client}
                context={session?.context ?? {}}
                disabled={blocked}
                onBusy={setCatalogBusy}
                open={(id) => navigate('competitions', id)}
                select={(id, message, target, action) => {
                  if (
                    blocked ||
                    catalogBusy ||
                    !competitions.some((competition) => competition.id === id)
                  )
                    return;
                  setSelection((previous) => ({
                    sequence: (previous?.sequence ?? 0) + 1,
                    competitionId: id,
                    message,
                    action,
                    ...(target ? { editionId: target.editionId, trackId: target.trackId } : {}),
                  }));
                  if (message) navigate('copilot');
                }}
              />
            </div>
            {/* Retain one live workspace: navigation never remounts or invokes it. */}
            <div hidden={page !== 'copilot'}>
              <Workspace
                {...props}
                client={scoped.client}
                readArtifacts={scoped.readArtifacts}
                embedded
                onSnapshot={setSession}
                contextSelection={selection}
                externalBusy={catalogBusy}
              />
            </div>
          </main>
        </div>
      </div>
    </CompetitionCatalog>
  );
}
