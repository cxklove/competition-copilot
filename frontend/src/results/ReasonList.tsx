const labels: Record<string, string> = {
  RULE_SATISFIED: '满足已声明规则',
  RULE_VIOLATED: '不满足已声明规则',
  PROFILE_DATA_MISSING: '学生画像信息不足',
  RULE_DATA_MISSING: '规则信息不足',
  no_plan_impact: '未发现方案影响',
  structural_revision_supported: '支持结构调整',
  requirement_data_missing: '技能要求信息不足',
};
export function ReasonList({ codes }: { codes: string[] }) {
  return codes.length ? (
    <ul className="reason-list" aria-label="理由代码">
      {codes.map((code, index) => (
        <li key={`${index}-${code}`}>
          <span>{Object.hasOwn(labels, code) ? labels[code] : '返回的理由代码'}</span>{' '}
          <code>{code}</code>
        </li>
      ))}
    </ul>
  ) : (
    <p className="unavailable">未提供理由代码。</p>
  );
}
