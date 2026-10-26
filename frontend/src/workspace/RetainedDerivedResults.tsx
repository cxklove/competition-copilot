import type { AgentContext, AgentResponse } from '../runtime/generated/contracts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import { ResultPanel } from '../results/ResultPanel.tsx';
import { derivedCandidates } from './ProfileFreshness.tsx';
import type { ReadRecord } from './competitionSession.ts';
import { planChoiceKey } from './plans.ts';

// Reuse validated session deliveries. Profile edits never invalidate result bodies.
// Keep the latest successful result of each kind in the current canonical scope.
export function RetainedDerivedResults({
  records,
  context,
  activeResponse,
  readArtifacts,
}: {
  records: readonly ReadRecord[];
  context: AgentContext;
  activeResponse: AgentResponse | null;
  readArtifacts?: ArtifactReader;
}) {
  const candidates = derivedCandidates(records, context);
  const latest = new Map<string, ReadRecord>();
  for (const record of records) {
    if (record.response.outcome !== 'COMPLETED') continue;
    for (const artifact of record.artifacts) {
      const candidate = candidates.find((c) => c.id === artifact.ref.ref_id);
      if (!candidate) continue;
      if (
        candidate.kind === 'CompetitionPlan' &&
        context.plan_ref &&
        (!candidate.planRef || planChoiceKey(candidate.planRef) !== planChoiceKey(context.plan_ref))
      )
        continue;
      latest.set(candidate.kind, record);
    }
  }
  const retained = [...new Set(latest.values())].filter(
    (r) => r.response.request_id !== activeResponse?.request_id,
  );
  if (!retained.length) return null;
  return (
    <section aria-label="已保留的分析结果">
      <h3>已保留的分析结果</h3>
      <p>画像更新不会删除或自动重算已有结论；画像版本状态由服务端读取。</p>
      {retained.map((record) => (
        <ResultPanel
          key={record.response.request_id}
          response={record.response}
          readArtifacts={readArtifacts}
        />
      ))}
    </section>
  );
}
