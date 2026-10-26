import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import type { ProfileAnalysis, ProfileFreshness } from '../src/results/generated/artifacts.ts';
import type { ReadRecord } from '../src/workspace/competitionSession.ts';
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
  configurable: true,
  writable: true,
});
const { render, fireEvent, cleanup, waitFor } = await import('@testing-library/react');
const {
  ProfileFreshnessContext,
  ProfileFreshnessBadge,
  ProfileAnalyses,
  DerivedResultFreshness,
  useProfileFreshness,
  derivedCandidates,
} = await import('../src/workspace/ProfileFreshness.tsx');
afterEach(cleanup);
const reference = {
  student_id: 'student',
  version: 1,
  content_digest: 'a'.repeat(64),
  host_scope: 'host',
};
function analysis(status: ProfileFreshness['status']): ProfileAnalysis {
  return {
    result_ref_id: 'result',
    binding: null,
    profile_freshness: {
      status,
      input_profile_ref: status === 'UNKNOWN' ? null : reference,
      current_profile_ref: status === 'STALE' ? { ...reference, version: 2 } : reference,
      reason:
        status === 'CURRENT'
          ? 'EXACT_REFERENCE_MATCH'
          : status === 'STALE'
            ? 'PROFILE_REFERENCE_CHANGED'
            : 'RESULT_PROFILE_REFERENCE_UNKNOWN',
    },
  };
}
for (const [status, label] of [
  ['CURRENT', '基于当前画像'],
  ['STALE', '基于较早画像'],
  ['UNKNOWN', '画像版本未记录，无法确认'],
] as const)
  test(`${status} is read metadata, preserves old content and hides technical refs initially`, () => {
    const view = render(
      <ProfileFreshnessContext.Provider
        value={{
          enabled: true,
          candidates: [{ id: 'result', kind: 'SkillGapDecision' }],
          analyses: [analysis(status)],
          loading: false,
          error: false,
        }}
      >
        <DerivedResultFreshness identity="result">
          <p>Original GAP / original score / plan v1</p>
        </DerivedResultFreshness>
      </ProfileFreshnessContext.Provider>,
    );
    assert.ok(view.getByText(label));
    assert.ok(view.getByText('Original GAP / original score / plan v1'));
    assert.equal(view.queryByRole('alert'), null);
    const details = view.getByText('查看画像版本审计').closest('details')!;
    assert.equal(details.open, false);
    assert.match(details.textContent!, /input_profile_ref/);
  });

test('mismatched student/target results are not shown as stale', () => {
  const view = render(
    <ProfileFreshnessContext.Provider
      value={{ enabled: true, candidates: [], analyses: [], loading: false, error: false }}
    >
      <DerivedResultFreshness identity="another-student">
        <p>Private result</p>
      </DerivedResultFreshness>
    </ProfileFreshnessContext.Provider>,
  );
  assert.equal(view.queryByText('Private result'), null);
  assert.equal(view.queryByText('基于较早画像'), null);
});

test('rerun CTAs dispatch only explicit existing actions and never execute on render', () => {
  const actions: string[] = [];
  const view = render(
    <ProfileFreshnessContext.Provider
      value={{
        enabled: true,
        candidates: [],
        analyses: [],
        loading: false,
        error: false,
        rerun: (a) => actions.push(a.intent),
      }}
    >
      <ProfileAnalyses
        context={{ student_id: 'student', competition_id: 'competition', edition_id: 'edition' }}
        disabled={false}
        openCopilot={() => {}}
      />
    </ProfileFreshnessContext.Provider>,
  );
  assert.deepEqual(actions, []);
  for (const name of ['根据当前画像推荐赛事', '重新分析技能差距', '重新生成计划'])
    fireEvent.click(view.getByRole('button', { name }));
  assert.deepEqual(actions, ['GET_RECOMMENDATIONS', 'ANALYZE_SKILL_GAP', 'BUILD_PLAN']);
});

test('freshness refresh after profile/skill save is a read only, with backend status unchanged', async () => {
  const calls: string[] = [];
  const bundles = new Map<string, unknown>();
  let serverStatus: ProfileFreshness['status'] = 'CURRENT';
  const client: InvocationClient = {
    async exchange({ request }) {
      assert.ok(request);
      calls.push(request.intent!);
      assert.equal(request.intent, 'GET_PROFILE_ANALYSES');
      const ref = { kind: 'TOOL_RESULT' as const, ref_id: request.request_id + '/result' };
      const response = {
        request_id: request.request_id,
        intent: request.intent!,
        outcome: 'COMPLETED' as const,
        message: 'Read',
        audit: { results: [ref], reasons: [] },
      };
      bundles.set(request.request_id, {
        request_id: request.request_id,
        artifacts: [
          {
            ref,
            model: 'ProfileAnalysesProjection',
            value: { student_id: 'student', analyses: [analysis(serverStatus)] },
          },
        ],
      });
      return { response };
    },
    async invoke() {
      throw new Error('unused');
    },
  };
  const base = {
    response: { request_id: 'old' },
    context: { student_id: 'student' },
    artifacts: [
      {
        ref: { kind: 'TOOL_RESULT', ref_id: 'result' },
        model: 'RecommendationRankingResult',
        value: {},
      },
    ],
  } as ReadRecord;
  const records: ReadRecord[] = [base];
  function Harness({ items }: { items: ReadRecord[] }) {
    const value = useProfileFreshness(
      items,
      { student_id: 'student' },
      client,
      (r) => bundles.get(r.request_id),
      false,
    );
    return (
      <ProfileFreshnessContext.Provider value={value}>
        <ProfileFreshnessBadge identity="result" />
      </ProfileFreshnessContext.Provider>
    );
  }
  const view = render(<Harness items={records} />);
  await view.findByText('基于当前画像');
  serverStatus = 'STALE';
  const changed = {
    response: {},
    context: {},
    artifacts: [
      {
        ref: { kind: 'TOOL_RESULT', ref_id: 'save' },
        model: 'ProfileMutationResult',
        value: { profile: { student_id: 'student', profile_ref: { ...reference, version: 2 } } },
      },
    ],
  } as ReadRecord;
  view.rerender(<Harness items={[...records, changed]} />);
  await view.findByText('基于较早画像');
  await waitFor(() => assert.equal(calls.length, 2));
  assert.deepEqual(calls, ['GET_PROFILE_ANALYSES', 'GET_PROFILE_ANALYSES']);
});

test('session candidate matching retains exact student, edition and track', () => {
  const record = {
    response: {},
    context: { student_id: 'student' },
    artifacts: [
      {
        ref: { kind: 'TOOL_RESULT', ref_id: 'gap' },
        model: 'SkillGapDecision',
        value: { target: { competition_id: 'c', edition_id: 'e', track_id: null } },
      },
    ],
  } as ReadRecord;
  assert.equal(
    derivedCandidates([record], { student_id: 'other', competition_id: 'c', edition_id: 'e' })
      .length,
    0,
  );
  assert.equal(
    derivedCandidates([record], {
      student_id: 'student',
      competition_id: 'c',
      edition_id: 'e',
      track_id: 't',
    }).length,
    0,
  );
  assert.equal(
    derivedCandidates([record], { student_id: 'student', competition_id: 'c', edition_id: 'e' })
      .length,
    1,
  );
});
