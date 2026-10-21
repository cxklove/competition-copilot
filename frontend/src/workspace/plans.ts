// Session presentation choices only. Digest/version always come from AgentResponse.
import { validateArtifacts } from '../results/artifacts.ts';
import type { AgentResponse, PlanReference } from '../runtime/generated/contracts.ts';

export type PlanChoice = { reference: PlanReference; status: string };
export const planChoiceKey = (reference: PlanReference) => JSON.stringify(reference);

export function collectPlanChoices(response: AgentResponse, raw: unknown): PlanChoice[] {
  const artifacts = validateArtifacts(response, raw);
  return artifacts.flatMap((artifact): PlanChoice[] => {
    if (artifact.model !== 'CompetitionPlan') return [];
    const plan = artifact.value;
    const matches = (response.plan_refs ?? []).filter(
      (ref) =>
        ref.plan_id === plan.id &&
        ref.student_id === plan.student_id &&
        ref.version === (plan.version ?? 1) &&
        ref.target.competition_id === plan.competition_id &&
        ref.target.edition_id === plan.edition_id &&
        (ref.target.track_id ?? null) === (plan.track_id ?? null) &&
        Date.parse(ref.updated_at) === Date.parse(plan.updated_at) &&
        JSON.stringify([...(ref.milestone_ids ?? [])].sort()) ===
          JSON.stringify((plan.milestones ?? []).map((m) => m.id).sort()),
    );
    if (matches.length !== 1) return [];
    return [{ reference: structuredClone(matches[0]!), status: plan.status ?? 'draft' }];
  });
}
