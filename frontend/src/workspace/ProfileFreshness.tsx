import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { AgentContext, PlanReference } from '../runtime/generated/contracts.ts';
import type { ProfileAnalysis, ProfileAnalysesProjection } from '../results/generated/artifacts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import type { ReadRecord } from './competitionSession.ts';
import type { InvocationClient } from './useConversation.ts';
import { guidedActions } from './actions.ts';
import type { GuidedAction } from './actions.ts';
import { planChoiceKey } from './plans.ts';

const kinds = ['RecommendationRankingResult', 'SkillGapDecision', 'CompetitionPlan'] as const;
type Kind = (typeof kinds)[number];
type Candidate = { id: string; kind: Kind; planRef?: PlanReference };
type FreshnessState = {
  enabled: boolean;
  candidates: Candidate[];
  analyses: ProfileAnalysis[];
  loading: boolean;
  error: boolean;
  rerun?: (action: GuidedAction) => void;
};
export const ProfileFreshnessContext = createContext<FreshnessState>({
  enabled: false,
  candidates: [],
  analyses: [],
  loading: false,
  error: false,
});

// Exact session/target matching precedes freshness. No profile-reference comparison here.
export function derivedCandidates(
  records: readonly ReadRecord[],
  context: AgentContext,
): Candidate[] {
  if (!context.student_id) return [];
  const seen = new Map<string, Candidate>();
  for (const record of records) {
    if (record.context.student_id !== context.student_id) continue;
    for (const artifact of record.artifacts) {
      if (!kinds.includes(artifact.model as Kind)) continue;
      if (artifact.model === 'SkillGapDecision' || artifact.model === 'CompetitionPlan') {
        const target =
          artifact.model === 'SkillGapDecision' ? artifact.value.target : artifact.value;
        if (
          target.competition_id !== context.competition_id ||
          target.edition_id !== context.edition_id ||
          (target.track_id ?? null) !== (context.track_id ?? null)
        )
          continue;
        if (
          artifact.model === 'CompetitionPlan' &&
          artifact.value.student_id !== context.student_id
        )
          continue;
      }
      const planRef =
        artifact.model === 'CompetitionPlan'
          ? record.response.plan_refs?.find(
              (ref) =>
                ref.plan_id === artifact.value.id &&
                ref.version === (artifact.value.version ?? 1) &&
                ref.student_id === artifact.value.student_id &&
                ref.target.competition_id === artifact.value.competition_id &&
                ref.target.edition_id === artifact.value.edition_id &&
                (ref.target.track_id ?? null) === (artifact.value.track_id ?? null),
            )
          : undefined;
      seen.set(artifact.ref.ref_id, {
        id: artifact.ref.ref_id,
        kind: artifact.model as Kind,
        ...(planRef ? { planRef } : {}),
      });
    }
  }
  return [...seen.values()];
}

export function useProfileFreshness(
  records: readonly ReadRecord[],
  context: AgentContext,
  client: InvocationClient,
  reader: ArtifactReader | undefined,
  disabled: boolean,
  viewToken?: string,
): FreshnessState {
  const candidates = derivedCandidates(records, context);
  const profile = records
    .flatMap((r) =>
      r.artifacts.flatMap((a) =>
        a.model === 'StudentProfileProjection'
          ? [a.value]
          : a.model === 'ProfileMutationResult'
            ? [a.value.profile]
            : [],
      ),
    )
    .findLast((p) => p.student_id === context.student_id);
  const key = JSON.stringify([context, candidates, profile?.profile_ref, viewToken]);
  const latest = useRef({ client, reader, context, candidates });
  latest.current = { client, reader, context, candidates };
  const [state, setState] = useState<{
    key: string;
    projection?: ProfileAnalysesProjection;
    loading: boolean;
    error: boolean;
  }>({ key: '', loading: false, error: false });
  useEffect(() => {
    const selected = latest.current;
    if (disabled || !selected.context.student_id || !selected.candidates.length) return;
    let active = true;
    const controller = new AbortController();
    setState({ key, loading: true, error: false });
    void (async () => {
      try {
        const result = await selected.client.exchange(
          {
            request: {
              request_id: `freshness-${crypto.randomUUID()}`,
              user_message: '查看分析所用画像版本',
              intent: 'GET_PROFILE_ANALYSES',
              context: selected.context,
              profile_result_refs: selected.candidates.map((c) => c.id),
            },
          },
          { signal: controller.signal },
        );
        if (result.response?.outcome !== 'COMPLETED') throw new Error('FRESHNESS_UNAVAILABLE');
        const projection = validateArtifacts(
          result.response,
          selected.reader?.(result.response),
        ).find((a) => a.model === 'ProfileAnalysesProjection');
        if (
          projection?.model !== 'ProfileAnalysesProjection' ||
          projection.value.student_id !== selected.context.student_id
        )
          throw new Error('FRESHNESS_IDENTITY_MISMATCH');
        if (active) setState({ key, projection: projection.value, loading: false, error: false });
      } catch {
        if (active) setState({ key, loading: false, error: true });
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [key, disabled]);
  return {
    enabled: true,
    candidates,
    analyses: state.key === key ? (state.projection?.analyses ?? []) : [],
    loading: state.key === key && state.loading,
    error: state.key === key && state.error,
  };
}

const labels = {
  CURRENT: '基于当前画像',
  STALE: '基于较早画像',
  UNKNOWN: '画像版本未记录，无法确认',
};
export function ProfileFreshnessBadge({ identity }: { identity: string }) {
  const state = useContext(ProfileFreshnessContext);
  const analysis = state.analyses.find((a) => a.result_ref_id === identity);
  return (
    <aside
      className={`profile-freshness freshness-${analysis?.profile_freshness.status.toLowerCase() ?? 'unknown'}`}
    >
      <span>
        {analysis
          ? labels[analysis.profile_freshness.status]
          : state.loading
            ? '正在读取画像版本状态…'
            : '无法确认画像版本状态'}
      </span>
      {analysis?.profile_freshness.status === 'STALE' && (
        <p>画像已更新，原结果仍保留生成时的结论；重新分析须由你明确发起。</p>
      )}
      {analysis && (
        <details>
          <summary>查看画像版本审计</summary>
          <pre>{JSON.stringify(analysis.profile_freshness, null, 2)}</pre>
        </details>
      )}
    </aside>
  );
}

export function ProfileAnalyses({
  context,
  disabled,
  openCopilot,
}: {
  context: AgentContext;
  disabled: boolean;
  openCopilot: () => void;
}) {
  const state = useContext(ProfileFreshnessContext);
  const titles = ['赛事推荐', '技能差距', '当前计划'];
  const actions = [guidedActions[1], guidedActions[2], guidedActions[3]];
  return (
    <div className="profile-analyses">
      {state.error && <p>无法确认画像版本状态。已有结果仍可查看。</p>}
      {kinds.map((kind, index) => {
        const candidate = state.candidates.findLast(
          (c) =>
            c.kind === kind &&
            (kind !== 'CompetitionPlan' ||
              (c.planRef &&
                context.plan_ref &&
                planChoiceKey(c.planRef) === planChoiceKey(context.plan_ref)) ||
              state.analyses.some(
                (a) =>
                  a.result_ref_id === c.id &&
                  a.binding?.plan_ref &&
                  context.plan_ref &&
                  planChoiceKey(a.binding.plan_ref) === planChoiceKey(context.plan_ref),
              )),
        );
        return (
          <section key={kind} className="analysis-summary">
            <h3>{titles[index]}</h3>
            {candidate ? (
              <>
                <ProfileFreshnessBadge identity={candidate.id} />
                <button onClick={openCopilot}>查看{titles[index]}</button>
              </>
            ) : (
              <p>
                {kind === 'CompetitionPlan'
                  ? '尚未选择具有当前范围结果的计划'
                  : '尚无当前学生与范围匹配的分析结果'}
              </p>
            )}
            <button
              disabled={
                disabled ||
                !context.student_id ||
                (index > 0 && (!context.competition_id || !context.edition_id))
              }
              onClick={() => state.rerun?.(actions[index]!)}
            >
              {
                [
                  candidate ? '根据当前画像重新推荐' : '根据当前画像推荐赛事',
                  '重新分析技能差距',
                  '重新生成计划',
                ][index]
              }
            </button>
          </section>
        );
      })}
      <p>画像变化不会自动重算或调整计划；重新生成计划使用正式规划流程，不等于赛事事件重规划。</p>
    </div>
  );
}

export function DerivedResultFreshness({
  identity,
  children,
}: {
  identity: string;
  children: ReactNode;
}) {
  const state = useContext(ProfileFreshnessContext);
  if (state.enabled && !state.candidates.some((c) => c.id === identity))
    return <p>该结果不属于当前学生或所选赛事范围。</p>;
  return (
    <>
      {state.enabled && <ProfileFreshnessBadge identity={identity} />}
      {children}
    </>
  );
}
