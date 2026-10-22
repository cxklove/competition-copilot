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
import { createPresentedClient, presentError } from '../src/results/ErrorPresentation.tsx';
import {
  PlanTimeline,
  RecommendationResults,
  SkillGapResults,
} from '../src/results/SemanticResults.tsx';
import { PlanDiffView } from '../src/results/PlanDiffView.tsx';
import { CompetitionCenter } from '../src/workspace/CompetitionCenter.tsx';
import { detailFacts } from '../src/workspace/competitionData.ts';
import type { ReadRecord } from '../src/workspace/competitionSession.ts';
import { competitionSession } from '../src/workspace/competitionSession.ts';
import type {
  CompetitionPlan,
  RecommendationEvaluation,
  SkillGapDecision,
  PlanDiff,
  SourceMetadata,
  CompetitionDetailProjection,
} from '../src/results/generated/artifacts.ts';

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

function catalogRecord(): ReadRecord {
  const ref = { kind: 'TOOL_RESULT', ref_id: 'synthetic-catalog-record' } as const;
  const response = {
    ...runtimeFixtures.completed.response,
    audit: { results: [ref], reasons: [] },
  } as AgentResponse;
  return {
    response,
    context: {},
    artifacts: validateArtifacts(response, {
      request_id: response.request_id,
      artifacts: [
        {
          ref,
          model: 'ListCompetitionsOutput',
          value: {
            competitions: [
              {
                id: 'competition',
                name: '明确标识的测试赛事',
                official_url: 'https://example.invalid/official',
              },
              { id: 'competition-a', name: '技能要求测试赛事' },
            ],
          },
        },
      ],
    }),
  };
}
function detailRecord(name: keyof typeof fixtures): ReadRecord {
  const value = fixtures[name];
  return {
    response: value.runtime.response as AgentResponse,
    context: { student_id: 'student', competition_id: 'competition', edition_id: 'edition' },
    artifacts: validateArtifacts(value.runtime.response as AgentResponse, value.bundle),
  };
}
function mountDetail(id: string, records: ReadRecord[], student = 'student') {
  const context = {
    student_id: student,
    competition_id: id,
    edition_id: id === 'competition-a' ? 'edition-a' : 'edition',
  };
  // Explicit synthetic server projections, validated through the same schema as
  // Runtime artifacts. The UI must no longer infer detail from a catalog row.
  const catalog = catalogRecord().artifacts[0];
  if (catalog.model !== 'ListCompetitionsOutput') throw Error('fixture');
  const competition = catalog.value.competitions.find((c) => c.id === id)!;
  const edition = {
    id: context.edition_id,
    competition_id: id,
    year: 2030,
    name: '测试届次',
    registration_window: null,
    competition_window: null,
  };
  const gap = records.flatMap((r) => r.artifacts).find((a) => a.model === 'SkillGapDecision');
  const sourceValues = records
    .flatMap((r) => r.artifacts)
    .flatMap((a) =>
      a.model === 'EligibilityDecision'
        ? (a.value.evidence ?? []).flatMap((e) => (e.source ? [e.source] : []))
        : [],
    );
  const availability = { requested: true, state: 'unknown' as const };
  const projections = [false, true].map((selected) => {
    const ref = { kind: 'TOOL_RESULT', ref_id: `detail-${selected}` } as const;
    const response: AgentResponse = {
      ...runtimeFixtures.completed.response,
      audit: { results: [ref] },
    } as AgentResponse;
    const value: CompetitionDetailProjection = {
      query: { competition_id: id, ...(selected ? { edition_id: edition.id } : {}) },
      competition,
      editions: [edition],
      selected_edition: selected ? edition : null,
      tracks: [],
      selected_track: null,
      eligibility_policy: null,
      skill_requirements:
        selected && gap
          ? {
              schema_version: '1.0',
              artifact_type: 'skill_requirement_set',
              requirement_version: 'synthetic-test-v1',
              review_note: 'Explicit synthetic frontend fixture',
              requirement_set: gap.value.requirements,
              skills: (gap.value.requirements.requirements ?? []).map((r) => ({
                id: r.skill_id,
                name: '测试技能',
              })),
            }
          : null,
      provenance: sourceValues.map((source) => ({
        competition_id: id,
        edition_id: edition.id,
        section: 'competition',
        source,
      })),
      availability: {
        competition: availability,
        editions: availability,
        tracks: availability,
        time_windows: availability,
        eligibility_policy: availability,
        skill_requirements: availability,
        provenance: availability,
        event_history: { ...availability, reason: 'EVENT_HISTORY_PERSISTENCE_GAP' },
      },
    };
    return {
      response,
      context: {},
      artifacts: validateArtifacts(response, {
        request_id: response.request_id,
        artifacts: [{ ref, model: 'CompetitionDetailProjection', value }],
      }),
    };
  });
  const view = render(
    <CompetitionCenter
      active={false}
      detailId={id}
      records={[...records, ...projections]}
      context={context}
      client={{
        exchange: async () => {
          throw Error('No read should run for a cached detail');
        },
        invoke: async () => {
          throw Error('No direct invocation');
        },
      }}
      disabled={false}
      onBusy={() => {}}
      open={() => {}}
      select={() => {}}
    />,
  );
  fireEvent.change(view.getByRole('combobox', { name: '届次' }), { target: { value: edition.id } });
  return view;
}
test('competition detail does not infer edition, tracks, rules, dates or personal conclusions from its name', () => {
  const view = mountDetail('competition', [catalogRecord()]);
  assert.ok(view.getByRole('heading', { name: '明确标识的测试赛事' }));
  fireEvent.click(view.getByRole('tab', { name: '参赛资格' }));
  assert.ok(view.getByText(/尚未分析你的参赛资格/));
  assert.equal(view.queryByText('资格已确认'), null);
  fireEvent.click(view.getByRole('tab', { name: '技能要求' }));
  assert.ok(view.getByText(/暂无.*已审核技能要求数据/));
  assert.ok(view.getByText(/尚未进行个人技能差距分析/));
  fireEvent.click(view.getByRole('tab', { name: '时间节点' }));
  assert.ok(view.getAllByText(/时间暂未确认/).length > 0);
  fireEvent.click(view.getByRole('tab', { name: '赛道' }));
  assert.ok(view.getByText(/暂无可展示的赛道记录/));
  fireEvent.click(view.getByRole('tab', { name: '证据来源' }));
  assert.ok(view.getByText(/暂无来源元数据/));
  fireEvent.click(view.getByRole('tab', { name: '变化历史' }));
  assert.ok(view.getByText('暂未提供完整赛事变化历史'));
  assert.ok(view.container.textContent?.includes('MISSING') === false);
});
for (const [name, label] of [
  ['eligible', '资格已确认'],
  ['ineligible', '当前资格受限'],
  ['unknown', '尚无法确认'],
] as const) {
  test(`detail renders existing ${name} decision without evaluating its rules`, () => {
    const record = detailRecord(name);
    const before = JSON.stringify(record);
    const view = mountDetail('competition', [catalogRecord(), record]);
    fireEvent.click(view.getByRole('tab', { name: '参赛资格' }));
    assert.ok(view.getByText(label));
    assert.equal(JSON.stringify(record), before);
  });
}
test('cached personal decision is not reused for a different student, edition or track', () => {
  const records = [catalogRecord(), detailRecord('eligible')];
  for (const context of [
    { student_id: 'other', competition_id: 'competition', edition_id: 'edition' },
    { student_id: 'student', competition_id: 'competition', edition_id: 'other' },
    {
      student_id: 'student',
      competition_id: 'competition',
      edition_id: 'edition',
      track_id: 'other',
    },
  ])
    assert.equal(detailFacts(records, 'competition', context).eligibility, undefined);
});
test('verified P7 snapshot with null required level remains partial and unknown, not a new skill-gap decision', () => {
  const record = detailRecord('undetermined');
  const gap = skillDecision(true);
  gap.requirements.requirements = gap.items?.map((item) => item.requirement);
  record.context = {
    student_id: 'student',
    competition_id: gap.target.competition_id,
    edition_id: gap.target.edition_id,
  };
  record.artifacts = [{ ref: record.artifacts[0].ref, model: 'SkillGapDecision', value: gap }];
  // Validate the same typed artifact path used by the production hosting reader.
  record.artifacts = validateArtifacts(record.response, {
    request_id: record.response.request_id,
    artifacts: record.artifacts,
  });
  const original = JSON.stringify(record);
  const view = mountDetail('competition-a', [catalogRecord(), record]);
  fireEvent.click(view.getByRole('tab', { name: '技能要求' }));
  assert.ok(view.getByText('所需能力等级暂未明确'));
  assert.ok(view.getByText('覆盖状态：部分已核验'));
  assert.ok(view.getByText('暂无法确认是否存在能力差距'));
  assert.equal(view.queryByText('能力已满足'), null);
  assert.equal(JSON.stringify(record), original);
});
test('detail sources visually aggregate observations and retain all original evidence refs in audit', () => {
  const record = detailRecord('eligible');
  const eligibility = record.artifacts[0];
  assert.equal(eligibility.model, 'EligibilityDecision');
  if (eligibility.model !== 'EligibilityDecision') throw Error('fixture');
  const source = {
    source_url: 'https://example.invalid/verified-rule',
    source_type: 'official',
    verification_status: 'verified',
    observed_at: '2030-01-01T00:00:00Z',
  } as const;
  eligibility.value.evidence = [
    { code: 'one', message: 'first', source },
    { code: 'two', message: 'second', source: { ...source, observed_at: '2030-01-02T00:00:00Z' } },
  ];
  const view = mountDetail('competition', [catalogRecord(), record]);
  fireEvent.click(view.getByRole('tab', { name: '证据来源' }));
  assert.equal(
    view.container.querySelectorAll(
      '.grouped-source-card a[href="https://example.invalid/verified-rule"]',
    ).length,
    1,
  );
  assert.ok(
    view.container
      .querySelector('.competition-audit pre')!
      .textContent!.includes(eligibility.ref.ref_id),
  );
  assert.ok(
    view.container
      .querySelector('.competition-audit pre')!
      .textContent!.includes('2030-01-01T00:00:00Z'),
  );
  assert.ok(
    view.container
      .querySelector('.competition-audit pre')!
      .textContent!.includes('2030-01-02T00:00:00Z'),
  );
});
test('returned controlled event is visibly demo-only and original before/after remains in audit', () => {
  const record = detailRecord('plan_diff');
  const diff = record.artifacts[0];
  if (diff.model !== 'PlanDiff') throw Error('fixture');
  diff.value.decision.impacts[0].event.source.source_url =
    'https://example.invalid/controlled-demo/test-only';
  const original = JSON.stringify(record);
  const view = mountDetail('competition', [catalogRecord(), record]);
  fireEvent.click(view.getByRole('tab', { name: '变化历史' }));
  assert.ok(view.getByText('模拟赛事变化 / 演示数据，不代表官方真实发生变化。'));
  assert.ok(view.getByRole('heading', { name: '赛道成员发生变化' }));
  assert.ok(
    view.container.querySelector('.competition-audit pre')!.textContent!.includes('source_diff'),
  );
  assert.equal(JSON.stringify(record), original);
});
test('detail tabs support arrow navigation, Home and End with real tab focus', () => {
  const view = mountDetail('competition', [catalogRecord()]);
  const first = view.getByRole('tab', { name: '赛事概览' });
  fireEvent.keyDown(first, { key: 'ArrowRight' });
  assert.equal(document.activeElement, view.getByRole('tab', { name: '参赛资格' }));
  fireEvent.keyDown(document.activeElement!, { key: 'End' });
  assert.equal(document.activeElement, view.getByRole('tab', { name: '变化历史' }));
  fireEvent.keyDown(document.activeElement!, { key: 'Home' });
  assert.equal(document.activeElement, first);
});
test('session read cache preserves exact older artifacts when another workflow replaces transport attachment', async () => {
  let attachment: unknown;
  const source = createPresentedClient(
    new FakeRuntimeTransport('LOCAL', [
      { body: fixtures.eligible.runtime },
      { body: fixtures.undetermined.runtime },
    ]),
    { mode: 'LOCAL', baseUrl: 'http://localhost:0' },
  );
  const exchange = source.exchange.bind(source);
  let index = 0;
  source.exchange = async (...args) => {
    const result = await exchange(...args);
    attachment = index++ ? fixtures.undetermined.bundle : fixtures.eligible.bundle;
    return result;
  };
  const records: ReadRecord[] = [];
  const scoped = competitionSession(
    source,
    () => attachment,
    (record) => records.push(record),
  );
  const first = await scoped.client.exchange({
    request: { request_id: fixtures.eligible.runtime.response.request_id, user_message: 'first' },
  });
  const original = structuredClone(scoped.readArtifacts(first.response!));
  await scoped.client.exchange({
    request: {
      request_id: fixtures.undetermined.runtime.response.request_id,
      user_message: 'second',
    },
  });
  assert.deepEqual(scoped.readArtifacts(first.response!), original);
  assert.equal(validateArtifacts(first.response!, scoped.readArtifacts(first.response!)).length, 1);
  assert.equal(records.length, 2);
});

for (const [message, title] of [
  ['NO_TARGET_CONSISTENT_REPLANNING_INPUT', '当前计划暂无可执行的调整依据'],
  ['INTENT_MODEL_FAILED', '暂时无法理解本次请求'],
  ['STALE_PLAN_REFERENCE', '当前计划已更新'],
  ['CONTINUATION_CONSUMED', '该审批已经处理'],
  ['FUTURE_PUBLIC_ERROR', '请求未完成'],
] as const) {
  test(`presentation-only error mapping: ${message}`, async () => {
    const fake = new FakeRuntimeTransport('LOCAL', [
      { body: { response: null, error: { code: 'CORE_VALIDATION_ERROR', message } } },
    ]);
    const client = createPresentedClient(fake, { mode: 'LOCAL', baseUrl: 'http://localhost:0' });
    const view = render(<Workspace client={client} nextRequestId={() => 'request-1'} />);
    fireEvent.change(view.getByLabelText('你的问题'), { target: { value: '请检查计划' } });
    await act(async () => {
      fireEvent.click(view.getByRole('button', { name: '发送请求' }));
    });
    assert.ok(view.getByText(title));
    assert.ok(view.getByRole('alert').textContent?.includes(message));
    assert.ok(view.getByRole('alert').textContent?.includes('CORE_VALIDATION_ERROR'));
    assert.equal(fake.calls.length, 1);
    assert.equal(view.container.querySelectorAll('.message-agent').length, 0);
    if (message === 'NO_TARGET_CONSISTENT_REPLANNING_INPUT') {
      assert.equal(view.queryByText(/稍后重试/), null);
      assert.equal(view.queryByRole('button', { name: '重试此请求' }), null);
    }
  });
}
test('network presentation asks for service availability, opaque validation error never guesses stale/replay', () => {
  assert.equal(
    presentError({ code: 'TRANSPORT_ERROR', message: 'TRANSPORT_ERROR' }).title,
    '服务连接失败',
  );
  assert.equal(
    presentError({ code: 'CORE_VALIDATION_ERROR', message: 'CORE_VALIDATION_ERROR' }).title,
    '请求未完成',
  );
});
test('error presentation capture isolates simultaneous requests and rethrows original taxonomy', async () => {
  const client = createPresentedClient(
    {
      mode: 'LOCAL',
      async send(envelope) {
        return {
          body: {
            response: null,
            error: { code: 'CORE_VALIDATION_ERROR', message: envelope.request!.user_message },
          },
        };
      },
    },
    { mode: 'LOCAL', baseUrl: 'http://localhost:0' },
  );
  const { errorDetails } = await import('../src/results/ErrorPresentation.tsx');
  const results = await Promise.allSettled(
    ['NO_TARGET_CONSISTENT_REPLANNING_INPUT', 'FUTURE_PUBLIC_ERROR'].map((user_message, index) =>
      client.invoke({ request_id: `parallel-${index}`, user_message }),
    ),
  );
  assert.deepEqual(
    results.map((r) => (r.status === 'rejected' ? errorDetails(r.reason).message : '')),
    ['NO_TARGET_CONSISTENT_REPLANNING_INPUT', 'FUTURE_PUBLIC_ERROR'],
  );
});
function skillEvaluation(score: number | null): RecommendationEvaluation {
  const result = structuredClone(
    fixtures.recommendation.bundle.artifacts[0].value,
  ) as RecommendationEvaluation;
  result.candidate.competition_id = 'comap-mcm';
  result.suitability_score = score;
  result.eligibility_decision.status = 'unknown';
  result.status = 'eligibility_uncertain';
  result.score_components =
    score == null
      ? []
      : [
          {
            component_id: 'verified-skill-overlap-v1',
            score,
            reason_code: 'VERIFIED_SKILL_OVERLAP',
            message: 'Explicit profile fact only',
            evidence: [],
          },
        ];
  return result;
}
for (const score of [1, null])
  test(`recommendation card preserves uncertain bucket and raw score ${score}`, () => {
    const value = { uncertain: [{ rank: 1, evaluation: skillEvaluation(score) }] };
    const before = JSON.stringify(value);
    const view = render(<RecommendationResults result={value} />);
    assert.ok(view.getByRole('heading', { name: '#1 comap-mcm' }));
    assert.ok(view.getByRole('region', { name: '资格尚待确认候选' }));
    assert.ok(
      view.getByText(score === 1 ? /技能匹配：已发现明确技能匹配/ : /技能匹配：暂无足够信息评分/),
    );
    assert.equal(view.queryByText(/100%|满分|强烈推荐|已确认适合/), null);
    assert.equal(JSON.stringify(value), before);
  });
function skillDecision(known: boolean): SkillGapDecision {
  const value = structuredClone(
    fixtures.undetermined.bundle.artifacts[0].value,
  ) as SkillGapDecision;
  value.requirements.coverage = 'partial';
  value.items = [
    {
      requirement: {
        skill_id: 'mathematical-modeling',
        required_level: null,
        requirement_type: 'required',
        presence_evidence: [
          {
            code: 'SKILL_REQUIREMENT_PRESENT',
            message: 'Explicit synthetic requirement fact',
            field: 'requirements.mathematical-modeling.present',
            value: true,
            source: structuredClone(
              fixtures.verified_source.bundle.artifacts[0].value,
            ) as SourceMetadata,
          },
        ],
      },
      student_level: known ? 'intermediate' : null,
      status: 'unknown',
      reason_codes: known
        ? ['REQUIREMENT_PROFICIENCY_UNSPECIFIED']
        : ['STUDENT_SKILL_DATA_MISSING'],
      student_evidence: known
        ? [
            {
              code: 'PROFILE_FACT',
              message:
                'LOCAL DEMO FIXTURE; student_id=local-recommendation-demo; skill_id=mathematical-modeling; self_assessed=true; Student profile self-assessed skill fact, level=intermediate.',
              field: 'skills.mathematical-modeling.level',
              value: 'intermediate',
              source: null,
            },
          ]
        : [],
    },
  ];
  return value;
}
for (const known of [true, false])
  test(`skill table preserves unknown requirement and profile missing=${!known}`, () => {
    const value = skillDecision(known);
    const original = JSON.stringify(value);
    const view = render(<SkillGapResults result={value} />);
    assert.ok(view.getByRole('table', { name: '技能与赛事要求对照' }));
    assert.ok(view.getByText('已确认需要该技能，但所需等级尚未明确'));
    assert.ok(view.getByText(known ? '中级（自评）' : '暂无画像记录'));
    assert.ok(view.getByText(known ? '暂无法确认是否存在能力差距' : '需要补充个人能力信息'));
    assert.equal(view.queryByText(/不具备|能力不足|已达到比赛要求/), null);
    assert.equal(JSON.stringify(value), original);
  });
test('timeline does not invent a missing deadline and preserves raw plan', () => {
  const plan = structuredClone(
    fixtures.plan_diff.bundle.artifacts[0].value.before,
  ) as CompetitionPlan;
  plan.status = 'draft';
  plan.milestones!.forEach((m) => {
    m.due_at = null;
  });
  const original = JSON.stringify(plan);
  const view = render(<PlanTimeline plan={plan} />);
  assert.ok(view.getByRole('region', { name: '备赛计划时间线' }));
  assert.ok(view.getAllByText(/截止时间：暂未设置/).length);
  assert.ok(view.getAllByText(/系统不会自动推断截止日期/).length);
  assert.equal(JSON.stringify(plan), original);
});
test('controlled demo diff shows supplied version/status and labels simulation without changing artifact', () => {
  const diff = structuredClone(fixtures.plan_diff.bundle.artifacts[0].value) as PlanDiff;
  diff.before.version = 1;
  diff.after.version = 2;
  diff.status_change = { field: 'status', before_status: 'draft', after_status: 'cancelled' };
  diff.decision.impacts[0].event.source.source_url =
    'https://example.invalid/competition-copilot/controlled-demo/huawei-track-removal';
  diff.decision.impacts[0].event.source.source_type = 'manual';
  const original = JSON.stringify(diff);
  const view = render(<PlanDiffView diff={diff} />);
  assert.ok(view.getByText('版本：1 → 2'));
  assert.ok(view.getByText('方案状态：草案 → 已取消'));
  assert.ok(view.getByText(/本次修订来自受控演示事件/));
  assert.equal(JSON.stringify(diff), original);
});
test('evidence/source/audit are folded by default and remain accessible after explicit expansion', async () => {
  const { response, bundle } = await preset('eligible');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  const folds = [...view.container.querySelectorAll('details')];
  assert.ok(folds.length >= 3);
  assert.ok(folds.every((item) => !item.open));
  for (const fold of folds) fireEvent.click(fold.querySelector('summary')!);
  assert.ok(view.getByRole('link', { name: 'https://example.org/synthetic-rules' }));
  assert.ok(view.getByRole('list', { name: '证据' }));
  assert.ok(view.getByRole('list', { name: '结果引用' }));
  assert.ok(view.getAllByText(/RULE_SATISFIED/).length);
  assert.ok(view.container.textContent?.includes(response.audit!.results![0].ref_id));
});

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
    if (name === 'undetermined') assert.ok(view.getByText('当前结论：暂无法完整判断'));
    else if (name === 'no_gap') assert.ok(view.getByText('当前结论：未发现已声明技能差距'));
    else assert.ok(view.getAllByText(name).length);
    if (name === 'unknown') assert.ok(view.getAllByText(/不能据此认定符合、不符合/).length);
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
  const audit = view.container.querySelector('.recommendation-audit')!;
  assert.equal((audit as HTMLDetailsElement).open, false);
  assert.ok(audit.textContent?.includes('"suitability_score": 0.8'));
  assert.ok(audit.textContent?.includes('goal-fit'));
  assert.ok(audit.textContent?.includes('GOAL_SIGNAL_PRESENT'));
});

test('12 uncertain recommendations show one summary, five default cards and seven folded cards in backend order', () => {
  const uncertain = Array.from({ length: 12 }, (_, index) => {
    const evaluation = skillEvaluation(index < 2 ? 1 : null);
    evaluation.candidate.competition_id = `candidate-${index}`;
    return { rank: index + 1, evaluation };
  });
  const result = { confirmed: [], uncertain, blocked: [] };
  const original = JSON.stringify(result);
  const view = render(<RecommendationResults result={result} />);
  assert.equal(view.getAllByRole('heading', { name: '推荐结果' }).length, 1);
  const summary = view.container.querySelector('.recommendation-counts')!;
  assert.deepEqual(
    [...summary.querySelectorAll('dt')].map((e) => e.textContent),
    ['资格已确认', '资格尚待确认', '当前资格受限'],
  );
  assert.deepEqual(
    [...summary.querySelectorAll('dd')].map((e) => e.textContent),
    ['0', '12', '0'],
  );
  const remaining = view.container.querySelector('.remaining-candidates') as HTMLDetailsElement;
  assert.equal(remaining.open, false);
  assert.equal(
    view.container.querySelectorAll('.recommendation-card').length -
      remaining.querySelectorAll('.recommendation-card').length,
    5,
  );
  assert.equal(remaining.querySelectorAll('.recommendation-card').length, 7);
  assert.deepEqual(
    [...view.container.querySelectorAll('.recommendation-card h5')].map((e) => e.textContent),
    uncertain.map((item, index) => `#${item.rank} candidate-${index}`),
  );
  fireEvent.click(view.getByText('查看其余 7 个候选'));
  assert.equal(remaining.open, true);
  for (const card of view.container.querySelectorAll('.recommendation-card')) {
    assert.ok(card.textContent?.includes('资格状态：资格尚待确认'));
    assert.equal(card.querySelectorAll('.recommendation-why').length, 1);
    assert.equal(card.querySelectorAll('.recommendation-sources').length, 1);
    assert.ok(!/100%|100分|满分|0分|不匹配|不适合|完全适合|强烈推荐/.test(card.textContent!));
  }
  assert.equal(view.container.querySelectorAll('.recommendation-audit').length, 1);
  assert.ok(!/结果结果|资格资格|推荐推荐/.test(view.container.textContent!));
  assert.equal(JSON.stringify(result), original);
});

test('candidate sources and profile facts are visually aggregated while all artifacts and refs remain in one audit', () => {
  const evaluation = skillEvaluation(1);
  const source = structuredClone(
    fixtures.verified_source.bundle.artifacts[0].value,
  ) as SourceMetadata;
  const sourceFact = {
    code: 'REVIEWED_RULE',
    message: 'Explicit reviewed skill fact',
    field: 'requirements.mathematical-modeling.present',
    value: true,
    source,
  };
  evaluation.evidence = [sourceFact, sourceFact];
  evaluation.eligibility_decision.evidence = [sourceFact];
  evaluation.eligibility_decision.rule_evaluations = [];
  evaluation.score_components![0].evidence = [
    sourceFact,
    {
      code: 'VERIFIED_SKILL_OVERLAP',
      message: 'Explicit match',
      field: 'scoring.matched_skill_id',
      value: 'mathematical-modeling',
    },
    {
      code: 'PROFILE_SKILL_FACT',
      message: 'Profile level',
      field: 'skills.mathematical-modeling.level',
      value: 'intermediate',
    },
    {
      code: 'PROFILE_SKILL_FACT',
      message: 'Profile origin',
      field: 'skills.mathematical-modeling.self_assessed',
      value: true,
    },
    {
      code: 'SCORING_CONFIGURATION',
      message: 'Version',
      field: 'scoring.policy_version',
      value: 'verified-skill-overlap-v1',
    },
    { code: 'COMPONENT_WEIGHT', message: 'Weight', field: 'weight', value: 1 },
    {
      code: 'REQUIREMENT_VERSION',
      message: 'Requirements',
      field: 'version',
      value: 'reviewed-v1',
    },
  ];
  const ref = { kind: 'TOOL_RESULT' as const, ref_id: 'recommendation-result-ref' };
  const evidenceRef = { kind: 'EVIDENCE' as const, ref_id: 'original-evidence-ref' };
  const response: AgentResponse = {
    request_id: 'recommendation-cleanup',
    intent: 'GET_RECOMMENDATIONS',
    outcome: 'COMPLETED',
    message: 'Original authoritative recommendation reply',
    audit: { results: [ref, evidenceRef], reasons: [] },
  };
  const bundle = {
    request_id: response.request_id,
    artifacts: [
      {
        model: 'RecommendationRankingResult',
        ref,
        value: { confirmed: [], uncertain: [{ rank: 1, evaluation }], blocked: [] },
      },
      { model: 'Evidence', ref: evidenceRef, value: sourceFact },
    ],
  };
  const original = JSON.stringify({ response, bundle });
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.equal(view.queryByRole('alert'), null);
  assert.equal(view.container.querySelectorAll('.recommendation-source-card').length, 1);
  const card = view.container.querySelector('.recommendation-card')!;
  assert.ok(card.textContent?.includes('数学建模 · 中级 · 来源：自评'));
  assert.equal(card.querySelectorAll('.recommendation-why h6 + ul > li').length, 1);
  for (const code of [
    'PROFILE_SKILL_FACT',
    'SCORING_CONFIGURATION',
    'COMPONENT_WEIGHT',
    'REQUIREMENT_VERSION',
  ]) {
    assert.ok(!card.textContent?.includes(code));
  }
  const audit = view.container.querySelector('.recommendation-audit') as HTMLDetailsElement;
  assert.equal(audit.open, false);
  fireEvent.click(view.getByText('查看高级审计信息'));
  assert.equal(audit.open, true);
  assert.ok(audit.textContent?.includes(evidenceRef.ref_id));
  assert.ok(audit.textContent?.includes(ref.ref_id));
  assert.ok(audit.textContent?.includes('SCORING_CONFIGURATION'));
  assert.ok(audit.textContent?.includes('COMPONENT_WEIGHT'));
  assert.ok(audit.textContent?.includes('reviewed-v1'));
  assert.ok(audit.textContent?.includes('REVIEWED_RULE'));
  const raw = view.container.querySelector('.recommendation-raw') as HTMLDetailsElement;
  assert.equal(raw.open, false);
  assert.ok(raw.textContent?.includes(response.message));
  assert.equal(view.container.querySelectorAll('.evidence-details').length, 0);
  assert.equal(view.container.querySelectorAll('.recommendation-audit').length, 1);
  assert.equal(JSON.stringify({ response, bundle }), original);
});

test('source URLs group historical observations visually while preserving original metadata in audit', () => {
  const evaluation = skillEvaluation(null);
  const source = structuredClone(
    fixtures.verified_source.bundle.artifacts[0].value,
  ) as SourceMetadata;
  evaluation.evidence = [source, { ...source, observed_at: '2031-01-01T00:00:00Z' }].map(
    (value) => ({ code: 'SOURCE_FACT', message: 'Reviewed fact', source: value }),
  );
  const view = render(<RecommendationResults result={{ uncertain: [{ rank: 1, evaluation }] }} />);
  assert.equal(view.container.querySelectorAll('.recommendation-source-card').length, 1);
  assert.ok(view.getByText(/历史观察记录 2 次/));
  assert.equal(
    view.container.querySelector('.recommendation-source-card time')!.getAttribute('datetime'),
    '2031-01-01T00:00:00Z',
  );
  assert.equal(evaluation.evidence.length, 2);
  assert.ok(
    view.container
      .querySelector('.recommendation-audit')!
      .textContent?.includes(source.observed_at),
  );
  assert.ok(
    view.container
      .querySelector('.recommendation-audit')!
      .textContent?.includes('2031-01-01T00:00:00Z'),
  );
});

test('skill gap summary folds all original artifacts and refs without turning PARTIAL/UNKNOWN into success', () => {
  const result = skillDecision(true);
  const ref = { kind: 'TOOL_RESULT' as const, ref_id: 'skill-gap-result-ref' };
  const evidenceRef = { kind: 'EVIDENCE' as const, ref_id: 'skill-evidence-ref' };
  const evidence = {
    code: 'REQUIREMENT_VERSION',
    message: 'Existing version fact',
    field: 'requirement_version',
    value: 'reviewed-skill-v1',
    source: null,
  };
  const response: AgentResponse = {
    request_id: 'skill-polish',
    intent: 'ANALYZE_SKILL_GAP',
    outcome: 'COMPLETED',
    message: 'Original skill analysis',
    audit: { results: [ref, evidenceRef], reasons: [] },
  };
  const bundle = {
    request_id: response.request_id,
    artifacts: [
      { model: 'SkillGapDecision', ref, value: result },
      { model: 'Evidence', ref: evidenceRef, value: evidence },
    ],
  };
  const original = JSON.stringify({ response, bundle });
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByRole('heading', { name: '技能差距分析' }));
  assert.ok(view.getByText('当前结论：暂无法完整判断'));
  assert.ok(view.getByText(/赛事技能要求覆盖仍不完整/));
  const main = view.container.cloneNode(true) as HTMLElement;
  main.querySelectorAll('details').forEach((d) => d.remove());
  assert.ok(
    !/UNDETERMINED|PARTIAL|REQUIREMENT_PROFICIENCY_UNSPECIFIED|能力已满足|无差距|要求已完整确认/.test(
      main.textContent!,
    ),
  );
  assert.equal(view.container.querySelectorAll('.semantic-audit').length, 1);
  assert.ok([...view.container.querySelectorAll('details')].every((d) => !d.open));
  const audit = view.container.querySelector('.semantic-audit') as HTMLDetailsElement;
  fireEvent.click(within(audit).getByText('查看高级审计信息'));
  assert.equal(audit.open, true);
  const retained = JSON.parse(audit.querySelector('pre')!.textContent!);
  assert.deepEqual(retained.artifacts, bundle.artifacts);
  assert.deepEqual(retained.response.audit.results, response.audit!.results);
  assert.ok(audit.textContent?.includes('reviewed-skill-v1'));
  const raw = view.container.querySelector('.semantic-raw') as HTMLDetailsElement;
  assert.equal(raw.open, false);
  assert.ok(raw.textContent?.includes(response.message));
  assert.equal(JSON.stringify({ response, bundle }), original);
});

function uncertaintyPlan(): CompetitionPlan {
  const plan = structuredClone(
    fixtures.plan_diff.bundle.artifacts[0].value.before,
  ) as CompetitionPlan;
  plan.id = 'baseline-plan-v1:long-authoritative-identity';
  plan.status = 'draft';
  plan.version = 1;
  plan.planning_needs = [
    {
      id: 'planning-need:requirement-set',
      kind: 'uncertainty_resolution',
      reason_codes: ['REQUIREMENT_DATA_MISSING'],
      source_item: null,
    },
  ];
  plan.milestones = [
    {
      id: 'milestone:only-stage',
      title: 'uncertainty_resolution requirement_set',
      source_need_id: plan.planning_needs[0].id,
      status: 'pending',
      due_at: null,
    },
  ];
  return plan;
}
test('one uncertainty-resolution milestone stays one stage with semantic title, draft label and no guessed deadline', () => {
  const plan = uncertaintyPlan();
  const original = JSON.stringify(plan);
  const view = render(<PlanTimeline plan={plan} />);
  assert.ok(view.getByRole('heading', { name: '备赛计划' }));
  assert.ok(view.getByRole('heading', { name: '阶段 1 · 确认赛事要求' }));
  assert.ok(view.getByText('计划状态：草案'));
  assert.ok(view.getByText('计划版本：v1'));
  assert.ok(view.getByText('计划阶段：1 个'));
  assert.ok(view.getByText('当前重点：确认赛事要求'));
  assert.ok(view.getByText('当前状态：待处理'));
  assert.ok(view.getByText('截止时间：暂未设置'));
  assert.equal(view.container.querySelectorAll('.plan-timeline > li').length, 1);
  assert.equal(view.container.querySelectorAll('.plan-timeline time').length, 0);
  assert.ok(view.getByRole('note').textContent?.includes('未新增正式计划阶段'));
  const main = view.container.cloneNode(true) as HTMLElement;
  main.querySelectorAll('details').forEach((d) => d.remove());
  assert.ok(
    !/baseline-plan|planning-need|milestone:|uncertainty_resolution|requirement_set|draft|None|null/.test(
      main.textContent!,
    ),
  );
  assert.ok(view.container.querySelector('.semantic-audit')!.textContent?.includes(plan.id));
  assert.equal(JSON.stringify(plan), original);
});
test('skill-target uncertainty uses the supplied skill name and keeps all milestone ordering and known dates', () => {
  const plan = uncertaintyPlan();
  plan.planning_needs![0].source_item = skillDecision(true).items![0];
  plan.milestones!.push({
    id: 'milestone:second',
    title: '后端第二阶段',
    status: 'pending',
    due_at: '2031-06-01T00:00:00Z',
  });
  const original = JSON.stringify(plan);
  const view = render(<PlanTimeline plan={plan} />);
  const stages = [...view.container.querySelectorAll('.plan-timeline h4')].map(
    (e) => e.textContent,
  );
  assert.deepEqual(stages, ['阶段 1 · 确认“数学建模”的具体能力要求', '阶段 2 · 后端第二阶段']);
  assert.equal(
    view.container.querySelectorAll('.plan-timeline > li').length,
    plan.milestones!.length,
  );
  assert.equal(
    view.container.querySelector('.plan-timeline time')!.getAttribute('datetime'),
    plan.milestones![1].due_at,
  );
  assert.equal(JSON.stringify(plan), original);
});
test('plan presentation retains the complete plan, source artifacts and exact reference audit', () => {
  const plan = uncertaintyPlan();
  const ref = { kind: 'TOOL_RESULT' as const, ref_id: 'plan-result-ref' };
  const sourceRef = { kind: 'SOURCE' as const, ref_id: 'original-source-ref' };
  const source = structuredClone(fixtures.verified_source.bundle.artifacts[0].value);
  const response: AgentResponse = {
    request_id: 'plan-polish',
    intent: 'BUILD_PLAN',
    outcome: 'COMPLETED',
    message: 'Original plan response',
    audit: { results: [ref, sourceRef], reasons: [] },
  };
  const bundle = {
    request_id: response.request_id,
    artifacts: [
      { model: 'CompetitionPlan', ref, value: plan },
      { model: 'SourceMetadata', ref: sourceRef, value: source },
    ],
  };
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.equal(view.queryByRole('alert'), null);
  const audit = view.container.querySelector('.semantic-audit') as HTMLDetailsElement;
  assert.equal(audit.open, false);
  const retained = JSON.parse(audit.querySelector('pre')!.textContent!);
  assert.deepEqual(retained.artifacts, bundle.artifacts);
  assert.deepEqual(retained.response.audit, response.audit);
  assert.equal((view.container.querySelector('.semantic-raw') as HTMLDetailsElement).open, false);
});

test('presentation preserves backend bucket boundaries and array order instead of sorting by score or rank', () => {
  const first = skillEvaluation(null),
    second = skillEvaluation(1),
    third = skillEvaluation(1);
  first.candidate.competition_id = 'first';
  second.candidate.competition_id = 'second';
  third.candidate.competition_id = 'third';
  const value = {
    confirmed: [{ rank: 9, evaluation: first }],
    uncertain: [
      { rank: 7, evaluation: second },
      { rank: 2, evaluation: third },
    ],
    blocked: [],
  };
  const view = render(<RecommendationResults result={value} />);
  assert.deepEqual(
    [...view.container.querySelectorAll('.recommendation-card h5')].map((e) => e.textContent),
    ['#9 first', '#7 second', '#2 third'],
  );
  assert.equal(
    view.getByRole('region', { name: '资格已确认候选' }).querySelectorAll('.recommendation-card')
      .length,
    1,
  );
  assert.equal(
    view.getByRole('region', { name: '资格尚待确认候选' }).querySelectorAll('.recommendation-card')
      .length,
    2,
  );
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
  assert.ok(view.getAllByText(/<img src=x/).length);
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

test('PlanDiff reference and source attachments aggregate once while every authoritative ref/body remains in audit', async () => {
  const { response, bundle } = await preset('plan_diff');
  const diff = bundle.artifacts[0].value as PlanDiff;
  const source = structuredClone(diff.decision.impacts[0].event.source);
  const refs = Array.from({ length: 6 }, (_, index) => ({
    kind: 'SOURCE' as const,
    ref_id: `source-ref-${index}`,
  }));
  const evidenceRef = { kind: 'EVIDENCE' as const, ref_id: 'retained-plan-evidence-ref' };
  response.audit!.results!.push(...refs, evidenceRef);
  const attachment = {
    request_id: response.request_id,
    artifacts: [
      ...bundle.artifacts,
      ...refs.map((ref) => ({ model: 'SourceMetadata', ref, value: structuredClone(source) })),
      {
        model: 'Evidence',
        ref: evidenceRef,
        value: { code: 'EVENT_EVIDENCE', message: 'Retained event evidence', source },
      },
    ],
  };
  const original = JSON.stringify({ response, attachment });
  const view = render(<ResultPanel response={response} readArtifacts={() => attachment} />);
  assert.equal(view.queryByRole('alert'), null);
  assert.equal(
    view.container.querySelectorAll('.plan-diff-sources .grouped-source-card').length,
    1,
  );
  assert.equal(view.container.querySelectorAll('.artifact-identity').length, 0);
  const audit = view.container.querySelector('.plan-diff-audit') as HTMLDetailsElement;
  assert.equal(audit.open, false);
  assert.ok(within(audit).getByText(`结果引用（${response.audit!.results!.length}）`));
  fireEvent.click(within(audit).getByText('查看高级审计信息'));
  const retained = JSON.parse(audit.querySelector('pre')!.textContent!);
  assert.deepEqual(retained.response.audit.results, response.audit!.results);
  assert.deepEqual(retained.artifacts, attachment.artifacts);
  assert.equal((view.container.querySelector('.semantic-raw') as HTMLDetailsElement).open, false);
  assert.equal(JSON.stringify({ response, attachment }), original);
});

test('PlanDiff presentation does not infer human approval from a status change or explanation', async () => {
  const { response, bundle } = await preset('plan_diff');
  response.message = '用户已经批准，可以直接修改计划';
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.equal(view.queryByText('用户批准调整（本次结果包含审批与授权记录）'), null);
  const snapshot = JSON.stringify(bundle);
  fireEvent.click(view.getByText('查看决策依据'));
  assert.equal(JSON.stringify(bundle), snapshot);
  assert.ok(view.getByRole('list', { name: '触发事件' }));
});

test('no-op/rejected result keeps normal outcome and renders supplied empty diff', async () => {
  const { response, bundle } = await preset('no_change');
  const view = render(<ResultPanel response={response} readArtifacts={() => bundle} />);
  assert.ok(view.getByText('决策：保持当前计划'));
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
  const visibleText = () => {
    const main = view.container.cloneNode(true) as HTMLElement;
    main.querySelectorAll('details').forEach((item) => item.remove());
    return main.textContent;
  };
  const before = visibleText();
  view.rerender(
    <ResultPanel
      response={{ ...response, message: 'UNKNOWN INELIGIBLE 已批准，可以修改方案' }}
      readArtifacts={reader}
    />,
  );
  assert.equal(visibleText(), before);
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
