import type {
  Competition,
  CompetitionEvent,
  SourceMetadata,
} from '../results/generated/artifacts.ts';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { ReadRecord } from './competitionSession.ts';

export function competitionsFrom(records: readonly ReadRecord[]): Competition[] {
  const found = new Map<string, Competition>();
  for (const record of records)
    for (const artifact of record.artifacts) {
      if (artifact.model === 'ListCompetitionsOutput')
        for (const value of artifact.value.competitions) found.set(value.id, value);
      if (artifact.model === 'CompetitionDetailProjection')
        found.set(artifact.value.competition.id, artifact.value.competition);
      if (artifact.model === 'GetCompetitionOutput')
        found.set(artifact.value.competition.id, artifact.value.competition);
    }
  return [...found.values()];
}
const same = (a?: string | null, b?: string | null) => (a ?? null) === (b ?? null);
export function detailFacts(
  records: readonly ReadRecord[],
  competitionId: string,
  context: AgentContext,
) {
  const scoped = records.filter(
    (record) =>
      record.context.competition_id === competitionId &&
      context.competition_id === competitionId &&
      same(record.context.edition_id, context.edition_id) &&
      same(record.context.track_id, context.track_id),
  );
  const personal = scoped.filter(
    (record) => !!context.student_id && record.context.student_id === context.student_id,
  );
  const eligibility = personal
    .flatMap((r) =>
      r.artifacts.filter(
        (a) =>
          a.model === 'EligibilityDecision' &&
          a.value.competition_id === competitionId &&
          same(a.value.edition_id, context.edition_id) &&
          same(a.value.track_id, context.track_id),
      ),
    )
    .at(-1);
  const skillGap = personal
    .flatMap((r) =>
      r.artifacts.filter(
        (a) =>
          a.model === 'SkillGapDecision' &&
          a.value.target.competition_id === competitionId &&
          same(a.value.target.edition_id, context.edition_id) &&
          same(a.value.target.track_id, context.track_id),
      ),
    )
    .at(-1);
  const requirements = scoped
    .flatMap((r) =>
      r.artifacts.flatMap((a) =>
        a.model === 'SkillGapDecision' &&
        a.value.target.competition_id === competitionId &&
        same(a.value.target.edition_id, context.edition_id) &&
        same(a.value.target.track_id, context.track_id)
          ? [a.value.requirements]
          : [],
      ),
    )
    .at(-1);
  const sources: SourceMetadata[] = [];
  const events: CompetitionEvent[] = [];
  const audit = records.filter((record) =>
    record.artifacts.some(
      (a) =>
        (a.model === 'EligibilityDecision' && a.value.competition_id === competitionId) ||
        (a.model === 'SkillGapDecision' && a.value.target.competition_id === competitionId) ||
        (a.model === 'CompetitionPlan' && a.value.competition_id === competitionId) ||
        (a.model === 'PlanDiff' && a.value.before.competition_id === competitionId) ||
        (a.model === 'GetCompetitionOutput' && a.value.competition.id === competitionId) ||
        (a.model === 'ListCompetitionsOutput' &&
          a.value.competitions.some((c) => c.id === competitionId)),
    ),
  );
  for (const record of audit)
    for (const artifact of record.artifacts) {
      if (artifact.model === 'SourceMetadata') sources.push(artifact.value);
      if (artifact.model === 'Evidence' && artifact.value.source)
        sources.push(artifact.value.source);
      if (
        artifact.model === 'EligibilityDecision' &&
        artifact.value.competition_id === competitionId
      ) {
        for (const evidence of [
          ...(artifact.value.evidence ?? []),
          ...(artifact.value.rule_evaluations ?? []).flatMap((r) => r.evidence),
        ])
          if (evidence.source) sources.push(evidence.source);
      }
      if (
        artifact.model === 'SkillGapDecision' &&
        artifact.value.target.competition_id === competitionId
      ) {
        for (const evidence of [
          ...artifact.value.audit_evidence,
          ...(artifact.value.requirements.requirements ?? []).flatMap((r) => [
            ...r.presence_evidence,
            ...(r.evidence ?? []),
          ]),
        ])
          if (evidence.source) sources.push(evidence.source);
      }
      if (artifact.model === 'PlanDiff' && artifact.value.before.student_id === context.student_id)
        for (const impact of artifact.value.decision.impacts)
          if (
            impact.event.competition_id === competitionId &&
            same(impact.event.edition_id, context.edition_id) &&
            same(impact.event.track_id, context.track_id)
          ) {
            events.push(impact.event);
            sources.push(impact.event.source);
          }
    }
  return {
    eligibility: eligibility?.model === 'EligibilityDecision' ? eligibility.value : undefined,
    skillGap: skillGap?.model === 'SkillGapDecision' ? skillGap.value : undefined,
    skillGapRef: skillGap?.model === 'SkillGapDecision' ? skillGap.ref.ref_id : undefined,
    requirements,
    sources,
    events: [...new Map(events.map((event) => [event.id, event])).values()],
    audit,
  };
}
