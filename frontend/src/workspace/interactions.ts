import { RuntimeClientError } from '../runtime/client.ts';
import type { ResumeEnvelope } from '../runtime/client.ts';
import { validateInput } from '../runtime/validation.ts';
import type {
  AgentContext,
  ApprovalDecision,
  ApprovalRequest,
  ClarificationRequest,
  ClarificationValues,
  ContextField,
  PublicRuntimeResult,
} from '../runtime/generated/contracts.ts';

export const clarificationFields: Partial<
  Record<ContextField, { key: keyof ClarificationValues; label: string; json?: boolean }>
> = {
  COMPETITION: { key: 'competition_id', label: '竞赛 ID' },
  EDITION: { key: 'edition_id', label: '届次 ID' },
  TRACK: { key: 'track_id', label: '赛道 ID' },
  STUDENT_PROFILE: { key: 'student', label: '学生画像（JSON）', json: true },
  PLAN: { key: 'plan_ref', label: '方案引用（JSON）', json: true },
  INTENT: { key: 'intent', label: '请求意图' },
  CAPABILITY_INVOCATION: { key: 'invocation', label: '能力调用提案（JSON）', json: true },
  CAPABILITY_ARGUMENTS: { key: 'arguments_json', label: '能力参数 JSON' },
};

// Client-controlled presentation data, never trusted authority/state.
export type PublicInteraction = {
  token: string;
  requestId: string;
  continuationRef: string;
  context?: AgentContext;
} & (
  | { kind: 'CLARIFICATION'; proposal: ClarificationRequest }
  | { kind: 'APPROVAL'; proposal: ApprovalRequest }
);

export function interactionFrom(
  result: PublicRuntimeResult,
  token: string,
  context?: AgentContext,
): PublicInteraction | null {
  const response = result.response;
  if (!response || !result.continuation_ref) return null;
  const shared = {
    token,
    requestId: response.request_id,
    continuationRef: result.continuation_ref,
    ...(context ? { context } : {}),
  };
  if (response.outcome === 'NEEDS_CLARIFICATION' && response.clarification)
    return structuredClone({ ...shared, kind: 'CLARIFICATION', proposal: response.clarification });
  if (response.outcome === 'WAITING_FOR_APPROVAL' && response.approval_request)
    return structuredClone({ ...shared, kind: 'APPROVAL', proposal: response.approval_request });
  return null;
}

export function clarificationEnvelope(
  interaction: PublicInteraction,
  values: ClarificationValues,
  submittedAt: string,
): ResumeEnvelope {
  if (
    interaction.kind !== 'CLARIFICATION' ||
    interaction.proposal.source_request_id !== interaction.requestId
  )
    throw new RuntimeClientError('CONTRACT_ERROR');
  const allowed = interaction.proposal.fields.map((field) => clarificationFields[field]?.key);
  if (
    allowed.some((key) => !key) ||
    Object.keys(values).some((key) => !allowed.includes(key as keyof ClarificationValues))
  )
    throw new RuntimeClientError('CONTRACT_ERROR');
  return checked({
    continuation_ref: interaction.continuationRef,
    clarification: {
      clarification_id: interaction.proposal.clarification_id,
      source_request_id: interaction.requestId,
      values,
      submitted_at: submittedAt,
    },
  });
}

export function approvalEnvelope(
  interaction: PublicInteraction,
  decision: ApprovalDecision,
  submittedAt: string,
): ResumeEnvelope {
  if (
    interaction.kind !== 'APPROVAL' ||
    interaction.proposal.source_request_id !== interaction.requestId ||
    !['APPROVE', 'REJECT'].includes(decision)
  )
    throw new RuntimeClientError('CONTRACT_ERROR');
  // P12 binds the opaque ref + IDs to Plan/version/scope/action at its trusted boundary.
  // No frontend-produced authority or invented echo fields.
  return checked({
    continuation_ref: interaction.continuationRef,
    approval: {
      approval_request_id: interaction.proposal.approval_request_id,
      source_request_id: interaction.requestId,
      decision,
      submitted_at: submittedAt,
    },
  });
}

function checked(envelope: ResumeEnvelope): ResumeEnvelope {
  try {
    return validateInput(structuredClone(envelope)) as ResumeEnvelope;
  } catch {
    throw new RuntimeClientError('CONTRACT_ERROR');
  }
}
