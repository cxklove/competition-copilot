import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import fixtures from './fixtures/planning-workspace.json' with { type: 'json' };
import type { PlanningWorkspaceProjection } from '../src/results/generated/artifacts.ts';
import type { AgentRequest, AgentResponse } from '../src/runtime/generated/contracts.ts';
import type { InvocationClient } from '../src/workspace/useConversation.ts';

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/' });
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
const { render, cleanup, fireEvent, waitFor, within } = await import('@testing-library/react');
const { PlanningWorkspace, PlanningWorkspaceView } =
  await import('../src/workspace/PlanningWorkspace.tsx');
afterEach(cleanup);

const fixture = (name: keyof typeof fixtures) =>
  structuredClone(fixtures[name]) as unknown as PlanningWorkspaceProjection;

for (const [status, label] of [
  ['CURRENT', '基于当前画像'],
  ['UNKNOWN', '画像版本未记录，无法确认'],
] as const)
  test(`formal Plan freshness ${status} remains visible independently of current advisory`, () => {
    const value = fixture('stale_plan');
    value.plan_freshness.status = status;
    const view = render(
      <PlanningWorkspaceView value={value} act={() => {}} detail={() => {}} profile={() => {}} />,
    );
    assert.ok(within(view.getByRole('region', { name: '备赛概览' })).getByText(label));
    assert.ok(
      within(view.getByRole('region', { name: '推荐准备任务' })).getByText(
        /^基于本次读取的当前画像/,
      ),
    );
  });

test('original Plan stages are schema-validated and rendered only under the folded audit', () => {
  const value = fixture('stale_plan');
  const view = render(
    <PlanningWorkspaceView value={value} act={() => {}} detail={() => {}} profile={() => {}} />,
  );
  const audit = view.getByRole('region', { name: '计划原文与审计' });
  const details = audit.querySelector('details')!;
  assert.equal(details.open, false);
  assert.ok(within(details).getByRole('heading', { name: /阶段 1/, hidden: true }));
  assert.equal(
    within(view.getByRole('region', { name: '推荐准备任务' })).queryAllByRole('heading', {
      name: /阶段/,
    }).length,
    0,
  );
  assert.equal([...details.querySelectorAll('pre')].at(-1)!.textContent, value.plan_original_json);
});

test('workspace partitions current suggestions from a stale unchanged Plan and hides audit refs', () => {
  const value = fixture('stale_plan');
  const before = JSON.stringify(value);
  const calls: string[] = [];
  const view = render(
    <PlanningWorkspaceView
      value={value}
      act={(a) => calls.push(a.intent)}
      detail={() => calls.push('DETAIL')}
      profile={() => calls.push('PROFILE')}
    />,
  );
  for (const label of [
    '备赛概览',
    '已确认约束',
    '推荐准备任务',
    '待确认事项',
    '时间参考',
    '计划原文与审计',
    '备赛操作',
  ])
    assert.ok(view.getByRole('region', { name: label }));
  assert.ok(view.getByText('基于较早画像'));
  assert.ok(view.getByText(/这些建议独立于正式计划/));
  assert.equal(
    within(view.getByRole('region', { name: '推荐准备任务' })).getAllByText('建议').length,
    3,
  );
  assert.ok(
    within(view.getByRole('region', { name: '待确认事项' })).getByText(/所需能力等级尚未明确/),
  );
  assert.ok(
    within(view.getByRole('region', { name: '待确认事项' })).getByText(/当前技能要求覆盖仍不完整/),
  );
  assert.ok(
    view
      .getByRole('region', { name: '计划原文与审计' })
      .querySelector('pre')
      ?.textContent?.includes('Original'),
  );
  assert.equal(view.container.querySelectorAll('details[open]').length, 0);
  assert.equal(view.container.querySelectorAll('input[type="checkbox"]').length, 0);
  assert.deepEqual(calls, []);
  fireEvent.click(view.getByRole('button', { name: '重新生成计划' }));
  fireEvent.click(view.getByRole('button', { name: '重新分析技能差距' }));
  fireEvent.click(view.getByRole('button', { name: '查看赛事详情' }));
  fireEvent.click(view.getByRole('button', { name: '完善个人画像' }));
  assert.deepEqual(calls, ['BUILD_PLAN', 'ANALYZE_SKILL_GAP', 'DETAIL', 'PROFILE']);
  assert.equal(JSON.stringify(value), before);
});

for (const hours of [null, 0, 7.5, 10, 168])
  test(`weekly hours ${hours} is display context, never task allocation`, () => {
    const value = fixture('without_plan');
    value.profile_context.weekly_available_hours = hours;
    const view = render(
      <PlanningWorkspaceView value={value} act={() => {}} detail={() => {}} profile={() => {}} />,
    );
    assert.ok(
      view.getByText(`当前画像每周可投入：${hours == null ? '尚未填写' : `${hours} 小时 / 周`}`),
    );
    assert.ok(view.getByText('尚未生成或选择正式备赛计划'));
    assert.ok(view.getByRole('button', { name: '生成备赛计划' }));
    assert.ok(view.getByText('个人目标：My free-text goal'));
  });

test('time candidates stay quotes with scope/precision/source, never confirmed deadlines', () => {
  const value = fixture('candidate');
  const view = render(
    <PlanningWorkspaceView value={value} act={() => {}} detail={() => {}} profile={() => {}} />,
  );
  const times = within(view.getByRole('region', { name: '时间参考' }));
  assert.ok(times.getAllByText('官方已公布 · 待核验').length > 0);
  assert.ok(times.getAllByText('届次级依据').length > 0);
  assert.ok(times.getByText(/各赛区报名截止: 2026-11-30/));
  assert.ok(times.getByText('信息粒度：日期'));
  assert.ok(times.getAllByText(/可用于计划和自动决策/).length > 0);
  assert.equal(
    view.getByRole('region', { name: '时间参考' }).querySelectorAll('time').length,
    value.time_references.filter((t) => t.kind === 'VERIFIED').length +
      view.getByRole('region', { name: '时间参考' }).querySelectorAll('.source-metadata time')
        .length,
  );
  assert.ok(view.getByText('暂无当前精确范围的准备建议；不会根据赛事名称猜测技能要求。'));
});

function environment(value = fixture('without_plan')) {
  const calls: AgentRequest[] = [];
  const bundles = new Map<string, unknown>();
  const client: InvocationClient = {
    async exchange({ request }) {
      assert.ok(request);
      calls.push(request);
      const ref = { kind: 'TOOL_RESULT' as const, ref_id: request.request_id + '/result' };
      const response: AgentResponse = {
        request_id: request.request_id,
        intent: 'GET_PLANNING_WORKSPACE',
        outcome: 'COMPLETED',
        message: 'Read',
        audit: { results: [ref], reasons: [] },
      };
      bundles.set(response.request_id, {
        request_id: response.request_id,
        artifacts: [{ model: 'PlanningWorkspaceProjection', ref, value }],
      });
      return { response };
    },
    async invoke() {
      throw Error('Use exchange');
    },
  };
  return { calls, client, readArtifacts: (r: AgentResponse) => bundles.get(r.request_id) };
}

test('explicit read only, no plan does not generate P8, refresh reads once', async () => {
  const env = environment();
  const view = render(
    <PlanningWorkspace
      {...env}
      active
      context={{ student_id: 'student', competition_id: 'comap-mcm', edition_id: 'comap-mcm-2027' }}
      profileToken=""
      disabled={false}
      act={() => {}}
      detail={() => {}}
      profile={() => {}}
      center={() => {}}
    />,
  );
  await view.findByText('尚未生成或选择正式备赛计划');
  assert.deepEqual(
    env.calls.map((c) => c.intent),
    ['GET_PLANNING_WORKSPACE'],
  );
  fireEvent.click(view.getByRole('button', { name: '刷新备赛资料' }));
  await waitFor(() => assert.equal(env.calls.length, 2));
  assert.ok(env.calls.every((c) => !c.context?.track_id));
});

test('no target and inactive views never read or choose a target', () => {
  const env = environment();
  const view = render(
    <PlanningWorkspace
      {...env}
      active
      context={{ student_id: 'student' }}
      profileToken=""
      disabled={false}
      act={() => {}}
      detail={() => {}}
      profile={() => {}}
      center={() => {}}
    />,
  );
  assert.ok(view.getByText('尚未选择当前赛事'));
  assert.ok(view.getByRole('button', { name: '前往赛事中心' }));
  assert.equal(env.calls.length, 0);
});

test('mismatched read target stays an error, not pending information', async () => {
  const env = environment();
  const view = render(
    <PlanningWorkspace
      {...env}
      active
      context={{ student_id: 'student', competition_id: 'huawei-ict' }}
      profileToken=""
      disabled={false}
      act={() => {}}
      detail={() => {}}
      profile={() => {}}
      center={() => {}}
    />,
  );
  await view.findByRole('alert');
  assert.ok(view.queryByRole('region', { name: '推荐准备任务' }) === null);
});
