import type { SourceMetadata } from './generated/artifacts.ts';
import { SourceLink, isControlledDemo } from './SourceMetadata.tsx';

// Display-only URL groups. Caller retains every original observation in audit.
export function groupSources(values: readonly SourceMetadata[]) {
  const groups = new Map<
    string,
    { latest: SourceMetadata; observations: Map<string, SourceMetadata> }
  >();
  for (const source of values) {
    const group = groups.get(source.source_url) ?? {
      latest: source,
      observations: new Map<string, SourceMetadata>(),
    };
    group.observations.set(JSON.stringify(source), source);
    if (Date.parse(source.observed_at) > Date.parse(group.latest.observed_at))
      group.latest = source;
    groups.set(source.source_url, group);
  }
  return [...groups.values()];
}
export function SourceGroups({
  sources,
  className = 'grouped-source-card',
}: {
  sources: readonly SourceMetadata[];
  className?: string;
}) {
  const groups = groupSources(sources);
  return (
    <>
      {groups.map(({ latest: source, observations }) => (
        <article className={className} key={source.source_url}>
          {isControlledDemo(source.source_url) && (
            <p>模拟赛事变化 / 演示数据，不代表真实官方变化。</p>
          )}
          <h6>{source.source_type === 'official' ? '赛事规则官方来源' : '赛事依据来源'}</h6>
          <dl>
            <dt>来源类型</dt>
            <dd>
              {source.source_type === 'official'
                ? '官方'
                : source.source_type === 'manual'
                  ? '人工记录'
                  : source.source_type}
            </dd>
            <dt>核验状态（最新记录）</dt>
            <dd>
              {source.verification_status === 'verified'
                ? '已核验'
                : source.verification_status === 'pending'
                  ? '待核验'
                  : '核验未通过'}
            </dd>
            <dt>最新观察时间</dt>
            <dd>
              <time dateTime={source.observed_at}>{source.observed_at}</time>
            </dd>
          </dl>
          {observations.size > 1 && (
            <p>历史观察记录 {observations.size} 次；全部原始记录保留在高级审计信息中。</p>
          )}
          <SourceLink url={source.source_url} />
        </article>
      ))}
      {!groups.length && <p>当前结果未提供可展示的来源元数据，不补造来源。</p>}
    </>
  );
}
