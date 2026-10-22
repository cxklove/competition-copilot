import type { AgentIntent, ContextField } from '../runtime/generated/contracts.ts';

// Labels only: requested fields still come exclusively from ClarificationRequest.
export const clarificationLabels: Partial<Record<ContextField, string>> = {
  COMPETITION: '竞赛 ID',
  EDITION: '届次 ID',
  TRACK: '赛道 ID',
  STUDENT_PROFILE: '学生画像',
  PLAN: '选择计划',
  INTENT: '请求意图',
  CAPABILITY_ARGUMENTS: '高级参数',
  CAPABILITY_INVOCATION: '高级调用信息',
};
export const intentLabels: Record<AgentIntent, string> = {
  DISCOVER_COMPETITIONS: '查找赛事',
  GET_COMPETITION_DETAILS: '查看赛事详情',
  CHECK_ELIGIBILITY: '检查参赛资格',
  GET_RECOMMENDATIONS: '获取赛事推荐',
  ANALYZE_SKILL_GAP: '分析技能差距',
  BUILD_PLAN: '生成备赛计划',
  CHECK_COMPETITION_CHANGES: '查看赛事变化',
  EXPLAIN_REPLANNING: '了解计划调整依据',
  REQUEST_PLAN_REVISION: '申请修订计划',
  APPROVE_PLAN_REVISION: '表达批准决定',
  REJECT_PLAN_REVISION: '表达拒绝决定',
  UNKNOWN: '暂不确定',
};
