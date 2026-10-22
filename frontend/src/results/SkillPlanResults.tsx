import type { ReactNode } from 'react';
import type {
  CompetitionPlan,
  Evidence,
  PlanMilestone,
  SkillGapDecision,
  SkillGapItem,
} from './generated/artifacts.ts';
import { SourceGroups } from './SourceGroups.tsx';

type SkillLabels = { skillLabel: (id: string) => string; levelLabel: (id: string) => string };
function selfAssessed(item: SkillGapItem) {
  return item.student_evidence?.some(
    (e) =>
      (e.field === `skills.${item.requirement.skill_id}.self_assessed` && e.value === true) ||
      (e.field === `skills.${item.requirement.skill_id}.level` &&
        e.message.includes(`skill_id=${item.requirement.skill_id}; self_assessed=true;`)),
  );
}
function ability(item: SkillGapItem, levelLabel: SkillLabels['levelLabel']) {
  return item.student_level == null
    ? '暂无画像记录'
    : item.student_level === 'unknown'
      ? '能力等级尚未明确'
      : `${levelLabel(item.student_level)}${selfAssessed(item) ? '（自评）' : '（画像记录）'}`;
}
function Audit({ value, audit }: { value: unknown; audit?: ReactNode }) {
  return (
    <details className="semantic-audit">
      <summary>查看高级审计信息</summary>
      {audit ?? <pre>{JSON.stringify(value, null, 2)}</pre>}
    </details>
  );
}
export function SkillGapPresentation({
  result,
  audit,
  skillLabel,
  levelLabel,
}: SkillLabels & { result: SkillGapDecision; audit?: ReactNode }) {
  const requirementEvidence: Evidence[] = [
    ...(result.requirements.requirements ?? []).flatMap((item) => [
      ...item.presence_evidence,
      ...(item.evidence ?? []),
    ]),
    ...(result.items ?? []).flatMap((item) => [
      ...item.requirement.presence_evidence,
      ...(item.requirement.evidence ?? []),
    ]),
  ];
  const conclusion = {
    undetermined: '暂无法完整判断',
    gap_identified: '存在已确认技能差距',
    no_gap: '未发现已声明技能差距',
  }[result.gap_status];
  const unspecified = result.items?.some(
    (item) =>
      item.requirement.required_level == null || item.requirement.required_level === 'unknown',
  );
  return (
    <section aria-label="技能差距分析" className="skill-gap-results">
      <h3>技能差距分析</h3>
      <p>当前结论：{conclusion}</p>
      {result.requirements.coverage !== 'complete' && (
        <p>
          {result.requirements.coverage === 'partial'
            ? '赛事技能要求覆盖仍不完整，当前仅部分要求已核验。'
            : '当前缺少可核验的赛事技能要求信息。'}
        </p>
      )}
      {unspecified && <p>部分所需能力等级尚未明确，不能据此判断已达到赛事要求。</p>}
      <div className="result-table-scroll">
        <table>
          <caption>技能与赛事要求对照</caption>
          <thead>
            <tr>
              <th scope="col">技能</th>
              <th scope="col">我的能力</th>
              <th scope="col">赛事要求</th>
              <th scope="col">当前判断</th>
            </tr>
          </thead>
          <tbody>
            {result.items?.map((item) => (
              <tr key={item.requirement.skill_id}>
                <th scope="row">{skillLabel(item.requirement.skill_id)}</th>
                <td>{ability(item, levelLabel)}</td>
                <td>
                  {item.requirement.required_level == null ||
                  item.requirement.required_level === 'unknown'
                    ? `已确认${item.requirement.requirement_type === 'required' ? '需要' : '期望'}该技能，但所需等级尚未明确`
                    : levelLabel(item.requirement.required_level)}
                </td>
                <td>
                  {item.status === 'gap'
                    ? '已确认存在技能差距'
                    : item.status === 'satisfied'
                      ? '满足当前已声明技能要求'
                      : item.student_level == null || item.student_level === 'unknown'
                        ? '需要补充个人能力信息'
                        : '暂无法确认是否存在能力差距'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!result.items?.length && <p>暂无可核验的技能要求明细。</p>}
      <details className="skill-gap-evidence">
        <summary>查看决策依据</summary>
        <details>
          <summary>查看能力依据</summary>
          <ul>
            {result.items?.map((item) => (
              <li key={item.requirement.skill_id}>
                {skillLabel(item.requirement.skill_id)}：{ability(item, levelLabel)}
              </li>
            ))}
          </ul>
          <p>自评仅为学生画像事实，不代表外部认证。</p>
        </details>
        <details>
          <summary>查看赛事要求来源</summary>
          <SourceGroups
            sources={requirementEvidence.flatMap((e) => (e.source ? [e.source] : []))}
          />
        </details>
      </details>
      <Audit value={result} audit={audit} />
    </section>
  );
}

type PlanLabels = {
  skillLabel: (id: string) => string;
  competitionLabel: (id: string) => string;
  statusLabel: (status?: string) => string | undefined;
};
function stage(
  plan: CompetitionPlan,
  milestone: PlanMilestone,
  skillLabel: PlanLabels['skillLabel'],
) {
  const need = plan.planning_needs?.find((n) => n.id === milestone.source_need_id);
  if (need?.kind === 'uncertainty_resolution') {
    return need.source_item
      ? {
          title: `确认“${skillLabel(need.source_item.requirement.skill_id)}”的具体能力要求`,
          reason: '当前技能要求或个人能力信息尚未明确，需要先补充或确认。',
        }
      : { title: '确认赛事要求', reason: '当前赛事要求信息尚不完整，需要先补充或确认关键规则。' };
  }
  if (need?.kind === 'skill_improvement' && need.source_item)
    return {
      title: `提升“${skillLabel(need.source_item.requirement.skill_id)}”备赛能力`,
      reason: '该阶段来自后端已生成的技能提升需求。',
    };
  return { title: milestone.title, reason: '沿用后端提供的计划阶段。' };
}
export function PlanPresentation({
  plan,
  audit,
  ...labels
}: PlanLabels & { plan: CompetitionPlan; audit?: ReactNode }) {
  const items = plan.milestones ?? [];
  const itemEvidence = (plan.planning_needs ?? []).flatMap((need) =>
    need.source_item
      ? [
          ...need.source_item.requirement.presence_evidence,
          ...(need.source_item.requirement.evidence ?? []),
          ...(need.source_item.student_evidence ?? []),
        ]
      : [],
  );
  const pendingInformation = items.some((m) =>
    plan.planning_needs?.some(
      (n) => n.id === m.source_need_id && n.kind === 'uncertainty_resolution',
    ),
  );
  return (
    <section aria-label="备赛计划时间线" className="plan-results">
      <h3>备赛计划</h3>
      <p>计划状态：{labels.statusLabel(plan.status)}</p>
      <p>计划版本：v{plan.version ?? 1}</p>
      <p>{labels.competitionLabel(plan.competition_id)}</p>
      <p>计划阶段：{items.length} 个</p>
      {items[0] && <p>当前重点：{stage(plan, items[0], labels.skillLabel).title}</p>}
      <ol className="plan-timeline" aria-label="计划里程碑">
        {items.map((milestone, index) => {
          const display = stage(plan, milestone, labels.skillLabel);
          const status = {
            pending: '待处理',
            in_progress: '进行中',
            completed: '已完成',
            blocked: '受阻',
            skipped: '已跳过',
          }[milestone.status ?? 'pending'];
          return (
            <li key={milestone.id}>
              <h4>
                阶段 {index + 1} · {display.title}
              </h4>
              <p>当前状态：{status}</p>
              <p>原因：{display.reason}</p>
              <p>
                截止时间：
                {milestone.due_at ? (
                  <time dateTime={milestone.due_at}>{milestone.due_at}</time>
                ) : (
                  '暂未设置'
                )}
              </p>
              {!milestone.due_at && <p>当前没有足够可信的时间信息，系统不会自动推断截止日期。</p>}
            </li>
          );
        })}
      </ol>
      {!items.length && <p>当前没有已生成的阶段任务。</p>}
      {pendingInformation && (
        <p className="plan-followup" role="note">
          后续计划说明：将在关键赛事信息明确后继续细化。此处仅为说明，未新增正式计划阶段。
        </p>
      )}
      <details className="plan-evidence">
        <summary>查看决策依据</summary>
        <p>计划阶段来自后端返回的备赛需求；保留原有顺序、日期与不确定性。</p>
        <SourceGroups sources={itemEvidence.flatMap((e) => (e.source ? [e.source] : []))} />
      </details>
      <Audit value={plan} audit={audit} />
    </section>
  );
}
