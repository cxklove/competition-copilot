import { useState } from 'react';
import type {
  CompetitionDetailProjection,
  DetailSectionAvailability,
  SourceMetadata,
  TimeWindow,
} from '../results/generated/artifacts.ts';
import type { ReadRecord } from './competitionSession.ts';
import { SourceGroups, groupSources } from '../results/SourceGroups.tsx';

export const detailSections = [
  ['competition', '赛事信息'],
  ['editions', '届次记录'],
  ['tracks', '赛道记录'],
  ['time_windows', '时间节点'],
  ['eligibility_policy', '资格规则'],
  ['skill_requirements', '技能要求'],
  ['provenance', '来源依据'],
] as const;

// Display-only labels. Coverage is read from the producer, never calculated here.
export function availabilityLabel(section: DetailSectionAvailability, coverage?: string) {
  if (!section.requested) return '尚未选择对应范围';
  if (section.state === 'known_value') {
    if (coverage === 'partial') return '部分数据已审核';
    if (coverage === 'missing') return '当前暂无可读取数据';
    return '已有数据';
  }
  if (section.state === 'known_absent') return '后端已记录为空';
  if (['NO_EXACT_POLICY', 'NO_EXACT_ARTIFACT'].includes(section.reason ?? ''))
    return '暂无精确范围数据';
  return '尚未确认';
}

export function cachedDetail(
  records: readonly ReadRecord[],
  id: string,
  exact?: { editionId?: string; trackId?: string },
) {
  return records
    .flatMap((r) => r.artifacts)
    .filter((a) => a.model === 'CompetitionDetailProjection')
    .map((a) => a.value)
    .findLast(
      (p) =>
        p.query.competition_id === id &&
        (exact === undefined ||
          ((p.query.edition_id ?? undefined) === exact.editionId &&
            (p.query.track_id ?? undefined) === exact.trackId)),
    );
}

export function DataAvailabilitySummary({
  detail,
  compact = false,
}: {
  detail?: CompetitionDetailProjection;
  compact?: boolean;
}) {
  if (!detail)
    return (
      <div className="availability-summary is-unread">
        <strong>赛事基本信息已读取</strong>
        <p>展开详情可读取届次、来源与各范围资料。</p>
      </div>
    );
  const known = detailSections.filter(
    ([key]) =>
      detail.availability[key].requested && detail.availability[key].state === 'known_value',
  ).length;
  const rows = (
    <dl className="availability-grid">
      {detailSections.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>
            <span className="availability-chip" data-state={detail.availability[key].state}>
              {availabilityLabel(
                detail.availability[key],
                key === 'eligibility_policy'
                  ? detail.eligibility_policy?.coverage
                  : key === 'skill_requirements'
                    ? detail.skill_requirements?.requirement_set.coverage
                    : undefined,
              )}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
  return (
    <section
      className={`availability-summary ${compact ? 'is-compact' : ''}`}
      aria-label="数据完整性"
    >
      <strong>已读取 {known} 类资料</strong>
      <p className="panel-note">仅描述当前范围的资料可用性，不表示资格或适合程度。</p>
      {compact ? (
        <details>
          <summary>查看资料状态</summary>
          {rows}
        </details>
      ) : (
        rows
      )}
    </section>
  );
}

export function verificationLabel(source?: SourceMetadata | null) {
  return source
    ? { verified: '已核验', pending: '待核验', rejected: '核验未通过' }[source.verification_status]
    : '尚未提供核验记录';
}

export function SourceStatus({
  sources,
  label,
}: {
  sources: readonly SourceMetadata[];
  label: string;
}) {
  const groups = groupSources(sources);
  return (
    <div className="source-status">
      <strong>{label}</strong>
      {groups.length ? (
        groups.map(({ latest }) => (
          <p key={latest.source_url}>
            <span className="semantic-chip">{verificationLabel(latest)}</span> · 最近观察：
            <time dateTime={latest.observed_at}>{latest.observed_at}</time>
          </p>
        ))
      ) : (
        <p>尚未提供该范围的来源核验记录</p>
      )}
    </div>
  );
}

export function windowSummary(window?: TimeWindow | null) {
  if (window?.start_at && window.end_at) return '开始与结束时间已记录';
  if (window?.start_at) return '仅开始时间已确认';
  if (window?.end_at) return '仅结束时间已确认';
  return '时间暂未确认';
}

export function CompetitionTimeline({ detail }: { detail: CompetitionDetailProjection }) {
  return (
    <section>
      <h2>赛事时间线</h2>
      <p className="panel-note">以下仅使用当前届次的正式时间记录；观察时间不是截止时间。</p>
      <ol className="competition-timeline">
        {(['registration_window', 'competition_window'] as const).map((field, index) => {
          const window = detail.selected_edition?.[field];
          return (
            <li key={field}>
              <span className="timeline-number" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <h3>{field === 'registration_window' ? '报名阶段' : '比赛阶段'}</h3>
                <span className="availability-chip">{windowSummary(window)}</span>
                <dl>
                  <div>
                    <dt>开始</dt>
                    <dd>
                      {window?.start_at ? (
                        <time dateTime={window.start_at}>{window.start_at}</time>
                      ) : (
                        '时间暂未确认'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>结束</dt>
                    <dd>
                      {window?.end_at ? (
                        <time dateTime={window.end_at}>{window.end_at}</time>
                      ) : (
                        '时间暂未确认'
                      )}
                    </dd>
                  </div>
                </dl>
              </div>
            </li>
          );
        })}
      </ol>
      <p className="panel-note">
        <span>提交时间：暂未提供</span>。系统不会自动推断日期。
      </p>
    </section>
  );
}

type Association = { section: string; scope: string; fields: string[]; source: SourceMetadata };
const evidenceSections = {
  competition: '赛事来源',
  edition: '届次来源',
  track: '赛道来源',
  eligibility_policy: '资格规则来源',
  skill_requirements: '技能要求来源',
  time_windows: '时间依据',
} as const;
const temporalFields = {
  registration_start: '报名开始',
  registration_end: '报名结束',
  competition_start: '比赛开始',
  competition_end: '比赛结束',
} as const;

export function evidenceAssociations(detail: CompetitionDetailProjection): Association[] {
  const editionName = (id: string) => detail.editions.find((e) => e.id === id)?.name ?? '届次记录';
  const rows: Association[] = detail.provenance.map((p) => ({
    section: p.section,
    source: p.source,
    scope:
      p.section === 'competition'
        ? `赛事层级 · ${detail.competition.name}`
        : p.section === 'track'
          ? `赛道层级 · ${editionName(p.edition_id)} / ${(detail.tracks ?? []).find((t) => t.id === p.track_id)?.name ?? '赛道名称尚未读取'}`
          : `届次层级 · ${editionName(p.edition_id)}`,
    fields: (p.temporal ?? []).map(
      (t) =>
        `${temporalFields[t.field]} · ${t.timezone_name} · ${t.timezone_basis === 'source_explicit' ? '来源明确时区' : '按审核辖区时区'} · ${t.precision === 'minute' ? '分钟精度' : '秒精度'}`,
    ),
  }));
  const scope = detail.selected_track
    ? `赛道层级 · ${detail.selected_edition?.name} / ${detail.selected_track.name}`
    : `届次层级 · ${detail.selected_edition?.name ?? '尚未选择'}`;
  if (detail.eligibility_policy) {
    rows.push({
      section: 'eligibility_policy',
      scope,
      source: detail.eligibility_policy.source,
      fields: ['当前政策覆盖声明'],
    });
    for (const c of detail.eligibility_policy.constraints ?? [])
      rows.push({
        section: 'eligibility_policy',
        scope: `${c.scope === 'competition' ? '赛事' : c.scope === 'edition' ? '届次' : '赛道'}层级约束 · ${scope}`,
        source: c.source,
        fields: [c.evidence_text],
      });
  }
  for (const r of detail.skill_requirements?.requirement_set.requirements ?? [])
    for (const e of [...r.presence_evidence, ...(r.evidence ?? [])])
      if (e.source)
        rows.push({
          section: 'skill_requirements',
          scope,
          source: e.source,
          fields: [
            detail.skill_requirements?.skills.find((s) => s.id === r.skill_id)?.name ??
              '技能要求记录',
            e.message,
          ],
        });
  return rows;
}

export function CompetitionEvidenceCenter({ detail }: { detail: CompetitionDetailProjection }) {
  const [filter, setFilter] = useState('all');
  const rows = evidenceAssociations(detail).filter((r) => filter === 'all' || r.section === filter);
  const groups = new Map<string, Association[]>();
  for (const row of rows)
    groups.set(row.source.source_url, [...(groups.get(row.source.source_url) ?? []), row]);
  return (
    <section className="competition-evidence">
      <h2>证据中心</h2>
      <p>来源按 URL 聚合；每项仍保留原始关联范围，不将届次来源升级为赛道核验。</p>
      <label>
        来源范围
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">全部来源范围</option>
          {Object.entries(evidenceSections).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {[...groups].map(([url, entries]) => (
        <article className="evidence-association" key={url}>
          <ul className="evidence-scopes">
            {[
              ...new Set(
                entries.map(
                  (r) =>
                    `${evidenceSections[r.section as keyof typeof evidenceSections]} · ${r.scope} · ${verificationLabel(r.source)} · 观察时间：${r.source.observed_at}`,
                ),
              ),
            ].map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
          <SourceGroups sources={entries.map((r) => r.source)} />
          {entries.some((r) => r.fields.length) && (
            <details>
              <summary>查看关联字段与解释</summary>
              <ul>
                {[...new Set(entries.flatMap((r) => r.fields))].map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </details>
          )}
        </article>
      ))}
      {!groups.size && (
        <p className="detail-empty">
          暂无来源元数据。当前范围没有来源记录，官网链接不能代替来源核验。
        </p>
      )}
      {detail.skill_requirements && (
        <details>
          <summary>查看需求审核记录</summary>
          <dl>
            <dt>Requirements Version</dt>
            <dd>{detail.skill_requirements.requirement_version}</dd>
            <dt>Review Note</dt>
            <dd>{detail.skill_requirements.review_note}</dd>
            <dt>Coverage</dt>
            <dd>{detail.skill_requirements.requirement_set.coverage}</dd>
          </dl>
        </details>
      )}
    </section>
  );
}
