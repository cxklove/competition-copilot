import type { PlanReference } from '../runtime/generated/contracts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import { MyCompetitionsProvider, MyCompetitionsPage, targetKey } from './MyCompetitions.tsx';
import type { MyCompetitionProjection } from '../results/generated/artifacts.ts';
import { guidedActions } from './actions.ts';
import {
  ProfileFreshnessContext,
  ProfileAnalyses,
  useProfileFreshness,
} from './ProfileFreshness.tsx';
import type { GuidedAction } from './actions.ts';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentProps } from 'react';
import { Workspace } from './Workspace.tsx';
import { ProfilePage } from './ProfilePage.tsx';
import { Dashboard } from './Dashboard.tsx';
import type { WorkspaceSnapshot } from './sessionPresentation.ts';
import { CompetitionCenter } from './CompetitionCenter.tsx';
import type { CompetitionSelection } from './CompetitionCenter.tsx';
import { competitionSession } from './competitionSession.ts';
import type { ReadRecord } from './competitionSession.ts';
import { competitionNamesFrom, competitionsFrom } from './competitionData.ts';
import { CompetitionCatalog } from '../results/competitionNames.tsx';
import { useRecommendationNames } from './useRecommendationNames.ts';
import { PlanningWorkspace } from './PlanningWorkspace.tsx';

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
    'embedded' | 'onSnapshot' | 'contextSelection' | 'externalBusy' | 'renderPlanningWorkspace'
  >,
) {
  const [route, setRoute] = useState(pageFromHash);
  const page = route.page;
  const [session, setSession] = useState<WorkspaceSnapshot | null>(null);
  const [records, setRecords] = useState<ReadRecord[]>([]);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [planSelectionError, setPlanSelectionError] = useState(false);
  const [selection, setSelection] = useState<CompetitionSelection>();
  const scoped = useMemo(
    () =>
      competitionSession(props.client, props.readArtifacts, (record) =>
        setRecords((previous) => [...previous, record]),
      ),
    [props.client, props.readArtifacts],
  );
  const competitions = useMemo(() => competitionsFrom(records), [records]);
  const competitionNames = useMemo(() => competitionNamesFrom(records), [records]);
  useRecommendationNames(records, scoped.client);
  const blocked = !!(session?.pending || session?.interactionPending);
  const main = useRef<HTMLElement>(null);
  const currentContext = session?.context ?? {};
  const profileToken = JSON.stringify(
    records
      .flatMap((r) =>
        r.artifacts.flatMap((a) =>
          a.model === 'ProfileMutationResult'
            ? [a.value.profile.profile_ref]
            : a.model === 'StudentProfileProjection'
              ? [a.value.profile_ref]
              : [],
        ),
      )
      .findLast((r) => r.student_id === currentContext.student_id),
  );
  const freshness = useProfileFreshness(
    records,
    currentContext,
    scoped.client,
    scoped.readArtifacts,
    blocked,
    page,
  );
  function rerun(action: GuidedAction) {
    if (blocked || catalogBusy || !currentContext.student_id) return;
    if (
      action.intent !== 'GET_RECOMMENDATIONS' &&
      (!currentContext.competition_id || !currentContext.edition_id)
    )
      return;
    setSelection((previous) => ({
      sequence: (previous?.sequence ?? 0) + 1,
      competitionId: currentContext.competition_id ?? '',
      editionId: currentContext.edition_id ?? undefined,
      trackId: currentContext.track_id ?? undefined,
      action,
      message: action.label,
    }));
    navigate('copilot');
  }
  const myToken = JSON.stringify(
    records
      .filter(
        (r) =>
          [
            'CHECK_ELIGIBILITY',
            'ANALYZE_SKILL_GAP',
            'BUILD_PLAN',
            'SELECT_MY_COMPETITION_PLAN',
            'UPDATE_PROFILE',
            'ADD_PROFILE_SKILL',
            'UPDATE_PROFILE_SKILL',
            'REMOVE_PROFILE_SKILL',
          ].includes(r.response.intent) && r.response.outcome === 'COMPLETED',
      )
      .map((r) => r.response.audit),
  );
  async function selectExistingPlan(reference: PlanReference) {
    if (blocked || catalogBusy || reference.student_id !== currentContext.student_id) return;
    setPlanSelectionError(false);
    try {
      const result = await scoped.client.exchange({
        request: {
          request_id: `select-plan-${crypto.randomUUID()}`,
          intent: 'SELECT_MY_COMPETITION_PLAN',
          user_message: 'Select exact Plan reference',
          context: { student_id: reference.student_id, ...reference.target, plan_ref: reference },
        },
      });
      if (result.response?.outcome !== 'COMPLETED') throw new Error('PLAN_SELECTION_UNAVAILABLE');
      const artifact = validateArtifacts(
        result.response,
        scoped.readArtifacts(result.response),
      ).find((a) => a.model === 'MyPlanSelectionResult');
      if (
        artifact?.model !== 'MyPlanSelectionResult' ||
        artifact.value.selected.student_id !== reference.student_id ||
        artifact.value.selected.kind !== 'PLAN_REFERENCE' ||
        targetKey(artifact.value.selected.target) !== targetKey(reference.target)
      )
        throw new Error('PLAN_SELECTION_IDENTITY_MISMATCH');
    } catch {
      setPlanSelectionError(true);
    }
  }
  function selectMy(item: MyCompetitionProjection, action?: GuidedAction, includePlan = true) {
    if (blocked || catalogBusy) return;
    setSelection((previous) => ({
      sequence: (previous?.sequence ?? 0) + 1,
      competitionId: item.target.competition_id,
      editionId: item.target.edition_id,
      trackId: item.target.track_id ?? undefined,
      ...(includePlan
        ? {
            planRef: item.plan_summary.plan_ref ?? null,
            planStatus: item.plan_summary.status ?? undefined,
          }
        : {}),
      action,
    }));
  }
  function nextMy(item: MyCompetitionProjection) {
    const kind = item.next_action.kind;
    if (kind === 'PROFILE') {
      navigate('profile');
      return;
    }
    if (kind === 'DETAIL') {
      navigate('competitions', item.target.competition_id);
      return;
    }
    if (kind === 'WORKSPACE') {
      selectMy(item);
      navigate('plans');
      return;
    }
    const intent = {
      ELIGIBILITY: 'CHECK_ELIGIBILITY',
      SKILL_GAP: 'ANALYZE_SKILL_GAP',
      PLAN: 'BUILD_PLAN',
    }[kind as 'ELIGIBILITY' | 'SKILL_GAP' | 'PLAN'];
    const action = guidedActions.find((a) => a.intent === intent);
    if (action) {
      selectMy(item, action);
      navigate('copilot');
    }
  }
  const relatedAnalyses = (
    <ProfileAnalyses
      context={currentContext}
      disabled={blocked || catalogBusy}
      openCopilot={() => navigate('copilot')}
    />
  );
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
    <MyCompetitionsProvider
      context={currentContext}
      client={scoped.client}
      readArtifacts={scoped.readArtifacts}
      disabled={blocked || catalogBusy}
      token={myToken}
      active={
        page === 'my-competitions' ||
        page === 'competitions' ||
        page === 'plans' ||
        records.some((r) =>
          r.artifacts.some(
            (a) =>
              a.model === 'RecommendationRankingResult' ||
              a.model === 'PlanningWorkspaceProjection',
          ),
        )
      }
    >
      <ProfileFreshnessContext.Provider value={{ ...freshness, rerun }}>
        <CompetitionCatalog value={competitionNames}>
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
                {planSelectionError && (
                  <p role="alert">计划关联暂不可用，请重新加载后再选择计划。</p>
                )}
                {currentContext.competition_id && (
                  <p role="status" aria-label="当前赛事范围">
                    当前范围：
                    {competitions.find((item) => item.id === currentContext.competition_id)?.name ??
                      '已选择赛事（名称待读取）'}
                  </p>
                )}
                {page === 'home' && (
                  <Dashboard
                    analyses={relatedAnalyses}
                    session={session}
                    openCopilot={() => navigate('copilot')}
                    openCompetition={() =>
                      navigate('competitions', session?.context.competition_id ?? null)
                    }
                  />
                )}
                {page !== 'home' &&
                  page !== 'copilot' &&
                  page !== 'competitions' &&
                  page !== 'profile' &&
                  page !== 'plans' &&
                  page !== 'my-competitions' && (
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
                <MyCompetitionsPage
                  active={page === 'my-competitions'}
                  setCurrent={(item) => selectMy(item, undefined, false)}
                  detail={(item) => {
                    selectMy(item, undefined, false);
                    navigate('competitions', item.target.competition_id);
                  }}
                  act={nextMy}
                  workspace={(item) => {
                    selectMy(item);
                    navigate('plans');
                  }}
                  browse={() => navigate('competitions')}
                  recommend={() => rerun(guidedActions[1])}
                />
                <PlanningWorkspace
                  active={page === 'plans'}
                  context={currentContext}
                  client={scoped.client}
                  readArtifacts={scoped.readArtifacts}
                  disabled={blocked || catalogBusy}
                  profileToken={profileToken}
                  act={rerun}
                  center={() => navigate('competitions')}
                  detail={() => navigate('competitions', currentContext.competition_id ?? null)}
                  profile={() => navigate('profile')}
                />
                <div hidden={page !== 'profile'}>
                  <ProfilePage
                    analyses={relatedAnalyses}
                    key={session?.context.student_id ?? 'unselected'}
                    active={page === 'profile'}
                    context={session?.context ?? {}}
                    client={scoped.client}
                    readArtifacts={scoped.readArtifacts}
                    disabled={blocked}
                    onBusy={setCatalogBusy}
                    openCopilot={() => navigate('copilot')}
                  />
                </div>
                <div hidden={page !== 'competitions'}>
                  <CompetitionCenter
                    active={page === 'competitions'}
                    detailId={route.detailId}
                    records={records}
                    client={scoped.client}
                    context={session?.context ?? {}}
                    disabled={blocked || catalogBusy}
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
                        editionId: target?.editionId,
                        trackId: target?.trackId,
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
                    onPlanSelection={(reference) => {
                      void selectExistingPlan(reference);
                    }}
                    externalBusy={catalogBusy}
                    resultRecords={records}
                    renderPlanningWorkspace={(context) => (
                      <PlanningWorkspace
                        active={page === 'copilot'}
                        context={context}
                        client={scoped.client}
                        readArtifacts={scoped.readArtifacts}
                        disabled={blocked || catalogBusy}
                        profileToken={profileToken}
                        act={rerun}
                        center={() => navigate('competitions')}
                        detail={() => navigate('competitions', context.competition_id ?? null)}
                        profile={() => navigate('profile')}
                      />
                    )}
                  />
                </div>
              </main>
            </div>
          </div>
        </CompetitionCatalog>
      </ProfileFreshnessContext.Provider>
    </MyCompetitionsProvider>
  );
}
