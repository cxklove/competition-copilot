import { useEffect, useRef, useState } from 'react';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { InvocationClient } from './useConversation.ts';
import type { ReadRecord } from './competitionSession.ts';
import { competitionsFrom } from './competitionData.ts';
import { ErrorPresentation, errorDetails } from '../results/ErrorPresentation.tsx';
import type { ErrorDetails } from '../results/ErrorPresentation.tsx';
import { CompetitionDetail } from './CompetitionDetail.tsx';
import type { DetailTarget } from './CompetitionDetail.tsx';

export type CompetitionSelection = {
  sequence: number;
  competitionId: string;
  editionId?: string;
  trackId?: string;
  message?: string;
};
export function CompetitionCenter({
  active,
  detailId,
  records,
  client,
  context,
  disabled,
  onBusy,
  open,
  select,
}: {
  active: boolean;
  detailId: string | null;
  records: readonly ReadRecord[];
  client: InvocationClient;
  context: AgentContext;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  open: (id: string | null) => void;
  select: (id: string, message?: string, target?: DetailTarget) => void;
}) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorDetails | null>(null);
  const attempted = useRef(false);
  const busy = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const values = competitionsFrom(records);
  const hasList = records.some((record) =>
    record.artifacts.some((a) => a.model === 'ListCompetitionsOutput'),
  );
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  async function load() {
    if (busy.current || disabled) return;
    attempted.current = true;
    busy.current = true;
    setLoading(true);
    setError(null);
    onBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      // Existing read workflow, not a new endpoint or direct Tool/Repository call.
      // DISCOVER is not admitted by the public explicit-action mapper yet.
      const result = await client.exchange(
        {
          request: {
            request_id: `catalog-${crypto.randomUUID()}`,
            user_message: 'discovery: 请列出正式赛事库中的现有竞赛。',
            context: {},
          },
        },
        { signal: abort.signal },
      );
      if (mounted.current && (!result.response || result.response.outcome !== 'COMPLETED'))
        setError(
          result.response?.error ?? {
            code: 'READ_NOT_COMPLETED',
            message: '赛事读取未完成，请在 Copilot 中查看或明确请求赛事列表。',
          },
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
    if (active && !detailId && !hasList && !attempted.current && !disabled) void load();
  }, [active, detailId, hasList, disabled]);
  const visible = values.filter(
    (value) =>
      [value.name, value.short_name ?? '']
        .join(' ')
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()) &&
      (filter === 'all' || (filter === 'link' ? !!value.official_url : !value.official_url)),
  );
  if (detailId)
    return (
      <CompetitionDetail
        key={detailId}
        id={detailId}
        active={active}
        records={records}
        client={client}
        context={context}
        disabled={disabled}
        onBusy={onBusy}
        open={open}
        select={select}
      />
    );
  return (
    <div className="competition-center">
      {loading && <p role="status">正在获取赛事数据...</p>}
      {error && (
        <div className="error-surface" role="alert">
          <h2>暂时无法加载赛事信息</h2>
          <ErrorPresentation error={error} />
        </div>
      )}
      {disabled && !hasList && <p>请先完成 Copilot 中当前的请求或交互，再加载赛事信息。</p>}
      {
        <>
          <header className="page-intro">
            <h1>赛事中心</h1>
            <p>发现、比较并了解适合自己的高校竞赛。</p>
          </header>
          <div className="competition-search">
            <label>
              搜索赛事名称
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索已加载的赛事名称或简称"
              />
            </label>
            <label>
              官方网站链接
              <select value={filter} onChange={(event) => setFilter(event.target.value)}>
                <option value="all">全部记录</option>
                <option value="link">已提供链接</option>
                <option value="missing">暂未提供链接</option>
              </select>
            </label>
            <button type="button" disabled={loading || disabled} onClick={() => void load()}>
              {hasList ? '重新加载赛事' : '加载赛事'}
            </button>
          </div>
          <p className="panel-note">
            仅筛选已返回的正式赛事记录。届次、年份、赛道与来源核验筛选尚无完整读取数据，不作推断。
          </p>
          {!visible.length && !loading && (
            <div className="product-empty">
              <h2>{hasList ? '没有搜索结果' : '暂无已加载赛事'}</h2>
              <p>
                {hasList
                  ? '请调整搜索条件；不会根据搜索文字创建赛事。'
                  : '加载赛事后可查看正式记录；没有返回记录不代表赛事库为空。'}
              </p>
            </div>
          )}
          <div className="competition-card-grid">
            {visible.map((value) => (
              <article className="dashboard-card competition-card" key={value.id}>
                <h2>{value.name}</h2>
                {value.short_name && <p>{value.short_name}</p>}
                <span className="semantic-chip">正式赛事记录</span>
                <p>届次信息暂未提供</p>
                <p>赛道信息暂未提供</p>
                <p>时间信息暂未确认</p>
                <p className="panel-note">来源核验状态与观察时间：需读取对应来源记录后确认。</p>
                <button type="button" onClick={() => open(value.id)}>
                  查看详情<span className="sr-only">：{value.name}</span>
                </button>
                <button
                  type="button"
                  disabled={disabled || loading}
                  onClick={() => select(value.id)}
                >
                  设为当前赛事<span className="sr-only">：{value.name}</span>
                </button>
                <details>
                  <summary>高级详情</summary>
                  <pre>{JSON.stringify(value, null, 2)}</pre>
                </details>
              </article>
            ))}
          </div>
        </>
      }
      {!loading && active && !hasList && !error && attempted.current && (
        <p>未取得正式赛事列表结果。可明确点击加载，或在 Copilot 中查询；不自动重试。</p>
      )}
    </div>
  );
}
