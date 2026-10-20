import { useEffect, useReducer, useRef } from 'react';
import { RuntimeClientError } from '../runtime/client.ts';
import { validateInput } from '../runtime/validation.ts';
import type { RuntimeInvocationClient, ResumeEnvelope } from '../runtime/client.ts';
import type {
  AgentContext,
  AgentRequest,
  ApprovalDecision,
  ClarificationValues,
} from '../runtime/generated/contracts.ts';
import { conversationReducer, initialState } from './state.ts';
import { approvalEnvelope, clarificationEnvelope, interactionFrom } from './interactions.ts';
import type { PublicInteraction } from './interactions.ts';

export type InvocationClient = Pick<RuntimeInvocationClient, 'invoke' | 'exchange'>;
export type InteractionResult = { accepted: boolean; error?: string };

export function useConversation(
  client: InvocationClient,
  nextRequestId: () => string,
  now: () => string = () => new Date().toISOString(),
) {
  const [state, dispatch] = useReducer(conversationReducer, initialState);
  const pending = useRef(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const current = useRef<PublicInteraction | null>(null);
  const context = useRef<AgentContext | undefined>(undefined);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current++;
      current.current = null;
      controller.current?.abort();
    };
  }, []);

  async function run(
    request: AgentRequest | Pick<AgentRequest, 'request_id'>,
    retry: boolean,
    continuation?: {
      envelope: ResumeEnvelope;
      interaction: PublicInteraction;
      content: string;
      renderKind: 'CLARIFICATION_RESPONSE' | 'APPROVAL_RESPONSE';
    },
  ): Promise<InteractionResult> {
    let freshRequest = 'user_message' in request ? request : undefined;
    if (!continuation && !freshRequest) return { accepted: false, error: '缺少请求内容。' };
    if (pending.current || !mounted.current)
      return { accepted: false, error: '当前请求正在处理或已失效。' };
    pending.current = true;
    current.current = null;
    const attempt = ++generation.current;
    if (freshRequest) {
      try {
        freshRequest = validateInput({ request: freshRequest }).request!;
        request = freshRequest;
      } catch {
        dispatch({ type: 'SUBMIT', attempt, request: freshRequest, retry });
        dispatch({ type: 'ERROR', attempt, request: freshRequest, code: 'CONTRACT_ERROR' });
        pending.current = false;
        return { accepted: false, error: '请检查公开请求的字段与格式。' };
      }
    }
    const abort = new AbortController();
    controller.current = abort;
    if (continuation)
      dispatch({
        type: 'CONTINUE',
        attempt,
        requestId: request.request_id,
        token: continuation.interaction.token,
        content: continuation.content,
        renderKind: continuation.renderKind,
      });
    else {
      context.current = freshRequest!.context;
      dispatch({ type: 'SUBMIT', attempt, request: freshRequest!, retry });
    }
    try {
      const result = await client.exchange(continuation?.envelope ?? { request: freshRequest! }, {
        signal: abort.signal,
      });
      if (mounted.current && generation.current === attempt && result.response) {
        const interaction = interactionFrom(result, `interaction-${attempt}`, context.current);
        current.current = interaction ? structuredClone(interaction) : null;
        dispatch({ type: 'RESOLVE', attempt, response: result.response, interaction });
      }
    } catch (error) {
      if (mounted.current && generation.current === attempt)
        dispatch({
          type: 'ERROR',
          attempt,
          request,
          code: error instanceof RuntimeClientError ? error.code : 'TRANSPORT_ERROR',
          continuation: !!continuation,
        });
    } finally {
      if (generation.current === attempt) pending.current = false;
    }
    return { accepted: true };
  }

  function submit(text: string, studentId: string, explicitContext: AgentContext = {}) {
    if (
      !text.trim() ||
      pending.current ||
      current.current ||
      state.continuationUnconfirmed ||
      state.response?.outcome === 'NEEDS_CLARIFICATION' ||
      state.response?.outcome === 'WAITING_FOR_APPROVAL'
    )
      return Promise.resolve({ accepted: false });
    return run(
      {
        request_id: nextRequestId(),
        user_message: text.trim(),
        context: {
          ...explicitContext,
          ...(studentId.trim() ? { student_id: studentId.trim() } : {}),
        },
      },
      false,
    );
  }
  function retry() {
    return state.retryRequest
      ? run(state.retryRequest, true)
      : Promise.resolve({ accepted: false });
  }
  function startNew() {
    if (pending.current) return;
    current.current = null;
    context.current = undefined;
    generation.current++;
    dispatch({ type: 'NEW_WORKFLOW' });
  }
  function continueWith(
    token: string,
    build: (interaction: PublicInteraction) => ResumeEnvelope,
    content: string,
    renderKind: 'CLARIFICATION_RESPONSE' | 'APPROVAL_RESPONSE',
  ) {
    const interaction = current.current;
    if (
      !interaction ||
      interaction.token !== token ||
      pending.current ||
      !mounted.current ||
      !state.interaction ||
      JSON.stringify(state.interaction) !== JSON.stringify(interaction)
    )
      return Promise.resolve({
        accepted: false,
        error: '这条交互已失效或已提交，请检查当前工作流。',
      });
    let envelope: ResumeEnvelope;
    try {
      envelope = build(interaction);
    } catch {
      return Promise.resolve({ accepted: false, error: '请检查所请求字段的类型、格式和必填值。' });
    }
    // Correlation only: no new AgentRequest is sent with this continuation.
    return run({ request_id: interaction.requestId }, false, {
      envelope,
      interaction,
      content,
      renderKind,
    });
  }
  function clarify(token: string, values: ClarificationValues) {
    return continueWith(
      token,
      (i) => clarificationEnvelope(i, values, now()),
      '已发送补充信息，等待 Runtime 回复。',
      'CLARIFICATION_RESPONSE',
    );
  }
  function decide(token: string, decision: ApprovalDecision) {
    return continueWith(
      token,
      (i) => approvalEnvelope(i, decision, now()),
      decision === 'APPROVE'
        ? '已发送批准意向，等待 Runtime 确认。'
        : '已发送拒绝意向，等待 Runtime 确认。',
      'APPROVAL_RESPONSE',
    );
  }
  return { state, submit, retry, startNew, clarify, decide };
}
