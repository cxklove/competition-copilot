import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import type { AgentRequest, AgentResponse } from '../src/runtime/generated/contracts.ts';
import type {
  MyCompetitionProjection,
  MyCompetitionTarget,
  DerivedSummary,
} from '../src/results/generated/artifacts.ts';
import type { InvocationClient } from '../src/workspace/useConversation.ts';
import {
  MyCompetitionsProvider,
  MyCompetitionsPage,
  AddMyCompetitionButton,
  myCompetitionError,
} from '../src/workspace/MyCompetitions.tsx';
import { CandidateCard } from '../src/results/RecommendationResults.tsx';
import presets from '../src/demo/result-fixtures.json' with { type: 'json' };
import { businessInvocations } from './runtimeTrace.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const name of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'Node',
  'Event',
  'MutationObserver',
] as const)
  Object.defineProperty(globalThis, name, {
    value: name === 'window' ? dom.window : dom.window[name],
    configurable: true,
  });
Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
  value: true,
  configurable: true,
  writable: true,
});
const { render, fireEvent, cleanup, waitFor } = await import('@testing-library/react');
afterEach(cleanup);

const target: MyCompetitionTarget = {
  competition_id: 'comap-mcm',
  edition_id: 'comap-mcm-2027',
  track_id: null,
};
function row(state: 'SAVED' | 'PREPARING' = 'SAVED', suffix = ''): MyCompetitionProjection {
  const exact = { ...target, edition_id: target.edition_id + suffix };
  const relationship = {
    ...exact,
    student_id: 'student',
    relationship_id: 'relationship' + suffix,
    state,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
  const ref = {
    relationship_id: relationship.relationship_id,
    student_id: 'student',
    target: exact,
    version: 1,
    content_digest: 'a'.repeat(64),
    host_scope: 'host',
  };
  const summary = (label: string): DerivedSummary => ({
    availability: 'NOT_ANALYZED',
    label,
    profile_freshness: {
      status: 'UNKNOWN',
      reason: 'RESULT_PROFILE_REFERENCE_UNKNOWN',
      input_profile_ref: null,
      current_profile_ref: null,
    },
  });
  return {
    relationship_ref: ref,
    student_id: 'student',
    target: exact,
    relationship_state: state,
    display_identity: {
      competition_name: 'COMAP Mathematical Contest in Modeling',
      edition_name: `2027 ${suffix}`,
      track_name: null,
    },
    eligibility_summary: summary('尚未判断'),
    skill_gap_summary: summary('尚未分析'),
    plan_summary: { ...summary('尚未关联正式计划'), availability: 'NOT_SELECTED' },
    planning_summary: {
      availability: 'AVAILABLE',
      confirmed_constraints_count: 1,
      pending_confirmations_count: 2,
      has_advisory: true,
    },
    time_summary: { availability: 'UNKNOWN', references: [] },
    next_action: {
      policy_version: 'next-action-v1',
      kind: 'ELIGIBILITY',
      label: '判断参赛资格',
      reason_code: 'ELIGIBILITY_NOT_ANALYZED',
      target: exact,
    },
    section_availability: [],
    persistence_boundary: 'HOST_MEMORY',
    audit: { relationship, relationship_ref: ref },
  };
}

function fixture(initial: MyCompetitionProjection[] = []) {
  let items = structuredClone(initial);
  const requests: AgentRequest[] = [];
  const bodies = new Map<string, unknown>();
  const client: InvocationClient = {
    async exchange(envelope) {
      const request = envelope.request!;
      requests.push(structuredClone(request));
      const reference = { kind: 'TOOL_RESULT' as const, ref_id: request.request_id + '/result' };
      let model: string, value: unknown;
      if (request.intent === 'GET_MY_COMPETITIONS') {
        model = 'MyCompetitionsProjection';
        value = { student_id: 'student', competitions: items, persistence_boundary: 'HOST_MEMORY' };
      } else {
        const command = request.my_competition_command!;
        const existing = items.find((r) => r.target.edition_id === command.target.edition_id);
        const next = existing ? structuredClone(existing) : row();
        if (!existing) {
          next.target = command.target;
          next.relationship_ref.target = command.target;
          next.audit.relationship_ref.target = command.target;
          Object.assign(next.audit.relationship, command.target);
        }
        if (command.operation === 'remove') items = items.filter((r) => r !== existing);
        else if (command.operation === 'update') {
          next.relationship_state = command.state!;
          next.audit.relationship.state = command.state!;
          next.audit.relationship.version += 1;
          next.relationship_ref.version += 1;
          next.audit.relationship_ref.version = next.relationship_ref.version;
          items = items.map((r) => (r === existing ? next : r));
        } else items = [...items, next];
        model = 'MyCompetitionMutationResult';
        value = {
          snapshot: next.audit,
          removed: command.operation === 'remove',
          persistence_boundary: 'HOST_MEMORY',
        };
      }
      const response: AgentResponse = {
        request_id: request.request_id,
        intent: request.intent!,
        outcome: 'COMPLETED',
        message: 'Returned',
        audit: { results: [reference], reasons: [] },
      };
      bodies.set(response.request_id, {
        request_id: response.request_id,
        artifacts: [{ ref: reference, model, value: structuredClone(value) }],
      });
      return { response, error: null };
    },
    async invoke(request, options) {
      return (await this.exchange({ request }, options)).response!;
    },
  };
  return {
    client,
    requests,
    readArtifacts: (response: AgentResponse) => bodies.get(response.request_id),
  };
}

function assertNoAutomaticAnalysis(env: ReturnType<typeof fixture>) {
  assert.deepEqual(
    businessInvocations({
      calls: env.requests.map((request) => ({ request })),
      responses: [],
    }),
    [],
  );
}

function page(
  env: ReturnType<typeof fixture>,
  children?: React.ReactNode,
  selected: string[] = [],
) {
  return render(
    <MyCompetitionsProvider
      context={{ student_id: 'student' }}
      {...env}
      disabled={false}
      token="stable"
    >
      {children ?? (
        <MyCompetitionsPage
          active
          setCurrent={(r) => selected.push(r.target.edition_id)}
          detail={() => {}}
          act={() => selected.push('explicit-action')}
          browse={() => selected.push('browse')}
          recommend={() => selected.push('recommend')}
        />
      )}
    </MyCompetitionsProvider>,
  );
}

test('empty state and persistence notice use only an explicit workspace READ', async () => {
  const env = fixture();
  const view = page(env);
  await view.findByText('还没有加入任何赛事');
  assert.match(view.container.textContent!, /服务重启后不会保留/);
  assertNoAutomaticAnalysis(env);
  assert.deepEqual(
    env.requests.map((r) => r.intent),
    ['GET_MY_COMPETITIONS'],
  );
});

test('authoritative identity, separate summaries, filters and explicit set-current', async () => {
  const env = fixture([row(), row('PREPARING', '-other')]);
  const selected: string[] = [];
  const view = page(env, undefined, selected);
  await view.findAllByRole('heading', { name: 'COMAP Mathematical Contest in Modeling' });
  assert.equal(view.container.querySelectorAll('article').length, 2);
  assert.match(view.container.textContent!, /2027/);
  assert.match(view.container.textContent!, /尚未判断/);
  assert.match(view.container.textContent!, /尚未分析/);
  assert.match(view.container.textContent!, /尚未关联正式计划/);
  assert.match(view.container.textContent!, /正式时间尚未确认/);
  fireEvent.click(view.getByRole('button', { name: '准备中' }));
  assert.equal(view.container.querySelectorAll('article').length, 1);
  fireEvent.click(view.getByRole('button', { name: '设为当前赛事' }));
  assert.deepEqual(selected, ['comap-mcm-2027-other']);
  assertNoAutomaticAnalysis(env);
  assert.deepEqual(
    env.requests.map((r) => r.intent),
    ['GET_MY_COMPETITIONS'],
  );
  fireEvent.click(view.getByRole('button', { name: '已关注' }));
  assert.equal(view.container.querySelectorAll('article').length, 1);
  fireEvent.click(view.getByRole('button', { name: '判断参赛资格' }));
  assert.equal(selected.at(-1), 'explicit-action');
  fireEvent.click(view.getByRole('button', { name: '全部' }));
  assert.equal(view.container.querySelectorAll('article').length, 2);
});

test('state edit and confirmed removal roundtrip through backend projections', async () => {
  const env = fixture([row()]);
  const view = page(env);
  await view.findByRole('button', { name: '开始准备' });
  fireEvent.click(view.getByRole('button', { name: '开始准备' }));
  await view.findByRole('button', { name: '改为已关注' });
  const update = env.requests.find((r) => r.intent === 'UPDATE_MY_COMPETITION')!;
  assert.equal(update.my_competition_command?.state, 'PREPARING');
  assert.equal(update.my_competition_command?.expected_reference?.version, 1);
  fireEvent.click(view.getByRole('button', { name: '移出我的赛事' }));
  assert.equal(
    env.requests.some((r) => r.intent === 'REMOVE_MY_COMPETITION'),
    false,
  );
  assert.match(view.container.textContent!, /已有分析和计划继续保留/);
  fireEvent.click(view.getByRole('button', { name: '取消' }));
  assert.equal(
    env.requests.some((r) => r.intent === 'REMOVE_MY_COMPETITION'),
    false,
  );
  fireEvent.click(view.getByRole('button', { name: '移出我的赛事' }));
  fireEvent.click(view.getByRole('button', { name: '确认移出' }));
  await view.findByText('还没有加入任何赛事');
  assert.equal(
    env.requests.find((r) => r.intent === 'REMOVE_MY_COMPETITION')?.my_competition_command
      ?.expected_reference?.version,
    2,
  );
  assertNoAutomaticAnalysis(env);
});

test('exact add uses canonical target and does not set current or run analysis', async () => {
  const env = fixture();
  const view = page(env, <AddMyCompetitionButton target={target} />);
  await waitFor(() =>
    assert.equal(
      view.getByRole('button', { name: '加入我的赛事' }).hasAttribute('disabled'),
      false,
    ),
  );
  fireEvent.click(view.getByRole('button', { name: '加入我的赛事' }));
  await view.findByRole('button', { name: '已关注' });
  assert.deepEqual(
    env.requests.map((r) => r.intent),
    ['GET_MY_COMPETITIONS', 'ADD_MY_COMPETITION', 'GET_MY_COMPETITIONS'],
  );
  const command = env.requests[1].my_competition_command!;
  assert.deepEqual(command.target, target);
  assert.deepEqual(env.requests[1].context, { student_id: 'student' });
  assertNoAutomaticAnalysis(env);
});

test('competition-only add asks for Edition without choosing one', async () => {
  const env = fixture();
  const view = page(env, <AddMyCompetitionButton target={{ competition_id: 'comap-mcm' }} />);
  await waitFor(() =>
    assert.equal(
      view.getByRole('button', { name: '加入我的赛事' }).hasAttribute('disabled'),
      false,
    ),
  );
  fireEvent.click(view.getByRole('button', { name: '加入我的赛事' }));
  await view.findByText('请先选择届次，再加入我的赛事。');
  assert.deepEqual(
    env.requests.map((r) => r.intent),
    ['GET_MY_COMPETITIONS', 'GET_COMPETITION_DETAILS'],
  );
  // This fixture supplies no detail projection: failed read must not create a relation.
  await view.findByText('届次读取不可用，请到赛事详情重新读取。');
});

test('current student missing never selects the first profile', () => {
  const env = fixture();
  const view = render(
    <MyCompetitionsProvider {...env} context={{}} disabled={false} token="stable">
      <MyCompetitionsPage
        active
        setCurrent={() => {}}
        detail={() => {}}
        act={() => {}}
        browse={() => {}}
        recommend={() => {}}
      />
    </MyCompetitionsProvider>,
  );
  assert.match(view.container.textContent!, /尚未选择当前学生/);
  assert.equal(env.requests.length, 0);
});

test('relationship conflicts and authorization have product errors', () => {
  assert.match(myCompetitionError('MY_COMPETITION_VERSION_CONFLICT'), /重新加载/);
  assert.match(myCompetitionError('MY_COMPETITION_FORBIDDEN'), /无权/);
  assert.match(myCompetitionError('MY_COMPETITION_ALREADY_EXISTS'), /已加入/);
});

test('recommendation CandidateCard exposes explicit add without changing ranking', async () => {
  const env = fixture();
  const { validateArtifacts } = await import('../src/results/artifacts.ts');
  const result = validateArtifacts(
    presets.recommendation.runtime.response as AgentResponse,
    presets.recommendation.bundle,
  ).find((a) => a.model === 'RecommendationEvaluation');
  assert.ok(result?.model === 'RecommendationEvaluation');
  const view = page(
    env,
    <CandidateCard
      result={result.value}
      competitionLabel={() => 'Authoritative name'}
      skillLabel={(s) => s}
    />,
  );
  await view.findByRole('button', { name: '加入我的赛事' });
  assert.match(view.container.textContent!, /Authoritative name/);
  assert.equal(
    env.requests.some((r) => r.intent === 'ADD_MY_COMPETITION'),
    false,
  );
  await waitFor(() =>
    assert.equal(
      view.getByRole('button', { name: '加入我的赛事' }).hasAttribute('disabled'),
      false,
    ),
  );
  fireEvent.click(view.getByRole('button', { name: '加入我的赛事' }));
  await view.findByRole('button', { name: '已关注' });
  assert.deepEqual(
    env.requests.find((r) => r.intent === 'ADD_MY_COMPETITION')?.my_competition_command?.target,
    { ...result.value.candidate, track_id: result.value.candidate.track_id ?? null },
  );
});

test('Planning Workspace explicit add stays outside original Plan milestones', async () => {
  const { PlanningWorkspaceView } = await import('../src/workspace/PlanningWorkspace.tsx');
  const fixtures = await import('./fixtures/planning-workspace.json', { with: { type: 'json' } });
  const { validateArtifacts } = await import('../src/results/artifacts.ts');
  const reference = { kind: 'TOOL_RESULT' as const, ref_id: 'workspace-fixture' };
  const response: AgentResponse = {
    request_id: 'workspace-fixture',
    intent: 'GET_PLANNING_WORKSPACE',
    outcome: 'COMPLETED',
    message: 'Read',
    audit: { results: [reference], reasons: [] },
  };
  const artifact = validateArtifacts(response, {
    request_id: response.request_id,
    artifacts: [
      {
        ref: reference,
        model: 'PlanningWorkspaceProjection',
        value: fixtures.default.without_plan,
      },
    ],
  }).find((a) => a.model === 'PlanningWorkspaceProjection');
  assert.ok(artifact?.model === 'PlanningWorkspaceProjection');
  const value = artifact.value;
  const env = fixture();
  const view = page(
    env,
    <PlanningWorkspaceView value={value} act={() => {}} detail={() => {}} profile={() => {}} />,
  );
  await waitFor(() =>
    assert.equal(
      view.getByRole('button', { name: '加入我的赛事' }).hasAttribute('disabled'),
      false,
    ),
  );
  assert.equal(
    env.requests.some((r) => r.intent === 'ADD_MY_COMPETITION'),
    false,
  );
  fireEvent.click(view.getByRole('button', { name: '加入我的赛事' }));
  await view.findByRole('button', { name: '已关注' });
  assert.equal(value.plan_original_json, null);
});

test('Product navigation uses the existing My Competitions route and set-current preserves relationship state', async () => {
  const { ProductApp } = await import('../src/workspace/ProductApp.tsx');
  const env = fixture([row('PREPARING')]);
  window.history.replaceState(null, '', '/#/copilot');
  const view = render(<ProductApp client={env.client} readArtifacts={env.readArtifacts} />);
  fireEvent.change(view.getByLabelText(/学生 ID/), { target: { value: 'student' } });
  fireEvent.click(view.getByRole('link', { name: '我的赛事' }));
  await view.findByRole('button', { name: '改为已关注' });
  fireEvent.click(view.getByRole('button', { name: '设为当前赛事' }));
  fireEvent.click(view.getByRole('link', { name: 'Copilot' }));
  assert.equal((view.getByLabelText('竞赛 ID') as HTMLInputElement).value, target.competition_id);
  assert.equal((view.getByLabelText('届次 ID') as HTMLInputElement).value, target.edition_id);
  assert.equal((view.getByLabelText(/赛道 ID/) as HTMLInputElement).value, '');
  fireEvent.click(view.getByRole('link', { name: '首页' }));
  await view.findByText('COMAP Mathematical Contest in Modeling');
  assert.equal(
    env.requests.some((r) =>
      ['ADD_MY_COMPETITION', 'UPDATE_MY_COMPETITION', 'REMOVE_MY_COMPETITION'].includes(
        r.intent ?? '',
      ),
    ),
    false,
  );
});
