# Development Plan

## 执行约束与阶段关口

按 P0 → P16 顺序交付；本文件中的目录和文件均为未来阶段的预计位置，不代表 P0 要创建它们。每个阶段只修改该阶段所需文件。所有业务判断留在 Domain Service，Repository 只做数据访问，Tool 只通过 Application/Domain Service 与抽象 Repository/Gateway 使用能力。硬约束必须可复现，关键决策返回 `reason_code` 和 `evidence`；新功能同时提交自动化测试。AgentArts 仅在 P16 接入隔离的运行与适配层。

MVP 1 是 P7 后的**后端能力验收关口**；MVP 2 是 P11 后的**后端能力验收关口**。两者不新增功能阶段，也不预设 Agent 或 Web 已完成。产品界面的完整演示安排在 P14 之后。

## P0 — Project foundation and architecture

- **Goal:** 固定产品边界、架构依赖和逐阶段验收口径。
- **Inputs:** 项目目标、`AGENTS.md`、三个创新方向和 P0 限制。
- **Main Deliverables:** 产品规格、架构设计、开发计划及跨文档术语表述一致性。
- **Files/Modules Expected:** `docs/PRODUCT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT_PLAN.md`；必要时仅补充 README 文档索引。
- **Tests Required:** 人工核对必需章节、阶段顺序、依赖方向和字段约束；运行 `git diff --check`。P0 无业务代码和自动化业务测试。
- **Acceptance Criteria:** 三份文档覆盖用户旅程、可信数据、Snapshot/Diff/Event、可审计重规划及平台迁移边界，且与 `AGENTS.md` 无冲突。
- **Explicitly Out of Scope:** P1 及后续实现；业务接口、Domain 类、数据库、Agent、LLM、MCP、前端、爬虫和算法。

## P1 — Domain Model

- **Goal:** 建立独立于框架和 LLM 的领域概念与不变量。
- **Inputs:** P0 术语、赛事结构、学生画像和可信事实规则。
- **Main Deliverables:** Competition、Edition、Track、StudentProfile、Skill、LearningResource、CompetitionEvent、CompetitionPlan 的模型与标识；事实溯源及版本约束。
- **Files/Modules Expected:** `backend/domain/`、`backend/tests/domain/`、对应模型文档。
- **Tests Required:** 不变量、序列化边界、无效数据拒绝与版本字段测试。
- **Acceptance Criteria:** 模型可独立测试；Domain 不导入 LLM、Agent SDK、数据库或 Web 实现。
- **Explicitly Out of Scope:** 数据接入、持久化、资格与推荐公式。

## P2 — Competition Data Ingestion + Seed Dataset

- **Goal:** 独立建立可审核、可追溯的少量赛事样本。
- **Inputs:** P1 Schema、公开赛事来源、人工审核标准。
- **Main Deliverables:** `External Source → Importer → Raw Data → Normalizer → Validator → CompetitionCandidate → Human Approval → Official Competition Data` 流程及审核记录；关键事实含 `source_url`、`source_type`、`observed_at`、`verification_status`。
- **Files/Modules Expected:** `data/seed/`、`data/raw/` 样例、`scripts/` 导入与校验工具、`backend/adapters/ingestion/`（按实现需要）。
- **Tests Required:** 格式转换、缺失来源、重复候选、审核拒绝和未经验证数据隔离测试。
- **Acceptance Criteria:** 种子数据能从来源复核；未验证的 `CompetitionCandidate` 不能进入正式数据或确定性决策。此阶段可用审阅后的文件数据，不依赖 P3 数据库层。
- **Explicitly Out of Scope:** 全网爬虫、自动审核、生产数据库和推荐逻辑。

## P3 — Repository Layer

- **Goal:** 用抽象接口提供已审核数据的读写与查询。
- **Inputs:** P1 模型、P2 审核后的数据与状态约束。
- **Main Deliverables:** Repository Interface、替代实现及数据映射；明确候选区与正式库隔离。
- **Files/Modules Expected:** `backend/repositories/` 接口、`backend/adapters/persistence/` 实现、`backend/tests/repositories/`。
- **Tests Required:** 接口契约、查询/保存、错误处理、候选隔离与适配器替换测试。
- **Acceptance Criteria:** 上层只依赖接口；Repository 和 Adapter 均不计算资格、评分或其他业务规则。
- **Explicitly Out of Scope:** Domain 决策、Agent 调用和 Tool 编排。

## P4 — Tool Layer

- **Goal:** 为未来 Agent/MCP 建立稳定、可独立调用的业务能力入口。
- **Inputs:** P1 模型、P3 Repository Interface、Application 用例边界。
- **Main Deliverables:** Tool 请求/响应契约和已审核赛事检索入口；后续功能阶段扩展对应 Tool。
- **Files/Modules Expected:** `backend/tools/`、`backend/application/`、`backend/tests/tools/`。
- **Tests Required:** 参数、错误、抽象依赖、独立调用和无具体基础设施依赖测试。
- **Acceptance Criteria:** Tool 只通过 Application/Domain Service 与抽象 Repository/Gateway 使用能力；不依赖具体 Web、数据库、Agent SDK 或第三方基础设施。
- **Explicitly Out of Scope:** Agent Runtime、MCP 服务、资格或推荐公式。

## P5 — Deterministic Eligibility Engine

- **Goal:** 对核验过的赛事规则执行硬资格判断。
- **Inputs:** 学生画像、已验证赛事事实、规则版本。
- **Main Deliverables:** 可复现的资格规则、缺失信息处理、Eligibility DecisionResult 及资格 Tool。
- **Files/Modules Expected:** `backend/domain/eligibility/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/eligibility/`。
- **Tests Required:** 满足、不满足、边界值、缺失/冲突事实、规则版本与相同输入同结果测试。
- **Acceptance Criteria:** 每项资格结论都有稳定 `reason_code` 和来源可追溯的 `evidence`；LLM 不判定硬规则。
- **Explicitly Out of Scope:** 个性化排序、技能诊断和自然语言猜测资格。

## P6 — Competition Matching / Recommendation Engine

- **Goal:** 在资格过滤后给出可解释的个性化排序。
- **Inputs:** P5 资格结果、学生偏好、已验证赛事事实、评分规则版本。
- **Main Deliverables:** `Hard Constraints → Candidate Filtering → Matching Score → Ranking → DecisionResult`；评分拆解与推荐 Tool。
- **Files/Modules Expected:** `backend/domain/recommendation/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/recommendation/`。
- **Tests Required:** 资格排除、并列排序、权重边界、缺失偏好、稳定性及理由证据测试。
- **Acceptance Criteria:** 不合资格项不进入可报名推荐；相同版本化输入排序相同，返回 `reason_code` 和 `evidence`。
- **Explicitly Out of Scope:** Agent 自行评分、未经验证的赛事推荐和备赛计划。

## P7 — Student Profile + Skill Gap

- **Goal:** 描述学生能力与赛事要求的差距，并匹配可核验学习资源。
- **Inputs:** 学生画像、技能体系、赛事技能要求、学习资源来源。
- **Main Deliverables:** 画像更新、技能差距结果、资源建议及相应 Tool。
- **Files/Modules Expected:** `backend/domain/profile/`、`backend/domain/skills/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/skills/`。
- **Tests Required:** 画像缺项、技能映射、差距边界、资源来源和诊断理由测试。
- **Acceptance Criteria:** 差距与资源建议可追溯到画像、赛事要求与来源；关键诊断提供 `reason_code` 和 `evidence`。
- **Explicitly Out of Scope:** 自动规划、赛事监控和 Agent 对话。

## MVP 1 — 决策与诊断验收关口

用一组可复核的学生画像和已审核种子赛事，经 Application/Tool 完成检索、资格检查、排序、技能差距与学习资源建议；核验硬规则可复现、候选隔离和所有关键结果的理由与证据。记录端到端场景测试结果及未覆盖风险。此关口不新增代码范围，也不要求 Web 或 Agent。

## P8 — Structured Planner

- **Goal:** 把赛事目标与技能差距转为有依赖和期限的任务计划。
- **Inputs:** StudentProfile、已验证 Competition、SkillGap、Deadline、可用时间。
- **Main Deliverables:** 结构化 CompetitionPlan、里程碑/任务/依赖/截止时间、计划生成 Tool。
- **Files/Modules Expected:** `backend/domain/planning/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/planning/`。
- **Tests Required:** 时间冲突、依赖顺序、不可行期限、缺失数据及稳定计划测试。
- **Acceptance Criteria:** 计划可保存与复现，关键安排有 `reason_code` 和 `evidence`；官方截止日期优先于模型推断。
- **Explicitly Out of Scope:** 自动监控、事件处理和重规划。

## P9 — Competition Digital Twin

- **Goal:** 分离赛事静态知识与动态状态，并建立状态版本链。
- **Inputs:** 已审核赛事、现有状态、P1 事件模型及来源元数据。
- **Main Deliverables:** 不可变 Snapshot、可比较 Diff、状态版本和手动确认的 CompetitionEvent 记录路径。
- **Files/Modules Expected:** `backend/domain/digital_twin/`、Repository Interface/Adapter 扩展、`backend/tests/digital_twin/`。
- **Tests Required:** 版本递增、快照不可变、Diff 准确、来源关联和静默覆盖拒绝测试。
- **Acceptance Criteria:** 每次被接受的动态状态变化均保留 Snapshot、Diff 和对应 CompetitionEvent，可追溯与重放。
- **Explicitly Out of Scope:** 自动抓取、定时监控和自动重规划。

## P9.5 — Competition Monitor

- **Goal:** 定期观察可信来源并发现潜在状态变化。
- **Inputs:** 已有 Competition、监控来源、当前 Snapshot、抓取/轮询策略。
- **Main Deliverables:** Monitor、New Snapshot 候选、Diff 候选、去重与审核队列；路径为 `Existing Competition → Snapshot → Monitor → New Snapshot → Diff → CompetitionEvent`。
- **Files/Modules Expected:** `backend/application/monitoring/`、`backend/adapters/monitoring/`、`backend/tests/monitoring/`。
- **Tests Required:** 无变化、重复观察、来源失效、冲突来源和候选隔离测试。
- **Acceptance Criteria:** 监控结果不静默覆盖正式状态；只有验证并关联 CompetitionEvent 后才接受状态变更。
- **Explicitly Out of Scope:** 全网爬虫、未经核验自动入库、影响分析和重规划。

## P10 — Competition Event Engine

- **Goal:** 将已核验 Diff 分类为可供下游处理的赛事事件。
- **Inputs:** P9/P9.5 Snapshot、Diff、核验状态及赛事规则。
- **Main Deliverables:** Event 类型、触发条件、去重/幂等、事件证据与订阅接口。
- **Files/Modules Expected:** `backend/domain/events/`、`backend/application/events/`、`backend/tests/events/`。
- **Tests Required:** 截止日期/材料/规则变化、重复事件、无效变化、乱序观察和重放测试。
- **Acceptance Criteria:** 每个被接受的状态变化有对应 CompetitionEvent，事件引用来源、Diff、版本与稳定标识。
- **Explicitly Out of Scope:** 自动生成新计划、Agent 解释和通知渠道。

## P11 — Event-driven Replanning

- **Goal:** 根据赛事事件评估影响并生成可审计的个人计划差异。
- **Inputs:** CompetitionEvent、受影响的 CompetitionPlan、StudentProfile、最新核验事实。
- **Main Deliverables:** `CompetitionEvent → Impact Analysis → Affected Plan → Replanning → Plan Diff`；保存 `before`、`after`、`trigger_event`、`trigger_event_id`、`reason_code`、`evidence`。
- **Files/Modules Expected:** `backend/domain/replanning/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/replanning/`。
- **Tests Required:** 无影响、多计划影响、时间冲突、重复事件幂等、前后版本与证据链测试。
- **Acceptance Criteria:** 受影响计划可定位，Diff 可解释可追踪；重复事件不产生重复重规划，旧计划仍可查看。
- **Explicitly Out of Scope:** Agent 自行改写规则、自动报名及前端可视化。

## MVP 2 — 自适应计划验收关口

使用受控赛事变更，从 Snapshot 经 Diff、CompetitionEvent、影响分析到 Plan Diff 完成端到端演示；验证来源、审核、版本、事件幂等及 `before`/`after`/`trigger_event_id`/`reason_code`/`evidence` 全链路。记录场景测试结果及已知风险。此关口不新增代码范围，也不要求 Agent 或 Web。

## P12 — Agent Runtime and Multi-Agent Orchestration

- **Goal:** 让 Agent 在已验证工具能力之上组织完整任务流程。
- **Inputs:** P4–P11 稳定 Tool、工具契约、用户旅程。
- **Main Deliverables:** Supervisor、Intelligence Agent、Planning Agent、Coach Agent 和平台无关 Runtime/Orchestration 边界。
- **Files/Modules Expected:** `backend/agents/`、`backend/adapters/agent_runtime/`、`backend/tests/agents/`。
- **Tests Required:** 工具选择、失败恢复、越权调用、无来源事实拒答和对话流程评测。
- **Acceptance Criteria:** Agent 不直接读数据库/原始 JSON，不实现资格或评分公式；关键结论来自 Tool 并附理由证据。
- **Explicitly Out of Scope:** 为多 Agent 而增加角色、AgentArts 集成和 Web 页面。

## P13 — MCP Adapter

- **Goal:** 把稳定 Tool 契约暴露给 MCP 客户端。
- **Inputs:** 稳定 Tool 列表、权限边界、请求/响应 Schema。
- **Main Deliverables:** MCP Adapter、工具映射、错误与权限处理文档。
- **Files/Modules Expected:** `backend/adapters/mcp/`、`backend/tests/mcp/`。
- **Tests Required:** Schema、调用映射、错误、鉴权及不越过 Tool 边界测试。
- **Acceptance Criteria:** MCP 只暴露已有能力，不复制业务规则或直接访问具体数据库。
- **Explicitly Out of Scope:** 新决策算法、AgentArts 和前端页面。

## P14 — Agent-native Frontend

- **Goal:** 通过 Web 展示完整旅程和可解释的状态变化。
- **Inputs:** 稳定 API/Tool、P12 Agent 流程、产品页面职责。
- **Main Deliverables:** AI Workspace、Discover、My Journey、Competition Workspace、Profile 的页面流程；资格理由和 Plan Diff 展示。
- **Files/Modules Expected:** `frontend/`、必要的 `backend/api/` 协议层、前端测试。
- **Tests Required:** 核心用户旅程、状态/错误处理、证据展示、可访问性和响应契约测试。
- **Acceptance Criteria:** 学生可完成推荐到重规划闭环；API 不实现业务规则，页面不伪造赛事事实。
- **Explicitly Out of Scope:** 大型社交/组队、自动报名、缴费或作品提交。

## P15 — Evaluation

- **Goal:** 用可复现用例评估正确性、解释性与完整用户旅程。
- **Inputs:** P5–P14 功能、人工标注场景、边界规则与来源样本。
- **Main Deliverables:** 资格/推荐/计划/监控/重规划基准集、评分脚本与评测报告。
- **Files/Modules Expected:** `evals/`、`scripts/` 评测入口、相关文档。
- **Tests Required:** 固定回归集、证据完整性、事件重放、工具/Agent 误用及端到端场景测试。
- **Acceptance Criteria:** 评测可重复运行；失败案例与已知风险记录清楚，关键硬规则无模型裁决。
- **Explicitly Out of Scope:** 用评测数据替代正式来源、改变 Domain 规则以迎合单个样例。

## P16 — Huawei AgentArts Integration

- **Goal:** 在平台开放后接入 AgentArts，同时保持核心业务能力不变。
- **Inputs:** P12 平台无关 Runtime/Orchestration 契约、P13 工具协议、AgentArts 官方能力与限制。
- **Main Deliverables:** 隔离的 AgentArts Adapter、运行配置、迁移验证与回退方案。
- **Files/Modules Expected:** `backend/adapters/agentarts/`、`backend/tests/agentarts/`、部署与迁移文档。
- **Tests Required:** 原平台与 AgentArts 合约一致性、工具权限、失败恢复、回归评测及迁移边界测试。
- **Acceptance Criteria:** 仅运行、编排与 Adapter 层需要替换/接入；Domain、Decision、Planning 代码和结果契约保持不变。
- **Explicitly Out of Scope:** 为平台重写业务规则、Repository 决策逻辑或赛事数据来源。

## Unified Definition of Done

每一阶段在进入下一阶段前完成以下检查：

1. **Implementation complete:** 阶段交付物与验收标准已完成；P0 的“实现”仅指文档。
2. **Tests pass:** 新功能配套正常和关键边界路径的可复现自动化测试并通过；纯文档阶段完成规定的审阅与 `git diff --check`。
3. **Documentation updated:** 受影响的架构、Schema、运行或测试命令已同步更新。
4. **Stage review completed:** 按阶段 Acceptance Criteria 审阅，并记录结论与遗留项。
5. **No unrelated changes:** 仅修改当前阶段及任务相关文件，不顺带重构或格式化。
6. **Known risks documented:** 记录数据来源、规则覆盖、平台依赖等已知风险、影响及后续处理阶段。
