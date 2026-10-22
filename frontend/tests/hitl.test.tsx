import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import fixtures from './fixtures/runtime.json' with { type: 'json' };
import { RuntimeInvocationClient, RuntimeClientError } from '../src/runtime/client.ts';
import { FakeRuntimeTransport } from '../src/runtime/fake.ts';
import type { PublicRuntimeResult, PlanReference } from '../src/runtime/generated/contracts.ts';
import {
  interactionFrom,
  clarificationEnvelope,
  approvalEnvelope,
} from '../src/workspace/interactions.ts';
import { useConversation } from '../src/workspace/useConversation.ts';
import { createDemoClient } from '../src/demo/client.ts';

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
const now = () => '2026-10-20T00:00:00Z';
const config = { mode: 'LOCAL', baseUrl: 'http://localhost:0' } as const;
function setup(steps: ConstructorParameters<typeof FakeRuntimeTransport>[1]) {
  const fake = new FakeRuntimeTransport('LOCAL', steps);
  const client = new RuntimeInvocationClient(fake, config);
  const view = render(<Workspace client={client} nextRequestId={() => 'request-1'} now={now} />);
  return { view, fake, client };
}
async function begin(view: ReturnType<typeof render>, text = '请处理这个请求') {
  fireEvent.change(view.getByRole('textbox', { name: '你的问题' }), { target: { value: text } });
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '发送请求' }));
  });
}
function deferred() {
  let release!: () => void;
  const promise = new Promise<void>((r) => {
    release = r;
  });
  return { promise, release };
}

test('clarification question and requested field produce exact P12 continuation, not a new request', async () => {
  const { view, fake } = setup([{ body: fixtures.clarification }, { body: fixtures.completed }]);
  await begin(view);
  assert.ok(view.getByRole('heading', { name: '补充所需信息' }));
  assert.ok(view.getByText('还需要补充一些信息'));
  assert.ok(
    view.container
      .querySelector('.clarification-audit pre')!
      .textContent?.includes(fixtures.clarification.response.clarification.question),
  );
  const panel = view.getByRole('region', { name: '补充所需信息' });
  assert.equal(within(panel).getAllByRole('textbox').length, 1);
  fireEvent.change(within(panel).getByRole('textbox', { name: /竞赛 ID/ }), {
    target: { value: ' competition-2 ' },
  });
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.equal(fake.calls.length, 2);
  assert.deepEqual(fake.calls[1], {
    continuation_ref: 'opaque-1',
    clarification: {
      clarification_id: 'question-1',
      source_request_id: 'request-1',
      values: { competition_id: 'competition-2' },
      submitted_at: now(),
    },
  });
  assert.equal('request' in fake.calls[1], false);
  assert.ok(view.getByRole('status').textContent?.includes('已完成'));
  assert.equal(view.queryByRole('alert'), null);
});

test('TRACK-only clarification cannot send a student or unrelated context field', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['TRACK'];
  const { view, fake } = setup([{ body }, { body: fixtures.completed }]);
  fireEvent.change(view.getByRole('textbox', { name: /学生 ID/ }), {
    target: { value: 'student-original' },
  });
  await begin(view);
  const panel = view.getByRole('region', { name: '补充所需信息' });
  assert.equal(within(panel).queryByRole('textbox', { name: /竞赛 ID/ }), null);
  fireEvent.change(within(panel).getByRole('textbox', { name: /赛道 ID/ }), {
    target: { value: 'track-2' },
  });
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.deepEqual(fake.calls[1].clarification?.values, { track_id: 'track-2' });
  const snapshot = interactionFrom(body as PublicRuntimeResult, 'token')!;
  assert.throws(
    () =>
      clarificationEnvelope(
        snapshot,
        { track_id: 'track-2', student: { id: 'unrequested' } },
        now(),
      ),
    RuntimeClientError,
  );
});

test('INTENT has no automatically selected option; unsupported approval context fails safe', async () => {
  const intent = structuredClone(fixtures.clarification);
  intent.response.clarification.fields = ['INTENT'];
  const first = setup([{ body: intent }]);
  await begin(first.view);
  assert.equal(
    (first.view.getByRole('combobox', { name: /请求意图/ }) as HTMLSelectElement).value,
    '',
  );
  assert.equal(first.fake.calls.length, 1);
  first.view.unmount();
  const unsupported = structuredClone(fixtures.clarification);
  unsupported.response.clarification.fields = ['APPROVAL_CONTEXT'];
  const second = setup([{ body: unsupported }]);
  await begin(second.view);
  assert.ok(second.view.getByText(/需要服务端可信上下文/));
  assert.equal(
    (second.view.getByRole('button', { name: '提交补充信息' }) as HTMLButtonElement).disabled,
    true,
  );
  assert.equal(second.fake.calls.length, 1);
});

test('typed nested clarification JSON is validated, with no default profile facts', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['STUDENT_PROFILE'];
  const { view, fake } = setup([{ body }, { body: fixtures.completed }]);
  await begin(view);
  assert.equal(view.container.querySelector('.hitl-panel textarea'), null);
  fireEvent.click(view.getByText('查看高级输入（学生画像）'));
  const field = (await view.findByRole('textbox', { name: /完整学生画像/ })) as HTMLTextAreaElement;
  fireEvent.change(field, { target: { value: 'not json' } });
  await act(async () => {
    fireEvent.submit(field.form!);
  });
  assert.equal(fake.calls.length, 1);
  assert.ok(view.getByRole('alert'));
  fireEvent.change(field, { target: { value: '{"id":"student-explicit"}' } });
  await act(async () => {
    fireEvent.submit(field.form!);
  });
  assert.deepEqual(fake.calls[1].clarification?.values, { student: { id: 'student-explicit' } });
});

test('capability arguments are an explicit advanced fallback, with no default JSON or inferred payload', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['CAPABILITY_ARGUMENTS'];
  body.response.clarification.question =
    'Provide explicit structured context: CAPABILITY_ARGUMENTS';
  body.response.message = body.response.clarification.question;
  const stillNeeds = structuredClone(body);
  stillNeeds.continuation_ref = 'opaque-next';
  const { view, fake } = setup([{ body }, { body: stillNeeds }]);
  await begin(view, '分析我的技能差距');
  const panel = view.getByRole('region', { name: '补充所需信息' });
  assert.ok(within(panel).getByText('需要补充高级参数'));
  assert.equal(panel.querySelector('textarea'), null);
  const main = view.container.cloneNode(true) as HTMLElement;
  main.querySelectorAll('details').forEach((item) => item.remove());
  assert.ok(
    !/CAPABILITY_ARGUMENTS|Provide explicit structured context|能力参数 JSON/.test(
      main.textContent!,
    ),
  );
  assert.equal(fake.calls.length, 1);
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.equal(fake.calls.length, 1);
  assert.ok(view.getByRole('status').textContent?.includes('需要补充信息'));
  fireEvent.click(within(panel).getByText('查看高级输入'));
  const field = await within(panel).findByRole('textbox', { name: '高级参数（JSON）' });
  fireEvent.change(field, { target: { value: '{"payload":{}}' } });
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.equal(fake.calls.length, 2);
  assert.deepEqual(fake.calls[1].clarification?.values, { arguments_json: '{"payload":{}}' });
  assert.equal(
    fake.calls[1].clarification?.clarification_id,
    body.response.clarification.clarification_id,
  );
  assert.equal(fake.calls[1].clarification?.source_request_id, body.response.request_id);
  assert.equal('request' in fake.calls[1], false);
  assert.ok(view.getByRole('status').textContent?.includes('需要补充信息'));
  assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
});

test('requested student profile uses a semantic form and omits all unentered facts', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['STUDENT_PROFILE'];
  const { view, fake } = setup([{ body }, { body: fixtures.completed }]);
  await begin(view);
  const panel = view.getByRole('region', { name: '补充所需信息' });
  assert.equal(panel.querySelector('textarea'), null);
  fireEvent.change(within(panel).getByRole('textbox', { name: '学生画像' }), {
    target: { value: 'student-semantic' },
  });
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.deepEqual(fake.calls[1].clarification?.values, { student: { id: 'student-semantic' } });
  assert.equal(fake.calls.length, 2);
});

test('plan clarification selects only an existing authoritative reference with no digest or version synthesis', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['PLAN'];
  const fake = new FakeRuntimeTransport('LOCAL', [{ body }, { body: fixtures.completed }]);
  const client = new RuntimeInvocationClient(fake, config);
  const ref = fixtures.approval.response.approval_request.before_plan;
  const view = render(
    <Workspace
      client={client}
      localPlan={ref as PlanReference}
      nextRequestId={() => 'request-1'}
      now={now}
    />,
  );
  await begin(view);
  const panel = view.getByRole('region', { name: '补充所需信息' });
  assert.equal(panel.querySelector('textarea'), null);
  const select = within(panel).getByRole('combobox', { name: '选择计划' });
  assert.equal((select as HTMLSelectElement).value, '');
  fireEvent.change(select, { target: { value: '0' } });
  await act(async () => {
    fireEvent.click(within(panel).getByRole('button', { name: '提交补充信息' }));
  });
  assert.deepEqual(fake.calls[1].clarification?.values, { plan_ref: ref });
});

test('semantic clarification values still fail existing public contract validation before invocation', async () => {
  const body = structuredClone(fixtures.clarification);
  body.response.clarification.fields = ['STUDENT_PROFILE'];
  const { view, fake } = setup([{ body }]);
  await begin(view);
  fireEvent.click(view.getByText('查看高级输入（学生画像）'));
  const input = await view.findByRole('textbox', { name: '完整学生画像（JSON）' });
  fireEvent.change(input, {
    target: { value: '{"id":"student","approved_by_ref":"browser-forgery"}' },
  });
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '提交补充信息' }));
  });
  assert.equal(fake.calls.length, 1);
  assert.ok(view.getByRole('alert'));
  assert.ok(view.getByRole('status').textContent?.includes('需要补充信息'));
});

test('clarification duplicate submit produces one continuation while pending', async () => {
  const gate = deferred();
  const fake = new FakeRuntimeTransport('LOCAL', [
    { body: fixtures.clarification },
    { body: fixtures.completed },
  ]);
  const client = new RuntimeInvocationClient(
    {
      mode: 'LOCAL',
      async send(envelope, options) {
        const reply = await fake.send(envelope, options);
        if (envelope.clarification) await gate.promise;
        return reply;
      },
    },
    config,
  );
  const view = render(<Workspace client={client} nextRequestId={() => 'request-1'} now={now} />);
  await begin(view);
  const field = within(view.getByRole('region', { name: '补充所需信息' })).getByRole('textbox', {
    name: /竞赛 ID/,
  }) as HTMLInputElement;
  fireEvent.change(field, { target: { value: 'competition-2' } });
  await act(async () => {
    fireEvent.submit(field.form!);
    fireEvent.submit(field.form!);
  });
  assert.equal(fake.calls.length, 2);
  assert.equal(
    (view.getByRole('button', { name: '提交补充信息' }) as HTMLButtonElement).disabled,
    true,
  );
  await act(async () => {
    gate.release();
  });
  assert.equal(fake.calls.length, 2);
});

for (const decision of ['APPROVE', 'REJECT'] as const) {
  test(`${decision} is explicit, typed, non-optimistic and double-click safe`, async () => {
    const gate = deferred();
    const fake = new FakeRuntimeTransport('LOCAL', [
      { body: fixtures.approval },
      { body: decision === 'REJECT' ? fixtures.reject : fixtures.completed },
    ]);
    const client = new RuntimeInvocationClient(
      {
        mode: 'LOCAL',
        async send(envelope, options) {
          const reply = await fake.send(envelope, options);
          if (envelope.approval) await gate.promise;
          return reply;
        },
      },
      config,
    );
    const view = render(<Workspace client={client} nextRequestId={() => 'request-1'} now={now} />);
    await begin(view);
    const panel = view.getByRole('region', { name: '请明确批准或拒绝' });
    assert.ok(within(panel).getByText('PLAN_REVISION'));
    for (const value of [
      'plan-1',
      'approval-1',
      'scope-1',
      'decision-1',
      'input-1',
      'instruction-1',
      'FIXTURE_REVISION',
    ])
      assert.ok(within(panel).getByText(value));
    assert.equal(within(panel).queryByRole('textbox'), null);
    const button = within(panel).getByRole('button', { name: new RegExp(decision) });
    assert.equal(button.getAttribute('type'), 'button');
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    assert.equal(fake.calls.length, 2);
    assert.deepEqual(fake.calls[1], {
      continuation_ref: 'opaque-2',
      approval: {
        approval_request_id: 'approval-1',
        source_request_id: 'request-1',
        decision,
        submitted_at: now(),
      },
    });
    assert.ok(!JSON.stringify(fake.calls[1]).includes('HUMAN_APPROVED'));
    assert.equal(
      (view.getByRole('button', { name: /APPROVE/ }) as HTMLButtonElement).disabled,
      true,
    );
    assert.equal(
      (view.getByRole('button', { name: /REJECT/ }) as HTMLButtonElement).disabled,
      true,
    );
    assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
    assert.ok(view.getAllByText(/等待 Runtime 确认/).length > 0);
    await act(async () => {
      gate.release();
    });
    assert.ok(view.getByRole('status').textContent?.includes('已完成'));
    assert.equal(view.queryByRole('alert'), null);
    assert.equal(fake.calls.length, 2);
    assert.ok(
      view.getByText(
        decision === 'REJECT'
          ? fixtures.reject.response.message
          : fixtures.completed.response.message,
      ),
    );
  });
}

test('ordinary agreement text and Enter do not create an approval response', async () => {
  const { view, fake } = setup([{ body: fixtures.approval }]);
  await begin(view);
  const composer = view.getByRole('textbox', { name: '你的问题' }) as HTMLTextAreaElement;
  fireEvent.change(composer, { target: { value: '同意，批准，可以' } });
  await act(async () => {
    fireEvent.submit(composer.form!);
    fireEvent.keyDown(view.getByRole('region', { name: '请明确批准或拒绝' }), { key: 'Enter' });
  });
  assert.equal(fake.calls.length, 1);
  assert.equal(fake.calls[0].approval, undefined);
});

for (const [code, step] of [
  ['TRANSPORT_ERROR', { error: new Error('private path secret') }],
  [
    'CONTRACT_ERROR',
    { body: { response: { outcome: 'COMPLETED', message: 'INVALID_WIRE_SECRET' } } },
  ],
] as const) {
  test(`continuation ${code} never claims success or offers unsafe replay`, async () => {
    const { view, fake } = setup([{ body: fixtures.approval }, step]);
    await begin(view);
    await act(async () => {
      fireEvent.click(view.getByRole('button', { name: /APPROVE/ }));
    });
    assert.ok(view.getByRole('alert').textContent?.includes(code));
    assert.ok(view.getByRole('alert').textContent?.includes('执行状态可能未知'));
    assert.equal(view.queryByRole('button', { name: '重试此请求' }), null);
    assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
    assert.equal(
      (view.getByRole('button', { name: /APPROVE/ }) as HTMLButtonElement).disabled,
      true,
    );
    assert.ok(!view.container.textContent?.includes('INVALID_WIRE_SECRET'));
    assert.ok(!view.container.textContent?.includes('private path secret'));
    assert.equal(fake.calls.length, 2);
  });
}

for (const kind of ['approval', 'clarification'] as const) {
  test(`${kind} stale token/callback cannot resume a different workflow`, async () => {
    const next = structuredClone(fixtures[kind]);
    next.response.request_id = 'request-2';
    if (kind === 'approval') next.response.approval_request!.source_request_id = 'request-2';
    else next.response.clarification!.source_request_id = 'request-2';
    const fake = new FakeRuntimeTransport('LOCAL', [{ body: fixtures[kind] }, { body: next }]);
    const client = new RuntimeInvocationClient(fake, config);
    let api!: ReturnType<typeof useConversation>;
    let count = 0;
    function Harness() {
      api = useConversation(client, () => `request-${++count}`, now);
      return null;
    }
    render(<Harness />);
    await act(async () => {
      await api.submit('first', '');
    });
    const token = api.state.interaction!.token;
    const oldDecide = api.decide;
    const oldClarify = api.clarify;
    await act(async () => {
      api.startNew();
    });
    await act(async () => {
      await api.submit('second', '');
    });
    const reply =
      kind === 'approval'
        ? await oldDecide(token, 'APPROVE')
        : await oldClarify(token, { competition_id: 'competition-2' });
    assert.equal(reply.accepted, false);
    assert.equal(fake.calls.length, 2);
    assert.equal(api.state.interaction?.requestId, 'request-2');
  });
}

test('tampered public proposal context is blocked; identity never comes from editable UI state', async () => {
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: fixtures.approval }]);
  const client = new RuntimeInvocationClient(fake, config);
  let api!: ReturnType<typeof useConversation>;
  function Harness() {
    api = useConversation(client, () => 'request-1', now);
    return null;
  }
  render(<Harness />);
  await act(async () => {
    await api.submit('start', '');
  });
  const snapshot = api.state.interaction!;
  if (snapshot.kind !== 'APPROVAL') throw new Error('fixture');
  snapshot.proposal.before_plan.version = 999;
  const result = await api.decide(snapshot.token, 'APPROVE');
  assert.equal(result.accepted, false);
  assert.equal(fake.calls.length, 1);
});

test('used approval interaction cannot replay after its validated completion', async () => {
  const fake = new FakeRuntimeTransport('LOCAL', [
    { body: fixtures.approval },
    { body: fixtures.completed },
  ]);
  const client = new RuntimeInvocationClient(fake, config);
  let api!: ReturnType<typeof useConversation>;
  function Harness() {
    api = useConversation(client, () => 'request-1', now);
    return null;
  }
  render(<Harness />);
  await act(async () => {
    await api.submit('start', '');
  });
  const token = api.state.interaction!.token;
  const old = api.decide;
  await act(async () => {
    await api.decide(token, 'REJECT');
  });
  assert.equal((await old(token, 'APPROVE')).accepted, false);
  assert.equal(fake.calls.length, 2);
});

test('a replacement approval in the same workflow invalidates the older approval identity', async () => {
  const replacement = structuredClone(fixtures.approval);
  replacement.response.approval_request.approval_request_id = 'approval-2';
  replacement.continuation_ref = 'opaque-3';
  const fake = new FakeRuntimeTransport('LOCAL', [
    { body: fixtures.approval },
    { body: replacement },
    { body: fixtures.completed },
  ]);
  const client = new RuntimeInvocationClient(fake, config);
  let api!: ReturnType<typeof useConversation>;
  function Harness() {
    api = useConversation(client, () => 'request-1', now);
    return null;
  }
  render(<Harness />);
  await act(async () => {
    await api.submit('start', '');
  });
  const oldToken = api.state.interaction!.token;
  const old = api.decide;
  await act(async () => {
    await api.decide(oldToken, 'APPROVE');
  });
  assert.equal((await old(oldToken, 'REJECT')).accepted, false);
  assert.equal(fake.calls.length, 2);
  await act(async () => {
    await api.decide(api.state.interaction!.token, 'REJECT');
  });
  assert.equal(fake.calls[2].approval?.approval_request_id, 'approval-2');
  assert.equal(fake.calls[2].continuation_ref, 'opaque-3');
  assert.equal(fake.calls[2].approval?.source_request_id, 'request-1');
});

test('KEEP/UNDETERMINED explanation without approval workflow never creates approval UI', async () => {
  const body = structuredClone(fixtures.completed);
  body.response.message = 'KEEP_CURRENT_PLAN UNDETERMINED 同意 批准';
  const { view, fake } = setup([{ body }]);
  await begin(view);
  assert.equal(view.queryByRole('button', { name: /APPROVE|REJECT/ }), null);
  assert.equal(fake.calls.length, 1);
});

test('builders preserve required IDs and reject wrong source identity/authority enums', () => {
  const snapshot = interactionFrom(fixtures.approval as PublicRuntimeResult, 'token')!;
  assert.deepEqual(
    approvalEnvelope(snapshot, 'REJECT', now()).approval?.approval_request_id,
    'approval-1',
  );
  assert.throws(
    () => approvalEnvelope(snapshot, 'HUMAN_APPROVED' as never, now()),
    RuntimeClientError,
  );
  assert.throws(
    () => approvalEnvelope({ ...snapshot, requestId: 'wrong' }, 'APPROVE', now()),
    RuntimeClientError,
  );
});

test('fake sequences consume receipts and complete either explicit decision without computing a Plan', async () => {
  for (const decision of ['APPROVE', 'REJECT'] as const) {
    const client = createDemoClient('approval');
    const result = await client.exchange({ request: fixtures.request });
    const snapshot = interactionFrom(result, 'token')!;
    const envelope = approvalEnvelope(snapshot, decision, now());
    const completed = await client.exchange(envelope);
    assert.equal(completed.response?.outcome, 'COMPLETED');
    await assert.rejects(client.exchange(envelope), RuntimeClientError);
  }
  const client = createDemoClient('clarification');
  const result = await client.exchange({ request: fixtures.request });
  const next = await client.exchange(
    clarificationEnvelope(
      interactionFrom(result, 'token')!,
      { competition_id: 'competition-2' },
      now(),
    ),
  );
  assert.equal(next.response?.outcome, 'COMPLETED');
});
