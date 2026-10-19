import { createRoot } from 'react-dom/client';
import { useMemo, useState } from 'react';
import { Workspace } from './workspace/Workspace.tsx';
import { createDemoClient } from './demo/client.ts';
import type { DemoScenario } from './demo/client.ts';
import './styles.css';

const scenarios: { value: DemoScenario; label: string }[] = [
  { value: 'completed', label: '完成回复' },
  { value: 'negative', label: '正常业务负向结果' },
  { value: 'clarification', label: '等待补充信息' },
  { value: 'approval', label: '等待用户确认' },
  { value: 'transport_error', label: '传输错误' },
  { value: 'runtime_error', label: 'Runtime 错误' },
  { value: 'contract_error', label: '契约错误' },
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
      <Workspace key={scenario} client={client} />
    </>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
createRoot(root).render(<DemoApp />);
