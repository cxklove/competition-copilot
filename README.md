# Competition Copilot

**高校竞赛全生命周期决策与成长平台。**

Competition Copilot 围绕赛事发现、参赛资格、个性化推荐、技能差距与备赛计划，
连接赛事变化、影响分析和用户审批，支持学生持续作出有依据的参赛与成长决策。
Copilot 是贯穿产品的智能入口；Dashboard、赛事中心与赛事详情提供结构化的产品视图。

## 核心创新

1. **Constraint-aware Competition Decision**：硬资格与软匹配严格分离。
   硬约束由 deterministic Domain rules 判断，LLM 不决定 eligibility truth；
   推荐保留 confirmed / uncertain / blocked，不以技能匹配分数覆盖资格不确定性。
2. **Competition Digital Twin**：以 `Snapshot → Diff → CompetitionEvent`
   表达可追溯的赛事状态变化，保留来源、观察时间和核验状态。
3. **Event-driven Adaptive Planning**：以
   `CompetitionEvent → Impact → ReplanningDecision → Proposal → Human Approval → PlanDiff`
   完成受控调整。**Preparation != Authorization**；用户批准之后才允许执行授权修订。

## 架构与 authority

```text
Frontend
  ↓
Agent Runtime → LangGraph → CapabilityFacade
  ↓
Application / Tool
  ↓
Domain Service
  ↓
Repository Interface
  ↓
Infrastructure Adapter
```

LLM decides what to ask and what capability to invoke. Domain decides what is true.
所有调用仍受输入校验、能力白名单和审批约束。Frontend 展示已验证的结构化结果；
Application 编排用例；Domain 独立决定业务结果；Repository 只提供数据访问。
源码依赖指向抽象，Infrastructure 实现接口，Domain 不依赖 LLM。

## 当前阶段

团队参考 checkpoint：**PX2 Authoritative Competition Read Baseline**。

| 范围 | 状态 |
|---|---|
| Core Agent Lifecycle P0–P14 | Stable / Frozen；P12/P13/P14 为 CLOSED_FROZEN |
| PX1 — Product Shell / Dashboard / Current Context | CLOSED_VERIFIED |
| PX2 Core — Competition Center / Authoritative Detail | CLOSED_VERIFIED |
| PX2 Competition Experience（含 PX2.1–PX2.4） | CLOSED_VERIFIED |
| PX2.1 / PX2.2 / PX2.3 / PX2.4 | COMPLETE / CLOSED_VERIFIED / CLOSED_VERIFIED / CLOSED_VERIFIED |
| PX3 — My Profile / Skills | CLOSED_VERIFIED |
| PX3.1 / PX3.2 / PX3.3 / PX3.4 | COMPLETE / CLOSED_VERIFIED / CLOSED_VERIFIED / CLOSED_VERIFIED |
| PX4 — My Competitions + Planning Workspace | IN_PROGRESS |
| PX4.1 — Planning Readiness & Actionable Preparation | CLOSED_VERIFIED |
| PX4.2 — My Competitions Workspace | CLOSED_VERIFIED_LOCAL |
| PX4.3 | NOT_STARTED |
| P15 Evaluation | NOT_STARTED |

PX3.4 Browser Smoke 已 PASS、Final Independent Review 已 REVIEW_PASS，PX3 整体验收关闭。
已完成画像读写、ProfileReference / 乐观并发、受信自编辑、技能目录与增改删、
画像与技能证据原子更新，以及 Recommendation / SkillGap / Plan 的三态 freshness。
missing != UNKNOWN != SkillGap；仅显式操作重新分析/生成，不自动重算或触发 P11。
画像仍为 host-scoped in-memory，重启恢复 fixture；完整账号系统、技能要求等级覆盖、
计划可执行性、完整赛事历史和 submission window 等限制继续保留。
PX4.1 Browser Smoke PASS、Final Independent Review REVIEW_PASS，现为 CLOSED_VERIFIED。
已完成只读 Planning Workspace、exact PlanReference / lineage freshness、正式约束、待确认、
时间参考和 deterministic advisory，以及产品接线和 target clarification 前的画像 hydration。
PLANNING_ACTIONABILITY_GAP 已通过 read-side advisory 缓解，未解决全部数据覆盖或持久化 gap。
P8 truth 和 P11 authority 保持不变。PX4.2 已完成显式 exact-target 赛事关系、
结果选择与只读摘要、我的赛事产品页面及本地验收，状态为 CLOSED_VERIFIED_LOCAL。
本地 Frontend Full 383 passed / 0 failed / 0 skipped；PX4.2 backend targeted
61 passed、frontend targeted 82 passed；lint、build、diff check PASS。
该状态不代表 GitHub Actions 全绿：CI_PIPELINE_STABILITY_GAP 继续 OPEN。
PX4 保持 IN_PROGRESS；PX4.3、P15 均 NOT_STARTED。
详细阶段记录见 [Development Plan](docs/DEVELOPMENT_PLAN.md)。

## 当前能力

- Competition Discovery、Eligibility Decision、Multi-candidate Recommendation。
- `verified-skill-overlap-v1`：基于已核验技能要求的有限软信号，不表示完整适合度。
- Canonical Student Skill Evidence、Skill Gap Analysis、Structured Competition Planning。
- Generated Plan Registry、精确 PlanReference、CAS 更新、历史与 lineage。
- Competition Digital Twin、Impact Analysis、Replanning Decision、Human Approval。
- Actual PlanDiff / Versioned Plan Change，含 stale / replay / mismatch 保护。
- Product Dashboard、Competition Center、Authoritative Competition Detail Projection。
- Evidence / Provenance 展示；详情读取不调用 LLM 或重新执行 P5/P7。

## 快速启动（Windows PowerShell）

需要 Git、Python **3.12**（现有 Windows 锁文件的解析基线）及 Node **24.12+**。
以下命令从仓库根目录执行；运行两个服务时使用两个独立终端。

尚未获取仓库时：

```powershell
git clone https://github.com/cxklove/competition-copilot.git
Set-Location competition-copilot
```

### 1. 安装 Backend / Local Runtime

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\python -m pip install "setuptools>=68"
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-agent.lock
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[agent,dev]"
.\backend\.venv\Scripts\python -m pip check
$env:COMPETITION_COPILOT_LLM_MODE = 'offline'
.\backend\.venv\Scripts\python scripts/run_local_runtime.py
```

Local Runtime 默认监听 `http://127.0.0.1:8765/runtime/invoke`，只允许 loopback。
默认离线演示不需要 API Key；快捷操作使用显式 intent，仍经过相同 Agent/Facade/Domain 路径。

### 2. 启动 Frontend（另一个终端）

```powershell
Set-Location frontend
npm ci --ignore-scripts --registry=https://registry.npmjs.org
$env:VITE_RUNTIME_MODE = 'LOCAL'
$env:VITE_LOCAL_RUNTIME_BASE_URL = 'http://127.0.0.1:8765'
npm run dev
```

浏览器访问 **http://127.0.0.1:5173**。前端变量只包含公开连接配置，不能放入 API Key。

### 3. 可选 Cloud LLM Local Demo（BigModel）

在 Backend 终端停止离线服务后，从仓库根目录执行：

```powershell
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-cloud-llm.lock
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[agent,cloud-llm,dev]"
.\backend\.venv\Scripts\python -m pip check
$env:COMPETITION_COPILOT_LLM_MODE = 'cloud'
$env:COMPETITION_COPILOT_LLM_PROVIDER = 'bigmodel'
$env:COMPETITION_COPILOT_LLM_MODEL = Read-Host '请输入账号可用、支持 JSON mode / Tool Calling 的模型 ID'
$demoSecret = Read-Host 'BigModel API Key（仅当前 Backend shell）' -AsSecureString
try {
    $env:COMPETITION_COPILOT_LLM_API_KEY = [System.Net.NetworkCredential]::new('', $demoSecret).Password
    .\backend\.venv\Scripts\python scripts/run_local_runtime.py
} finally {
    Remove-Item Env:COMPETITION_COPILOT_LLM_API_KEY -ErrorAction SilentlyContinue
    $demoSecret.Dispose()
}
```

Key 只进入当前 shell 及其 Backend 子进程，服务结束后清除；不得提交到 Git、写入前端配置或打印。
BigModel intent 使用 `json_mode` / temperature `0.1`，无自动 retry。
切换 provider、覆盖参数及 OpenAI/DeepSeek 配置见 [Backend README](backend/README.md#independent-local-demo---optional-provider-neutral-cloud-llm)。

## 测试与验证

完整回归还需要现有 MCP、AgentArts 和 cloud-model 测试依赖；安装 SDK 不需要云凭据，
测试使用离线、deterministic 或 mocked 路径：

```powershell
# 从仓库根目录：requirements-agentarts.lock 已包含 core / Agent / MCP 锁文件
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-agentarts.lock -r backend/requirements-cloud-llm.lock
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[dev,agent,agentarts,mcp,cloud-llm]"
.\backend\.venv\Scripts\python -m pip check
$env:COMPETITION_COPILOT_LLM_MODE = 'offline'
.\backend\.venv\Scripts\python -m pytest backend/tests

# Ruff 在 backend 中使用项目配置
Push-Location backend
.\.venv\Scripts\python -m ruff check .
Pop-Location

# Frontend tests 包含真实本地 Runtime，需先安装上述 Backend 依赖
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location

.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
.\backend\.venv\Scripts\python scripts/export_frontend_results.py --check
git diff --check
```

[CI](.github/workflows/ci.yml) 在 push 到 `master` 和 Pull Request 时运行 Backend、Frontend 与
generated contract 检查。沿用 Python 锁文件及 `npm ci`，使用 Windows runner 匹配现有测试路径，
不提供云 API Key。GitHub 首次运行结果以 Actions 为准。

## Demo User Journey

```text
Student Profile → Discover → Eligibility → Recommendation → Skill Gap → Plan
→ Competition Change → Impact → Replanning → Approval → PlanDiff
```

可从明确标记的 `local-recommendation-demo` 模拟画像开始，使用 Copilot 的快捷操作。
选择刚生成的计划后再请求调整，审批由用户显式 REJECT / APPROVE。
Huawei 同计划演示中的赛道移除是 **manual controlled demo observation**，
仅验证事件驱动重规划，不代表 Huawei 官方真实删除了赛道。

## 已知边界

- 赛事详情的信息丰富度取决于 authoritative data coverage；未知届次、赛道、日期不作推断。
- 完整赛事 Event History 尚未持久化：`EVENT_HISTORY_PERSISTENCE_GAP`。
  Current Session Evidence 不等于完整历史。
- Local PlanRegistry 为 in-memory；server restart 后 generated plans 不持久化。
- 部分 requirement / eligibility 数据仍为 PARTIAL / UNKNOWN；缺少画像记录不等于能力不足。
- submission window 为 `DATA_CONTRACT_GAP`，当前未实现。
- Cloud BigModel Local Demo 不代表 production deployment；本地 hosting 不提供生产级多用户 IAM。

## 目录与文档导航

| 路径 | 职责 |
|---|---|
| `backend/` | Domain、Application、Tool、Repository/Infrastructure、Agent 与 Runtime adapters |
| `frontend/` | 产品 shell、Copilot、结构化结果与证据展示 |
| `data/` | 正式审核 seed、政策/要求、来源及显式 demo fixtures；raw/candidate 不作为正式 truth |
| `docs/` | 产品、架构、阶段计划与评审记录 |
| `scripts/` | 启动、schema 导出及可重复执行的开发脚本 |
| `.github/` | CI 与 Pull Request 模板 |

`evals/` 当前无受版本管理的内容，正式评测将在 P15 建立/使用；P15 尚未开始。

- [AGENTS.md — 开发规范与架构约束](AGENTS.md)
- [CONTRIBUTING.md — 团队协作与验证流程](CONTRIBUTING.md)
- [Product Spec](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development Plan](docs/DEVELOPMENT_PLAN.md)
- [Backend README](backend/README.md)
- [Frontend README](frontend/README.md)

## License

**LICENSE STRATEGY: UNDECIDED**。当前未授予项目许可证，后续由项目维护者明确决定。
