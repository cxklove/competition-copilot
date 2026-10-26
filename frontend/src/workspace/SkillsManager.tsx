import { useEffect, useRef, useState } from 'react';
import type { SkillCommand } from '../runtime/generated/contracts.ts';
import type { CatalogSkill, StudentProfileProjection } from '../results/generated/artifacts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import type { ArtifactReader } from '../results/artifacts.ts';
import type { InvocationClient } from './useConversation.ts';
import { errorDetails } from '../results/ErrorPresentation.tsx';

const levels = { unknown: '尚未评定', beginner: '初级', intermediate: '中级', advanced: '高级' };
export function skillError(code: string) {
  if (code.includes('PROFILE_VERSION_CONFLICT')) return '画像已发生变化，请重新加载后再保存。';
  if (code.includes('PROFILE_EDIT_FORBIDDEN')) return '当前操作者无权编辑此学生画像。';
  if (code.includes('SKILL_ALREADY_EXISTS')) return '已记录该技能，请编辑现有记录。';
  if (code.includes('SKILL_NOT_FOUND')) return '未找到该技能记录，请重新加载画像。';
  if (code.includes('SKILL_NOT_IN_CATALOG')) return '该技能不在当前可添加的技能目录中。';
  if (code.includes('SKILL_EVIDENCE_INCONSISTENT'))
    return '技能资料与自评依据不一致，本次修改未保存。';
  if (code.includes('SKILL_CATALOG_CONFLICT')) return '技能目录定义存在冲突，暂时无法加载目录。';
  if (
    code.includes('INVALID_SKILL_LEVEL') ||
    code.includes('INVALID_INPUT') ||
    code.includes('INVALID_PROFILE_FIELD')
  )
    return '技能等级或备注无效，请检查输入。';
  return '暂时无法读取或保存技能，请检查 Runtime 连接。';
}

export function SkillsManager({
  profile,
  client,
  readArtifacts,
  disabled,
  onBusy,
  onUpdated,
}: {
  profile: StudentProfileProjection;
  client: InvocationClient;
  readArtifacts?: ArtifactReader;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  onUpdated: (profile: StudentProfileProjection) => void;
}) {
  const [catalog, setCatalog] = useState<CatalogSkill[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState<{
    operation: 'add' | 'update';
    skill_id: string;
    level: SkillCommand['level'];
    note: string;
    expected_profile_ref: StudentProfileProjection['profile_ref'];
  } | null>(null);
  const [remove, setRemove] = useState<{
    skill_id: string;
    expected_profile_ref: StudentProfileProjection['profile_ref'];
  } | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const skills = profile.skills ?? [];
  const available = catalog.filter(
    (s) => !skills.some((existing) => existing.skill_id === s.skill_id),
  );
  const name = (id: string) => catalog.find((s) => s.skill_id === id)?.name ?? id;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  async function exchange(command?: SkillCommand) {
    if (inFlight.current || (command && disabled)) return;
    inFlight.current = true;
    setPending(true);
    setError('');
    setNotice('');
    onBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const intent = command
        ? (
            {
              add: 'ADD_PROFILE_SKILL',
              update: 'UPDATE_PROFILE_SKILL',
              remove: 'REMOVE_PROFILE_SKILL',
            } as const
          )[command.operation]
        : 'GET_SKILL_CATALOG';
      const result = await client.exchange(
        {
          request: {
            request_id: `skills-${crypto.randomUUID()}`,
            user_message: command ? '保存技能记录' : '读取技能目录',
            intent,
            context: { student_id: profile.student_id },
            ...(command ? { skill_command: command } : {}),
          },
        },
        { signal: abort.signal },
      );
      if (!mounted.current) return;
      if (result.response?.outcome !== 'COMPLETED') {
        setError(skillError(`${result.response?.error?.code} ${result.response?.error?.message}`));
        return;
      }
      const artifacts = validateArtifacts(result.response, readArtifacts?.(result.response));
      if (command) {
        const saved = artifacts.find((a) => a.model === 'ProfileMutationResult');
        if (
          saved?.model !== 'ProfileMutationResult' ||
          saved.value.profile.student_id !== profile.student_id
        )
          throw new Error('INVALID_SKILL_ARTIFACT');
        onUpdated(saved.value.profile);
        setForm(null);
        setRemove(null);
        setNotice('技能记录已保存。已有分析和计划不会自动更新。');
      } else {
        const data = artifacts.find((a) => a.model === 'SkillCatalogProjection');
        if (data?.model !== 'SkillCatalogProjection') throw new Error('INVALID_CATALOG_ARTIFACT');
        setCatalog(data.value.skills);
        setLoaded(true);
      }
    } catch (failure) {
      if (mounted.current) {
        const detail = errorDetails(failure);
        setError(skillError(`${detail.code} ${detail.message}`));
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) {
        setPending(false);
        onBusy(false);
      }
    }
  }
  useEffect(() => {
    void exchange();
  }, []);
  return (
    <section className="profile-section" id="profile-skills" aria-busy={pending}>
      <h2>我的技能</h2>
      <p>
        已记录 {skills.length} 项技能，其中{' '}
        {skills.filter((s) => (s.level ?? 'unknown') === 'unknown').length} 项尚未评定
      </p>
      <p>自评记录与用户备注不代表认证能力。技能差距须通过正式分析确认。</p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!loaded && (
        <button disabled={pending || disabled} onClick={() => void exchange()}>
          重新加载技能目录
        </button>
      )}
      {loaded && available.length === 0 && <p>当前暂无可添加的技能目录项</p>}
      <button
        disabled={disabled || pending || !available.length || !!form || !!remove}
        onClick={() =>
          setForm({
            operation: 'add',
            skill_id: '',
            level: 'unknown',
            note: '',
            expected_profile_ref: profile.profile_ref,
          })
        }
      >
        添加技能
      </button>
      {!skills.length && <p>尚未记录技能。你可以从技能目录添加自评技能。</p>}
      {skills.map((skill) => (
        <article key={skill.skill_id} className="skill-record">
          <h3>{name(skill.skill_id)}</h3>
          <p>等级：{levels[skill.level ?? 'unknown']}</p>
          <p>来源：{skill.self_assessed === false ? '非自评，来源尚未记录' : '自评'}</p>
          {skill.note && <p>备注：{skill.note}</p>}
          <button
            aria-label={`编辑 ${name(skill.skill_id)}`}
            disabled={disabled || pending || !!form || !!remove}
            onClick={() =>
              setForm({
                expected_profile_ref: profile.profile_ref,
                operation: 'update',
                skill_id: skill.skill_id,
                level: skill.level ?? 'unknown',
                note: skill.note ?? '',
              })
            }
          >
            编辑
          </button>
          <button
            aria-label={`删除 ${name(skill.skill_id)} 记录`}
            disabled={disabled || pending || !!form || !!remove}
            onClick={() =>
              setRemove({ skill_id: skill.skill_id, expected_profile_ref: profile.profile_ref })
            }
          >
            删除
          </button>
        </article>
      ))}
      {form && (
        <form
          aria-label={form.operation === 'add' ? '添加技能' : '编辑技能'}
          onSubmit={(e) => {
            e.preventDefault();
            void exchange({
              operation: form.operation,
              expected_profile_ref: form.expected_profile_ref,
              skill_id: form.skill_id,
              level: form.level,
              note: form.note.trim() || null,
            });
          }}
        >
          <fieldset disabled={disabled || pending}>
            <legend>{form.operation === 'add' ? '添加自评技能' : '编辑技能记录'}</legend>
            {form.operation === 'add' ? (
              <label>
                选择技能
                <select
                  required
                  value={form.skill_id}
                  onChange={(e) => setForm({ ...form, skill_id: e.target.value })}
                >
                  <option value="">请选择技能</option>
                  {available.map((s) => (
                    <option key={s.skill_id} value={s.skill_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p>技能：{name(form.skill_id)}（不可修改）</p>
            )}
            <label>
              技能等级
              <select
                value={form.level}
                onChange={(e) =>
                  setForm({ ...form, level: e.target.value as SkillCommand['level'] })
                }
              >
                {Object.entries(levels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              用户备注
              <textarea
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </label>
            <p>
              来源：
              {form.operation === 'add' ||
              skills.find((s) => s.skill_id === form.skill_id)?.self_assessed !== false
                ? '自评'
                : '非自评，来源尚未记录'}
            </p>
            <button type="submit">保存技能</button>
            <button
              type="button"
              onClick={() => {
                setForm(null);
                setError('');
              }}
            >
              取消技能编辑
            </button>
          </fieldset>
        </form>
      )}
      {remove && (
        <section role="dialog" aria-label="确认删除技能记录">
          <p>删除 {name(remove.skill_id)} 的技能记录后，它将变为“尚未记录”，而不是“等级未知”。</p>
          <button
            disabled={disabled || pending}
            onClick={() =>
              void exchange({
                operation: 'remove',
                skill_id: remove.skill_id,
                expected_profile_ref: remove.expected_profile_ref,
              })
            }
          >
            确认删除记录
          </button>
          <button
            disabled={pending}
            onClick={() => {
              setRemove(null);
              setError('');
            }}
          >
            取消删除
          </button>
        </section>
      )}
    </section>
  );
}
