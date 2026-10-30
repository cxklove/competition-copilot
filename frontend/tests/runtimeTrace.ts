import assert from 'node:assert/strict';
import type {
  AgentArtsInvocationEnvelope,
  AgentIntent,
  AgentResponse,
  PublicRuntimeResult,
} from '../src/runtime/generated/contracts.ts';

export function responseSnapshotKey(response: AgentResponse) {
  return JSON.stringify([
    response.request_id,
    response.outcome,
    response.audit,
    response.clarification ?? null,
    response.approval_request ?? null,
  ]);
}

type ActionKind = 'READ' | 'MUTATION' | 'BUSINESS' | 'UNRESOLVED';
const actionKinds = {
  GET_MY_COMPETITIONS: 'READ',
  GET_MY_COMPETITION: 'READ',
  ADD_MY_COMPETITION: 'MUTATION',
  UPDATE_MY_COMPETITION: 'MUTATION',
  REMOVE_MY_COMPETITION: 'MUTATION',
  SELECT_MY_COMPETITION_PLAN: 'MUTATION',
  GET_PLANNING_WORKSPACE: 'READ',
  GET_PROFILE_ANALYSES: 'READ',
  GET_PROFILE: 'READ',
  GET_SKILL_CATALOG: 'READ',
  ADD_PROFILE_SKILL: 'MUTATION',
  UPDATE_PROFILE_SKILL: 'MUTATION',
  REMOVE_PROFILE_SKILL: 'MUTATION',
  UPDATE_PROFILE: 'MUTATION',
  DISCOVER_COMPETITIONS: 'READ',
  GET_COMPETITION_DETAILS: 'READ',
  CHECK_ELIGIBILITY: 'BUSINESS',
  GET_RECOMMENDATIONS: 'BUSINESS',
  ANALYZE_SKILL_GAP: 'BUSINESS',
  BUILD_PLAN: 'BUSINESS',
  CHECK_COMPETITION_CHANGES: 'BUSINESS',
  EXPLAIN_REPLANNING: 'READ',
  REQUEST_PLAN_REVISION: 'BUSINESS',
  APPROVE_PLAN_REVISION: 'BUSINESS',
  REJECT_PLAN_REVISION: 'BUSINESS',
  UNKNOWN: 'UNRESOLVED',
} satisfies Record<AgentIntent, ActionKind>;

type RuntimeTrace = {
  calls: readonly AgentArtsInvocationEnvelope[];
  responses: readonly PublicRuntimeResult[];
};

export function runtimeTrace(source: RuntimeTrace) {
  return source.calls.map((call) => {
    const requestId =
      call.request?.request_id ??
      call.clarification?.source_request_id ??
      call.approval?.source_request_id ??
      call.message?.source_request_id;
    const response = source.responses.find((r) => r.response?.request_id === requestId)?.response;
    const intent = call.request?.intent ?? response?.intent ?? 'UNKNOWN';
    return { request_id: requestId, intent, kind: actionKinds[intent], outcome: response?.outcome };
  });
}

export function businessInvocations(source: RuntimeTrace) {
  const trace = runtimeTrace(source);
  assert.equal(
    trace.some((r) => r.kind === 'UNRESOLVED'),
    false,
    `Unclassified request must not be ignored: ${JSON.stringify(trace)}`,
  );
  return trace.filter((r) => r.kind === 'BUSINESS').map((r) => r.intent);
}

export async function waitForResponseByRequestId(
  source: RuntimeTrace,
  requestId: string,
  timeout = 10000,
) {
  const { waitFor } = await import('@testing-library/react');
  let matched: PublicRuntimeResult | undefined;
  await waitFor(
    () => {
      matched = source.responses.find((r) => r.response?.request_id === requestId);
      assert.ok(
        matched,
        `Missing response for request_id=${requestId}\n` +
          `Observed requests: ${JSON.stringify(runtimeTrace(source))}\n` +
          `Observed responses: ${JSON.stringify(
            source.responses.map((r) => ({
              request_id: r.response?.request_id,
              intent: r.response?.intent,
              outcome: r.response?.outcome,
              error: r.error,
            })),
          )}`,
      );
    },
    { timeout },
  );
  return matched!;
}
