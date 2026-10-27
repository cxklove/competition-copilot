import { Ajv2020 } from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import schemas from './generated/artifacts.json' with { type: 'json' };
import type * as Models from './generated/artifacts.ts';
import type { AgentResponse, ResultReference } from '../runtime/generated/contracts.ts';

type Values = {
  PlanningWorkspaceProjection: Models.PlanningWorkspaceProjection;
  ProfileAnalysesProjection: Models.ProfileAnalysesProjection;
  SkillCatalogProjection: Models.SkillCatalogProjection;
  StudentProfileProjection: Models.StudentProfileProjection;
  ProfileMutationResult: Models.ProfileMutationResult;
  CompetitionDetailProjection: Models.CompetitionDetailProjection;
  EligibilityDecision: Models.EligibilityDecision;
  RecommendationEvaluation: Models.RecommendationEvaluation;
  SkillGapDecision: Models.SkillGapDecision;
  PlanDiff: Models.PlanDiff;
  Evidence: Models.Evidence;
  SourceMetadata: Models.SourceMetadata;
  ListCompetitionsOutput: Models.ListCompetitionsOutput;
  GetCompetitionOutput: Models.GetCompetitionOutput;
  CompetitionPlan: Models.CompetitionPlan;
  RecommendationRankingResult: Models.RecommendationRankingResult;
};
export type LinkedArtifact = {
  [K in keyof Values]: {
    ref: ResultReference;
    model: K;
    value: Values[K];
  };
}[keyof Values];
// Optional readonly hosting projection, NOT an extension of P12 AgentResponse.
// Fake composition supplies presets; Local hosting supplies validated receipt projections.
export type ArtifactReader = (response: AgentResponse) => unknown;
const kinds: Record<keyof Values, string[]> = {
  PlanningWorkspaceProjection: ['TOOL_RESULT'],
  ProfileAnalysesProjection: ['TOOL_RESULT'],
  SkillCatalogProjection: ['TOOL_RESULT'],
  StudentProfileProjection: ['TOOL_RESULT'],
  ProfileMutationResult: ['TOOL_RESULT'],
  CompetitionDetailProjection: ['TOOL_RESULT'],
  EligibilityDecision: ['ELIGIBILITY_RESULT', 'TOOL_RESULT'],
  RecommendationEvaluation: ['RECOMMENDATION_RESULT'],
  SkillGapDecision: ['SKILL_GAP_RESULT', 'TOOL_RESULT'],
  PlanDiff: ['PLAN_DIFF'],
  Evidence: ['EVIDENCE'],
  SourceMetadata: ['SOURCE'],
  ListCompetitionsOutput: ['TOOL_RESULT'],
  GetCompetitionOutput: ['TOOL_RESULT'],
  CompetitionPlan: ['TOOL_RESULT'],
  RecommendationRankingResult: ['TOOL_RESULT'],
};
const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false });
addFormats(ajv);
ajv.addKeyword('discriminator'); // oneOf still validates every supplied branch.
const validators = Object.fromEntries(
  Object.entries(schemas).map(([name, schema]) => [name, ajv.compile(schema)]),
);
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function exact(value: Record<string, unknown>, keys: string[]) {
  return Object.keys(value).length === keys.length && keys.every((key) => key in value);
}
// Read-side original Plan JSON uses the same generated model validator as results.
// This validates presentation data only; it cannot create a PlanReference or digest.
export function parseOriginalPlan(text: string): Models.CompetitionPlan | null {
  try {
    const value: unknown = JSON.parse(text);
    return validators.CompetitionPlan!(value) ? (value as Models.CompetitionPlan) : null;
  } catch {
    return null;
  }
}
export function validateArtifacts(response: AgentResponse, raw?: unknown): LinkedArtifact[] {
  if (raw === undefined || response.outcome !== 'COMPLETED') return [];
  const body: unknown = JSON.parse(JSON.stringify(raw));
  if (
    !record(body) ||
    !exact(body, ['request_id', 'artifacts']) ||
    body.request_id !== response.request_id ||
    !Array.isArray(body.artifacts)
  )
    throw new Error('ARTIFACT_CONTRACT_ERROR');
  const seen = new Set<string>();
  for (const entry of body.artifacts) {
    if (
      !record(entry) ||
      !exact(entry, ['ref', 'model', 'value']) ||
      typeof entry.model !== 'string' ||
      !Object.hasOwn(validators, entry.model) ||
      !record(entry.ref) ||
      !exact(entry.ref, ['kind', 'ref_id']) ||
      !kinds[entry.model as keyof Values].includes(entry.ref.kind as string) ||
      !response.audit?.results?.some(
        (ref) =>
          ref.kind === (entry.ref as Record<string, unknown>).kind &&
          ref.ref_id === (entry.ref as Record<string, unknown>).ref_id,
      ) ||
      !validators[entry.model]!(entry.value)
    )
      throw new Error('ARTIFACT_CONTRACT_ERROR');
    const key = `${entry.ref.kind}:${entry.ref.ref_id}`;
    if (seen.has(key)) throw new Error('ARTIFACT_CONTRACT_ERROR');
    seen.add(key);
  }
  return body.artifacts as LinkedArtifact[];
}
