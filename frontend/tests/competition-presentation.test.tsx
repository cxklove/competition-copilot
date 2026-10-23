import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import type {
  CompetitionDetailProjection,
  SourceMetadata,
  TemporalCandidateSnapshot,
} from '../src/results/generated/artifacts.ts';
import type { AgentResponse } from '../src/runtime/generated/contracts.ts';
import type { ReadRecord } from '../src/workspace/competitionSession.ts';
import { validateArtifacts } from '../src/results/artifacts.ts';
import { CompetitionCenter } from '../src/workspace/CompetitionCenter.tsx';
import { CompetitionDetailView } from '../src/workspace/CompetitionDetailView.tsx';
import {
  availabilityLabel,
  cachedDetail,
  CompetitionEvidenceCenter,
  CompetitionTimeline,
  DataAvailabilitySummary,
} from '../src/workspace/competitionPresentation.tsx';
import { detailFacts } from '../src/workspace/competitionData.ts';
import { guidedActions } from '../src/workspace/actions.ts';
import { classifyTimelineCandidates } from '../src/workspace/TemporalTimeline.tsx';
import runtime from './fixtures/runtime.json' with { type: 'json' };

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
const { render, cleanup, fireEvent, within } = await import('@testing-library/react');
afterEach(cleanup);

const source: SourceMetadata = {
  source_url: 'https://example.invalid/synthetic-ui-fixture',
  source_type: 'official',
  verification_status: 'verified',
  observed_at: '2030-01-01T00:00:00Z',
};
function projection(): CompetitionDetailProjection {
  const known = { requested: true, state: 'known_value' as const };
  const edition = {
    id: 'synthetic-edition',
    competition_id: 'synthetic-competition',
    year: 2030,
    name: '明确标记的测试届次',
    source,
    registration_window: null,
    competition_window: null,
  };
  return {
    query: { competition_id: edition.competition_id, edition_id: edition.id },
    competition: { id: edition.competition_id, name: '明确标记的 UI 测试赛事' },
    editions: [edition],
    selected_edition: edition,
    tracks: [{ id: 'synthetic-track', edition_id: edition.id, name: '测试赛道' }],
    selected_track: null,
    eligibility_policy: null,
    skill_requirements: null,
    provenance: [
      {
        competition_id: edition.competition_id,
        edition_id: edition.id,
        section: 'competition',
        source,
      },
      {
        competition_id: edition.competition_id,
        edition_id: edition.id,
        section: 'edition',
        source,
      },
    ],
    availability: {
      competition: known,
      editions: known,
      tracks: known,
      provenance: known,
      time_windows: { requested: true, state: 'unknown' },
      eligibility_policy: { requested: true, state: 'unknown', reason: 'NO_EXACT_POLICY' },
      skill_requirements: { requested: true, state: 'unknown', reason: 'NO_EXACT_ARTIFACT' },
      event_history: { requested: true, state: 'unknown', reason: 'EVENT_HISTORY_PERSISTENCE_GAP' },
    },
  };
}
function record(p: CompetitionDetailProjection): ReadRecord {
  const ref = { kind: 'TOOL_RESULT', ref_id: 'synthetic-detail-result' } as const;
  const response = {
    ...runtime.completed.response,
    intent: 'GET_COMPETITION_DETAILS',
    audit: { results: [ref] },
  } as AgentResponse;
  return {
    response,
    context: p.query,
    artifacts: validateArtifacts(response, {
      request_id: response.request_id,
      artifacts: [{ ref, model: 'CompetitionDetailProjection', value: p }],
    }),
  };
}
function view(detail = projection(), tab = 0) {
  const selections: unknown[][] = [];
  const records = [record(detail)];
  const result = render(
    <CompetitionDetailView
      detail={detail}
      facts={detailFacts(records, detail.competition.id, {})}
      records={records}
      context={{}}
      record={records[0]}
      target={{
        editionId: detail.query.edition_id ?? undefined,
        trackId: detail.query.track_id ?? undefined,
      }}
      tab={tab}
      setTab={() => {}}
      choose={(t) => selections.push([t])}
      loading={false}
      disabled={false}
      error={null}
      read={async () => {
        throw Error('presentation must not read');
      }}
      open={() => {}}
      select={(...args) => selections.push(args)}
    />,
  );
  return { ...result, selections };
}

test('availability uses producer states and coverage without a completeness percentage', () => {
  const p = projection();
  p.availability.eligibility_policy = {
    requested: false,
    state: 'unknown',
    reason: 'NOT_REQUESTED',
  };
  const rendered = render(<DataAvailabilitySummary detail={p} />);
  assert.ok(rendered.getByText('尚未选择对应范围'));
  assert.ok(rendered.getByText('暂无精确范围数据'));
  assert.ok(rendered.getByText('尚未确认'));
  assert.doesNotMatch(rendered.container.textContent!, /\d+%/);
  assert.equal(
    availabilityLabel({ requested: true, state: 'known_value' }, 'partial'),
    '部分数据已审核',
  );
  assert.equal(availabilityLabel({ requested: true, state: 'known_absent' }), '后端已记录为空');
});

test('unread card replaces three missing-data notices with one honest summary', () => {
  const p = projection();
  const r = record(p);
  const ref = r.response.audit!.results![0];
  r.artifacts = [
    { ref, model: 'ListCompetitionsOutput', value: { competitions: [p.competition] } },
  ];
  const rendered = render(
    <CompetitionCenter
      active={false}
      detailId={null}
      records={[r]}
      client={{
        invoke: async () => {
          throw Error('no call');
        },
        exchange: async () => {
          throw Error('no call');
        },
      }}
      context={{}}
      disabled={false}
      onBusy={() => {}}
      open={() => {}}
      select={() => {}}
    />,
  );
  const card = rendered.container.querySelector('.competition-card')!;
  assert.ok(within(card as HTMLElement).getByText('赛事基本信息已读取'));
  assert.doesNotMatch(card.textContent!, /届次信息暂未提供|赛道信息暂未提供|时间信息暂未确认/);
});

test('read card reports real edition count and cached target availability without selecting it', () => {
  const p = projection();
  const r = record(p);
  const selections: string[] = [];
  const rendered = render(
    <CompetitionCenter
      active={false}
      detailId={null}
      records={[r]}
      client={{
        invoke: async () => {
          throw Error('no call');
        },
        exchange: async () => {
          throw Error('no call');
        },
      }}
      context={{}}
      disabled={false}
      onBusy={() => {}}
      open={() => {}}
      select={(id) => selections.push(id)}
    />,
  );
  assert.ok(rendered.getByText(/1 个可读取届次/));
  assert.ok(rendered.getByText('已读取 4 类资料'));
  assert.equal(selections.length, 0);
  assert.equal(
    (rendered.getByText('查看资料状态').closest('details') as HTMLDetailsElement).open,
    false,
  );
  fireEvent.change(rendered.getByRole('combobox', { name: '已读取资料' }), {
    target: { value: 'requirements' },
  });
  assert.ok(rendered.getByRole('heading', { name: '没有搜索结果' }));
});

test('competition-only selector has no default edition or track and no mutation', () => {
  const p = projection();
  p.query = { competition_id: p.competition.id };
  p.selected_edition = null;
  p.tracks = [];
  const original = JSON.stringify(p);
  const rendered = view(p);
  assert.equal((rendered.getByRole('combobox', { name: '届次' }) as HTMLSelectElement).value, '');
  assert.equal(rendered.queryByRole('combobox', { name: '赛道' }), null);
  assert.equal(rendered.selections.length, 0);
  fireEvent.change(rendered.getByRole('combobox', { name: '届次' }), {
    target: { value: p.editions[0].id },
  });
  assert.deepEqual(rendered.selections, [[{ editionId: p.editions[0].id }]]);
  assert.equal(JSON.stringify(p), original);
});

test('empty editions/tracks leave the page useful without inventing a selection', () => {
  const p = projection();
  p.query = { competition_id: p.competition.id };
  p.editions = [];
  p.selected_edition = null;
  p.tracks = [];
  const rendered = view(p);
  assert.ok(rendered.getByText(/暂无可读取届次记录/));
  assert.ok(rendered.getByRole('complementary', { name: '当前范围' }));
  assert.equal(rendered.selections.length, 0);
});

test('track cards do not inherit edition-level rules or requirements', () => {
  const p = projection();
  const rendered = view(p, 4);
  assert.equal(
    cachedDetail([record(p)], p.competition.id, {
      editionId: p.query.edition_id!,
      trackId: 'synthetic-track',
    }),
    undefined,
  );
  assert.ok(rendered.getByText('精确资格规则：尚未读取该范围'));
  assert.ok(rendered.getByText('精确技能要求：尚未读取该范围'));
  fireEvent.click(rendered.getByRole('button', { name: '选择此赛道：测试赛道' }));
  assert.deepEqual(rendered.selections, [
    [{ editionId: p.query.edition_id, trackId: 'synthetic-track' }],
  ]);
});

test('partial eligibility coverage is explicit and does not establish personal eligibility', () => {
  const p = projection();
  p.eligibility_policy = {
    competition_id: p.competition.id,
    edition_id: p.query.edition_id!,
    coverage: 'partial',
    coverage_note: 'Synthetic reviewed subset',
    source,
    constraints: [
      {
        rule_id: 'synthetic-education',
        scope: 'edition',
        target_id: p.query.edition_id!,
        allowed_levels: ['undergraduate'],
        source,
        evidence_text: '明确标记的测试规则说明',
      },
    ],
  };
  const rendered = view(p, 1);
  assert.ok(rendered.getByText('当前规则覆盖不完整'));
  assert.ok(rendered.getByText('系统仅展示当前已审核规则，不代表全部官方资格要求。'));
  assert.ok(rendered.getByText('尚未分析你的参赛资格。'));
  assert.equal(rendered.queryByText('资格已确认'), null);
  assert.equal(rendered.selections.length, 0);
});

test('null required level and authoritative catalog stay separate from personal skill analysis', () => {
  const p = projection();
  p.skill_requirements = {
    schema_version: '1.0',
    artifact_type: 'skill_requirement_set',
    requirement_version: 'synthetic-requirement-version',
    review_note: 'Synthetic UI-only review note',
    requirement_set: {
      coverage: 'partial',
      coverage_note: 'Explicit synthetic partial UI fixture',
      target: {
        competition_id: p.competition.id,
        edition_id: p.query.edition_id!,
        scope: 'edition',
      },
      requirements: [
        {
          skill_id: 'synthetic-skill',
          requirement_type: 'required',
          required_level: null,
          presence_evidence: [
            { code: 'SYNTHETIC_FACT', message: 'Synthetic requirement presence', source },
          ],
          evidence: [{ code: 'SYNTHETIC_SOURCE', message: 'Synthetic evidence', source }],
        },
      ],
    },
    skills: [{ id: 'synthetic-skill', name: '正式目录中的测试技能名' }],
  };
  const rendered = view(p, 2);
  assert.ok(rendered.getByRole('heading', { name: '正式目录中的测试技能名' }));
  assert.ok(rendered.getByText('所需能力等级暂未明确'));
  assert.ok(rendered.getByText('尚未进行个人技能差距分析。'));
  assert.equal(rendered.selections.length, 0);
  const panel = rendered.getByRole('tabpanel');
  assert.ok(!panel.textContent?.includes('synthetic-requirement-version'));
});

for (const [window, label] of [
  [null, '当前资料中暂未发现可靠时间信息'],
  [{ start_at: '2030-01-01T10:00:00+08:00', end_at: null }, '部分确认'],
  [{ start_at: null, end_at: '2030-01-02T10:00:00+08:00' }, '部分确认'],
] as const)
  test(`timeline preserves ${label} without submission milestones`, () => {
    const p = projection();
    p.availability.time_windows.requested = true;
    p.selected_edition!.registration_window = window;
    const rendered = render(<CompetitionTimeline detail={p} />);
    assert.ok(rendered.getAllByText(label).length > 0);
    assert.equal(rendered.container.querySelectorAll('ol > li').length, 2);
    assert.equal(rendered.queryByRole('heading', { name: /提交|决赛/ }), null);
    if (window?.start_at)
      assert.equal(rendered.container.querySelector('time')?.dateTime, window.start_at);
  });

function temporal(p: CompetitionDetailProjection): TemporalCandidateSnapshot {
  return {
    schema_version: '1.0',
    candidate_id: 'synthetic-ui-candidate',
    competition_id: p.competition.id,
    edition_id: p.query.edition_id!,
    field: 'registration_end',
    raw_text: '明确标记的测试原文：2030年5月',
    precision: 'MONTH',
    source,
    verification_status: 'pending',
    raw_reference: 'data/raw/synthetic.json',
    raw_digest: '0'.repeat(64),
    text_locator: '/raw_payload/registration_text',
    review_reference: 'synthetic-review',
    review_note: 'Synthetic UI-only candidate; never a real competition fact.',
  };
}

test('official pending text remains an edition quote, not a confirmed date', () => {
  const p = projection();
  p.temporal_candidates = [temporal(p)];
  p.query.track_id = 'synthetic-track';
  const original = JSON.stringify(p);
  const rendered = render(<CompetitionTimeline detail={p} />);
  assert.ok(rendered.getAllByText('官方已公布 · 待核验').length);
  assert.ok(rendered.getByText(temporal(p).raw_text));
  assert.ok(rendered.getByText('届次级时间依据（不代表特定赛道日程）'));
  assert.ok(rendered.getByText(/信息粒度：月份/));
  assert.ok(rendered.getByRole('link'));
  assert.equal(rendered.container.querySelectorAll('time[datetime="2030-05-01"]').length, 0);
  assert.equal(rendered.queryByText('时间已确认'), null);
  assert.equal(JSON.stringify(p), original);
});

test('verified full takes priority and pending text remains in evidence disclosure', () => {
  const p = projection();
  p.selected_edition!.registration_window = {
    start_at: '2030-01-01T10:00:00Z',
    end_at: '2030-01-02T10:00:00Z',
  };
  p.temporal_candidates = [temporal(p)];
  const rendered = render(<CompetitionTimeline detail={p} />);
  assert.ok(rendered.getByText('时间已确认'));
  const disclosure = rendered.getByText('存在待核验时间依据').closest('details')!;
  assert.equal(disclosure.open, false);
  assert.ok(within(disclosure).getByText(temporal(p).raw_text));
  assert.ok(rendered.container.querySelector('time[datetime="2030-01-02T10:00:00Z"]'));
});

test('partial verified window plus end candidate never fills the missing end', () => {
  const p = projection();
  p.selected_edition!.registration_window = { start_at: '2030-01-01T10:00:00Z', end_at: null };
  p.temporal_candidates = [temporal(p)];
  const rendered = render(<CompetitionTimeline detail={p} />);
  assert.ok(rendered.getByText('部分确认'));
  assert.ok(rendered.getAllByText('官方已公布 · 待核验').length);
  assert.equal(p.selected_edition!.registration_window.end_at, null);
});

for (const family of ['registration', 'competition'] as const) {
  for (const [known, field, mainExpected] of [
    ['start', 'end', true],
    ['start', 'start', false],
    ['end', 'start', true],
    ['end', 'end', false],
  ] as const) {
    test(`${family}: verified ${known} protects same endpoint; ${field} candidate main=${mainExpected}`, () => {
      const p = projection();
      const verified = '2030-01-01T10:00:00Z';
      p.selected_edition![`${family}_window`] = {
        start_at: known === 'start' ? verified : null,
        end_at: known === 'end' ? verified : null,
      };
      const c: TemporalCandidateSnapshot = {
        ...temporal(p),
        field: `${family}_${field}`,
        raw_text: `Synthetic ${family} ${field} quote`,
      };
      p.temporal_candidates = [c];
      const before = JSON.stringify(p);
      const rendered = render(<CompetitionTimeline detail={p} />);
      const section = rendered
        .getByRole('heading', { name: family === 'registration' ? '报名阶段' : '比赛阶段' })
        .closest('li')!;
      const main = section.querySelector('.timeline-main') as HTMLElement;
      assert.equal(!!within(main).queryByText(c.raw_text), mainExpected);
      const confirmed = within(main).getByText(known === 'start' ? '开始' : '结束').parentElement!;
      assert.equal(confirmed.querySelector('time')?.dateTime, verified);
      if (mainExpected) {
        const missing = within(main).getByText(field === 'start' ? '开始' : '结束').parentElement!;
        assert.ok(within(missing).getByText(c.raw_text));
        assert.equal(section.querySelector('details.temporal-audit'), null);
      } else {
        const audit = section.querySelector('details.temporal-audit') as HTMLDetailsElement;
        assert.equal(audit.open, false);
        assert.ok(within(audit).getByText(c.raw_text));
        assert.ok(within(audit).getByRole('link'));
        assert.equal(within(main).queryByText('官方已公布 · 待核验'), null);
      }
      assert.equal(JSON.stringify(p), before);
    });
  }

  for (const state of ['full', 'empty', 'partial-stage', 'empty-stage'] as const) {
    test(`${family}: ${state} keeps candidates in their permitted scope`, () => {
      const p = projection();
      p.selected_edition![`${family}_window`] = {
        start_at: state === 'full' || state === 'partial-stage' ? '2030-01-01T10:00:00Z' : null,
        end_at: state === 'full' ? '2030-01-02T10:00:00Z' : null,
      };
      const fields: TemporalCandidateSnapshot['field'][] = state.endsWith('stage')
        ? [family]
        : [`${family}_start`, `${family}_end`, family];
      const candidates = fields.map((field) => ({
        ...temporal(p),
        field,
        candidate_id: `synthetic-${field}`,
        raw_text: `Synthetic ${field} raw quote: deadline / start`,
      }));
      p.temporal_candidates = candidates;
      const before = JSON.stringify(p);
      const rendered = render(<CompetitionTimeline detail={p} />);
      const section = rendered
        .getByRole('heading', { name: family === 'registration' ? '报名阶段' : '比赛阶段' })
        .closest('li')!;
      const main = section.querySelector('.timeline-main') as HTMLElement;
      if (state === 'full' || state === 'partial-stage') {
        const audit = section.querySelector('details.temporal-audit') as HTMLDetailsElement;
        assert.equal(audit.open, false);
        for (const c of candidates) {
          assert.equal(within(main).queryByText(c.raw_text), null);
          assert.ok(within(audit).getByText(c.raw_text));
        }
        assert.equal(within(main).queryByText('官方已公布 · 待核验'), null);
      } else {
        for (const c of candidates) assert.ok(within(main).getByText(c.raw_text));
        assert.equal(section.querySelector('details.temporal-audit'), null);
        if (state === 'empty-stage') {
          // Source cards contain their own metadata lists; only a direct child
          // list here would incorrectly assign stage evidence to endpoints.
          assert.equal(Boolean(main.querySelector(':scope > dl')), false);
          assert.ok(within(section).getByText('官方已公布相关时间信息 · 待核验'));
        } else {
          for (const endpoint of ['start', 'end'] as const) {
            const row = within(main).getByText(
              endpoint === 'start' ? '开始' : '结束',
            ).parentElement!;
            assert.ok(
              within(row).getByText(
                candidates.find((c) => c.field === `${family}_${endpoint}`)!.raw_text,
              ),
            );
          }
        }
      }
      assert.equal(JSON.stringify(p), before);
    });
  }
}

test('classification preserves backend order and uses field identity, never quote wording', () => {
  const p = projection();
  const start: TemporalCandidateSnapshot = {
    ...temporal(p),
    field: 'registration_start',
    raw_text: 'deadline',
  };
  const end: TemporalCandidateSnapshot = {
    ...temporal(p),
    field: 'registration_end',
    raw_text: 'starts',
  };
  const stage: TemporalCandidateSnapshot = {
    ...temporal(p),
    field: 'registration',
    raw_text: 'start / end',
  };
  const second = { ...end, candidate_id: 'synthetic-second-end' };
  const candidates = [end, stage, start, second];
  const before = JSON.stringify(candidates);
  const result = classifyTimelineCandidates(
    { start_at: '2030-01-01T00:00:00Z', end_at: null },
    candidates,
    'registration',
  );
  assert.deepEqual(result.mainEndCandidates, [end, second]);
  assert.deepEqual(result.mainStartCandidates, []);
  assert.deepEqual(result.sectionCandidates, []);
  assert.deepEqual(result.auditCandidates, [stage, start]);
  assert.equal(JSON.stringify(candidates), before);
});

for (const kind of [
  'no-evidence',
  'non-official',
  'rejected',
  'wrong-target',
  'verified-candidate',
]) {
  test(`no official announcement inferred from ${kind}`, () => {
    const p = projection();
    const c = temporal(p);
    if (kind === 'non-official') c.source = { ...source, source_type: 'manual' };
    if (kind === 'rejected') c.verification_status = 'rejected';
    if (kind === 'verified-candidate') c.verification_status = 'verified';
    if (kind === 'wrong-target') c.edition_id = 'other-edition';
    p.temporal_candidates = kind === 'no-evidence' ? [] : [c];
    p.competition.official_url = 'https://example.invalid/official-fixture';
    const rendered = render(<CompetitionTimeline detail={p} />);
    assert.equal(rendered.queryByText('官方已公布 · 待核验'), null);
    assert.ok(rendered.getAllByText('当前资料中暂未发现可靠时间信息').length);
  });
}

test('unselected edition is not an unknown requested timeline', () => {
  const p = projection();
  p.selected_edition = null;
  p.query.edition_id = null;
  p.availability.time_windows.requested = false;
  const rendered = render(<CompetitionTimeline detail={p} />);
  assert.ok(rendered.getByText('请选择届次后查看时间信息。'));
  assert.equal(rendered.queryByText('当前资料中暂未发现可靠时间信息'), null);
});

test('evidence deduplicates URLs while preserving competition/edition associations and observations', () => {
  const p = projection();
  p.provenance[1].source = { ...source, observed_at: '2030-01-02T00:00:00Z' };
  const original = JSON.stringify(p);
  const rendered = render(<CompetitionEvidenceCenter detail={p} />);
  assert.equal(rendered.container.querySelectorAll('.grouped-source-card').length, 1);
  assert.ok(rendered.getByText(/赛事来源 · 赛事层级/));
  assert.ok(rendered.getByText(/届次来源 · 届次层级/));
  assert.ok(rendered.getByText(/历史观察记录 2 次/));
  fireEvent.change(rendered.getByRole('combobox', { name: '来源范围' }), {
    target: { value: 'track' },
  });
  assert.equal(rendered.container.querySelectorAll('.grouped-source-card').length, 0);
  assert.equal(JSON.stringify(p), original);
});

test('track header never upgrades an edition source to verified track evidence', () => {
  const p = projection();
  p.query.track_id = 'synthetic-track';
  p.selected_track = p.tracks![0];
  const rendered = view(p);
  const header = rendered.container.querySelector('.detail-hero')!;
  assert.ok(header.textContent?.includes('当前赛道来源'));
  assert.ok(header.textContent?.includes('尚未提供该范围的来源核验记录'));
});

test('guided action supplies an existing explicit action, canonical scope and no business result', () => {
  const p = projection();
  const rendered = view(p);
  fireEvent.click(rendered.getByRole('button', { name: '分析技能差距' }));
  assert.deepEqual(rendered.selections, [
    [
      p.competition.id,
      '分析技能差距',
      { editionId: p.query.edition_id, trackId: undefined },
      guidedActions.find((a) => a.intent === 'ANALYZE_SKILL_GAP'),
    ],
  ]);
  assert.equal(rendered.queryByText('资格已确认'), null);
});

test('event history remains unavailable and session evidence is a separate section', () => {
  const rendered = view(projection(), 6);
  assert.ok(rendered.getByText('暂未提供完整赛事变化历史'));
  assert.ok(rendered.getByRole('heading', { name: '当前会话中的赛事变化证据' }));
  assert.equal(rendered.selections.length, 0);
});
