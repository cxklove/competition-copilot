import { useEffect, useReducer, useRef } from 'react';
import { RuntimeClientError } from '../runtime/client.ts';
import type { RuntimeInvocationClient } from '../runtime/client.ts';
import type { AgentRequest } from '../runtime/generated/contracts.ts';
import { conversationReducer, initialState } from './state.ts';

export type InvocationClient = Pick<RuntimeInvocationClient, 'invoke'>;

export function useConversation(client: InvocationClient, nextRequestId: () => string) {
  const [state, dispatch] = useReducer(conversationReducer, initialState);
  const pending = useRef(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      controller.current?.abort();
    };
  }, []);

  async function invoke(request: AgentRequest, retry: boolean) {
    // Synchronous lock closes the window before React commits the disabled button.
    if (pending.current || !mounted.current) return false;
    pending.current = true;
    const attempt = ++generation.current;
    const abort = new AbortController();
    controller.current = abort;
    dispatch({ type: 'SUBMIT', attempt, request, retry });
    try {
      const response = await client.invoke(request, { signal: abort.signal });
      if (mounted.current && generation.current === attempt)
        dispatch({ type: 'RESOLVE', attempt, response });
    } catch (error) {
      if (mounted.current && generation.current === attempt)
        dispatch({
          type: 'ERROR',
          attempt,
          request,
          code: error instanceof RuntimeClientError ? error.code : 'TRANSPORT_ERROR',
        });
    } finally {
      if (generation.current === attempt) pending.current = false;
    }
    return true;
  }

  function submit(text: string, studentId: string) {
    if (
      !text.trim() ||
      pending.current ||
      state.response?.outcome === 'NEEDS_CLARIFICATION' ||
      state.response?.outcome === 'WAITING_FOR_APPROVAL'
    )
      return Promise.resolve(false);
    return invoke(
      {
        request_id: nextRequestId(),
        user_message: text.trim(),
        ...(studentId.trim() ? { context: { student_id: studentId.trim() } } : {}),
      },
      false,
    );
  }

  function retry() {
    return state.retryRequest ? invoke(state.retryRequest, true) : Promise.resolve(false);
  }
  return { state, submit, retry };
}
