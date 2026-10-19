import assert from 'node:assert/strict';
import test from 'node:test';
import fixtures from './fixtures/runtime.json' with { type: 'json' };
import { RuntimeClientError, RuntimeInvocationClient } from '../src/runtime/client.ts';
import { FakeRuntimeTransport } from '../src/runtime/fake.ts';
import type {
  AgentRequest,
  AgentArtsInvocationEnvelope,
  PublicRuntimeResult,
} from '../src/runtime/generated/contracts.ts';
import type { RuntimeMode, RuntimeConfig } from '../src/runtime/transport.ts';

const request = fixtures.request as AgentRequest;
const copy = <T>(value: T): T => structuredClone(value);
const config = (mode: RuntimeMode): RuntimeConfig =>
  mode === 'LOCAL'
    ? { mode, baseUrl: 'http://localhost:0' }
    : { mode, baseUrl: 'https://proxy.example.org', runtimeName: 'test-runtime' };
const rejects = (code: string) => (error: unknown) =>
  error instanceof RuntimeClientError && error.code === code;

for (const entry of fixtures.behavior) {
  test(`P12 behavioral parity: ${entry.name}`, async () => {
    const reply = copy(fixtures.completed);
    const canonicalInput = entry.expected as AgentArtsInvocationEnvelope | null;
    reply.response.request_id = canonicalInput?.request?.request_id ?? request.request_id;
    const transport = new FakeRuntimeTransport('LOCAL', [
      {
        body: entry.kind === 'output' ? entry.raw : reply,
      },
    ]);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    const pending =
      entry.kind === 'input'
        ? client.exchange(entry.raw as AgentArtsInvocationEnvelope)
        : client.exchange({ request });
    if (entry.expected === null) {
      await assert.rejects(pending, rejects('CONTRACT_ERROR'));
      assert.equal(transport.calls.length, entry.kind === 'input' ? 0 : 1);
    } else {
      const result = await pending;
      assert.deepEqual(entry.kind === 'input' ? transport.calls[0] : result, entry.expected);
    }
  });
}

test('canonical request identity is sent and compared without altering caller input', async () => {
  const caller = { ...request, request_id: ' request-1 ' };
  const transport = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.completed }]);
  const result = await new RuntimeInvocationClient(transport, config('LOCAL')).invoke(caller);
  assert.equal(result.request_id, 'request-1');
  assert.equal(transport.calls[0].request?.request_id, 'request-1');
  assert.equal(caller.request_id, ' request-1 ');
});

for (const runtimeName of [undefined, null, true, 123, [], {}, '', '   ', ' test-runtime ']) {
  test(`config rejects runtimeName ${JSON.stringify(runtimeName)} without coercion`, () => {
    assert.throws(
      () =>
        new RuntimeInvocationClient(new FakeRuntimeTransport('AGENTARTS', []), {
          mode: 'AGENTARTS',
          baseUrl: 'https://proxy.example.org',
          runtimeName,
        } as RuntimeConfig),
      rejects('CONTRACT_ERROR'),
    );
  });
}

test('config requires runtimeName and strict Local/AgentArts root, mode and baseUrl types', () => {
  for (const raw of [
    null,
    [],
    true,
    {},
    { mode: 'AGENTARTS', baseUrl: 'https://proxy.example.org' },
    ...(['LOCAL', 'AGENTARTS'] as const).flatMap((mode) =>
      [undefined, null, true, 123, [], {}, ' http://localhost:0 '].map((baseUrl) => ({
        mode,
        baseUrl,
        ...(mode === 'AGENTARTS' ? { runtimeName: 'test-runtime' } : {}),
      })),
    ),
  ]) {
    assert.throws(
      () =>
        new RuntimeInvocationClient(new FakeRuntimeTransport('LOCAL', []), raw as RuntimeConfig),
      rejects('CONTRACT_ERROR'),
    );
  }
  new RuntimeInvocationClient(new FakeRuntimeTransport('LOCAL', []), config('LOCAL'));
  new RuntimeInvocationClient(new FakeRuntimeTransport('AGENTARTS', []), config('AGENTARTS'));
});

test('core Agent FAILED remains an AgentResponse, distinct from runtime failure', async () => {
  const transport = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.agent_error }]);
  const result = await new RuntimeInvocationClient(transport, config('LOCAL')).invoke(request);
  assert.equal(result.outcome, 'FAILED');
  assert.deepEqual(result.error, fixtures.agent_error.response.error);
  assert.equal(transport.calls.length, 1);
});

for (const mode of ['LOCAL', 'AGENTARTS'] as const) {
  for (const name of ['completed', 'ineligible', 'unknown', 'reject'] as const) {
    test(`${mode} ${name} stays a valid AgentResponse without business interpretation`, async () => {
      const wire = fixtures[name];
      const transport = new FakeRuntimeTransport(mode, [{ body: wire }]);
      const client = new RuntimeInvocationClient(transport, config(mode));
      const result = await client.invoke(request);
      assert.deepEqual(result, wire.response);
      assert.deepEqual(transport.calls, [{ request }]);
      assert.equal(result.request_id, request.request_id);
      assert.equal(result.outcome, 'COMPLETED');
    });
  }
}

test('clarification and explicit approval/reject preserve actual continuation envelopes', async () => {
  for (const [pending, reply] of [
    [fixtures.clarification, fixtures.clarification_reply],
    [fixtures.approval, fixtures.approve_reply],
    [fixtures.approval, fixtures.reject_reply],
  ]) {
    const transport = new FakeRuntimeTransport('LOCAL', [
      { body: pending },
      { body: fixtures.completed },
    ]);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    const result = await client.exchange({ request });
    assert.deepEqual(result, pending);
    assert.equal(result.continuation_ref, reply.continuation_ref);
    await client.resume(reply as AgentArtsInvocationEnvelope & { continuation_ref: string });
    assert.deepEqual(transport.calls[1], reply);
    assert.equal(transport.calls.length, 2);
    assert.ok(!JSON.stringify(transport.calls).includes('HUMAN_APPROVED'));
  }
});

test('canonical refs/URL strings/aware timestamps survive JSON without rewriting', async () => {
  const transport = new FakeRuntimeTransport('LOCAL', [
    { body: fixtures.approval },
    { body: fixtures.completed },
  ]);
  const client = new RuntimeInvocationClient(transport, config('LOCAL'));
  const approval = await client.invoke(request);
  assert.equal(approval.approval_request?.created_at, '2026-10-19T00:00:00Z');
  const completed = await client.invoke(request);
  assert.deepEqual(completed.audit, fixtures.completed.response.audit);
  assert.ok(completed.audit?.results?.some((r) => r.kind === 'PLAN_DIFF'));
  assert.ok(
    completed.audit?.results?.some(
      (r) => r.kind === 'SOURCE' && r.ref_id === 'https://example.org/official',
    ),
  );
});

for (const mutate of [
  (r: any) => {
    delete r.response.request_id;
  },
  (r: any) => {
    r.response.outcome = 'NEW_UNKNOWN_STATUS';
  },
  (r: any) => {
    r.response.request_id = 'another-request';
  },
  (r: any) => {
    r.response.extra = true;
  },
  (r: any) => {
    r.response.clarification = {};
  },
  (r: any) => {
    r.response.audit.reasons[0].result.ref_id = 'missing-lineage';
  },
  (r: any) => {
    r.continuation = { state: { approved: true } };
  },
  (r: any) => {
    r.version = 'invented';
  },
]) {
  test(`invalid response ${mutate.toString()} fails closed`, async () => {
    const wire = copy(fixtures.completed);
    mutate(wire);
    const transport = new FakeRuntimeTransport('LOCAL', [{ body: wire }]);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    await assert.rejects(client.invoke(request), rejects('CONTRACT_ERROR'));
    assert.equal(transport.calls.length, 1);
  });
}

test('nested approval invalid enum/date/reference and unsafe pending result fail closed', async () => {
  for (const mutate of [
    (r: any) => {
      r.response.approval_request.action = 'HUMAN_APPROVED';
    },
    (r: any) => {
      r.response.approval_request.before_plan.version = '1';
    },
    (r: any) => {
      r.response.approval_request.created_at = '2026-10-19T08:00:00';
    },
    (r: any) => {
      r.response.approval_request.decision_ref.kind = 'SOURCE';
    },
    (r: any) => {
      r.continuation_ref = null;
    },
    (r: any) => {
      r.response.approval_request.source_request_id = 'wrong-request';
    },
  ]) {
    const wire = copy(fixtures.approval);
    mutate(wire);
    const client = new RuntimeInvocationClient(
      new FakeRuntimeTransport('LOCAL', [{ body: wire }]),
      config('LOCAL'),
    );
    await assert.rejects(client.invoke(request), rejects('CONTRACT_ERROR'));
  }
});

test('request defaults/IDs/targets/authority are never guessed or overwritten', async () => {
  for (const raw of [
    { ...request, capability_id: 'revise_plan' },
    { ...request, request_id: '' },
    { ...request, context: { edition_id: 'unbound-edition' } },
    { ...request, request_id: Number.NaN },
    { ...request, admin_override: true },
  ]) {
    const transport = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.completed }]);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    await assert.rejects(client.invoke(raw as AgentRequest), rejects('CONTRACT_ERROR'));
    assert.equal(transport.calls.length, 0);
  }
});

test('mixed/free-form/untrusted authority resume envelopes are rejected before sending', async () => {
  for (const raw of [
    { ...fixtures.approve_reply, request },
    { ...fixtures.approve_reply, approved_by_ref: 'admin' },
    {
      ...fixtures.approve_reply,
      approval: { ...fixtures.approve_reply.approval, decision: 'HUMAN_APPROVED' },
    },
    { continuation_ref: 'opaque', message: 'approve' },
    {
      ...fixtures.clarification_reply,
      clarification: { ...fixtures.clarification_reply.clarification, values: {} },
    },
  ]) {
    const transport = new FakeRuntimeTransport('LOCAL', []);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    await assert.rejects(
      client.exchange(raw as AgentArtsInvocationEnvelope),
      rejects('CONTRACT_ERROR'),
    );
    assert.equal(transport.calls.length, 0);
  }
});

test('transport and safe runtime errors are normalized without secrets or retries', async () => {
  for (const step of [
    { error: new Error('C:/private secret') },
    { body: fixtures.runtime_error },
  ]) {
    const transport = new FakeRuntimeTransport('LOCAL', [step]);
    const client = new RuntimeInvocationClient(transport, config('LOCAL'));
    await assert.rejects(client.invoke(request), (error: unknown) => {
      assert.ok(error instanceof RuntimeClientError);
      assert.equal(error.code, 'error' in step ? 'TRANSPORT_ERROR' : 'RUNTIME_ERROR');
      assert.ok(!error.message.includes('secret'));
      return true;
    });
    assert.equal(transport.calls.length, 1);
  }
});

test('cancellation is transport ABORTED, never an approval REJECT', async () => {
  const abort = new AbortController();
  abort.abort();
  const transport = new FakeRuntimeTransport('LOCAL', []);
  const client = new RuntimeInvocationClient(transport, config('LOCAL'));
  await assert.rejects(client.invoke(request, { signal: abort.signal }), rejects('ABORTED'));
  assert.equal(transport.calls.length, 0);
});

test('in-flight cancellation forwards signal and never sends an implicit REJECT', async () => {
  const abort = new AbortController();
  const calls: AgentArtsInvocationEnvelope[] = [];
  const transport = {
    mode: 'LOCAL' as const,
    send: async (envelope: AgentArtsInvocationEnvelope, options?: { signal?: AbortSignal }) => {
      calls.push(envelope);
      await new Promise((_resolve, reject) =>
        options?.signal?.addEventListener('abort', () => reject(new Error('aborted'))),
      );
      return { body: fixtures.completed };
    },
  };
  const client = new RuntimeInvocationClient(transport, config('LOCAL'));
  const pending = client.invoke(request, { signal: abort.signal });
  abort.abort();
  await assert.rejects(pending, rejects('ABORTED'));
  assert.deepEqual(calls, [{ request }]);
});

test('simultaneous calls correlate by explicit request ID without client session state', async () => {
  const rawA = copy(fixtures.completed);
  const rawB = copy(fixtures.completed);
  rawB.response.request_id = 'request-2';
  const transport = new FakeRuntimeTransport('LOCAL', [{ body: rawA }, { body: rawB }]);
  const client = new RuntimeInvocationClient(transport, config('LOCAL'));
  const [a, b] = await Promise.all([
    client.invoke(request),
    client.invoke({ ...request, request_id: 'request-2' }),
  ]);
  assert.equal(a.request_id, 'request-1');
  assert.equal(b.request_id, 'request-2');
  assert.equal(transport.calls.length, 2);
});

test('Local/AgentArts parity and metadata isolation for identical contracts', async () => {
  const results: PublicRuntimeResult[] = [];
  for (const mode of ['LOCAL', 'AGENTARTS'] as const) {
    const transport = new FakeRuntimeTransport(mode, [
      {
        body: fixtures.completed,
        metadata: {
          sessionId: 'wrong-student-admin-approved',
          correlationId: mode,
          httpStatus: 200,
        },
      },
    ]);
    const client = new RuntimeInvocationClient(transport, config(mode));
    results.push(await client.exchange({ request }));
    assert.deepEqual(transport.calls[0], { request });
    assert.ok(!JSON.stringify(results).includes('wrong-student'));
  }
  assert.deepEqual(results[0], results[1]);
});

test('public config rejects secret fields/credential URLs and mode mismatch', () => {
  for (const raw of [
    { ...config('LOCAL'), apiKey: 'private' },
    { mode: 'LOCAL', baseUrl: 'https://user:password@example.org' },
    {
      mode: 'AGENTARTS',
      baseUrl: 'https://proxy.example.org?token=private',
      runtimeName: 'test-runtime',
    },
    { mode: 'AGENTARTS', baseUrl: 'https://proxy.example.org', runtimeName: '' },
    config('AGENTARTS'),
  ]) {
    assert.throws(
      () =>
        new RuntimeInvocationClient(new FakeRuntimeTransport('LOCAL', []), raw as RuntimeConfig),
      rejects('CONTRACT_ERROR'),
    );
  }
});
