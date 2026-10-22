import { createRoot } from 'react-dom/client';
import { useMemo, useState } from 'react';
import { ProductApp } from './workspace/ProductApp.tsx';
import { createDemoClient, readDemoArtifacts } from './demo/client.ts';
import type { DemoScenario } from './demo/client.ts';
import './styles.css';
import { createLocalClient } from './localClient.ts';
import { createAgentArtsClient } from './agentartsClient.ts';
import localPlan from './demo/local-plan.json' with { type: 'json' };
import type { PlanReference } from './runtime/generated/contracts.ts';

function RuntimeApp() {
  const agentarts = import.meta.env.VITE_RUNTIME_MODE === 'AGENTARTS';
  const composition = useMemo(
    () =>
      agentarts
        ? createAgentArtsClient(
            import.meta.env.VITE_AGENTARTS_BRIDGE_BASE_URL || window.location.origin,
            import.meta.env.VITE_AGENTARTS_RUNTIME_NAME,
          )
        : createLocalClient(import.meta.env.VITE_LOCAL_RUNTIME_BASE_URL || window.location.origin),
    [],
  );
  return (
    <ProductApp
      {...composition}
      localPlan={localPlan as PlanReference}
      runtimeLabel={agentarts ? 'AGENTARTS · Runtime transport' : 'LOCAL · 本地 Runtime'}
      invocationNote={
        agentarts
          ? '通过受信服务端边界调用 Runtime；业务结论以返回的验证结果为准。'
          : '使用真实本地业务服务；意图模式以服务端配置为准。示例画像/受控事件不代表真实个人或赛事历史。'
      }
    />
  );
}

const scenarios: { value: DemoScenario; label: string }[] = [
  { value: 'completed', label: '完成回复' },
  { value: 'negative', label: '正常业务负向结果' },
  { value: 'eligible', label: '资格结果与核验来源' },
  { value: 'ineligible', label: '资格不符与依据' },
  { value: 'unknown', label: '资格信息不足' },
  { value: 'undetermined', label: '技能差距无法确定' },
  { value: 'no_gap', label: '无已声明技能差距' },
  { value: 'recommendation', label: '后端提供的推荐评分' },
  { value: 'verified_source', label: '完整来源元数据' },
  { value: 'pending_source', label: '待核验来源' },
  { value: 'partial_evidence', label: '来源缺失的证据' },
  { value: 'plan_diff', label: '方案前后集合变化' },
  { value: 'no_change', label: '预设拒绝/方案未变化' },
  { value: 'clarification', label: '等待补充信息' },
  { value: 'approval', label: '等待用户确认' },
  { value: 'transport_error', label: '传输错误' },
  { value: 'runtime_error', label: 'Runtime 错误' },
  { value: 'contract_error', label: '契约错误' },
  { value: 'approval_transport_error', label: '批准续接传输失败' },
  { value: 'approval_contract_error', label: '批准续接契约错误' },
];

function DemoApp() {
  const [scenario, setScenario] = useState<DemoScenario>('completed');
  const client = useMemo(() => createDemoClient(scenario), [scenario]);
  return (
    <>
      {import.meta.env.DEV && (
        <details className="dev-scenarios">
          <summary>开发演示场景</summary>
          <label htmlFor="demo-scenario">预设回复</label>
          <select
            id="demo-scenario"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as DemoScenario)}
          >
            {scenarios.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>
          <small>切换场景会清空当前演示会话。</small>
        </details>
      )}
      <ProductApp key={scenario} client={client} readArtifacts={readDemoArtifacts} />
    </>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
if (
  import.meta.env.VITE_RUNTIME_MODE &&
  !['LOCAL', 'AGENTARTS'].includes(import.meta.env.VITE_RUNTIME_MODE)
)
  throw new Error('Unsupported Runtime mode');
createRoot(root).render(import.meta.env.VITE_RUNTIME_MODE ? <RuntimeApp /> : <DemoApp />);
