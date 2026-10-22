import type { AgentContext, AgentResponse } from '../runtime/generated/contracts.ts';
import type { PlanChoice } from './plans.ts';

// Readonly UI projection, never a second workflow or a server current-plan registry.
export type WorkspaceSnapshot = {
  context: AgentContext;
  selectedPlan: { reference: PlanChoice['reference']; status?: string } | null;
  recentResponse: AgentResponse | null;
  pendingApproval: AgentResponse['approval_request'];
  pending: boolean;
  continuationUnconfirmed: boolean;
  interactionPending: boolean;
};
