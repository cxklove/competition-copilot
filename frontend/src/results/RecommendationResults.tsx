import { AddMyCompetitionButton } from '../workspace/MyCompetitions.tsx';
import type { ReactNode } from 'react';
import type {
  Evidence,
  RecommendationEvaluation,
  RecommendationRankingResult,
} from './generated/artifacts.ts';
import { SourceGroups } from './SourceGroups.tsx';

type Labels = { competitionLabel: (id: string) => string; skillLabel: (id: string) => string };
const buckets = { confirmed: '资格已确认', uncertain: '资格尚待确认', blocked: '当前资格受限' };
function evidenceFor(result: RecommendationEvaluation): Evidence[] {
  return [
    ...(result.evidence ?? []),
    ...(result.eligibility_decision.evidence ?? []),
    ...(result.eligibility_decision.rule_evaluations ?? []).flatMap((rule) => rule.evidence),
    ...(result.score_components ?? []).flatMap((part) => part.evidence),
  ];
}

export function CandidateCard({
  result,
  rank,
  competitionLabel,
  skillLabel,
}: Labels & { result: RecommendationEvaluation; rank?: number }) {
  const facts = evidenceFor(result);
  // Only visual duplicates are collapsed. The complete supplied snapshots are
  // retained by the parent's one audit disclosure, including every reference.
  const overlap = result.score_components?.find(
    (part) => part.component_id === 'verified-skill-overlap-v1',
  );
  const matched = overlap?.score === 1;
  const matchedIds = [
    ...new Set(
      overlap?.evidence
        .filter((e) => e.field === 'scoring.matched_skill_id' && typeof e.value === 'string')
        .map((e) => String(e.value)) ?? [],
    ),
  ];
  const profile = new Map<string, { level?: string; selfAssessed?: boolean }>();
  for (const fact of facts) {
    const field = fact.field?.match(/^skills\.(.+)\.(level|self_assessed)$/);
    if (fact.code !== 'PROFILE_SKILL_FACT' || !field) continue;
    const value = profile.get(field[1]) ?? {};
    if (field[2] === 'level' && typeof fact.value === 'string') value.level = fact.value;
    if (field[2] === 'self_assessed' && typeof fact.value === 'boolean')
      value.selfAssessed = fact.value;
    profile.set(field[1], value);
  }
  const status = { eligible: '资格已确认', unknown: '资格尚待确认', ineligible: '当前资格受限' }[
    result.eligibility_decision.status
  ];
  return (
    <article className="recommendation-card">
      <h5>
        {rank != null ? `#${rank} ` : ''}
        {competitionLabel(result.candidate.competition_id)}
      </h5>
      <AddMyCompetitionButton target={result.candidate} />
      <p>资格状态：{status}</p>
      <p>技能匹配：{matched ? '已发现明确技能匹配' : '暂无足够信息评分'}</p>
      <p>
        {matched
          ? '当前已核验技能要求与画像中的明确能力记录存在匹配；这不表示技能等级达标或已确认可参赛。'
          : '当前信息不足以形成明确技能匹配结论，不能据此判断你不具备相关能力。'}
      </p>
      <details className="recommendation-why">
        <summary>查看为什么推荐</summary>
        <ul>
          {matchedIds.map((id) => (
            <li key={id}>当前已核验技能要求中包含“{skillLabel(id)}”，你的画像中有对应能力记录。</li>
          ))}
          {matched && !matchedIds.length && (
            <li>当前已核验的必需技能要求均有对应的非未知画像记录。</li>
          )}
          {!matched && <li>当前尚无足够的技能匹配信息，不将缺少记录解释为能力不足。</li>}
          <li>
            {result.eligibility_decision.status === 'unknown'
              ? '当前资格仍存在未确认信息，因此结果保持“资格尚待确认”。'
              : result.eligibility_decision.status === 'ineligible'
                ? '当前资格受限，需先核对参赛规则。'
                : '资格结论沿用后端已核验结果。'}
          </li>
          {matched && <li>匹配仅覆盖当前已核验技能要求，不代表完整赛事要求或整体适合程度。</li>}
        </ul>
        <h6>个人能力依据</h6>
        {profile.size ? (
          <ul>
            {[...profile].map(([id, fact]) => (
              <li key={id}>
                {skillLabel(id)} ·{' '}
                {fact.level === 'intermediate'
                  ? '中级'
                  : fact.level === 'beginner'
                    ? '初级'
                    : fact.level === 'advanced'
                      ? '高级'
                      : '等级信息未确认'}
                {fact.selfAssessed === true ? ' · 来源：自评' : ' · 来源：画像记录'}
              </li>
            ))}
          </ul>
        ) : (
          <p>当前结果未提供可展示的个人技能明细，不能据此认定缺乏能力。</p>
        )}
      </details>
      <details className="recommendation-sources">
        <summary>查看赛事依据</summary>
        <SourceGroups
          sources={facts.flatMap((fact) => (fact.source ? [fact.source] : []))}
          className="recommendation-source-card"
        />
      </details>
    </article>
  );
}

export function RecommendationPresentation({
  result,
  audit,
  ...labels
}: Labels & { result: RecommendationRankingResult; audit?: ReactNode }) {
  const keys = ['confirmed', 'uncertain', 'blocked'] as const;
  // Keep backend bucket boundaries, entry order and rank. No score sorting.
  const entries = keys.flatMap((bucket) =>
    (result[bucket] ?? []).map((entry) => ({ bucket, entry })),
  );
  function cards(items: typeof entries) {
    return keys.map((bucket) => {
      const selected = items.filter((item) => item.bucket === bucket);
      if (!selected.length) return null;
      return (
        <section key={bucket} aria-label={`${buckets[bucket]}候选`}>
          <ol>
            {selected.map(({ entry }, index) => (
              <li key={index}>
                <CandidateCard
                  result={'evaluation' in entry ? entry.evaluation : entry}
                  rank={'rank' in entry ? entry.rank : undefined}
                  {...labels}
                />
              </li>
            ))}
          </ol>
        </section>
      );
    });
  }
  return (
    <div className="recommendation-results">
      <h3>推荐结果</h3>
      <dl className="recommendation-counts">
        {keys.map((bucket) => (
          <div key={bucket}>
            <dt>{buckets[bucket]}</dt>
            <dd>{result[bucket]?.length ?? 0}</dd>
          </div>
        ))}
      </dl>
      {!!result.uncertain?.length && (
        <p>当前推荐结果中仍存在资格或数据不确定性，“资格尚待确认”不代表已确认可参赛。</p>
      )}
      {cards(entries.slice(0, 5))}
      {entries.length > 5 && (
        <details className="remaining-candidates">
          <summary>查看其余 {entries.length - 5} 个候选</summary>
          {cards(entries.slice(5))}
        </details>
      )}
      <details className="recommendation-audit">
        <summary>查看高级审计信息</summary>
        {audit ?? <pre>{JSON.stringify(result, null, 2)}</pre>}
      </details>
    </div>
  );
}
