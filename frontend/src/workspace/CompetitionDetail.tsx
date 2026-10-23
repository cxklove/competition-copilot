import { useEffect, useRef, useState } from 'react';
import type { AgentContext } from '../runtime/generated/contracts.ts';
import type { CompetitionDetailProjection } from '../results/generated/artifacts.ts';
import type { InvocationClient } from './useConversation.ts';
import type { ReadRecord } from './competitionSession.ts';
import { detailFacts } from './competitionData.ts';
import { errorDetails } from '../results/ErrorPresentation.tsx';
import type { ErrorDetails } from '../results/ErrorPresentation.tsx';

import { CompetitionDetailView } from './CompetitionDetailView.tsx';
import type { GuidedAction } from './actions.ts';

export type DetailTarget = { editionId?: string; trackId?: string };
export function CompetitionDetail({
  id,
  active,
  records,
  client,
  context,
  disabled,
  onBusy,
  open,
  select,
}: {
  id: string;
  active: boolean;
  records: readonly ReadRecord[];
  client: InvocationClient;
  context: AgentContext;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  open: (id: string | null) => void;
  select: (id: string, message?: string, target?: DetailTarget, action?: GuidedAction) => void;
}) {
  const [target, setTarget] = useState<DetailTarget>({});
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorDetails | null>(null);
  const attempts = useRef(new Set<string>());
  const busy = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const query = {
    competition_id: id,
    ...(target.editionId ? { edition_id: target.editionId } : {}),
    ...(target.trackId ? { track_id: target.trackId } : {}),
  };
  const queryKey = JSON.stringify(query);
  const record = records.findLast((r) =>
    r.artifacts.some(
      (a) =>
        a.model === 'CompetitionDetailProjection' &&
        a.value.query.competition_id === id &&
        (a.value.query.edition_id ?? undefined) === target.editionId &&
        (a.value.query.track_id ?? undefined) === target.trackId,
    ),
  );
  const artifact = record?.artifacts.find((a) => a.model === 'CompetitionDetailProjection');
  const detail: CompetitionDetailProjection | undefined = artifact?.value;
  const facts = detailFacts(records, id, {
    ...context,
    competition_id: id,
    edition_id: target.editionId,
    track_id: target.trackId,
  });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
      onBusy(false);
    };
  }, []);
  async function read() {
    if (busy.current || disabled) return;
    busy.current = true;
    attempts.current.add(queryKey);
    setLoading(true);
    setError(null);
    onBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const result = await client.exchange(
        {
          request: {
            request_id: `detail-${crypto.randomUUID()}`,
            user_message: '查看赛事详情',
            intent: 'GET_COMPETITION_DETAILS',
            context: query,
          },
        },
        { signal: abort.signal },
      );
      if (mounted.current && result.response?.outcome !== 'COMPLETED')
        setError(
          result.response?.error ?? { code: 'DETAIL_READ_FAILED', message: '赛事详情读取未完成。' },
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
    if (active && !detail && !attempts.current.has(queryKey) && !disabled && !loading) void read();
  }, [active, queryKey, detail, disabled, loading]);
  function choose(next: DetailTarget) {
    setTarget(next);
    setError(null);
    select(id, undefined, next);
  }
  return (
    <CompetitionDetailView
      detail={detail}
      facts={facts}
      context={context}
      records={records}
      record={record}
      target={target}
      tab={tab}
      setTab={setTab}
      choose={choose}
      loading={loading}
      disabled={disabled}
      error={error}
      read={read}
      open={open}
      select={select}
    />
  );
}
