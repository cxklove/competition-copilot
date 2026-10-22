import assert from 'node:assert/strict';
import test, { before, after, afterEach } from 'node:test';
import { readFileSync } from 'node:fs';
import { createServer } from 'node:net';
import {
  modes,
  composition,
  deferred,
  fault,
  resetScenario,
  startHarness,
  stopHarness,
  semanticTrace,
  assertParity,
  root,
  stamp,
} from './e2e/support.ts';
import type { Composition } from './e2e/support.ts';
import type { PlanReference } from '../src/runtime/generated/contracts.ts';
import { RuntimeClientError } from '../src/runtime/client.ts';
import { validateArtifacts } from '../src/results/artifacts.ts';
import { Workspace } from '../src/workspace/Workspace.tsx';
import { useConversation } from '../src/workspace/useConversation.ts';
import plan from '../src/demo/local-plan.json' with { type: 'json' };

// support installs jsdom before testing-library is imported. Real clients and
// HTTP classes remain intact: only time, HTTP faults and delivery timing vary.
const { render, fireEvent, act, cleanup, within } = await import('@testing-library/react');
before(startHarness);
after(stopHarness);
afterEach(cleanup);
const timeout = { timeout: 10000 };
type View = ReturnType<typeof render>;
function mount(
  value: Composition,
  reference = plan as PlanReference,
  id: string | (() => string) = ' request-1 ',
) {
  return render(
    <Workspace
      {...value}
      runtimeLabel={value.mode}
      invocationNote="真实 HTTP / Agent / Domain 测试环境，无真实云。"
      localPlan={reference}
      nextRequestId={typeof id === 'string' ? () => id : id}
      now={() => stamp}
    />,
  );
}
function field(view: View, label: string | RegExp, text: string) {
  fireEvent.change(view.getByLabelText(label), { target: { value: text } });
}
async function send(view: View, text: string) {
  field(view, '你的问题', text);
  await act(async () => {
    const send = view.getByRole('button', { name: '发送请求' });
    fireEvent.click(send);
    fireEvent.click(send);
  });
}
async function settled(view: View) {
  await view.findByRole(
    'heading',
    { name: /^(回复已就绪|推荐结果|技能差距分析|备赛计划)$/ },
    timeout,
  );
  assert.equal(view.queryByRole('alert'), null);
}
function artifacts(value: Composition, index = value.deliveries.length - 1) {
  const delivery = value.deliveries[index];
  return validateArtifacts(delivery.runtime.response!, delivery.presentation);
}
function assertCounts(value: Composition, expected: number) {
  assert.equal(value.calls.length, expected);
  assert.equal(value.deliveries.length, expected);
  for (let i = 1; i < value.serverCounts.length; i++)
    assert.equal(value.serverCounts[i] - value.serverCounts[i - 1], 1);
  assert.ok(!JSON.stringify(value.calls).includes('HUMAN_APPROVED'));
}

const scenarioMatrix = [
  { name: 'Discovery', message: '赛事列表', model: 'ListCompetitionsOutput' },
  {
    name: 'Business Negative',
    message: '检查资格',
    student: 'local-graduate',
    competition: 'gcxl-engineering-practice-innovation',
    status: 'ineligible',
    model: 'EligibilityDecision',
  },
  {
    name: 'UNKNOWN',
    message: '检查资格',
    student: 'local-unknown',
    competition: 'gcxl-engineering-practice-innovation',
    status: 'unknown',
    model: 'EligibilityDecision',
  },
  {
    name: 'UNDETERMINED',
    message: '分析技能',
    student: 'local-graduate',
    competition: 'comap-mcm',
    status: 'undetermined',
    model: 'SkillGapDecision',
  },
  {
    name: 'Planning',
    message: '备赛计划',
    student: 'local-graduate',
    competition: 'comap-mcm',
    model: 'CompetitionPlan',
  },
  {
    name: 'Recommendation',
    message: '推荐',
    student: 'local-graduate',
    competition: 'gcxl-engineering-practice-innovation',
    model: 'RecommendationRankingResult',
  },
];
for (const scenario of scenarioMatrix) {
  test(`UI E2E matrix: ${scenario.name}, real Local/AgentArts authorities and semantic parity`, async () => {
    const traces = [];
    for (const mode of modes) {
      await resetScenario();
      const value = composition(mode, { sessionId: 'unrelated-transport-session' });
      const view = mount(value);
      if (scenario.student) field(view, /学生 ID/, scenario.student);
      if (scenario.competition) {
        field(view, '竞赛 ID', scenario.competition);
        field(view, '届次 ID', scenario.competition + '-2027');
      }
      await send(view, scenario.message);
      await settled(view);
      assertCounts(value, 1);
      assert.equal(value.calls[0].request!.request_id, 'request-1');
      assert.equal(value.deliveries[0].runtime.response!.request_id, 'request-1');
      assert.ok(artifacts(value).some((artifact) => artifact.model === scenario.model));
      if (scenario.model === 'SkillGapDecision')
        assert.ok(view.getByText('当前结论：暂无法完整判断'));
      else if (scenario.status) assert.ok(view.getAllByText(scenario.status).length);
      if (scenario.status === 'unknown')
        assert.ok(view.getAllByText(/返回结果保留不确定性/).length);
      for (const entry of view.container.querySelectorAll('[data-request-id]'))
        assert.equal(entry.getAttribute('data-request-id'), 'request-1');
      if (scenario.name === 'Business Negative') {
        const decision = artifacts(value).find((a) => a.model === 'EligibilityDecision')!;
        if (decision.model !== 'EligibilityDecision') throw Error('P5 result missing');
        const section = view.getByRole('region', { name: `结果 ${decision.ref.ref_id}` });
        assert.deepEqual(
          [
            ...section.querySelectorAll(':scope > .evidence-details > .evidence-list > li strong'),
          ].map((e) => e.textContent),
          decision.value.evidence!.map((e) => e.code),
        );
        const source = decision.value.evidence!.find((e) => e.source)!.source!;
        const link = view.getAllByRole('link', { name: source.source_url })[0];
        assert.equal(link.getAttribute('href'), source.source_url);
        assert.equal(link.getAttribute('rel'), 'noopener noreferrer');
        assert.ok(view.getAllByText(source.source_type).length);
        assert.ok(view.getAllByText(new RegExp(source.verification_status)).length);
        assert.ok(
          [...view.container.querySelectorAll('time')].some(
            (t) => t.dateTime === source.observed_at && t.title === source.observed_at,
          ),
        );
        assert.ok(view.getAllByRole('list', { name: '证据' }).length);
      }
      traces.push(semanticTrace(value, view.container));
      view.unmount();
    }
    assertParity(traces[0], traces[1]);
  });
}

test('UI E2E matrix: clarification request/resume, only requested fields, one invocation, full identity parity', async () => {
  const traces = [];
  for (const mode of modes) {
    await resetScenario();
    const value = composition(mode);
    const view = mount(value);
    await send(view, '赛事详情');
    const panel = await view.findByRole('region', { name: '补充所需信息' }, timeout);
    const pending = value.deliveries[0].runtime;
    assert.equal(pending.response!.outcome, 'NEEDS_CLARIFICATION');
    const input = within(panel).getByRole('textbox', { name: /竞赛 ID/ }) as HTMLInputElement;
    assert.equal(input.value, '');
    assert.equal(within(panel).getAllByRole('textbox').length, 1);
    assert.ok((view.getByLabelText('你的问题') as HTMLTextAreaElement).disabled);
    const stages = [semanticTrace(value, view.container)];
    fireEvent.change(input, { target: { value: 'huawei-ict' } });
    await act(async () => {
      fireEvent.submit(input.form!);
      fireEvent.submit(input.form!);
    });
    await settled(view);
    assertCounts(value, 2);
    assert.deepEqual(value.calls[1], {
      continuation_ref: pending.continuation_ref,
      clarification: {
        clarification_id: pending.response!.clarification!.clarification_id,
        source_request_id: 'request-1',
        values: { competition_id: 'huawei-ict' },
        submitted_at: stamp,
      },
    });
    stages.push(semanticTrace(value, view.container));
    traces.push(stages);
    view.unmount();
  }
  assertParity(traces[0], traces[1]);
});

for (const decision of ['APPROVE', 'REJECT'] as const) {
  test(`UI E2E matrix: approval wait/${decision}, no optimistic truth, one continuation and backend replay rejection`, async () => {
    const traces = [];
    for (const mode of modes) {
      await resetScenario();
      const hold = deferred(),
        arrived = deferred();
      let seen = 0;
      const value = composition(mode, {
        beforeDeliver: async () => {
          if (++seen === 2) {
            arrived.resolve();
            await hold.promise;
          }
        },
      });
      const view = mount(value);
      fireEvent.click(view.getByRole('checkbox', { name: /使用本地受控/ }));
      await send(view, '受控修订');
      const panel = await view.findByRole('region', { name: '请明确批准或拒绝' }, timeout);
      const pending = value.deliveries[0].runtime;
      const proposal = pending.response!.approval_request!;
      assert.equal(proposal.before_plan.version, plan.version);
      assert.equal(within(panel).queryByRole('textbox'), null);
      for (const ref of [
        proposal.approval_request_id,
        proposal.before_plan.plan_id,
        proposal.affected_scope_ref.ref_id,
      ])
        assert.ok(panel.textContent!.includes(ref));
      const stages = [semanticTrace(value, view.container)];
      await act(async () => {
        const button = within(panel).getByRole('button', { name: new RegExp(decision) });
        fireEvent.click(button);
        fireEvent.click(button);
      });
      await arrived.promise;
      for (const name of ['APPROVE', 'REJECT'])
        assert.ok(
          (within(panel).getByRole('button', { name: new RegExp(name) }) as HTMLButtonElement)
            .disabled,
        );
      assert.ok(view.getByText('正在等待回复…'));
      assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
      assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
      await act(async () => {
        hold.resolve();
      });
      await settled(view);
      assertCounts(value, 2);
      assert.deepEqual(value.calls[1], {
        continuation_ref: pending.continuation_ref,
        approval: {
          approval_request_id: proposal.approval_request_id,
          source_request_id: 'request-1',
          decision,
          submitted_at: stamp,
        },
      });
      const diff = artifacts(value).find((a) => a.model === 'PlanDiff');
      assert.equal(!!diff, decision === 'APPROVE');
      if (decision === 'APPROVE') {
        assert.ok(view.getByRole('region', { name: '方案变更' }));
        assert.ok(view.getByRole('heading', { name: '变更前' }));
        assert.ok(view.getByRole('heading', { name: '变更后' }));
        assert.ok(view.getByText('方案状态：执行中 → 已取消'));
      } else assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
      stages.push(semanticTrace(value, view.container));
      // Explicit adversarial replay is a test call, never a UI retry. It cannot
      // grant authority or yield a second mutation/PlanDiff even in same session.
      await assert.rejects(
        value.client.exchange(value.calls[1]),
        (error) =>
          error instanceof RuntimeClientError &&
          error.code === 'RUNTIME_ERROR' &&
          error.runtimeCode === 'CORE_VALIDATION_ERROR',
      );
      assert.ok(value.deliveries[2].runtime.response == null);
      assert.ok(value.deliveries[2].presentation == null);
      traces.push(stages);
      view.unmount();
    }
    assertParity(traces[0], traces[1]);
  });
}

for (const kind of ['clarification', 'approval'] as const) {
  test(`real hook + HTTP: stale ${kind} callback fails across workflow/request; modified identity fails before HTTP`, async () => {
    for (const mode of modes) {
      await resetScenario();
      const value = composition(mode);
      let api!: ReturnType<typeof useConversation>,
        sequence = 0;
      function Harness() {
        api = useConversation(
          value.client,
          () => `workflow-${++sequence}`,
          () => stamp,
        );
        return <output>{api.state.response?.outcome}</output>;
      }
      const view = render(<Harness />);
      const message = kind === 'approval' ? 'controlled revision' : 'detail';
      const context = kind === 'approval' ? { plan_ref: plan as PlanReference } : {};
      await act(async () => {
        await api.submit(message, '', context);
      });
      const old = api,
        token = api.state.interaction!.token;
      await act(async () => {
        api.startNew();
      });
      await act(async () => {
        await api.submit(message, '', context);
      });
      const result =
        kind === 'approval'
          ? await old.decide(token, 'APPROVE')
          : await old.clarify(token, { competition_id: 'huawei-ict' });
      assert.equal(result.accepted, false);
      assert.equal(value.calls.length, 2);
      assert.equal(api.state.interaction!.requestId, 'workflow-2');
      const current = api.state.interaction!;
      // Public state is client-controlled; neither plan version nor request IDs
      // may be changed to reuse the private interaction captured by the hook.
      if (current.kind === 'APPROVAL') current.proposal.before_plan.version++;
      else current.proposal.source_request_id = 'another-request';
      const tampered =
        kind === 'approval'
          ? await api.decide(current.token, 'APPROVE')
          : await api.clarify(current.token, { competition_id: 'huawei-ict' });
      assert.equal(tampered.accepted, false);
      assert.equal(value.calls.length, 2);
      view.unmount();
    }
  });
}

for (const category of ['CONTRACT_ERROR', 'RUNTIME_ERROR', 'TRANSPORT_ERROR'] as const) {
  test(`UI E2E matrix: ${category} remains separate from business truth, identical error UI and no retry`, async () => {
    const snapshots = [];
    for (const mode of modes) {
      await resetScenario();
      if (category === 'CONTRACT_ERROR')
        await fault(mode, { body: { runtime: { response: { outcome: 'invalid' } } } });
      if (category === 'TRANSPORT_ERROR')
        await fault(mode, { status: 503, body: { message: 'PRIVATE traceback secret' } });
      const value = composition(mode);
      // Actual server-side reference validation failure; not a fabricated result.
      const view = mount(
        value,
        category === 'RUNTIME_ERROR'
          ? ({ ...plan, version: 999 } as PlanReference)
          : (plan as PlanReference),
      );
      if (category === 'RUNTIME_ERROR')
        fireEvent.click(view.getByRole('checkbox', { name: /使用本地受控/ }));
      await send(view, category === 'RUNTIME_ERROR' ? 'controlled revision' : 'discovery');
      const alert = await view.findByRole('alert', {}, timeout);
      assert.ok(alert.textContent!.includes(category));
      assert.ok(!alert.textContent!.includes('PRIVATE'));
      assert.equal(view.queryByRole('heading', { name: '回复已就绪' }), null);
      assert.equal(view.container.querySelector('.business-status'), null);
      assert.equal(value.calls.length, 1);
      snapshots.push({
        error: alert.textContent,
        workflow: view.container.querySelector('.workflow-status')!.textContent,
      });
      view.unmount();
    }
    assertParity(snapshots[0], snapshots[1]);
  });
}

test('AgentArts auth/unavailable/timeout error UI does not create negative facts or retry', async () => {
  for (const faultValue of [{ status: 401 }, { status: 403 }, { status: 404 }, { delay: 0.8 }]) {
    await resetScenario();
    await fault('AGENTARTS', {
      ...faultValue,
      body: { message: 'PRIVATE confidential credential' },
    });
    const value = composition('AGENTARTS');
    const view = mount(value);
    await send(view, 'discovery');
    assert.ok(
      (await view.findByRole('alert', {}, timeout)).textContent!.includes('TRANSPORT_ERROR'),
    );
    assert.equal(value.calls.length, 1);
    assert.equal(view.container.querySelector('.business-status'), null);
    assert.ok(!view.container.textContent!.includes('PRIVATE'));
    view.unmount();
  }
});

test('real socket unavailable in either mode gives one TRANSPORT_ERROR, never UNKNOWN', async () => {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as { port: number }).port;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  for (const mode of modes) {
    const value = composition(mode, { baseUrl: `http://127.0.0.1:${port}` });
    const view = mount(value);
    await send(view, 'discovery');
    assert.ok(
      (await view.findByRole('alert', {}, timeout)).textContent!.includes('TRANSPORT_ERROR'),
    );
    assert.equal(value.calls.length, 1);
    assert.equal(view.container.querySelector('.business-status'), null);
    view.unmount();
  }
});

test('real response A cannot leak evidence/PlanDiff into next UI request B or a replacement mode/workspace', async () => {
  for (const mode of modes) {
    await resetScenario();
    const hold = deferred(),
      arrived = deferred();
    let signal: AbortSignal | null | undefined;
    const value = composition(mode, {
      beforeDeliver: async (_body, currentSignal) => {
        signal = currentSignal;
        arrived.resolve();
        await hold.promise;
      },
    });
    const old = mount(value, plan as PlanReference, 'old-request');
    await send(old, 'detail');
    await arrived.promise;
    old.unmount();
    assert.ok(signal?.aborted);
    const next = composition(mode === 'LOCAL' ? 'AGENTARTS' : 'LOCAL');
    const view = mount(next, plan as PlanReference, 'new-request');
    await send(view, 'discovery');
    await settled(view);
    await act(async () => {
      hold.resolve();
    });
    assert.equal(view.queryByRole('region', { name: '补充所需信息' }), null);
    for (const entry of view.container.querySelectorAll('[data-request-id]'))
      assert.equal(entry.getAttribute('data-request-id'), 'new-request');
    assert.equal(value.calls.length, 1);
    assert.equal(next.calls.length, 1);
    view.unmount();

    // Same mounted conversation keeps historical entries but result slot must
    // clear A while B is pending, and bind only B after resolution.
    const live = composition(mode);
    let sequence = 0;
    const conversation = mount(live, plan as PlanReference, () => `history-${++sequence}`);
    field(conversation, /学生 ID/, 'local-graduate');
    field(conversation, '竞赛 ID', 'gcxl-engineering-practice-innovation');
    field(conversation, '届次 ID', 'gcxl-engineering-practice-innovation-2027');
    await send(conversation, 'eligibility');
    await settled(conversation);
    const oldResult = conversation.container.querySelector('.result-slot')!.textContent;
    fireEvent.click(conversation.getByRole('button', { name: '开始新请求' }));
    assert.equal(conversation.container.querySelector('.result-slot .result-artifact'), null);
    field(conversation, /学生 ID/, '');
    field(conversation, '竞赛 ID', '');
    field(conversation, '届次 ID', '');
    await send(conversation, 'discovery');
    await settled(conversation);
    assert.notEqual(conversation.container.querySelector('.result-slot')!.textContent, oldResult);
    assert.equal(conversation.container.querySelector('.result-slot .evidence-list'), null);
    assert.equal(conversation.queryByRole('region', { name: '方案变更' }), null);
    assert.equal(live.deliveries[1].runtime.response!.request_id, 'history-2');
    conversation.unmount();
  }
});

test('two mounted frontend workflows keep independent request/HITL/artifact state under reversed delivery order', async () => {
  for (const mode of modes) {
    await resetScenario();
    const hold = deferred(),
      arrived = deferred();
    const left = composition(mode, {
      sessionId: 'shared-correlation',
      beforeDeliver: async () => {
        arrived.resolve();
        await hold.promise;
      },
    });
    const right = composition(mode, { sessionId: 'shared-correlation' });
    const a = mount(left, plan as PlanReference, 'independent-a');
    const b = mount(right, plan as PlanReference, 'independent-b');
    // Separate workflow containers model independent frontend roots. Global HTML
    // labels are not used to choose controls belonging to the other root.
    fireEvent.change(a.container.querySelector('textarea')!, { target: { value: 'detail' } });
    await act(async () => {
      fireEvent.submit(a.container.querySelector('form')!);
    });
    await arrived.promise;
    fireEvent.change(b.container.querySelector('textarea')!, { target: { value: 'discovery' } });
    await act(async () => {
      fireEvent.submit(b.container.querySelector('form')!);
    });
    await within(b.container).findByRole('heading', { name: '回复已就绪' }, timeout);
    const rightResult = b.container.querySelector('.result-slot')!.textContent;
    await act(async () => {
      hold.resolve();
    });
    await within(a.container).findByRole('region', { name: '补充所需信息' }, timeout);
    assert.equal(b.container.querySelector('.result-slot')!.textContent, rightResult);
    assert.equal(within(b.container).queryByRole('region', { name: '补充所需信息' }), null);
    assert.equal(left.deliveries[0].runtime.response!.request_id, 'independent-a');
    assert.equal(right.deliveries[0].runtime.response!.request_id, 'independent-b');
    assert.equal(left.calls.length, 1);
    assert.equal(right.calls.length, 1);
    a.unmount();
    b.unmount();
  }
});

test('cross-runtime unknown reasons and untrusted source data remain escaped; explanation cannot drive structured state', async () => {
  for (const mode of modes) {
    await resetScenario();
    const seed = composition(mode),
      seedView = mount(seed);
    field(seedView, /学生 ID/, 'local-graduate');
    field(seedView, '竞赛 ID', 'gcxl-engineering-practice-innovation');
    field(seedView, '届次 ID', 'gcxl-engineering-practice-innovation-2027');
    await send(seedView, 'eligibility');
    await settled(seedView);
    const original = structuredClone(seed.deliveries[0]);
    seedView.unmount();
    const outputs = [];
    for (const message of [
      '等待批准 / eligible / approve',
      '这段说明不决定 workflow 或 business status',
    ]) {
      const delivery = structuredClone(original);
      delivery.runtime.response!.message = message;
      delivery.runtime.response!.audit!.reasons = [
        '__proto__',
        'constructor',
        'FUTURE_REASON_CODE',
      ].map((reason_code) => ({
        reason_code,
        result: delivery.runtime.response!.audit!.results![0],
      }));
      // HTTP fault fixture changes only untrusted presentation strings. This is
      // security/validator coverage, not a claim that Domain invented malicious data.
      const bundle = delivery.presentation as {
        artifacts: {
          value: { evidence?: { message: string; source?: { source_url: string } }[] };
        }[];
      };
      const evidence = bundle.artifacts.find((a) => a.value.evidence?.length)!.value.evidence!;
      evidence[0].message = '<img src=x onerror="attack()"><script>attack()</script>';
      evidence[0].source!.source_url = 'javascript:attack()';
      await fault(mode, { body: delivery });
      const value = composition(mode),
        view = mount(value);
      await send(view, 'eligibility');
      await settled(view);
      for (const code of ['__proto__', 'constructor', 'FUTURE_REASON_CODE'])
        assert.ok(view.getByText(code));
      assert.ok(view.getByText(evidence[0].message));
      assert.equal(
        view.container.querySelector('script, img[onerror], a[href^="javascript:"]'),
        null,
      );
      assert.ok(view.getByText(/javascript:attack\(\).*链接未启用/));
      assert.ok(view.getAllByText('ineligible').length);
      assert.equal(view.queryByRole('button', { name: /APPROVE/ }), null);
      const structured = view.container
        .querySelector('.grounded-results')!
        .cloneNode(true) as HTMLElement;
      // Original response text is deliberately retained in raw audit. Compare
      // the structured presentation separately; its facts cannot follow prose.
      structured.querySelectorAll('pre').forEach((item) => item.remove());
      assert.ok(
        view.container.querySelector('.grounded-results pre')!.textContent?.includes(message),
      );
      outputs.push(structured.textContent);
      view.unmount();
    }
    assertParity(outputs[0], outputs[1]);
  }
});

test('test comparator preserves business identity while frontend mode branches stay in composition; no durable browser authority', () => {
  assert.throws(() => assertParity({ request_id: 'a' }, { request_id: 'b' }));
  for (const name of ['Workspace.tsx', 'useConversation.ts', 'state.ts', 'HitlPanel.tsx']) {
    const source = readFileSync(`${root}/frontend/src/workspace/${name}`, 'utf8');
    assert.ok(
      !/AGENTARTS|LocalRuntimeTransport|AgentArtsRuntimeTransport|localStorage|sessionStorage|tools\/call/.test(
        source,
      ),
    );
  }
  const comparator = readFileSync(`${root}/frontend/tests/e2e/support.ts`, 'utf8');
  assert.ok(comparator.includes('semanticTrace'));
});
