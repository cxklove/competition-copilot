import { RuntimeInvocationClient, RuntimeClientError } from '../runtime/client.ts';
import { responseOf } from '../runtime/validation.ts';
import { FakeRuntimeTransport } from '../runtime/fake.ts';
import type {
  AgentArtsInvocationEnvelope,
  AgentRequest,
  PublicRuntimeResult,
} from '../runtime/generated/contracts.ts';
import type { InvocationClient } from '../workspace/useConversation.ts';
import fixtures from './fixtures.json' with { type: 'json' };
import resultFixtures from './result-fixtures.json' with { type: 'json' };
import type { ArtifactReader } from '../results/artifacts.ts';

export type ResultScenario = keyof typeof resultFixtures;
export const readDemoArtifacts: ArtifactReader = (response) => {
  const preset = Object.values(resultFixtures).find((item) =>
    item.runtime.response.audit.results.some((ref) =>
      response.audit?.results?.some(
        (actual) => actual.kind === ref.kind && actual.ref_id === ref.ref_id,
      ),
    ),
  );
  return preset
    ? { ...structuredClone(preset.bundle), request_id: response.request_id }
    : undefined;
};

export type DemoScenario =
  | ResultScenario
  | 'completed'
  | 'negative'
  | 'clarification'
  | 'approval'
  | 'transport_error'
  | 'runtime_error'
  | 'contract_error'
  | 'approval_transport_error'
  | 'approval_contract_error';

// Local preset sequences only, not an authority resolver or a real Runtime adapter.
export function createDemoClient(scenario: DemoScenario = 'completed'): InvocationClient {
  const flows = new Map<string, RuntimeInvocationClient>();
  const config = { mode: 'LOCAL', baseUrl: 'http://localhost:0' } as const;
  async function exchange(
    envelope: AgentArtsInvocationEnvelope,
    options?: { signal?: AbortSignal },
  ): Promise<PublicRuntimeResult> {
    if (!envelope.request) {
      const ref = envelope.continuation_ref;
      const client = ref ? flows.get(ref) : undefined;
      if (!client || !ref) throw new RuntimeClientError('CONTRACT_ERROR');
      flows.delete(ref); // A fake receipt is consumed once, even on failure.
      return client.exchange(envelope, options);
    }
    const id = envelope.request.request_id;
    const name =
      scenario === 'negative'
        ? 'ineligible'
        : scenario === 'runtime_error'
          ? 'runtime_error'
          : scenario === 'clarification'
            ? 'clarification'
            : scenario.startsWith('approval')
              ? 'approval'
              : 'completed';
    const body = structuredClone(
      Object.hasOwn(resultFixtures, scenario)
        ? resultFixtures[scenario as ResultScenario].runtime
        : fixtures[name],
    ) as
      | typeof fixtures.completed
      | typeof fixtures.approval
      | typeof fixtures.clarification
      | typeof fixtures.runtime_error;
    if (body.response) {
      body.response.request_id = id;
      if (body.response.clarification) body.response.clarification.source_request_id = id;
      if (body.response.approval_request) body.response.approval_request.source_request_id = id;
    }
    const ref = `demo-continuation-${id}`;
    if (body.continuation_ref) body.continuation_ref = ref;
    const completed = structuredClone(fixtures.completed);
    completed.response.request_id = id;
    // Fixed receipt for either explicit decision; no decision/rule/diff computation.
    completed.response.message = '演示续接已返回完成结果。该预设场景没有执行任何真实计划修改。';
    const first =
      scenario === 'transport_error'
        ? { error: new Error('DEMO_TRANSPORT_FAILURE') }
        : { body: scenario === 'contract_error' ? { response: { outcome: 'invalid' } } : body };
    const second =
      scenario === 'approval_transport_error'
        ? { error: new Error('DEMO_CONTINUATION_FAILURE') }
        : {
            body:
              scenario === 'approval_contract_error'
                ? { response: { outcome: 'invalid' } }
                : completed,
          };
    const client = new RuntimeInvocationClient(
      new FakeRuntimeTransport('LOCAL', [first, second]),
      config,
    );
    const result = await client.exchange(envelope, options);
    if (result.continuation_ref) flows.set(result.continuation_ref, client);
    return result;
  }
  return {
    exchange,
    async invoke(request: AgentRequest, options?: { signal?: AbortSignal }) {
      return responseOf(await exchange({ request }, options));
    },
  };
}
