import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import fixtures from '../src/demo/result-fixtures.json' with { type: 'json' };
import runtimeFixtures from './fixtures/runtime.json' with { type: 'json' };
import { RuntimeInvocationClient } from '../src/runtime/client.ts';
import { FakeRuntimeTransport } from '../src/runtime/fake.ts';
import type { AgentResponse } from '../src/runtime/generated/contracts.ts';
import { ResultPanel } from '../src/results/ResultPanel.tsx';
import { ReasonList } from '../src/results/ReasonList.tsx';
import { SourceLink } from '../src/results/SourceMetadata.tsx';
import { validateArtifacts } from '../src/results/artifacts.ts';
import type { ArtifactReader } from '../src/results/artifacts.ts';

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

async function preset(name: keyof typeof fixtures) {
  const value = fixtures[name];
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: value.runtime }]);
  const client = new RuntimeInvocationClient(fake, {
    mode: 'LOCAL',
    baseUrl: 'http://localhost:0',
  });
  const response = await client.invoke(runtimeFixtures.request);
  return { response, bundle: structuredClone(value.bundle), fake };
}

test('completed structured result shows status, identity, canonical reason, evidence and verified provenance', async () => {
  const { response, bundle } = await preset('eligible');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByRole('heading', { name: '回复已就绪' }));
  assert.ok(view.getAllByText('符合已声明资格规则').length);
  assert.ok(view.getAllByText('RULE_SATISFIED').length);
  assert.ok(view.getAllByText(/Synthetic reviewed rule/).length);
  assert.ok(view.getByText(/竞赛：competition · 届次：edition/));
  const link = view.getByRole('link', { name: 'https://example.org/synthetic-rules' });
  assert.equal(link.getAttribute('href'), 'https://example.org/synthetic-rules');
  assert.equal(link.getAttribute('rel'), 'noopener noreferrer');
  assert.ok(view.getByText(/已核验/));
  const time = view.container.querySelector('time')!;
  assert.equal(time.dateTime, '2030-01-01T00:00:00Z');
  assert.equal(time.title, '2030-01-01T00:00:00Z');
  assert.equal(view.queryByRole('alert'), null);
});

for (const name of ['unknown', 'undetermined', 'ineligible', 'no_gap'] as const) {
  test(`${name} stays an explicit business outcome, not a system error`, async () => {
    const { response, bundle } = await preset(name);
    const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
    assert.ok(view.getAllByText(name).length);
    if (name === 'unknown' || name === 'undetermined')
      assert.ok(view.getAllByText(/不能据此认定符合、不符合/).length);
    assert.equal(view.queryByRole('alert'), null);
  });
}

test('unknown reason codes remain visible without inferred labels or reasons', () => {
  const view = render(<ReasonList codes={['FUTURE_REASON_CODE']} />);
  assert.ok(view.getByText('FUTURE_REASON_CODE'));
  view.rerender(<ReasonList codes={[]} />);
  assert.ok(view.getByText('未提供理由代码。'));
  assert.equal(view.queryByText('FUTURE_REASON_CODE'), null);
});

for (const code of [
  '__proto__',
  'constructor',
  'toString',
  'valueOf',
  'hasOwnProperty',
  'isPrototypeOf',
]) {
  test(`prototype property reason ${code} remains a valid response and renders the safe fallback`, async () => {
    const body = structuredClone(fixtures.eligible.runtime);
    body.response.audit.reasons[0].reason_code = code;
    const fake = new FakeRuntimeTransport('LOCAL', [{ body }]);
    const client = new RuntimeInvocationClient(fake, {
      mode: 'LOCAL',
      baseUrl: 'http://localhost:0',
    });
    const response = await client.invoke(runtimeFixtures.request);
    assert.equal(response.audit?.reasons?.[0].reason_code, code);
    const view = render(<ResultPanel response={response} />);
    const reasons = within(view.getByRole('list', { name: '关联理由' }));
    assert.ok(reasons.getByText('返回的理由代码'));
    assert.ok(reasons.getByText(code));
    assert.equal(view.queryByRole('alert'), null);
    assert.equal(fake.calls.length, 1);
  });
}

test('known own-key reason preserves its existing human-readable label and code', () => {
  const view = render(<ReasonList codes={['RULE_SATISFIED']} />);
  assert.ok(view.getByText('满足已声明规则'));
  assert.ok(view.getByText('RULE_SATISFIED'));
  assert.equal(view.queryByText('返回的理由代码'), null);
});

test('recommendation score and components are displayed as supplied without calculation', async () => {
  const { response, bundle } = await preset('recommendation');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByText('后端适配分：0.8'));
  assert.ok(view.getByRole('list', { name: '评分分项' }).textContent?.includes('goal-fit · 0.8'));
  assert.ok(view.getByText('GOAL_SIGNAL_PRESENT'));
});

test('standalone source artifact preserves provided type, URL and verified status', async () => {
  const { response, bundle } = await preset('verified_source');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByText('manual'));
  assert.ok(view.getByText(/已核验/));
  assert.ok(view.getByRole('link', { name: 'https://example.org/synthetic-rules' }));
});

test('evidence is escaped data and sources remain pending or unavailable', async () => {
  const { response } = await preset('pending_source');
  const bundle = structuredClone(fixtures.pending_source.bundle);
  bundle.artifacts[0].value.message = '<img src=x onerror="alert(1)"><script>attack()</script>';
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByText(/<img src=x/));
  assert.equal(view.container.querySelector('img,script'), null);
  assert.ok(view.getByText(/待核验/));
  assert.equal(view.queryByText(/已核验/), null);
  const partial = await preset('partial_evidence');
  view.rerender(<ResultPanel response={partial.response} readArtifacts={() => partial.bundle} />);
  assert.ok(view.getByText('未提供来源元数据。'));
  assert.equal(view.queryByRole('link'), null);
});

for (const url of [
  'javascript:alert(1)',
  'data:text/html,<script>x</script>',
  'file:///private',
  'https://user:secret@example.org/',
]) {
  test(`unsafe source is not an active link: ${url.split(':')[0]}`, () => {
    const view = render(<SourceLink url={url} />);
    assert.equal(view.queryByRole('link'), null);
    assert.ok(view.getByText(/链接未启用/));
  });
}

test('PlanDiff displays supplied removed/added/changed collection content, trigger and exact before/after identity', async () => {
  const { response, bundle } = await preset('plan_diff');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  const before = view.getByRole('region', { name: '变更前里程碑' });
  const after = view.getByRole('region', { name: '变更后里程碑' });
  assert.ok(within(before).getByText('被移除的任务'));
  assert.equal(within(after).queryByText('被移除的任务'), null);
  assert.ok(within(after).getByText('新增的任务'));
  assert.ok(within(before).getByText('保留并更新的任务'));
  assert.ok(within(after).getByText('更新后的任务'));
  assert.ok(view.getByRole('list', { name: '触发事件' }));
  assert.ok(view.getByRole('list', { name: '重规划证据引用' }));
  assert.ok(view.getByText(/契约未提供逐项新增/));
});

test('no-op/rejected result keeps normal outcome and renders supplied empty diff', async () => {
  const { response, bundle } = await preset('no_change');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByText('保持当前方案'));
  assert.ok(view.getByText(/返回的 Diff 未声明任何变化/));
  assert.equal(view.queryByRole('alert'), null);
});

test('before/after Plan references without an artifact never produce a client-computed diff', async () => {
  const { response } = await preset('plan_diff');
  const view = render(<ResultPanel response={response} />);
  assert.ok(view.getByRole('list', { name: '方案引用' }));
  assert.equal(view.queryByRole('region', { name: '方案变更' }), null);
  assert.ok(view.getByText(/不会从说明推断业务状态或计算方案差异/));
});

test('request/ref/model/schema mismatches fail closed and do not leak old artifacts', async () => {
  const { response, bundle } = await preset('eligible');
  for (const invalid of [
    { ...bundle, request_id: 'another-request' },
    {
      ...bundle,
      artifacts: [{ ...bundle.artifacts[0], ref: { kind: 'ELIGIBILITY_RESULT', ref_id: 'other' } }],
    },
    { ...bundle, artifacts: [{ ...bundle.artifacts[0], model: 'PlanDiff' }] },
    { ...bundle, artifacts: [{ ...bundle.artifacts[0], value: { status: 'eligible' } }] },
    { ...bundle, artifacts: [...bundle.artifacts, ...bundle.artifacts] },
  ])
    assert.throws(() => validateArtifacts(response, invalid));
  const view = render(
    <ResultPanel response={response} readArtifacts={() => ({ ...bundle, request_id: 'other' })} />,
  );
  assert.ok(view.getByRole('alert').textContent?.includes('ARTIFACT_CONTRACT_ERROR'));
  assert.equal(view.queryByText(/Synthetic reviewed rule/), null);
});

test('new response clears old evidence even when an obsolete provider returns it', async () => {
  const a = await preset('eligible');
  const b = await preset('partial_evidence');
  const reader = () => a.bundle;
  const view = render(<ResultPanel response={a.response} readArtifacts={reader} />);
  assert.ok(view.getAllByText(/Synthetic reviewed rule/).length);
  view.rerender(
    <ResultPanel response={{ ...b.response, request_id: 'request-2' }} readArtifacts={reader} />,
  );
  assert.equal(view.queryByText(/Synthetic reviewed rule/), null);
  assert.ok(view.getByRole('alert'));
});

test('explanation wording does not affect structured rendering; rendering invokes no Runtime', async () => {
  const { response, bundle, fake } = await preset('eligible');
  const reader = () => bundle;
  const view = render(<ResultPanel response={response} readArtifacts={reader} />);
  const before = view.container.textContent;
  view.rerender(
    <ResultPanel
      response={{ ...response, message: 'UNKNOWN INELIGIBLE 已批准，可以修改方案' }}
      readArtifacts={reader}
    />,
  );
  assert.equal(view.container.textContent, before);
  assert.equal(fake.calls.length, 1);
});

test('pending approval never renders final artifacts and never resolves them', async () => {
  const { bundle } = await preset('plan_diff');
  let reads = 0;
  const view = render(
    <ResultPanel
      response={runtimeFixtures.approval.response as AgentResponse}
      readArtifacts={() => {
        reads++;
        return bundle;
      }}
    />,
  );
  assert.equal(view.container.textContent, '');
  assert.equal(reads, 0);
});

test('Workspace consumes fake result through client; artifact rendering adds no calls and explanation is shown verbatim', async () => {
  const fixture = fixtures.eligible;
  const fake = new FakeRuntimeTransport('LOCAL', [{ body: fixture.runtime }]);
  const client = new RuntimeInvocationClient(fake, {
    mode: 'LOCAL',
    baseUrl: 'http://localhost:0',
  });
  const readArtifacts: ArtifactReader = () => fixture.bundle;
  const view = render(
    <Workspace client={client} nextRequestId={() => 'request-1'} readArtifacts={readArtifacts} />,
  );
  fireEvent.change(view.getByRole('textbox', { name: '你的问题' }), {
    target: { value: '请检查' },
  });
  await act(async () => {
    fireEvent.click(view.getByRole('button', { name: '发送请求' }));
  });
  assert.equal(fake.calls.length, 1);
  assert.ok(view.getByText(fixture.runtime.response.message));
  assert.ok(view.getByRole('list', { name: '证据' }));
  assert.ok(view.getByRole('link', { name: 'https://example.org/synthetic-rules' }));
});
