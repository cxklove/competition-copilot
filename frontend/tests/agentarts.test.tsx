import assert from 'node:assert/strict';
import test, { before, after, afterEach } from 'node:test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { renderToStaticMarkup } from 'react-dom/server';
import { RuntimeInvocationClient, RuntimeClientError } from '../src/runtime/client.ts';
import { LocalRuntimeTransport } from '../src/runtime/local.ts';
import { AgentArtsRuntimeTransport, AgentArtsTransportError } from '../src/runtime/agentarts.ts';
import type {
  AgentArtsInvocationEnvelope,
  AgentResponse,
  PublicRuntimeResult,
  PlanReference,
} from '../src/runtime/generated/contracts.ts';
import { ResultPanel } from '../src/results/ResultPanel.tsx';
import { HitlPanel } from '../src/workspace/HitlPanel.tsx';
import { interactionFrom } from '../src/workspace/interactions.ts';
import plan from '../src/demo/local-plan.json' with { type: 'json' };

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const stamp = '2026-01-01T00:00:00Z';
let urls: { local: string; bridge: string; gateway: string };
let processHandle: ReturnType<typeof spawn>;
before(async () => {
  processHandle = spawn(
    path.join(root, 'backend/.venv/Scripts/python.exe'),
    ['backend/tests/agentarts_gateway_harness.py'],
    { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  urls = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => {
      processHandle.kill();
      reject(Error('Compatibility harness startup timeout'));
    }, 20000);
    processHandle.stdout!.on('data', (value) => {
      output += value;
      const match = output.match(/COMPAT_URLS=(\{[^\r\n]+\})/);
      if (match) {
        clearTimeout(timer);
        resolve(JSON.parse(match[1]));
      }
    });
    processHandle.once('error', reject);
    processHandle.stderr!.on('data', (value) => reject(Error(String(value))));
  });
});
after(async () => {
  if (processHandle?.exitCode === null) {
    const stopped = once(processHandle, 'exit');
    processHandle.kill();
    await stopped;
  }
});

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const key of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'Node',
  'Event',
  'MutationObserver',
] as const)
  Object.defineProperty(globalThis, key, {
    value: key === 'window' ? dom.window : dom.window[key],
    configurable: true,
  });
Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
  value: true,
  writable: true,
  configurable: true,
});
const { render, fireEvent, cleanup, act, within } = await import('@testing-library/react');
const { Workspace } = await import('../src/workspace/Workspace.tsx');
afterEach(cleanup);

function composition(
  mode: 'LOCAL' | 'AGENTARTS',
  sessionId = 'browser-session',
  gate?: Promise<void>,
) {
  let attachment: unknown;
  const calls: AgentArtsInvocationEnvelope[] = [];
  const deliveries: unknown[] = [];
  const fetcher: typeof fetch = async function (this: typeof globalThis, url, init) {
    assert.equal(this, globalThis);
    assert.equal(init?.credentials, 'omit');
    const headers = new Headers(init?.headers);
    assert.equal(headers.has('Authorization'), false);
    assert.equal(headers.has('X-Hw-Agentgateway-User-Id'), false);
    assert.equal(String(url).includes('tools/call'), false);
    calls.push(JSON.parse(String(init?.body)));
    const result = await fetch(url, init);
    deliveries.push(await result.clone().json());
    if (gate) await gate;
    return result;
  };
  const config =
    mode === 'LOCAL'
      ? ({ mode, baseUrl: urls.local } as const)
      : ({ mode, baseUrl: urls.bridge, runtimeName: 'competition-copilot' } as const);
  const readArtifacts = (_response?: AgentResponse) => attachment;
  const receive = (value: unknown) => {
    attachment = value;
  };
  const transport =
    config.mode === 'LOCAL'
      ? new LocalRuntimeTransport(config, receive, fetcher)
      : new AgentArtsRuntimeTransport(config, receive, { fetcher, sessionId });
  return {
    client: new RuntimeInvocationClient(transport, config),
    readArtifacts,
    calls,
    deliveries,
  };
}

function markup(
  result: PublicRuntimeResult,
  readArtifacts: ReturnType<typeof composition>['readArtifacts'],
) {
  const response = result.response!;
  if (response.outcome === 'NEEDS_CLARIFICATION' || response.outcome === 'WAITING_FOR_APPROVAL')
    return renderToStaticMarkup(
      <HitlPanel
        response={response}
        interaction={interactionFrom(result, 'same-interaction')}
        disabled={false}
        clarify={async () => ({ accepted: false })}
        decide={async () => ({ accepted: false })}
      />,
    );
  return renderToStaticMarkup(<ResultPanel response={response} readArtifacts={readArtifacts} />);
}
async function parity(payload: AgentArtsInvocationEnvelope) {
  const local = composition('LOCAL');
  const agentarts = composition('AGENTARTS');
  const left = await local.client.exchange(payload);
  const right = await agentarts.client.exchange(payload);
  assert.deepEqual(right, left);
  assert.deepEqual(agentarts.calls, local.calls);
  assert.deepEqual(agentarts.readArtifacts(), local.readArtifacts());
  assert.equal(markup(right, agentarts.readArtifacts), markup(left, local.readArtifacts));
  return { result: right, local, agentarts };
}

for (const [message, context] of [
  ['discovery', {}],
  [
    'eligibility',
    {
      student_id: 'local-graduate',
      competition_id: 'gcxl-engineering-practice-innovation',
      edition_id: 'gcxl-engineering-practice-innovation-2027',
    },
  ],
  [
    'eligibility',
    {
      student_id: 'local-unknown',
      competition_id: 'gcxl-engineering-practice-innovation',
      edition_id: 'gcxl-engineering-practice-innovation-2027',
    },
  ],
  [
    'skill',
    { student_id: 'local-graduate', competition_id: 'comap-mcm', edition_id: 'comap-mcm-2027' },
  ],
  [
    'plan',
    { student_id: 'local-graduate', competition_id: 'comap-mcm', edition_id: 'comap-mcm-2027' },
  ],
  [
    'recommend',
    { student_id: 'local-graduate', competition_id: 'comap-mcm', edition_id: 'comap-mcm-2027' },
  ],
] as const) {
  test(`real AgentArts-compatible ${message}/${'student_id' in context ? context.student_id : 'none'} equals Local response, artifacts and presentation`, async () => {
    const value = await parity({
      request: { request_id: ' request-1 ', user_message: message, context },
    });
    assert.equal(value.result.response!.request_id, 'request-1');
    assert.equal(value.agentarts.calls[0].request!.request_id, 'request-1');
    assert.equal(value.result.response!.outcome, 'COMPLETED');
    assert.equal(value.agentarts.calls.length, 1);
  });
}

test('clarification and resume parity preserves request and question identity with changed transport session', async () => {
  const pending = await parity({ request: { request_id: 'question', user_message: 'detail' } });
  const question = pending.result.response!.clarification!;
  const reply = {
    continuation_ref: pending.result.continuation_ref!,
    clarification: {
      clarification_id: question.clarification_id,
      source_request_id: 'question',
      values: { competition_id: 'huawei-ict' },
      submitted_at: stamp,
    },
  };
  const local = composition('LOCAL');
  const agentarts = composition('AGENTARTS', 'changed-session-not-identity');
  const left = await local.client.exchange(reply);
  const right = await agentarts.client.exchange(reply);
  assert.deepEqual(left, right);
  assert.equal(markup(left, local.readArtifacts), markup(right, agentarts.readArtifacts));
  assert.equal(right.response!.request_id, 'question');
  await assert.rejects(
    agentarts.client.exchange(reply),
    (e) => e instanceof RuntimeClientError && e.code === 'RUNTIME_ERROR',
  );
});

for (const decision of ['REJECT', 'APPROVE'] as const) {
  test(`explicit ${decision} UI has Local parity and one HTTP continuation, no browser authority`, async () => {
    const expected: unknown[] = [];
    const rendered: string[] = [];
    for (const mode of ['LOCAL', 'AGENTARTS'] as const) {
      const value = composition(mode);
      const view = render(
        <Workspace
          {...value}
          nextRequestId={() => 'approval-request'}
          now={() => stamp}
          localPlan={plan as PlanReference}
        />,
      );
      fireEvent.click(view.getByRole('checkbox', { name: /使用本地受控修订示例方案/ }));
      fireEvent.change(view.getByLabelText('你的问题'), {
        target: { value: 'controlled revision' },
      });
      await act(async () => {
        fireEvent.click(view.getByRole('button', { name: '发送请求' }));
      });
      const button = await view.findByRole(
        'button',
        { name: new RegExp(decision) },
        { timeout: 10000 },
      );
      assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
      await act(async () => {
        fireEvent.click(button);
        fireEvent.click(button);
      });
      await view.findByRole('heading', { name: '回复已就绪' }, { timeout: 10000 });
      assert.equal(value.calls.length, 2);
      assert.equal(value.calls[1].approval!.decision, decision);
      assert.ok(!JSON.stringify(value.calls).includes('HUMAN_APPROVED'));
      assert.equal(view.queryByRole('alert'), null);
      expected.push(value.deliveries);
      rendered.push(view.container.querySelector('.grounded-results')!.textContent!);
      if (decision === 'APPROVE') assert.ok(view.getByText('方案状态：执行中 → 已取消'));
      view.unmount();
    }
    assert.deepEqual(expected[0], expected[1]);
    assert.equal(rendered[0], rendered[1]);
  });
}

test('normal and clarification double-submit invoke once per pending UI action with either real transport', async () => {
  for (const mode of ['LOCAL', 'AGENTARTS'] as const) {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const value = composition(mode, 'duplicate-check', gate);
    const view = render(
      <Workspace
        {...value}
        nextRequestId={() => 'duplicate-request'}
        now={() => stamp}
        localPlan={plan as PlanReference}
      />,
    );
    fireEvent.change(view.getByLabelText('你的问题'), { target: { value: 'detail' } });
    await act(async () => {
      const send = view.getByRole('button', { name: '发送请求' });
      fireEvent.click(send);
      fireEvent.click(send);
    });
    assert.equal(value.calls.length, 1);
    assert.ok((view.getByRole('button', { name: /提交中/ }) as HTMLButtonElement).disabled);
    await act(async () => {
      release();
    });
    const panel = await view.findByRole('region', { name: '补充所需信息' }, { timeout: 10000 });
    const field = within(panel).getByRole('textbox', { name: /竞赛 ID/ }) as HTMLInputElement;
    fireEvent.change(field, { target: { value: 'huawei-ict' } });
    await act(async () => {
      fireEvent.submit(field.form!);
      fireEvent.submit(field.form!);
    });
    await view.findByRole('heading', { name: '回复已就绪' }, { timeout: 10000 });
    assert.equal(value.calls.length, 2);
    assert.deepEqual(value.calls[1].clarification!.values, { competition_id: 'huawei-ict' });
    view.unmount();
  }
});

async function fault(value: unknown) {
  await fetch(urls.gateway + '/__test__/control', { method: 'POST', body: JSON.stringify(value) });
}
test('unknown reasons survive AgentArts HTTP and the same validator/renderer without prototype lookup', async () => {
  const value = await parity({
    request: { request_id: 'unknown-reason', user_message: 'discovery' },
  });
  const delivery = structuredClone(value.agentarts.deliveries[0]) as {
    runtime: PublicRuntimeResult;
  };
  const response = delivery.runtime.response!;
  response.audit!.reasons = ['__proto__', 'constructor', 'FUTURE_REASON_CODE'].map(
    (reason_code) => ({ reason_code, result: response.audit!.results![0] }),
  );
  await fault({ body: delivery });
  const client = composition('AGENTARTS');
  const result = await client.client.exchange({
    request: { request_id: 'unknown-reason', user_message: 'discovery' },
  });
  const html = markup(result, client.readArtifacts);
  for (const code of ['__proto__', 'constructor', 'FUTURE_REASON_CODE'])
    assert.ok(html.includes(`<code>${code}</code>`));
});

test('cloud auth/not-found/server/timeout stay transport errors and never retry or become business negatives', async () => {
  for (const [status, code] of [
    [401, 'AGENTARTS_AUTH_ERROR'],
    [403, 'AGENTARTS_AUTH_ERROR'],
    [404, 'AGENTARTS_RUNTIME_NOT_FOUND'],
    [500, 'AGENTARTS_SERVER_ERROR'],
    [302, 'AGENTARTS_HTTP_ERROR'],
  ] as const) {
    await fault({ status, body: { message: 'PRIVATE upstream body' } });
    const transport = new AgentArtsRuntimeTransport({
      mode: 'AGENTARTS',
      runtimeName: 'competition-copilot',
      baseUrl: urls.bridge,
    });
    await assert.rejects(
      transport.send({ request: { request_id: 'failure', user_message: 'discovery' } }),
      (e) =>
        e instanceof AgentArtsTransportError && e.code === code && !e.message.includes('PRIVATE'),
    );
  }
  await fault({ delay: 0.8, body: {} });
  const value = composition('AGENTARTS');
  await assert.rejects(
    value.client.invoke({ request_id: 'failure', user_message: 'discovery' }),
    (e) => e instanceof RuntimeClientError && e.code === 'TRANSPORT_ERROR',
  );
  assert.equal(value.calls.length, 1);
});

test('invalid/private upstream fails contract closed; runtime errors remain separate', async () => {
  for (const [body, code] of [
    [
      { runtime: { response: { outcome: 'bad' }, continuation: { state: 'private' } } },
      'CONTRACT_ERROR',
    ],
    [
      {
        runtime: { error: { code: 'CORE_EXECUTION_ERROR', message: 'CORE_EXECUTION_ERROR' } },
        presentation: null,
      },
      'RUNTIME_ERROR',
    ],
  ] as const) {
    await fault({ body });
    const value = composition('AGENTARTS');
    await assert.rejects(
      value.client.invoke({ request_id: 'failure', user_message: 'discovery' }),
      (e) => e instanceof RuntimeClientError && e.code === code,
    );
    assert.equal(value.calls.length, 1);
    assert.ok(!JSON.stringify(value.deliveries).includes('private'));
  }
});

test('AbortSignal is cancellation, not REJECT; no auto replay', async () => {
  const controller = new AbortController();
  let count = 0;
  const config = {
    mode: 'AGENTARTS',
    runtimeName: 'competition-copilot',
    baseUrl: urls.bridge,
  } as const;
  const transport = new AgentArtsRuntimeTransport(config, () => {}, {
    fetcher: async (_url, init) => {
      count++;
      assert.equal(init?.signal, controller.signal);
      controller.abort();
      throw Error('abort');
    },
  });
  await assert.rejects(
    new RuntimeInvocationClient(transport, config).invoke(
      { request_id: 'abort', user_message: 'discovery' },
      { signal: controller.signal },
    ),
    (e) => e instanceof RuntimeClientError && e.code === 'ABORTED',
  );
  assert.equal(count, 1);
});

test('cloud credential and MCP/business dependency stay outside browser transport/UI', async () => {
  const records = await (await fetch(urls.gateway + '/__test__/observations')).json();
  assert.ok(
    records.every((r: { authorized: boolean; mcp: unknown }) => r.authorized && r.mcp === null),
  );
  for (const file of ['src/runtime/agentarts.ts', 'src/agentartsClient.ts', '.env.example']) {
    const source = readFileSync(path.join(root, 'frontend', file), 'utf8');
    assert.ok(!source.includes('COPILOT_AGENTARTS_AUTHORIZATION'));
    assert.ok(!source.includes('synthetic-harness-only-not-a-credential'));
    assert.ok(!source.includes('tools/call'));
    assert.ok(!source.includes('tools/list'));
  }
});
