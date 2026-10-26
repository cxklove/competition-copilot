import { useEffect, useRef } from 'react';
import type { ReadRecord } from './competitionSession.ts';
import type { InvocationClient } from './useConversation.ts';
import { competitionsFrom } from './competitionData.ts';

// P6 returns canonical identities. Resolve labels using the existing authoritative
// read path, independently of profile freshness, ranking and current selection.
export function useRecommendationNames(records: readonly ReadRecord[], client: InvocationClient) {
  const ids = [
    ...new Set(
      records.flatMap((record) =>
        record.artifacts.flatMap((artifact) =>
          artifact.model === 'RecommendationRankingResult'
            ? [
                ...(artifact.value.confirmed ?? []),
                ...(artifact.value.uncertain ?? []),
                ...(artifact.value.blocked ?? []),
              ].map(
                (item) => ('evaluation' in item ? item.evaluation : item).candidate.competition_id,
              )
            : [],
        ),
      ),
    ),
  ].sort();
  const key = JSON.stringify(ids);
  const latest = useRef({ records, client });
  latest.current = { records, client };
  const attempted = useRef(new Set<string>());
  useEffect(() => {
    const selected = latest.current;
    const known = new Set(competitionsFrom(selected.records).map((c) => c.id));
    const missing = (JSON.parse(key) as string[]).filter(
      (id) => !known.has(id) && !attempted.current.has(id),
    );
    let active = true;
    const controller = new AbortController();
    void (async () => {
      // Read sequentially: clients may expose only their last transport attachment.
      for (const id of missing) {
        if (!active) break;
        try {
          await selected.client.exchange(
            {
              request: {
                request_id: `recommendation-name-${crypto.randomUUID()}`,
                user_message: '读取推荐赛事的正式名称',
                intent: 'GET_COMPETITION_DETAILS',
                context: { competition_id: id },
              },
            },
            { signal: controller.signal },
          );
        } catch {
          // A failed name read never changes or discards a recommendation.
          // The shared resolver retains its canonical-ID fallback.
        } finally {
          if (!controller.signal.aborted) attempted.current.add(id);
        }
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [key]);
}
