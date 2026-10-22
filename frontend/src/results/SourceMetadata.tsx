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
  const demo = isControlledDemo(source.source_url);
  const status = { verified: '已核验', pending: '待核验', rejected: '核验未通过' }[
    source.verification_status
  ];
  const date = new Date(source.observed_at);
  const display = Number.isNaN(date.valueOf())
    ? source.observed_at
    : date.toLocaleString('zh-CN', { timeZone: 'UTC', hour12: false });
  return (
    <details className="source-metadata">
      <summary>
        {demo
          ? '模拟赛事变化 / 演示数据 · 查看演示来源'
          : source.source_type === 'official'
            ? '查看官方来源'
            : '查看来源'}
      </summary>
      {demo && <p>模拟赛事变化 / 演示数据，并非真实官方变化。</p>}
      <SourceLink url={source.source_url} />
      <dl>
        <div>
          <dt>来源类型</dt>
          <dd>
            {source.source_type === 'official'
              ? '官方'
              : source.source_type === 'manual'
                ? '人工记录'
                : '来源记录'}{' '}
            · <code>{source.source_type}</code>
          </dd>
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
    </details>
  );
}

export function isControlledDemo(value: string): boolean {
  try {
    const url = new URL(value);
    return url.hostname === 'example.invalid' && url.pathname.includes('/controlled-demo/');
  } catch {
    return false;
  }
}
