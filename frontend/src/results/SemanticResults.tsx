import type { ReactNode } from 'react';
import { useCompetitionName } from './competitionNames.tsx';
import { CandidateCard, RecommendationPresentation } from './RecommendationResults.tsx';
import type {
  CompetitionPlan,
  RecommendationEvaluation,
  RecommendationRankingResult,
  SkillGapDecision,
} from './generated/artifacts.ts';
import { SkillGapPresentation, PlanPresentation } from './SkillPlanResults.tsx';

const skills: Record<string, string> = {
  'mathematical-modeling': '数学建模',
  'machine-learning-modeling': '机器学习建模',
};
const levels: Record<string, string> = {
  intermediate: '中级',
  beginner: '初级',
  advanced: '高级',
  unknown: '未知',
};
export const skillName = (id: string) => label(skills, id);
export const planStatus = (status?: string) =>
  ({
    draft: '草案',
    active: '执行中',
    cancelled: '已取消',
    completed: '已完成',
    superseded: '已替代',
  })[status ?? 'draft'] ?? status;
function label(values: Record<string, string>, id: string) {
  return Object.hasOwn(values, id) ? values[id] : id;
}
export function RawDetails({ value }: { value: unknown }) {
  return (
    <details className="audit-details">
      <summary>高级详情</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function RecommendationCard({
  result,
  rank,
}: {
  result: RecommendationEvaluation;
  rank?: number;
}) {
  const competitionLabel = useCompetitionName();
  return (
    <CandidateCard
      result={result}
      rank={rank}
      competitionLabel={competitionLabel}
      skillLabel={(id) => label(skills, id)}
    />
  );
}
export function RecommendationResults({
  result,
  audit,
}: {
  result: RecommendationRankingResult;
  audit?: ReactNode;
}) {
  const competitionLabel = useCompetitionName();
  return (
    <RecommendationPresentation
      result={result}
      audit={audit}
      competitionLabel={competitionLabel}
      skillLabel={(id) => label(skills, id)}
    />
  );
}
export function SkillGapResults({
  result,
  audit,
}: {
  result: SkillGapDecision;
  audit?: ReactNode;
}) {
  return (
    <SkillGapPresentation
      result={result}
      audit={audit}
      skillLabel={(id) => label(skills, id)}
      levelLabel={(id) => label(levels, id)}
    />
  );
}
export function PlanTimeline({ plan, audit }: { plan: CompetitionPlan; audit?: ReactNode }) {
  const competitionLabel = useCompetitionName();
  return (
    <PlanPresentation
      plan={plan}
      audit={audit}
      competitionLabel={competitionLabel}
      skillLabel={(id) => label(skills, id)}
      statusLabel={planStatus}
    />
  );
}
