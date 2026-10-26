import assert from 'node:assert/strict';
import test, { afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import type { AgentResponse, AgentRequest } from '../src/runtime/generated/contracts.ts';
import type { StudentProfileProjection } from '../src/results/generated/artifacts.ts';
import type { InvocationClient } from '../src/workspace/useConversation.ts';

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
const { render, cleanup, fireEvent, waitFor } = await import('@testing-library/react');
const { ProfilePage, profileCompletion, profileError } =
  await import('../src/workspace/ProfilePage.tsx');
const { SkillsManager, skillError } = await import('../src/workspace/SkillsManager.tsx');
afterEach(cleanup);

function profile(): StudentProfileProjection {
  return {
    id: 'test-student',
    student_id: 'test-student',
    education_level: 'undergraduate',
    grade: null,
    school: null,
    major: 'Original',
    interests: [],
    goals: [],
    weekly_available_hours: 0,
    skills: [
      { skill_id: 'catalog-unresolved', level: 'unknown', self_assessed: false, note: 'User note' },
    ],
    profile_ref: {
      student_id: 'test-student',
      version: 1,
      content_digest: 'a'.repeat(64),
      host_scope: 'test-host',
    },
    updated_at: '2026-10-23T00:00:00Z',
    updated_by: 'fixture-bootstrap',
    persistence_boundary: 'HOST_MEMORY',
  };
}
function environment(initial = profile(), failure?: string, emptyCatalog = false) {
  let server = structuredClone(initial);
  const calls: AgentRequest[] = [];
  const bundles = new Map<string, unknown>();
  const client: InvocationClient = {
    async exchange(envelope) {
      assert.ok(envelope.request);
      const request = envelope.request;
      calls.push(structuredClone(request));
      const bad =
        request.intent === 'UPDATE_PROFILE' || request.skill_command
          ? failure
          : failure === 'PROFILE_NOT_FOUND'
            ? failure
            : undefined;
      const ref = { kind: 'TOOL_RESULT' as const, ref_id: `${request.request_id}/result` };
      const response: AgentResponse = {
        request_id: request.request_id,
        intent: request.intent!,
        outcome: bad ? 'FAILED' : 'COMPLETED',
        message: bad ?? 'Completed',
        audit: { results: bad ? [] : [ref], reasons: [] },
        ...(bad ? { error: { code: 'CAPABILITY_EXECUTION_FAILED', message: bad } } : {}),
      };
      if (!bad) {
        if (request.skill_command) {
          const command = request.skill_command;
          assert.deepEqual(command.expected_profile_ref, server.profile_ref);
          const skills = server.skills ?? [];
          server = {
            ...server,
            skills:
              command.operation === 'remove'
                ? skills.filter((s) => s.skill_id !== command.skill_id)
                : command.operation === 'add'
                  ? [
                      ...skills,
                      {
                        skill_id: command.skill_id,
                        level: command.level ?? 'unknown',
                        note: command.note,
                        self_assessed: true,
                      },
                    ]
                  : skills.map((s) =>
                      s.skill_id === command.skill_id
                        ? { ...s, level: command.level, note: command.note }
                        : s,
                    ),
            profile_ref: { ...server.profile_ref, version: server.profile_ref.version + 1 },
          };
        }
        if (request.profile_update) {
          assert.deepEqual(request.profile_update.expected_profile_ref, server.profile_ref);
          server = {
            ...server,
            ...request.profile_update.patch,
            profile_ref: { ...server.profile_ref, version: server.profile_ref.version + 1 },
          };
        }
        bundles.set(response.request_id, {
          request_id: response.request_id,
          artifacts: [
            {
              ref,
              model:
                request.intent === 'GET_SKILL_CATALOG'
                  ? 'SkillCatalogProjection'
                  : request.profile_update || request.skill_command
                    ? 'ProfileMutationResult'
                    : 'StudentProfileProjection',
              value:
                request.intent === 'GET_SKILL_CATALOG'
                  ? {
                      skills: emptyCatalog
                        ? []
                        : [
                            {
                              skill_id: 'modeling',
                              name: 'Mathematical Modeling',
                              description: 'Catalog description',
                              aliases: [],
                            },
                            {
                              skill_id: 'known',
                              name: 'Known Skill',
                              description: null,
                              aliases: [],
                            },
                          ],
                    }
                  : request.profile_update || request.skill_command
                    ? {
                        profile: server,
                        changed_fields: request.profile_update
                          ? Object.keys(request.profile_update.patch)
                          : ['skills'],
                        request_id: request.request_id,
                      }
                    : server,
            },
          ],
        });
      }
      return { response };
    },
    async invoke(request, options) {
      return (await this.exchange({ request }, options)).response!;
    },
  };
  return {
    client,
    calls,
    readArtifacts: (response: AgentResponse) => bundles.get(response.request_id),
    current: () => server,
  };
}
function page(env: ReturnType<typeof environment>, student: string | undefined = 'test-student') {
  return render(
    <ProfilePage
      active
      context={{ student_id: student }}
      client={env.client}
      readArtifacts={env.readArtifacts}
      disabled={false}
      onBusy={() => {}}
      openCopilot={() => {}}
    />,
  );
}

test('reads explicit current profile, hides identities and displays persistence and skill semantics', async () => {
  const env = environment();
  const view = page(env);
  await view.findByRole('button', { name: '编辑画像' });
  assert.equal(env.calls[0].intent, 'GET_PROFILE');
  assert.deepEqual(env.calls[0].context, { student_id: 'test-student' });
  assert.ok(view.getByText('0 小时 / 周'));
  assert.ok(view.getByText('基础画像已填写 3/7 项'));
  assert.ok(view.getByText('等级：尚未评定'));
  assert.ok(view.getByText('来源：非自评，来源尚未记录'));
  assert.ok(view.getByText(/服务重启后不会保留/));
  assert.equal(view.container.querySelector('details')?.open, false);
  assert.equal(view.queryByText('已认证'), null);
  assert.ok(view.getByRole('button', { name: '添加技能' }));
});

test('missing student never selects a default or invokes runtime', () => {
  const env = environment();
  const view = page(env, '');
  assert.ok(view.getByRole('heading', { name: '尚未选择当前学生' }));
  assert.equal(env.calls.length, 0);
});

test('profile not found is distinct from empty profile fields', async () => {
  const env = environment(profile(), 'PROFILE_NOT_FOUND');
  const view = page(env);
  assert.match((await view.findByRole('alert')).textContent ?? '', /尚未创建个人画像/);
  assert.equal(view.queryByRole('button', { name: '编辑画像' }), null);
});

test('cancel is local only; save sends exact reference and seven fields without skills', async () => {
  const env = environment();
  const view = page(env);
  fireEvent.click(await view.findByRole('button', { name: '编辑画像' }));
  fireEvent.change(view.getByRole('textbox', { name: '专业' }), { target: { value: 'Cancelled' } });
  fireEvent.click(view.getByRole('button', { name: '取消编辑' }));
  assert.equal(env.calls.filter((c) => c.intent !== 'GET_SKILL_CATALOG').length, 1);
  assert.equal(env.current().major, 'Original');
  fireEvent.click(view.getByRole('button', { name: '编辑画像' }));
  fireEvent.change(view.getByRole('textbox', { name: '专业' }), { target: { value: 'Computing' } });
  fireEvent.change(view.getByRole('spinbutton'), { target: { value: '7.5' } });
  fireEvent.click(view.getByRole('button', { name: '保存画像' }));
  await view.findByText('画像已保存。已有分析和计划不会自动更新。');
  assert.equal(env.calls.filter((c) => c.intent !== 'GET_SKILL_CATALOG').length, 2);
  const save = env.calls.find((c) => c.intent === 'UPDATE_PROFILE')!;
  assert.equal(save.intent, 'UPDATE_PROFILE');
  assert.equal(save.profile_update?.patch.weekly_available_hours, 7.5);
  assert.equal(save.profile_update?.expected_profile_ref.version, 1);
  assert.equal(Object.hasOwn(save.profile_update!.patch, 'skills'), false);
  assert.equal(Object.keys(save.profile_update!.patch).length, 7);
  assert.ok(view.getByText('Computing'));
  assert.ok(view.getByText('7.5 小时 / 周'));
});

test('zero and explicit clears survive frontend save', async () => {
  const env = environment();
  const view = page(env);
  fireEvent.click(await view.findByRole('button', { name: '编辑画像' }));
  fireEvent.change(view.getByRole('textbox', { name: '专业' }), { target: { value: '' } });
  fireEvent.click(view.getByRole('button', { name: '保存画像' }));
  await waitFor(() => assert.ok(env.calls.find((c) => c.intent === 'UPDATE_PROFILE')));
  const saved = env.calls.find((c) => c.intent === 'UPDATE_PROFILE')!;
  assert.equal(saved.profile_update?.patch.major, null);
  assert.equal(saved.profile_update?.patch.weekly_available_hours, 0);
  assert.deepEqual(saved.profile_update?.patch.interests, []);
});

test('version conflict preserves draft and never auto-overwrites', async () => {
  const env = environment(profile(), 'PROFILE_VERSION_CONFLICT');
  const view = page(env);
  fireEvent.click(await view.findByRole('button', { name: '编辑画像' }));
  fireEvent.change(view.getByRole('textbox', { name: '专业' }), { target: { value: 'Unsaved' } });
  fireEvent.click(view.getByRole('button', { name: '保存画像' }));
  assert.match(
    (await view.findByRole('alert')).textContent ?? '',
    /画像已发生变化，请重新加载后再保存/,
  );
  assert.equal((view.getByRole('textbox', { name: '专业' }) as HTMLInputElement).value, 'Unsaved');
  assert.equal(env.calls.filter((c) => c.intent !== 'GET_SKILL_CATALOG').length, 2);
  assert.equal(env.current().major, 'Original');
});

test('missing skill records are not a skill deficit; self-assessment is not certification', async () => {
  const env = environment({ ...profile(), skills: [] });
  const view = page(env);
  await view.findByText(/尚未记录技能。你可以/);
  assert.equal(view.queryByText('技能为 0'), null);
  cleanup();
  const self = environment({
    ...profile(),
    skills: [{ skill_id: 'known', level: 'intermediate', self_assessed: true }],
  });
  const selfView = page(self);
  await selfView.findByText('来源：自评');
  assert.ok(selfView.getByText('等级：中级'));
});

test('completion excludes skills and counts zero hours', () => {
  assert.equal(profileCompletion(profile()), 3);
  assert.equal(profileCompletion({ ...profile(), skills: [] }), 3);
  assert.equal(profileCompletion({ ...profile(), weekly_available_hours: null }), 2);
  assert.equal(
    profileCompletion({
      ...profile(),
      grade: 'Year 2',
      school: 'School',
      interests: ['A'],
      goals: ['B'],
    }),
    7,
  );
});

test('catalog add, edit UNKNOWN and delete roundtrip preserve canonical refs and completion', async () => {
  const env = environment();
  const view = page(env);
  const add = await view.findByRole('button', { name: '添加技能' });
  await waitFor(() => assert.equal((add as HTMLButtonElement).disabled, false));
  fireEvent.click(add);
  const selector = view.getByRole('combobox', { name: '选择技能' });
  assert.ok(view.getByRole('option', { name: 'Mathematical Modeling' }));
  fireEvent.change(selector, { target: { value: 'modeling' } });
  fireEvent.change(view.getByRole('combobox', { name: '技能等级' }), {
    target: { value: 'intermediate' },
  });
  fireEvent.change(view.getByRole('textbox', { name: '用户备注' }), {
    target: { value: 'Course project' },
  });
  fireEvent.click(view.getByRole('button', { name: '保存技能' }));
  await view.findByRole('heading', { name: 'Mathematical Modeling' });
  assert.ok(view.getByText('备注：Course project'));
  assert.ok(view.getByText('基础画像已填写 3/7 项'));
  assert.ok(view.getByText('已记录 2 项技能，其中 1 项尚未评定'));
  fireEvent.click(view.getByRole('button', { name: '添加技能' }));
  assert.equal(view.queryByRole('option', { name: 'Mathematical Modeling' }), null);
  fireEvent.click(view.getByRole('button', { name: '取消技能编辑' }));
  fireEvent.click(view.getByRole('button', { name: '编辑 Mathematical Modeling' }));
  assert.equal(view.queryByRole('combobox', { name: '选择技能' }), null);
  fireEvent.change(view.getByRole('combobox', { name: '技能等级' }), {
    target: { value: 'unknown' },
  });
  fireEvent.click(view.getByRole('button', { name: '保存技能' }));
  await view.findByText('已记录 2 项技能，其中 2 项尚未评定');
  fireEvent.click(view.getByRole('button', { name: '删除 Mathematical Modeling 记录' }));
  assert.ok(view.getByRole('dialog', { name: '确认删除技能记录' }));
  assert.ok(view.getByText(/将变为“尚未记录”，而不是“等级未知”/));
  fireEvent.click(view.getByRole('button', { name: '确认删除记录' }));
  await waitFor(() =>
    assert.ok(view.queryByRole('heading', { name: 'Mathematical Modeling' }) === null),
  );
  assert.ok(view.getByText('已记录 1 项技能，其中 1 项尚未评定'));
  const commands = env.calls.filter((c) => c.skill_command);
  assert.deepEqual(
    commands.map((c) => c.intent),
    ['ADD_PROFILE_SKILL', 'UPDATE_PROFILE_SKILL', 'REMOVE_PROFILE_SKILL'],
  );
  assert.deepEqual(
    commands.map((c) => c.skill_command!.expected_profile_ref.version),
    [1, 2, 3],
  );
  assert.equal(commands[0].skill_command!.skill_id, 'modeling');
  assert.ok(
    env.calls.every((c) =>
      [
        'GET_PROFILE',
        'GET_SKILL_CATALOG',
        'ADD_PROFILE_SKILL',
        'UPDATE_PROFILE_SKILL',
        'REMOVE_PROFILE_SKILL',
      ].includes(c.intent!),
    ),
  );
});

test('skill conflict preserves user draft without changing current profile', async () => {
  const env = environment(profile(), 'PROFILE_VERSION_CONFLICT');
  const view = page(env);
  const edit = await view.findByRole('button', { name: '编辑 catalog-unresolved' });
  await waitFor(() => assert.equal((edit as HTMLButtonElement).disabled, false));
  fireEvent.click(edit);
  fireEvent.change(view.getByRole('textbox', { name: '用户备注' }), {
    target: { value: 'Unsaved note' },
  });
  fireEvent.click(view.getByRole('button', { name: '保存技能' }));
  assert.match((await view.findByRole('alert')).textContent ?? '', /画像已发生变化/);
  assert.equal(
    (view.getByRole('textbox', { name: '用户备注' }) as HTMLTextAreaElement).value,
    'Unsaved note',
  );
  assert.equal(env.current().skills?.[0].note, 'User note');
  assert.equal(view.queryByText('已认证'), null);
});

test('delete cancel preserves record and makes no mutation request', async () => {
  const env = environment();
  const view = page(env);
  const button = await view.findByRole('button', { name: '删除 catalog-unresolved 记录' });
  await waitFor(() => assert.equal((button as HTMLButtonElement).disabled, false));
  fireEvent.click(button);
  fireEvent.click(view.getByRole('button', { name: '取消删除' }));
  assert.ok(view.getByRole('heading', { name: 'catalog-unresolved' }));
  assert.equal(env.calls.filter((c) => c.skill_command).length, 0);
});

test('empty catalog disables additions and provides no free-ID input', async () => {
  const env = environment(profile(), undefined, true);
  const view = page(env);
  await view.findByText('当前暂无可添加的技能目录项');
  assert.equal(
    (view.getByRole('button', { name: '添加技能' }) as HTMLButtonElement).disabled,
    true,
  );
  assert.equal(view.queryByRole('textbox', { name: 'skill_id' }), null);
});

test('skill form retains its opening reference if a newer projection arrives', async () => {
  const env = environment();
  const props = {
    client: env.client,
    readArtifacts: env.readArtifacts,
    disabled: false,
    onBusy: () => {},
    onUpdated: () => {},
  };
  const initial = profile();
  const view = render(<SkillsManager {...props} profile={initial} />);
  const edit = view.getByRole('button', { name: '编辑 catalog-unresolved' });
  await waitFor(() => assert.equal((edit as HTMLButtonElement).disabled, false));
  fireEvent.click(edit);
  view.rerender(
    <SkillsManager
      {...props}
      profile={{ ...initial, profile_ref: { ...initial.profile_ref, version: 2 } }}
    />,
  );
  fireEvent.change(view.getByRole('textbox', { name: '用户备注' }), {
    target: { value: 'Updated annotation' },
  });
  fireEvent.click(view.getByRole('button', { name: '保存技能' }));
  await waitFor(() => assert.ok(env.calls.some((c) => c.skill_command)));
  assert.equal(
    env.calls.find((c) => c.skill_command)!.skill_command!.expected_profile_ref.version,
    1,
  );
});

for (const code of [
  'SKILL_ALREADY_EXISTS',
  'SKILL_NOT_FOUND',
  'SKILL_NOT_IN_CATALOG',
  'INVALID_SKILL_LEVEL',
  'PROFILE_VERSION_CONFLICT',
  'PROFILE_EDIT_FORBIDDEN',
  'SKILL_EVIDENCE_INCONSISTENT',
])
  test(`skill error ${code} has product wording`, () => {
    assert.notEqual(skillError(code), code);
    assert.doesNotMatch(skillError(code), /Pydantic|ValueError|traceback/);
  });

for (const code of [
  'PROFILE_EDIT_FORBIDDEN',
  'INVALID_EDUCATION_LEVEL',
  'INVALID_WEEKLY_HOURS',
  'INVALID_PROFILE_FIELD',
])
  test(`semantic validation maps ${code} without raw exception prose`, () => {
    assert.notEqual(profileError(code), code);
    assert.doesNotMatch(profileError(code), /ValueError|Pydantic|traceback/);
  });
