import type { ReactNode } from 'react';
import { SkillsManager } from './SkillsManager.tsx';
import { useEffect, useRef, useState } from 'react';
import type { AgentContext, ProfilePatch } from '../runtime/generated/contracts.ts';
import type { StudentProfileProjection } from '../results/generated/artifacts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import { errorDetails } from '../results/ErrorPresentation.tsx';
import type { InvocationClient } from './useConversation.ts';

const fields = [
  ['grade', '年级'],
  ['school', '学校'],
  ['major', '专业'],
] as const;
const education = { undergraduate: '本科', graduate: '研究生' };
const persistence = '当前 Demo 的画像修改仅保存在运行中的服务内，服务重启后不会保留。';
type Draft = {
  education_level: string;
  grade: string;
  school: string;
  major: string;
  interests: string;
  goals: string;
  weekly_available_hours: string;
};
function draftFrom(profile: StudentProfileProjection): Draft {
  return {
    education_level: profile.education_level ?? '',
    grade: profile.grade ?? '',
    school: profile.school ?? '',
    major: profile.major ?? '',
    interests: (profile.interests ?? []).join('\n'),
    goals: (profile.goals ?? []).join('\n'),
    weekly_available_hours:
      profile.weekly_available_hours == null ? '' : String(profile.weekly_available_hours),
  };
}
export function profileCompletion(profile: StudentProfileProjection) {
  return [
    profile.education_level,
    profile.grade,
    profile.school,
    profile.major,
    (profile.interests ?? []).length || null,
    (profile.goals ?? []).length || null,
    profile.weekly_available_hours,
  ].filter((value) => value != null && value !== '').length;
}
export function profileError(identity: string) {
  if (identity.includes('PROFILE_VERSION_CONFLICT')) return '画像已发生变化，请重新加载后再保存。';
  if (identity.includes('PROFILE_NOT_FOUND')) return '尚未创建个人画像。';
  if (identity.includes('PROFILE_EDIT_FORBIDDEN')) return '当前操作者无权访问或编辑此学生画像。';
  if (identity.includes('INVALID_EDUCATION_LEVEL')) return '请选择有效的教育阶段。';
  if (identity.includes('INVALID_WEEKLY_HOURS'))
    return '每周时间须为 0 至 168 之间的有限数，可填写小数。';
  if (identity.includes('INVALID_PROFILE_FIELD') || identity.includes('INVALID_INPUT'))
    return '画像字段无效，请检查空白内容和输入范围。';
  return '暂时无法读取或保存画像，请检查 Runtime 连接后重新加载。';
}

export function ProfilePage({
  analyses,
  active,
  context,
  client,
  readArtifacts,
  disabled,
  onBusy,
  openCopilot,
}: {
  analyses?: ReactNode;
  active: boolean;
  context: AgentContext;
  client: InvocationClient;
  readArtifacts?: ArtifactReader;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  openCopilot: () => void;
}) {
  const student = context.student_id;
  const [profile, setProfile] = useState<StudentProfileProjection | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const busy = useRef(false);
  const attempted = useRef(false);
  const mounted = useRef(true);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      abort.current?.abort();
    };
  }, []);
  async function exchange(patch?: ProfilePatch) {
    if (!student || disabled || busy.current || (patch && !profile)) return;
    busy.current = true;
    attempted.current = true;
    setLoading(true);
    setError('');
    setNotice('');
    onBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    try {
      const result = await client.exchange(
        {
          request: {
            request_id: `profile-${crypto.randomUUID()}`,
            user_message: patch ? '保存个人画像' : '查看个人画像',
            intent: patch ? 'UPDATE_PROFILE' : 'GET_PROFILE',
            context: { student_id: student },
            ...(patch
              ? { profile_update: { expected_profile_ref: profile!.profile_ref, patch } }
              : {}),
          },
        },
        { signal: controller.signal },
      );
      if (!mounted.current) return;
      if (!result.response || result.response.outcome !== 'COMPLETED') {
        setError(
          profileError(`${result.response?.error?.code} ${result.response?.error?.message}`),
        );
        return;
      }
      const artifacts = validateArtifacts(result.response, readArtifacts?.(result.response));
      const value = artifacts
        .flatMap((artifact) =>
          artifact.model === 'StudentProfileProjection'
            ? [artifact.value]
            : artifact.model === 'ProfileMutationResult'
              ? [artifact.value.profile]
              : [],
        )
        .at(-1);
      if (!value || value.student_id !== student) throw new Error('INVALID_PROFILE_ARTIFACT');
      setProfile(value);
      setDraft(draftFrom(value));
      setEditing(false);
      if (patch) setNotice('画像已保存。已有分析和计划不会自动更新。');
    } catch (failure) {
      if (mounted.current) {
        const detail = errorDetails(failure);
        setError(profileError(`${detail.code} ${detail.message}`));
      }
    } finally {
      busy.current = false;
      if (mounted.current) {
        setLoading(false);
        onBusy(false);
      }
    }
  }
  useEffect(() => {
    if (active && student && !disabled && !attempted.current) void exchange();
  }, [active, student, disabled]);
  if (!student)
    return (
      <section className="profile-page">
        <h1>我的能力</h1>
        <div className="product-empty">
          <h2>尚未选择当前学生</h2>
          <p>请在 Copilot 中明确选择学生上下文。</p>
          <button onClick={openCopilot}>打开 Copilot</button>
        </div>
      </section>
    );

  return (
    <section className="profile-page" aria-busy={loading}>
      <header>
        <h1>我的能力</h1>
        <p>个人画像记录你提供的信息，业务判断仍由正式分析完成。</p>
      </header>
      <p className="profile-persistence">{persistence}</p>
      <nav
        aria-label="画像页面分区"
        onClick={(event) => {
          const anchor = (event.target as HTMLElement).closest('a');
          if (anchor) {
            event.preventDefault();
            document.getElementById(anchor.hash.slice(1))?.scrollIntoView?.({ behavior: 'smooth' });
          }
        }}
      >
        <a href="#profile-basics">个人画像</a> · <a href="#profile-skills">我的技能</a> ·{' '}
        <a href="#profile-analysis">相关分析</a>
      </nav>
      {loading && <p role="status">{editing ? '正在保存个人画像…' : '正在读取个人画像…'}</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <button disabled={disabled || loading} onClick={() => void exchange()}>
        重新加载画像
      </button>
      {profile && draft && (
        <>
          <section className="profile-section" id="profile-basics">
            <h2>个人画像</h2>
            <p>基础画像已填写 {profileCompletion(profile)}/7 项</p>
            <p>填写情况不代表能力分数或推荐准确率。</p>
            {!editing ? (
              <>
                <dl>
                  <dt>教育阶段</dt>
                  <dd>
                    {profile.education_level ? education[profile.education_level] : '尚未填写'}
                  </dd>
                  {fields.map(([key, label]) => (
                    <div key={key}>
                      <dt>{label}</dt>
                      <dd>{profile[key] ?? '尚未填写'}</dd>
                    </div>
                  ))}
                  <dt>兴趣</dt>
                  <dd>{profile.interests?.join('、') || '尚未填写'}</dd>
                  <dt>目标</dt>
                  <dd>{profile.goals?.join('、') || '尚未填写'}</dd>
                  <dt>每周可投入时间</dt>
                  <dd>
                    {profile.weekly_available_hours == null
                      ? '尚未填写'
                      : `${profile.weekly_available_hours} 小时 / 周`}
                  </dd>
                </dl>
                <button
                  disabled={disabled || loading}
                  onClick={() => {
                    setDraft(draftFrom(profile));
                    setEditing(true);
                    setNotice('');
                  }}
                >
                  编辑画像
                </button>
              </>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void exchange({
                    education_level: (draft.education_level ||
                      null) as ProfilePatch['education_level'],
                    grade: draft.grade === '' ? null : draft.grade,
                    school: draft.school === '' ? null : draft.school,
                    major: draft.major === '' ? null : draft.major,
                    interests: draft.interests === '' ? [] : draft.interests.split('\n'),
                    goals: draft.goals === '' ? [] : draft.goals.split('\n'),
                    weekly_available_hours:
                      draft.weekly_available_hours === ''
                        ? null
                        : Number(draft.weekly_available_hours),
                  });
                }}
              >
                <fieldset disabled={disabled || loading}>
                  <legend>编辑基础画像</legend>
                  <label>
                    教育阶段
                    <select
                      value={draft.education_level}
                      onChange={(e) => setDraft({ ...draft, education_level: e.target.value })}
                    >
                      <option value="">尚未填写</option>
                      <option value="undergraduate">本科</option>
                      <option value="graduate">研究生</option>
                    </select>
                  </label>
                  {fields.map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input
                        value={draft[key]}
                        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                      />
                    </label>
                  ))}
                  <label>
                    兴趣（每行一项）
                    <textarea
                      value={draft.interests}
                      onChange={(e) => setDraft({ ...draft, interests: e.target.value })}
                    />
                  </label>
                  <label>
                    目标（每行一项）
                    <textarea
                      value={draft.goals}
                      onChange={(e) => setDraft({ ...draft, goals: e.target.value })}
                    />
                  </label>
                  <label>
                    每周可投入时间（小时 / 周）
                    <input
                      type="number"
                      min="0"
                      max="168"
                      step="any"
                      value={draft.weekly_available_hours}
                      onChange={(e) =>
                        setDraft({ ...draft, weekly_available_hours: e.target.value })
                      }
                    />
                  </label>
                  <button type="submit">保存画像</button>
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(draftFrom(profile));
                      setEditing(false);
                      setError('');
                    }}
                  >
                    取消编辑
                  </button>
                </fieldset>
              </form>
            )}
            <details>
              <summary>查看技术详情</summary>
              <pre>
                {JSON.stringify(
                  {
                    profile_ref: profile.profile_ref,
                    updated_at: profile.updated_at,
                    updated_by: profile.updated_by,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
          <SkillsManager
            profile={profile}
            client={client}
            readArtifacts={readArtifacts}
            disabled={disabled || loading || editing}
            onBusy={onBusy}
            onUpdated={(saved) => {
              setProfile(saved);
              setDraft(draftFrom(saved));
            }}
          />
          <section className="profile-section" id="profile-analysis">
            <h2>相关分析</h2>
            {analyses ?? <p>View existing analysis results in Copilot.</p>}
            <button onClick={openCopilot}>Copilot</button>
          </section>
        </>
      )}
    </section>
  );
}
