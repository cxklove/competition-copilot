import type { AgentRequest, AgentResponse } from '../runtime/generated/contracts.ts';
import type { ClientErrorCode } from '../runtime/client.ts';

// Presentation records only. These are neither AgentState nor trusted workflow state.
export type ConversationEntry = {
  id: string;
  role: 'USER' | 'AGENT' | 'SYSTEM';
  requestId: string;
  content: string;
  response?: AgentResponse;
};
export type ConversationState = {
  entries: ConversationEntry[];
  uiStatus: 'IDLE' | 'SUBMITTING' | 'READY' | 'ERROR';
  active: { attempt: number; requestId: string } | null;
  response: AgentResponse | null;
  error: ClientErrorCode | null;
  retryRequest: AgentRequest | null;
};
export const initialState: ConversationState = {
  entries: [],
  uiStatus: 'IDLE',
  active: null,
  response: null,
  error: null,
  retryRequest: null,
};
export type ConversationAction =
  | { type: 'SUBMIT'; attempt: number; request: AgentRequest; retry: boolean }
  | { type: 'RESOLVE'; attempt: number; response: AgentResponse }
  | { type: 'ERROR'; attempt: number; request: AgentRequest; code: ClientErrorCode };

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  if (action.type === 'SUBMIT') {
    if (state.uiStatus === 'SUBMITTING') return state;
    return {
      ...state,
      entries: action.retry
        ? state.entries
        : [
            ...state.entries,
            {
              id: `user-entry-${action.attempt}`,
              role: 'USER',
              requestId: action.request.request_id,
              content: action.request.user_message,
            },
          ],
      uiStatus: 'SUBMITTING',
      active: { attempt: action.attempt, requestId: action.request.request_id },
      response: null,
      error: null,
      retryRequest: null,
    };
  }
  if (state.active?.attempt !== action.attempt) return state;
  if (action.type === 'RESOLVE') {
    if (action.response.request_id !== state.active.requestId) return state;
    return {
      ...state,
      uiStatus: 'READY',
      active: null,
      response: action.response,
      entries: [
        ...state.entries,
        {
          id: `agent-entry-${action.attempt}`,
          role: 'AGENT',
          requestId: action.response.request_id,
          content: action.response.message,
          response: action.response,
        },
      ],
    };
  }
  return {
    ...state,
    uiStatus: 'ERROR',
    active: null,
    error: action.code,
    retryRequest: action.request,
    entries: [
      ...state.entries,
      {
        id: `status-entry-${action.attempt}`,
        role: 'SYSTEM',
        requestId: action.request.request_id,
        content: '本次请求未完成。',
      },
    ],
  };
}

export function workflowLabel(state: ConversationState): string {
  if (state.uiStatus === 'SUBMITTING') return '正在提交';
  if (state.uiStatus === 'ERROR') return '调用未完成';
  switch (state.response?.outcome) {
    case 'COMPLETED':
      return '已完成';
    case 'NEEDS_CLARIFICATION':
      return '需要补充信息';
    case 'WAITING_FOR_APPROVAL':
      return '等待用户确认';
    case 'FAILED':
      return 'Agent 未完成请求';
    default:
      return '等待开始';
  }
}
