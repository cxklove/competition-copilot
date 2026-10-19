import { RuntimeInvocationClient } from '../runtime/client.ts';
import { FakeRuntimeTransport } from '../runtime/fake.ts';
import type { AgentRequest } from '../runtime/generated/contracts.ts';
import type { InvocationClient } from '../workspace/useConversation.ts';
import fixtures from './fixtures.json' with { type: 'json' };

export type DemoScenario =
  | 'completed'
  | 'negative'
  | 'clarification'
  | 'approval'
  | 'transport_error'
  | 'runtime_error'
  | 'contract_error';

// Composition root only: fixed presets, never input-based intent/business routing.
// Rebinding caller-owned transport identity does not resolve any business reference.
export function createDemoClient(scenario: DemoScenario = 'completed'): InvocationClient {
  return {
    async invoke(request: AgentRequest, options?: { signal?: AbortSignal }) {
      const name =
        scenario === 'negative'
          ? 'ineligible'
          : scenario === 'runtime_error'
            ? 'runtime_error'
            : scenario === 'clarification' || scenario === 'approval'
              ? scenario
              : 'completed';
      const body = structuredClone(fixtures[name]);
      if (body.response) {
        body.response.request_id = request.request_id;
        if (body.response.clarification)
          body.response.clarification.source_request_id = request.request_id;
        if (body.response.approval_request)
          body.response.approval_request.source_request_id = request.request_id;
      }
      const step =
        scenario === 'transport_error'
          ? { error: new Error('DEMO_TRANSPORT_FAILURE') }
          : { body: scenario === 'contract_error' ? { response: { outcome: 'invalid' } } : body };
      const transport = new FakeRuntimeTransport('LOCAL', [step]);
      return new RuntimeInvocationClient(transport, {
        mode: 'LOCAL',
        baseUrl: 'http://localhost:0',
      }).invoke(request, options);
    },
  };
}
