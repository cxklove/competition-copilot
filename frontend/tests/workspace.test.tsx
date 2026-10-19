import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import fixtures from './fixtures/runtime.json' with { type: 'json' };
import { RuntimeInvocationClient } from '../src/runtime/client.ts';
import { FakeRuntimeTransport } from '../src/runtime/fake.ts';
import type { RuntimeMode } from '../src/runtime/transport.ts';
import type { AgentResponse } from '../src/runtime/generated/contracts.ts';
import { conversationReducer, initialState, workflowLabel } from '../src/workspace/state.ts';
import { createDemoClient } from '../src/demo/client.ts';
import type { InvocationClient } from '../src/workspace/useConversation.ts';

// Install DOM before React DOM's event support detection; keep existing Node runner.
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
  configurable: true,
  writable: true,
});
const { render, fireEvent, cleanup, act, within } = await import('@testing-library/react');
const { Workspace } = await import('../src/workspace/Workspace.tsx');
afterEach(cleanup);

function config(mode: RuntimeMode) {
  return mode === 'LOCAL'
    ? ({ mode, baseUrl: 'http://localhost:0' } as const)
    : ({ mode, baseUrl: 'https://proxy.example.org', runtimeName: 'test-runtime' } as const);
}
function clientFor(body: unknown, mode: RuntimeMode = 'LOCAL') {
  const transport = new FakeRuntimeTransport(mode, [{ body }]);
  return { transport, client: new RuntimeInvocationClient(transport, config(mode)) };
}
function mount(client: InvocationClient, id = 'request-1') {
  return render(<Workspace client={client} nextRequestId={() => id} />);
}
async function send(view: ReturnType<typeof mount>, message = '帮我发现赛事') {
  fireEvent.change(view.getByRole('textbox', { name: '你的问题' }), { target: { value: message } });
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '发送请求' }));
  });
}
function deferred() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

test('initial accessible shell, examples fill input without invoking', () => {
  const { client, transport } = clientFor(fixtures.completed);
  const view = mount(client);
  assert.ok(view.getByRole('main'));
  assert.ok(view.getByRole('heading', { name: '从一个问题开始' }));
  const input = view.getByRole('textbox', { name: '你的问题' }) as HTMLTextAreaElement;
  const button = view.getByRole('button', { name: '发送请求' }) as HTMLButtonElement;
  assert.equal(button.disabled, true);
  fireEvent.click(view.getByRole('button', { name: /有哪些适合我的竞赛/ }));
  assert.equal(input.value, '有哪些适合我的竞赛？');
  assert.equal(button.disabled, false);
  assert.equal(transport.calls.length, 0);
  assert.ok(view.getByRole('status').textContent?.includes('等待开始'));
});

test('submit once, preserve explicit context and correlate both entries to the request', async () => {
  const { client, transport } = clientFor(fixtures.completed);
  const view = mount(client);
  fireEvent.change(view.getByRole('textbox', { name: /学生 ID/ }), {
    target: { value: ' student-1 ' },
  });
  await send(view);
  assert.equal(transport.calls.length, 1);
  assert.deepEqual(transport.calls[0].request, {
    request_id: 'request-1',
    user_message: '帮我发现赛事',
    context: { student_id: 'student-1' },
  });
  const entries = view.getByRole('list', { name: '对话记录' }).querySelectorAll('li');
  assert.equal(entries.length, 2);
  assert.ok([...entries].every((v) => v.dataset.requestId === 'request-1'));
  assert.ok(view.getByText(fixtures.completed.response.message));
  assert.ok(view.getByRole('heading', { name: '回复已就绪' }));
  assert.equal(view.queryByRole('alert'), null);
});

test('Enter remains a newline and explicit Ctrl+Enter sends once', async () => {
  const { client, transport } = clientFor(fixtures.completed);
  const view = mount(client);
  const input = view.getByRole('textbox', { name: '你的问题' });
  fireEvent.change(input, { target: { value: '多行问题' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  assert.equal(transport.calls.length, 0);
  await act(async () => {
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
  });
  assert.equal(transport.calls.length, 1);
});

test('pending submission is accessible and synchronous double-submit invokes exactly once', async () => {
  const gate = deferred();
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.completed }]);
  const client = new RuntimeInvocationClient(
    {
      mode: 'LOCAL',
      async send(envelope, options) {
        const reply = await fake.send(envelope, options);
        await gate.promise;
        return reply;
      },
    },
    config('LOCAL'),
  );
  const view = mount(client);
  const input = view.getByRole('textbox', { name: '你的问题' }) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: '同一请求' } });
  await act(async () => {
    fireEvent.submit(input.form!);
    fireEvent.submit(input.form!);
  });
  assert.equal(fake.calls.length, 1);
  assert.equal((view.getByRole('button', { name: '提交中…' }) as HTMLButtonElement).disabled, true);
  assert.ok(view.getByText('正在等待回复…').getAttribute('role') === 'status');
  assert.equal(input.disabled, true);
  await act(async () => {
    gate.release();
  });
  assert.equal(fake.calls.length, 1);
  assert.ok(view.getByRole('status').textContent?.includes('已完成'));
});

for (const name of ['ineligible', 'unknown', 'reject'] as const) {
  test(`${name} business outcome stays in normal conversation, without error banner`, async () => {
    const { client } = clientFor(fixtures[name]);
    const view = mount(client);
    await send(view);
    assert.equal(view.queryByRole('alert'), null);
    assert.ok(view.getByText(fixtures[name].response.message));
    assert.ok(view.getByRole('status').textContent?.includes('已完成'));
  });
}

for (const [name, title] of [
  ['clarification', '需要补充信息'],
  ['approval', '等待用户确认'],
] as const) {
  test(`${name} shows HITL controls without automatic continuation`, async () => {
    const { client, transport } = clientFor(fixtures[name]);
    const view = mount(client);
    await send(view);
    assert.ok(view.getByRole('heading', { name: title }));
    assert.ok(view.getByRole('status').textContent?.includes(title));
    assert.ok(view.getByRole('button', { name: name === 'approval' ? /APPROVE/ : '提交补充信息' }));
    assert.equal(
      (view.getByRole('button', { name: '发送请求' }) as HTMLButtonElement).disabled,
      true,
    );
    assert.equal(transport.calls.length, 1);
    assert.ok(!transport.calls[0].approval && !transport.calls[0].clarification);
  });
}

test('explicit retry resends the same request once; no silent retry or duplicate user entry', async () => {
  const transport = new FakeRuntimeTransport('LOCAL', [
    { error: new Error('secret transport detail') },
    { body: fixtures.completed },
  ]);
  const view = mount(new RuntimeInvocationClient(transport, config('LOCAL')));
  await send(view);
  assert.ok(view.getByRole('alert').textContent?.includes('TRANSPORT_ERROR'));
  assert.ok(!view.container.textContent?.includes('secret transport detail'));
  assert.equal(transport.calls.length, 1);
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '重试此请求' }));
  });
  assert.equal(transport.calls.length, 2);
  assert.deepEqual(transport.calls[0], transport.calls[1]);
  assert.equal(view.container.querySelectorAll('.message-user').length, 1);
  assert.equal(view.queryByRole('alert'), null);
});

test('invalid wire response is CONTRACT_ERROR and never an Agent conversation entry', async () => {
  const { client } = clientFor({
    response: { outcome: 'COMPLETED', message: 'INVALID_WIRE_SECRET' },
  });
  const view = mount(client);
  await send(view);
  assert.ok(view.getByRole('alert').textContent?.includes('CONTRACT_ERROR'));
  assert.ok(view.getByRole('alert').textContent?.includes('无法解析'));
  assert.equal(view.container.querySelectorAll('.message-agent').length, 0);
  assert.ok(!view.container.textContent?.includes('INVALID_WIRE_SECRET'));
});

test('runtime envelope error and core Agent FAILED stay distinct', async () => {
  const view = mount(clientFor(fixtures.runtime_error).client);
  await send(view);
  assert.ok(view.getByRole('alert').textContent?.includes('RUNTIME_ERROR'));
  view.unmount();
  const core = mount(clientFor(fixtures.agent_error).client);
  await send(core);
  assert.equal(core.queryByRole('alert'), null);
  assert.ok(core.container.querySelector('.message-agent'));
  assert.ok(core.getByRole('status').textContent?.includes('Agent 未完成请求'));
});

test('structured outcome controls presentation regardless of explanation wording', async () => {
  const body = structuredClone(fixtures.completed);
  body.response.message = 'WAITING_FOR_APPROVAL 需要补充信息 系统错误';
  const view = mount(clientFor(body).client);
  await send(view);
  assert.ok(view.getByRole('status').textContent?.includes('已完成'));
  assert.ok(view.getByRole('heading', { name: '回复已就绪' }));
  assert.equal(view.queryByRole('heading', { name: '等待用户确认' }), null);
  assert.equal(view.queryByRole('alert'), null);
});

test('swapping fake Local and AgentArts transports preserves presentation semantics', async () => {
  const snapshots = [];
  for (const mode of ['LOCAL', 'AGENTARTS'] as const) {
    const view = mount(clientFor(fixtures.completed, mode).client);
    await send(view);
    snapshots.push(view.container.textContent);
    view.unmount();
  }
  assert.equal(snapshots[0], snapshots[1]);
});

test('unmount aborts request and late completion cannot overwrite a fresh workspace', async () => {
  const gate = deferred();
  let signal: AbortSignal | undefined;
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.completed }]);
  const client = new RuntimeInvocationClient(
    {
      mode: 'LOCAL',
      async send(envelope, options) {
        signal = options?.signal;
        const reply = await fake.send(envelope, options);
        await gate.promise;
        return reply;
      },
    },
    config('LOCAL'),
  );
  const old = mount(client);
  await send(old, '旧请求');
  old.unmount();
  assert.equal(signal?.aborted, true);
  const body = structuredClone(fixtures.completed);
  body.response.request_id = 'request-2';
  body.response.message = '新请求的回复';
  const fresh = mount(clientFor(body).client, 'request-2');
  await send(fresh, '新请求');
  await act(async () => {
    gate.release();
  });
  assert.ok(fresh.getByText('新请求的回复'));
  assert.equal(fresh.queryByText(fixtures.completed.response.message), null);
});

test('pure reducer is deterministic and rejects stale/mismatched response actions', () => {
  const start = { type: 'SUBMIT', attempt: 1, request: fixtures.request, retry: false } as const;
  const pending = conversationReducer(initialState, start);
  const action = {
    type: 'RESOLVE',
    attempt: 1,
    response: fixtures.completed.response as AgentResponse,
  } as const;
  assert.deepEqual(conversationReducer(pending, action), conversationReducer(pending, action));
  assert.equal(workflowLabel(conversationReducer(pending, action)), '已完成');
  assert.equal(conversationReducer(pending, { ...action, attempt: 2 }), pending);
  assert.equal(
    conversationReducer(pending, {
      ...action,
      response: { ...action.response, request_id: 'other' },
    }),
    pending,
  );
});

test('demo composition uses validated fake presets; workspace has no transport/MCP/storage dependency', async () => {
  for (const scenario of ['completed', 'negative', 'clarification', 'approval'] as const) {
    const response = await createDemoClient(scenario).invoke({
      ...fixtures.request,
      request_id: 'demo-caller',
    });
    assert.equal(response.request_id, 'demo-caller');
  }
  for (const file of ['Workspace.tsx', 'useConversation.ts', 'state.ts']) {
    const source = readFileSync(new URL(`../src/workspace/${file}`, import.meta.url), 'utf8');
    assert.doesNotMatch(
      source,
      /fetch\(|localStorage|sessionStorage|FakeRuntimeTransport|tools\/call|tools\/list|from ['"].*transport/,
    );
  }
  assert.ok(within(document.body));
});
