import assert from 'node:assert/strict';
import test, { before, after, afterEach } from 'node:test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';
import { RuntimeInvocationClient, RuntimeClientError } from '../src/runtime/client.ts';
import { LocalRuntimeTransport } from '../src/runtime/local.ts';
import { FakeRuntimeTransport } from '../src/runtime/fake.ts';
import type { AgentArtsInvocationEnvelope } from '../src/runtime/generated/contracts.ts';
import type { PublicRuntimeResult } from '../src/runtime/generated/contracts.ts';
import type { ArtifactReader } from '../src/results/artifacts.ts';
import { validateArtifacts } from '../src/results/artifacts.ts';
import { ResultPanel } from '../src/results/ResultPanel.tsx';
import { HitlPanel } from '../src/workspace/HitlPanel.tsx';
import { interactionFrom } from '../src/workspace/interactions.ts';
import { renderToStaticMarkup } from 'react-dom/server';
import plan from '../src/demo/local-plan.json' with { type: 'json' };
import type { PlanReference } from '../src/runtime/generated/contracts.ts';
import { collectPlanChoices } from '../src/workspace/plans.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
let baseUrl: string;
let backend: ReturnType<typeof spawn>;
before(async () => {
  backend = spawn(
    path.join(root, 'backend/.venv/Scripts/python.exe'),
    ['scripts/run_local_runtime.py', '--port', '0'],
    {
      cwd: root,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      // An explicitly cloud-enabled demo shell must not turn regression tests
      // into billable external-model calls.
      env: { ...process.env, COMPETITION_COPILOT_LLM_MODE: 'offline' },
    },
  );
  baseUrl = await new Promise<string>((resolve, reject) => {
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      backend.kill();
      reject(new Error('Local Runtime startup timed out'));
    }, 20000);
    backend.stderr!.on('data', (chunk) => {
      stderr += chunk;
    });
    backend.stdout!.on('data', (chunk) => {
      stdout += chunk;
      const match = stdout.match(/LOCAL_RUNTIME_URL=(http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
    backend.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    backend.once('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`Local Runtime exited ${code}: ${stderr}`));
    });
  });
});
after(async () => {
  if (backend && backend.exitCode === null) {
    const ended = once(backend, 'exit');
    backend.kill();
    await ended;
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

function composition(gate?: Promise<void>) {
  const calls: AgentArtsInvocationEnvelope[] = [];
  const deliveries: Array<{ runtime: unknown; presentation: unknown; count: number }> = [];
  let attachment: unknown;
  const fetcher: typeof fetch = async function (this: typeof globalThis, url, init) {
    // Native browser fetch requires its Window/global receiver (Node does not).
    assert.equal(this, globalThis);
    assert.equal(new URL(String(url)).pathname, '/runtime/invoke');
    calls.push(JSON.parse(init!.body as string));
    assert.equal(init!.credentials, 'omit');
    const response = await fetch(url, init);
    const delivery = await response.clone().json();
    deliveries.push({ ...delivery, count: Number(response.headers.get('X-Local-Handler-Count')) });
    if (gate) await gate;
    return response;
  };
  const config = { mode: 'LOCAL', baseUrl } as const;
  const client = new RuntimeInvocationClient(
    new LocalRuntimeTransport(
      config,
      (value) => {
        attachment = value;
      },
      fetcher,
    ),
    config,
  );
  const responses: PublicRuntimeResult[] = [];
  const exchange = client.exchange.bind(client);
  client.exchange = async (...args: Parameters<RuntimeInvocationClient['exchange']>) => {
    const result = await exchange(...args);
    responses.push(result);
    return result;
  };
  const readArtifacts: ArtifactReader = () => attachment;
  return { client, readArtifacts, calls, deliveries, responses };
}

async function assertFakeParity(value: ReturnType<typeof composition>, index: number) {
  const delivery = value.deliveries[index];
  const fake = new RuntimeInvocationClient(
    new FakeRuntimeTransport('LOCAL', [{ body: delivery.runtime }]),
    { mode: 'LOCAL', baseUrl },
  );
  const replayed = await fake.exchange(value.calls[index]);
  assert.deepEqual(replayed, value.responses[index]);
  function markup(result: PublicRuntimeResult) {
    const response = result.response!;
    if (response.outcome === 'NEEDS_CLARIFICATION' || response.outcome === 'WAITING_FOR_APPROVAL')
      return renderToStaticMarkup(
        <HitlPanel
          response={response}
          interaction={interactionFrom(result, 'parity', value.calls[0].request?.context)}
          disabled={false}
          clarify={async () => ({ accepted: false })}
          decide={async () => ({ accepted: false })}
        />,
      );
    return renderToStaticMarkup(
      <ResultPanel response={response} readArtifacts={() => delivery.presentation} />,
    );
  }
  assert.equal(markup(replayed), markup(value.responses[index]));
}
function mount(value: ReturnType<typeof composition>, id = 'request-1') {
  return render(
    <Workspace
      client={value.client}
      readArtifacts={value.readArtifacts}
      nextRequestId={() => id}
      localPlan={plan as PlanReference}
      runtimeLabel="LOCAL"
    />,
  );
}
async function send(view: ReturnType<typeof render>, text: string) {
  fireEvent.change(view.getByRole('textbox', { name: '你的问题' }), { target: { value: text } });
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '发送请求' }));
  });
}
async function settled(view: ReturnType<typeof render>) {
  await within(view.container).findByRole('heading', { name: '回复已就绪' }, { timeout: 10000 });
}

test('real Local completed UI uses P12 Agent chain; whitespace identity is canonical before HTTP and correlation', async () => {
  const value = composition();
  const view = mount(value, ' request-1 ');
  await send(view, '有哪些比赛？');
  await settled(view);
  assert.equal(value.calls.length, 1);
  assert.equal(value.calls[0].request?.request_id, 'request-1');
  assert.ok(view.getByRole('list', { name: '赛事结果' }).textContent?.includes('华为'));
  for (const item of view.container.querySelectorAll('[data-request-id]'))
    assert.equal(item.getAttribute('data-request-id'), 'request-1');
  assert.equal(view.queryByRole('alert'), null);
  await assertFakeParity(value, 0);
});

test('real Local INELIGIBLE remains HTTP/Agent success and preserves source URL/time/enums in renderer', async () => {
  const value = composition();
  const view = mount(value);
  fireEvent.change(view.getByLabelText(/学生 ID/), { target: { value: 'local-graduate' } });
  fireEvent.change(view.getByLabelText('竞赛 ID'), {
    target: { value: 'gcxl-engineering-practice-innovation' },
  });
  fireEvent.change(view.getByLabelText('届次 ID'), {
    target: { value: 'gcxl-engineering-practice-innovation-2027' },
  });
  await send(view, '检查资格');
  await settled(view);
  assert.ok(view.getAllByText('ineligible').length);
  assert.equal(view.queryByRole('alert'), null);
  const response = await new RuntimeInvocationClient(
    new FakeRuntimeTransport('LOCAL', [{ body: value.deliveries[0].runtime }]),
    { mode: 'LOCAL', baseUrl },
  ).invoke(value.calls[0].request!);
  const artifacts = validateArtifacts(response, value.deliveries[0].presentation);
  const eligibility = artifacts.find((a) => a.model === 'EligibilityDecision')!;
  if (eligibility.model !== 'EligibilityDecision') throw Error('expected real P5 result');
  const source = eligibility.value.evidence!.find((e) => e.source)!.source!;
  assert.ok(['verified', 'pending', 'rejected'].includes(source.verification_status));
  const link = view.getAllByRole('link', { name: source.source_url })[0];
  assert.equal(link.getAttribute('href'), source.source_url);
  assert.ok(
    [...view.container.querySelectorAll('time')].some(
      (t) => t.dateTime === source.observed_at && t.title === source.observed_at,
    ),
  );
  assert.equal(value.calls.length, 1);
  await assertFakeParity(value, 0);
});

test('real clarification form resumes same request with exact identity; double submit sends one HTTP continuation', async () => {
  const value = composition();
  const view = mount(value);
  await send(view, '赛事详情');
  const panel = await view.findByRole('region', { name: '补充所需信息' }, { timeout: 10000 });
  const field = within(panel).getByRole('textbox', { name: /竞赛 ID/ }) as HTMLInputElement;
  fireEvent.change(field, { target: { value: 'huawei-ict' } });
  await act(async () => {
    fireEvent.submit(field.form!);
    fireEvent.submit(field.form!);
  });
  await settled(view);
  assert.equal(value.calls.length, 2);
  const first = value.deliveries[0].runtime as {
    response: { clarification: { clarification_id: string; source_request_id: string } };
    continuation_ref: string;
  };
  assert.equal(value.calls[1].continuation_ref, first.continuation_ref);
  assert.equal(
    value.calls[1].clarification?.clarification_id,
    first.response.clarification.clarification_id,
  );
  assert.equal(value.calls[1].clarification?.source_request_id, 'request-1');
  assert.deepEqual(value.calls[1].clarification?.values, { competition_id: 'huawei-ict' });
  assert.equal(value.deliveries[1].count - value.deliveries[0].count, 1);
  assert.equal(view.queryByRole('alert'), null);
  await assertFakeParity(value, 0);
  await assertFakeParity(value, 1);
});

test('real Local and replayed Fake delivery have identical authoritative UI semantics without extra calls', async () => {
  const value = composition();
  const local = mount(value);
  await send(local, 'discovery');
  await settled(local);
  const expected = local.container.querySelector('.grounded-results')!.textContent;
  const delivery = value.deliveries[0];
  local.unmount();
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: delivery.runtime }]);
  const client = new RuntimeInvocationClient(fake, { mode: 'LOCAL', baseUrl });
  const view = render(
    <Workspace
      client={client}
      readArtifacts={() => delivery.presentation}
      nextRequestId={() => 'request-1'}
    />,
  );
  await send(view, 'discovery');
  await settled(view);
  assert.equal(view.container.querySelector('.grounded-results')!.textContent, expected);
  assert.equal(value.calls.length, 1);
  assert.equal(fake.calls.length, 1);
});

for (const [message, model, competition, edition] of [
  ['skill', 'SkillGapDecision', 'comap-mcm', 'comap-mcm-2027'],
  ['plan', 'CompetitionPlan', 'comap-mcm', 'comap-mcm-2027'],
  [
    'recommend',
    'RecommendationRankingResult',
    'gcxl-engineering-practice-innovation',
    'gcxl-engineering-practice-innovation-2027',
  ],
] as const) {
  test(`real Local ${model} reaches the shared result renderer`, async () => {
    const value = composition();
    const response = await value.client.invoke({
      request_id: 'request-1',
      user_message: message,
      context: { student_id: 'local-graduate', competition_id: competition, edition_id: edition },
    });
    const artifacts = validateArtifacts(response, value.readArtifacts(response));
    assert.ok(artifacts.some((item) => item.model === model));
    const view = render(<ResultPanel response={response} readArtifacts={value.readArtifacts} />);
    assert.equal(view.queryByRole('alert'), null);
    if (model === 'CompetitionPlan') assert.ok(view.getByRole('list', { name: '计划里程碑' }));
    if (model === 'RecommendationRankingResult')
      assert.ok(view.getByRole('region', { name: 'blocked' }));
    if (model === 'SkillGapDecision') assert.ok(view.getByText('undetermined'));
    assert.equal(value.calls.length, 1);
    await assertFakeParity(value, 0);
  });
}

test('real Local pending double-send invokes exactly once and does not optimistically complete', async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });
  const value = composition(gate);
  const view = mount(value);
  fireEvent.change(view.getByRole('textbox', { name: '你的问题' }), {
    target: { value: 'discovery' },
  });
  await act(async () => {
    const button = view.getByRole('button', { name: '发送请求' });
    fireEvent.click(button);
    fireEvent.click(button);
  });
  assert.equal(value.calls.length, 1);
  assert.ok((view.getByRole('button', { name: /提交中/ }) as HTMLButtonElement).disabled);
  assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
  await act(async () => {
    release();
  });
  await settled(view);
});

for (const decision of ['REJECT', 'APPROVE'] as const) {
  test(`real Local ${decision} keeps approval identity, one continuation and authoritative outcome`, async () => {
    const value = composition();
    const view = mount(value);
    fireEvent.click(view.getByRole('checkbox', { name: /使用本地受控修订示例方案/ }));
    await send(view, 'controlled revision');
    const button = await view.findByRole(
      'button',
      { name: new RegExp(decision) },
      { timeout: 10000 },
    );
    assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
    const initial = value.deliveries[0].runtime as {
      response: { approval_request: { approval_request_id: string; before_plan: unknown } };
      continuation_ref: string;
    };
    assert.deepEqual(initial.response.approval_request.before_plan, plan);
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    await settled(view);
    assert.equal(value.calls.length, 2);
    assert.equal(value.calls[1].approval?.decision, decision);
    assert.equal(
      value.calls[1].approval?.approval_request_id,
      initial.response.approval_request.approval_request_id,
    );
    assert.equal(value.calls[1].approval?.source_request_id, 'request-1');
    assert.equal(value.calls[1].continuation_ref, initial.continuation_ref);
    assert.ok(!JSON.stringify(value.calls[1]).includes('HUMAN_APPROVED'));
    assert.equal(value.deliveries[1].count - value.deliveries[0].count, 1);
    assert.equal(view.queryByRole('alert'), null);
    await assertFakeParity(value, 0);
    await assertFakeParity(value, 1);
    if (decision === 'APPROVE') {
      assert.ok(view.getByRole('region', { name: '方案变更' }));
      assert.ok(view.getByText('方案状态：active → cancelled'));
    } else {
      assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
      assert.ok(view.container.textContent?.includes('REJECTED'));
    }
  });
}

test('transport unavailable, invalid delivery and runtime error stay distinct and never retry', async () => {
  const listener = createServer();
  listener.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const port = (listener.address() as { port: number }).port;
  await new Promise<void>((r) => listener.close(() => r()));
  const dead = { mode: 'LOCAL', baseUrl: `http://127.0.0.1:${port}` } as const;
  const request = { request_id: 'failure', user_message: 'discovery' };
  let calls = 0;
  const fetcher: typeof fetch = (...args) => {
    calls++;
    return fetch(...args);
  };
  await assert.rejects(
    new RuntimeInvocationClient(new LocalRuntimeTransport(dead, () => {}, fetcher), dead).invoke(
      request,
    ),
    (e) => e instanceof RuntimeClientError && e.code === 'TRANSPORT_ERROR',
  );
  assert.equal(calls, 1);
  for (const [body, code] of [
    [
      { runtime: { response: { request_id: 'failure', outcome: 'INVALID' } }, presentation: null },
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
    let count = 0;
    const stub: typeof fetch = async () => {
      count++;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };
    const config = { mode: 'LOCAL', baseUrl } as const;
    await assert.rejects(
      new RuntimeInvocationClient(new LocalRuntimeTransport(config, () => {}, stub), config).invoke(
        request,
      ),
      (e) => e instanceof RuntimeClientError && e.code === code,
    );
    assert.equal(count, 1);
  }
});

test('Local cancellation forwards AbortSignal without generating REJECT or retry', async () => {
  const controller = new AbortController();
  let calls = 0;
  const config = { mode: 'LOCAL', baseUrl } as const;
  const fetcher: typeof fetch = async (_url, init) => {
    calls++;
    assert.equal(init?.signal, controller.signal);
    controller.abort();
    throw new Error('aborted');
  };
  await assert.rejects(
    new RuntimeInvocationClient(
      new LocalRuntimeTransport(config, () => {}, fetcher),
      config,
    ).invoke({ request_id: 'abort', user_message: 'discovery' }, { signal: controller.signal }),
    (e) => e instanceof RuntimeClientError && e.code === 'ABORTED',
  );
  assert.equal(calls, 1);
});

test('real generated plan is an explicit session choice; exact ref is sent without automatic approval', async () => {
  const value = composition();
  const view = mount(value, 'generated-plan-session');
  fireEvent.change(view.getByLabelText(/学生 ID/), {
    target: { value: 'local-recommendation-demo' },
  });
  fireEvent.change(view.getByLabelText('竞赛 ID'), { target: { value: 'comap-mcm' } });
  fireEvent.change(view.getByLabelText('届次 ID'), { target: { value: 'comap-mcm-2027' } });
  await send(view, 'plan');
  await settled(view);
  const response = value.responses[0].response!;
  const reference = response.plan_refs![0];
  assert.equal(collectPlanChoices(response, value.deliveries[0].presentation).length, 1);
  await view.findByRole('option', { name: new RegExp(reference.plan_id) });
  const select = view.getByRole('combobox', { name: '当前计划 / 选择计划' }) as HTMLSelectElement;
  assert.equal(select.value, '');
  assert.equal(select.options.length, 2);
  assert.ok(select.options[1].textContent?.includes('draft'));
  assert.ok(select.options[1].textContent?.includes(reference.plan_id));
  assert.equal(value.calls.length, 1);
  assert.equal(value.calls[0].request?.context?.plan_ref, undefined);

  // No implicit selection, even on a later request in the same page session.
  fireEvent.click(view.getByRole('button', { name: '开始新请求' }));
  await send(view, 'discovery');
  await settled(view);
  assert.equal(value.calls[1].request?.context?.plan_ref, undefined);
  fireEvent.click(view.getByRole('button', { name: '开始新请求' }));
  const controlled = view.getByRole('checkbox', {
    name: /使用本地受控修订示例方案/,
  }) as HTMLInputElement;
  fireEvent.click(controlled);
  assert.equal(controlled.checked, true);
  fireEvent.change(select, { target: { value: select.options[1].value } });
  assert.equal(controlled.checked, false);
  await send(view, 'revision');
  await view.findByRole('alert', {}, { timeout: 10000 });
  assert.deepEqual(value.calls[2].request?.context?.plan_ref, reference);
  assert.equal(value.calls.length, 3);
  const limitation = value.deliveries[2].runtime as { error: { code: string; message: string } };
  assert.deepEqual(limitation.error, {
    code: 'CORE_VALIDATION_ERROR',
    message: 'NO_TARGET_CONSISTENT_REPLANNING_INPUT',
  });
  assert.ok(value.calls.every((call) => !call.approval && !call.continuation_ref));

  const presentation = value.deliveries[0].presentation;
  assert.deepEqual(collectPlanChoices(response, presentation)[0].reference, reference);
  assert.deepEqual(collectPlanChoices({ ...response, plan_refs: [] }, presentation), []);
  const wrongIdentity = structuredClone(response);
  wrongIdentity.plan_refs![0].student_id = 'different-student';
  assert.deepEqual(collectPlanChoices(wrongIdentity, presentation), []);
  assert.deepEqual(collectPlanChoices(response, undefined), []);
  assert.throws(() => collectPlanChoices(response, { request_id: 'wrong', artifacts: [] }));

  view.unmount();
  const fresh = mount(composition(), 'fresh-session');
  assert.equal(
    (fresh.getByRole('combobox', { name: '当前计划 / 选择计划' }) as HTMLSelectElement).options
      .length,
    1,
  );
});

test('real generated Huawei plan -> explicit selection -> REJECT then APPROVE -> same-plan PlanDiff', async () => {
  const value = composition();
  let sequence = 0;
  const view = render(
    <Workspace
      client={value.client}
      readArtifacts={value.readArtifacts}
      nextRequestId={() => `same-plan-${++sequence}`}
      localPlan={plan as PlanReference}
      runtimeLabel="LOCAL"
    />,
  );
  for (const [label, input] of [
    [/学生 ID/, 'local-recommendation-demo'],
    ['竞赛 ID', 'huawei-ict'],
    ['届次 ID', 'huawei-ict-2026'],
    [/赛道 ID/, 'huawei-ict-2026-innovation'],
  ] as const)
    fireEvent.change(view.getByLabelText(label), { target: { value: input } });
  await send(view, 'plan');
  await settled(view);
  const reference = value.responses[0].response!.plan_refs![0];
  assert.equal(reference.student_id, 'local-recommendation-demo');
  assert.deepEqual(reference.target, {
    competition_id: 'huawei-ict',
    edition_id: 'huawei-ict-2026',
    track_id: 'huawei-ict-2026-innovation',
  });
  const option = (await view.findByRole('option', {
    name: new RegExp(reference.plan_id),
  })) as HTMLOptionElement;
  const select = view.getByRole('combobox', { name: '当前计划 / 选择计划' }) as HTMLSelectElement;
  assert.equal(select.value, '');
  fireEvent.change(select, { target: { value: option.value } });

  for (const [index, decision] of ['REJECT', 'APPROVE'].entries()) {
    fireEvent.click(view.getByRole('button', { name: '开始新请求' }));
    await send(view, '请修订这个计划。');
    const button = await view.findByRole(
      'button',
      { name: new RegExp(decision) },
      { timeout: 10000 },
    );
    const pendingIndex = 1 + index * 2;
    assert.deepEqual(value.calls[pendingIndex].request?.context?.plan_ref, reference);
    const pending = value.responses[pendingIndex].response!;
    assert.equal(pending.outcome, 'WAITING_FOR_APPROVAL');
    assert.deepEqual(pending.approval_request!.before_plan, reference);
    assert.ok(pending.approval_request!.summary.includes('target-track-removed-cancel-v1'));
    assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    await settled(view);
    assert.equal(value.calls.length, pendingIndex + 2);
    assert.equal(value.calls[pendingIndex + 1].approval?.decision, decision);
    assert.equal(value.calls[pendingIndex + 1].approval?.source_request_id, pending.request_id);
    if (decision === 'REJECT') {
      assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
      assert.ok(view.container.textContent?.includes('REJECTED'));
    } else {
      assert.ok(view.getByRole('region', { name: '方案变更' }));
      assert.ok(view.getByText('方案状态：draft → cancelled'));
      const response = value.responses[pendingIndex + 1].response!;
      const diff = validateArtifacts(
        response,
        value.deliveries[pendingIndex + 1].presentation,
      ).find((artifact) => artifact.model === 'PlanDiff');
      if (!diff || diff.model !== 'PlanDiff')
        throw Error('Expected authoritative same-plan PlanDiff');
      assert.equal(diff.value.before.id, reference.plan_id);
      assert.equal(diff.value.before.student_id, reference.student_id);
      assert.equal(diff.value.before.track_id, reference.target.track_id);
      assert.equal(diff.value.after.version, reference.version + 1);
      assert.equal(diff.value.after.status, 'cancelled');
      assert.ok(!JSON.stringify(diff.value).includes('test-only-p11-5-student'));
    }
  }
  assert.equal(value.calls.length, 5);
  assert.ok(value.calls.every((call) => !JSON.stringify(call).includes('HUMAN_APPROVED')));
});
