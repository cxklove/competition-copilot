import type { AgentIntent } from '../runtime/generated/contracts.ts';

// Operations only. Context, outcomes and authorization remain server-owned.
export const guidedActions = [
  { label: '判断参赛资格', intent: 'CHECK_ELIGIBILITY', message: '判断这个比赛的参赛资格' },
  { label: '查看赛事推荐', intent: 'GET_RECOMMENDATIONS', message: '查看适合我的赛事推荐' },
  { label: '分析技能差距', intent: 'ANALYZE_SKILL_GAP', message: '分析这个比赛的技能差距' },
  { label: '生成备赛计划', intent: 'BUILD_PLAN', message: '为这个比赛生成备赛计划' },
  { label: '调整当前计划', intent: 'REQUEST_PLAN_REVISION', message: '请修订当前选择的计划' },
] as const satisfies readonly { label: string; intent: AgentIntent; message: string }[];

export type GuidedAction = (typeof guidedActions)[number];

export function actionHint(
  action: GuidedAction,
  hasTarget: boolean,
  hasPlan: boolean,
  hasCompetition = hasTarget,
): string {
  if (action.intent === 'REQUEST_PLAN_REVISION' && !hasPlan) return '请先生成或选择一个计划。';
  if (action.intent === 'ANALYZE_SKILL_GAP' && !hasCompetition) return '请先选择比赛。';
  if (action.intent === 'BUILD_PLAN' && !hasTarget) return '请先选择比赛和届次。';
  return '';
}
