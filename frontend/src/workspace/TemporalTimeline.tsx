import type {
  CompetitionDetailProjection,
  TemporalCandidateSnapshot,
  TimeWindow,
} from '../results/generated/artifacts.ts';
import { SourceGroups } from '../results/SourceGroups.tsx';

export function classifyTimelineCandidates(
  verifiedWindow: TimeWindow | null | undefined,
  candidates: readonly TemporalCandidateSnapshot[],
  section: 'registration' | 'competition',
) {
  const mainStartCandidates: TemporalCandidateSnapshot[] = [];
  const mainEndCandidates: TemporalCandidateSnapshot[] = [];
  const sectionCandidates: TemporalCandidateSnapshot[] = [];
  const auditCandidates: TemporalCandidateSnapshot[] = [];
  const hasVerifiedEndpoint = !!(verifiedWindow?.start_at || verifiedWindow?.end_at);
  for (const candidate of candidates) {
    if (candidate.field === `${section}_start`) {
      (verifiedWindow?.start_at ? auditCandidates : mainStartCandidates).push(candidate);
    } else if (candidate.field === `${section}_end`) {
      (verifiedWindow?.end_at ? auditCandidates : mainEndCandidates).push(candidate);
    } else if (candidate.field === section) {
      (hasVerifiedEndpoint ? auditCandidates : sectionCandidates).push(candidate);
    }
  }
  return { mainStartCandidates, mainEndCandidates, sectionCandidates, auditCandidates };
}

export function visibleTemporalCandidates(detail: CompetitionDetailProjection) {
  return (detail.temporal_candidates ?? []).filter(
    (c) =>
      c.verification_status === 'pending' &&
      c.source.source_type === 'official' &&
      c.source.verification_status === 'verified' &&
      c.competition_id === detail.query.competition_id &&
      c.edition_id === detail.query.edition_id &&
      (c.track_id == null || c.track_id === detail.query.track_id),
  );
}

export function TemporalCandidateCards({
  candidates,
  showSource = true,
}: {
  candidates: TemporalCandidateSnapshot[];
  showSource?: boolean;
}) {
  return (
    <div className="temporal-candidates">
      {candidates.map((c) => (
        <article className="detail-section" key={c.candidate_id}>
          <strong>官方已公布 · 待核验</strong>
          <p>{c.track_id ? '当前赛道时间依据' : '届次级时间依据（不代表特定赛道日程）'}</p>
          <blockquote>{c.raw_text}</blockquote>
          <p>
            信息粒度：
            {
              { DATETIME: '日期与时刻', DATE: '日期', MONTH: '月份', TEXT_ONLY: '原文说明' }[
                c.precision
              ]
            }
            {c.relation === 'RANGE' ? ' · 范围' : c.relation === 'BEFORE' ? ' · 之前' : ''}
          </p>
          <p className="panel-note">
            “待核验”表示已保存官方时间原文，尚未形成可用于计划和自动决策的确定时间。
          </p>
          {showSource && <SourceGroups sources={[c.source]} />}
        </article>
      ))}
    </div>
  );
}

export function TemporalTimeline({ detail }: { detail: CompetitionDetailProjection }) {
  if (!detail.selected_edition || !detail.availability.time_windows.requested)
    return <p className="detail-empty">请选择届次后查看时间信息。</p>;
  const candidates = visibleTemporalCandidates(detail);
  const source = detail.selected_edition.source;
  return (
    <section>
      <h2>赛事时间线</h2>
      <p className="panel-note">以下为届次级时间依据；观察时间不是截止时间。</p>
      <ol className="competition-timeline">
        {(['registration', 'competition'] as const).map((family, index) => {
          const window = detail.selected_edition?.[`${family}_window`];
          const verified = source?.verification_status === 'verified';
          const start = verified ? window?.start_at : null;
          const end = verified ? window?.end_at : null;
          const classified = classifyTimelineCandidates(
            verified ? window : null,
            candidates,
            family,
          );
          const full = !!(start && end);
          const partial = !!(start || end) && !full;
          const status = full
            ? '时间已确认'
            : partial
              ? '部分确认'
              : classified.mainStartCandidates.length || classified.mainEndCandidates.length
                ? '官方已公布 · 待核验'
                : classified.sectionCandidates.length
                  ? '官方已公布相关时间信息 · 待核验'
                  : '当前资料中暂未发现可靠时间信息';
          return (
            <li key={family}>
              <span className="timeline-number" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <h3>{family === 'registration' ? '报名阶段' : '比赛阶段'}</h3>
                <span className="availability-chip">{status}</span>
                <div className="timeline-main">
                  {(start ||
                    end ||
                    classified.mainStartCandidates.length > 0 ||
                    classified.mainEndCandidates.length > 0) && (
                    <dl>
                      {(['start', 'end'] as const).map((endpoint) => {
                        const value = endpoint === 'start' ? start : end;
                        const pending =
                          endpoint === 'start'
                            ? classified.mainStartCandidates
                            : classified.mainEndCandidates;
                        return (
                          <div key={endpoint}>
                            <dt>{endpoint === 'start' ? '开始' : '结束'}</dt>
                            <dd>
                              {value ? (
                                <time dateTime={value}>{value}</time>
                              ) : pending.length ? (
                                <TemporalCandidateCards candidates={pending} />
                              ) : (
                                '暂未确认'
                              )}
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                  )}
                  {(start || end) && source && <SourceGroups sources={[source]} />}
                  {classified.sectionCandidates.length > 0 && (
                    <div aria-label="阶段级待核验依据">
                      <TemporalCandidateCards candidates={classified.sectionCandidates} />
                    </div>
                  )}
                </div>
                {classified.auditCandidates.length > 0 && (
                  <details className="temporal-audit">
                    <summary>存在待核验时间依据</summary>
                    <p>以下原文不替代已确认时间。</p>
                    <TemporalCandidateCards candidates={classified.auditCandidates} />
                  </details>
                )}
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
