import type { SourceMetadata as Source } from './generated/artifacts.ts';

export function safeSourceUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password;
  } catch {
    return false;
  }
}
export function SourceLink({ url }: { url: string }) {
  return safeSourceUrl(url) ? (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {url}
    </a>
  ) : (
    <span>{url}（链接未启用）</span>
  );
}
export function SourceMetadata({ source }: { source: Source }) {
  const status = { verified: '已核验', pending: '待核验', rejected: '核验未通过' }[
    source.verification_status
  ];
  const date = new Date(source.observed_at);
  const display = Number.isNaN(date.valueOf())
    ? source.observed_at
    : date.toLocaleString('zh-CN', { timeZone: 'UTC', hour12: false });
  return (
    <div className="source-metadata">
      <SourceLink url={source.source_url} />
      <dl>
        <div>
          <dt>来源类型</dt>
          <dd>{source.source_type}</dd>
        </div>
        <div>
          <dt>核验状态</dt>
          <dd>
            {status ?? source.verification_status} · {source.verification_status}
          </dd>
        </div>
        <div>
          <dt>观察时间</dt>
          <dd>
            <time dateTime={source.observed_at} title={source.observed_at}>
              {display} UTC
            </time>
          </dd>
        </div>
      </dl>
    </div>
  );
}
