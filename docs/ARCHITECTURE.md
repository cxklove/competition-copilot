# Competition Copilot Architecture

> P0 架构设计；本文定义边界和数据契约，不代表相关模块已经实现。

## 1. Architecture Goals

系统须模块化、可测试、可解释，且独立于具体 Agent 平台。赛事事实可追溯到来源与核验状态；资格、推荐和重规划可回放其输入、规则版本与证据。未来接入 Huawei AgentArts 时只调整运行、编排和适配边界，不改写 Domain、Decision、Planning 的业务能力。

## 2. Overall Layered Architecture

运行时能力调用的完整参考路径为：

```text
Frontend
  ↓
API
  ↓
Application / Workflow
  ↓
Tool
  ↓
Domain Service
  ↓
Repository Interface
  ↓
Infrastructure Adapter
```

此图展示允许的由外到内路径，不要求每次请求经过全部节点。普通 API 请求由 Application 编排 Domain Service；Agent Runtime 和 MCP 从上层调用 Tool，不能直接操作数据库。需要由 Workflow 发起 Tool 调用时，Workflow 依赖抽象 Tool Port；Tool 可调用独立的 Application 用例或 Domain Service，但不得回调同一个发起用例。运行时最后一步由接口委托 Adapter；源码依赖相反，由 Adapter 实现接口，内层代码不导入具体 Adapter。

## 3. Domain Layer

`Competition` 表示跨届赛事身份；`CompetitionEdition` 表示某一届的规则与时间范围；`CompetitionTrack` 表示该届赛道及其条件。`StudentProfile` 记录学生授权提供的背景、目标和时间约束；`Skill` 是版本化能力词表；`LearningResource` 是可溯源的学习材料。`CompetitionEvent` 表示已核验的赛事状态变化；`CompetitionPlan` 表示有任务、依赖、期限和版本的个人备赛计划。辅助概念包括 `SkillGap`、`DecisionResult`、`Snapshot` 和 `Diff`。Domain Service 承担资格、匹配、诊断、规划约束与影响规则，不依赖 LLM、Agent SDK 或数据库实现。

## 4. Data Architecture

**Static Competition Knowledge** 保存赛事、届次、赛道、资格规则、技能要求和官方材料等相对稳定的知识。**Dynamic Competition State** 保存报名状态、截止日期、材料清单、规则修订等随时间变化的届次状态。静态知识与动态状态分开建模，避免一条赛事记录同时承担身份、规则和实时状态。

Competition Digital Twin 用版本化 `Snapshot` 表达某届赛事在某次观测后的状态，比较相邻快照生成 `Diff`，再形成 `CompetitionEvent`。动态状态不得静默覆盖。每条用于判断的关键事实都保存 `source_url`、`source_type`、`observed_at`、`verification_status`；未经验证的事实只能作为待核验线索。

## 5. Data Ingestion Architecture

```text
External Source → Raw → Normalize → Validate → Candidate
→ Human Approval → Source Verification → Verified Seed
```

P2 已完成上述可审计的文件数据链：Raw 保留原始证据，Normalizer 只做确定性结构化，Validator 不代替人工判断。Human Review Manifest 以 Raw SHA256 绑定明确的批准和来源核验决定；执行器默认 dry-run，只有显式执行才生成 Verified Seed。未批准或未核验的 Candidate 不得成为正式业务数据，也不得支持确定性资格、推荐或计划决策。当前共有 12 份 Verified Seed，兼容 1.0 与 1.1；P2 ingestion scope is frozen。

P3 Repository 以 Verified Seed 为正式数据输入，通过 `Competition`、`CompetitionEdition`、`CompetitionTrack`、`SourceMetadata` 和 `TimeWindow` 读取核心事实；不直接以 `data/raw` 为业务数据源，也不要求常规读取方解析 Manifest 或 `raw_payload`。Manifest 保留在 ingestion audit layer。阶段日程、资格、团队规则、名额、评审、奖项和动态状态的结构化属于后续阶段。

## 6. Competition Monitoring Architecture

```text
Existing Competition → Snapshot → Monitor → New Snapshot → Diff → CompetitionEvent
```

Monitor 对已收录赛事取得新观察并核验关键事实；未核验变化留在候选/待审状态。接受新状态时追加新 `Snapshot`，以规则化比较生成 `Diff`，再生成带稳定 ID、前后快照引用、变化字段与来源证据的 `CompetitionEvent`。重复观察须避免重复事件；旧快照和事件均保留以供追溯与重放。

## 7. Decision Architecture

```text
Hard Constraints → Candidate Filtering → Matching Score → Ranking → DecisionResult
```

Domain Service 使用版本化输入和规则确定性检查硬资格；事实缺失或未核验时返回待核验状态，不能推断为合格。只有通过硬约束的已核验赛事进入匹配评分与排序。评分公式和版本属于 Domain，不属于 Agent 或 Repository。`DecisionResult` 返回状态、排序依据、稳定的 `reason_code` 与逐项 `evidence`，引用事实来源及规则版本。用户旅程中 Agent 在资格检查前给出的赛事仅为发现候选清单，不是最终合格结论或正式排名。

## 8. Planning Architecture

```text
StudentProfile + Competition + SkillGap + Deadline
→ Structured CompetitionPlan
```

Application 汇集已核验的赛事期限与规则，Domain Service 生成或验证结构化任务、先后依赖、计划时间、完成状态和依据。计划关联画像、赛事届次、来源快照及版本；遇到期限缺失或冲突时标记待确认，不能编造确定日期。Agent 可以解释或建议任务，但不能绕过领域约束。

## 9. Replanning Architecture

```text
CompetitionEvent → Impact Analysis → Affected Plan → Replanning → Plan Diff
```

影响分析以事件关联赛事、学生 Journey 和计划版本；仅受影响的计划进入重规划。每次自动重规划追加新计划版本，`Plan Diff` 至少保存 `before`、`after`、`trigger_event_id`（关联 `trigger_event`）、`reason_code` 和 `evidence`。证据指向事件、快照、事实来源和所用规则版本；旧计划不被覆盖，界面可展示具体任务和期限变化。

## 10. Agent Architecture

```text
Supervisor
├── Intelligence Agent
├── Planning Agent
└── Coach Agent
```

Supervisor 负责路由和上下文；Intelligence Agent 解释发现、资格、推荐和技能结果；Planning Agent 协调计划与重规划工具；Coach Agent 解释学习资源和进度。Agent 只通过 Tool 获取经核验事实与业务结果，不读取原始 JSON/数据库做事实判断，也不实现资格规则或推荐评分。按清晰职责设置这三个 Agent，避免为了 Multi-Agent 数量而继续拆分。

## 11. Tool Architecture

Tool 是 Agent 与业务能力之间的标准接口之一，提供稳定的输入、输出、错误和来源契约。Tool 通过 Application/Domain Service 执行业务能力，可通过抽象 Repository/Gateway 访问数据或外部能力；业务判断必须留在 Domain Service。Tool 不直接依赖具体 Web、数据库、Agent SDK 或第三方基础设施。每个 Tool 应能用替身依赖独立运行及测试；关键决策输出透传 `reason_code` 和 `evidence`。

P4.1 在 `backend/competition_copilot/tools/` 定义最小 `Tool` Protocol、模型 Schema 元数据和结构化 `ToolResult`；错误码区分无效输入、未找到实体与内部错误。P4.2 提供六个只读 Competition / Edition / Track Tool，均通过构造函数接收 `CompetitionRepository`，不依赖 JSON Adapter 或 Seed 文件。输出用薄包装承载正式 Pydantic Domain 模型，保留可序列化的稳定边界而不复制 Domain 字段。

P4 Tool Layer 已完成：P4.3 验证 JSON 序列化、Schema、时间窗口、来源元数据、空列表、顺序及 Artifact 隔离；P4.4 验证真实 `Verified Seed → JsonSeedCompetitionRepository → CompetitionRepository → Competition Read Tools → ToolResult → JSON` 链路，Final Review PASS。正式依赖边界为未来 Application / Agent / MCP → Tool → `CompetitionRepository` → Domain；Tool 不导入具体 Adapter、`CompetitionSeedEnvelope`、`RawCompetitionData` 或 `HumanReviewManifest`。**P4 Competition Read Tool scope is frozen**；只有真正的 Tool boundary defect 才重新打开。P5 的确定性资格判断应成为独立业务能力，不进入现有六个读取 Tool。

## 12. MCP Architecture

稳定 Tool 的契约可由 MCP Adapter 暴露给授权客户端；MCP 只处理协议、参数映射、访问控制和响应序列化，不复制业务规则，也不直接访问数据库。MCP 与 Agent 都是业务入口，最终复用相同的 Tool 和 Domain Service 结果。

## 13. AgentArts Migration Boundary

当前 Runtime、Tool 契约和编排均保持平台无关。AgentArts 开放后，接入或替换的范围仅是 Agent Runtime、orchestration 和隔离的 AgentArts Adapter；AgentArts SDK 不得进入 Domain、Application、Repository Interface 或通用 Tool。Domain、Decision、Planning 及其测试保持有效。

## 14. Repository Structure

顶层目录约定：`backend/` 承载服务端，`frontend/` 承载界面，`data/` 承载可共享样例，`docs/` 承载设计，`evals/` 承载评测，`scripts/` 承载可复用操作。已完成的 Domain 与 P2 ingestion 实现位于 `backend/competition_copilot/`，真实 Raw、Review Manifest 和 Verified Seed 位于 `data/`。P3 只读接口位于 `backend/competition_copilot/repositories/`，当前 JSON Verified Seed Adapter 位于 `backend/competition_copilot/infrastructure/repositories/`。后续 `backend/` 可按 `application/`（用例及流程）、`tools/`（工具契约）、`agents/`（平台无关运行与编排）、`adapters/`（其他持久化、外部能力、MCP、AgentArts 实现）、`api/`（协议入口）扩展。

P3 Repository Layer 已完成并冻结。`CompetitionRepository` 只读地返回 `Competition`、`CompetitionEdition` 和 `CompetitionTrack`：未知实体或父实体抛出 `RepositoryEntityNotFoundError`，已存在父实体的空子集合返回 `[]`；Competition 按 ID、Edition 按 `(year, id)` 升序，Track 保留 Verified Seed 顺序。当前 `JsonSeedCompetitionRepository` 是可替换的 Infrastructure Adapter，不是唯一存储方案。P4 通过抽象 Repository 读取赛事，测试可注入 fake / in-memory 实现；P4 不直接依赖 JSON Adapter、Seed Envelope、Raw 或 Manifest。

## 15. Dependency Rules

- 遵守 `AGENTS.md` 的 `API / Agent / MCP → Application / Tool → Domain Service → Repository Interface → Infrastructure Adapter` 运行时方向；Frontend 只通过 API 接入。
- 源码依赖指向内层抽象：Infrastructure Adapter 实现 Repository/Gateway，Tool 实现 Workflow 所需的抽象 Tool Port；Application、Domain 与 Tool 不导入具体基础设施。禁止 Application 与 Tool 相互静态导入或递归调用。
- Repository Interface 及其 Adapter 只负责数据访问；Gateway 及其 Adapter 只封装外部能力。API、Agent、MCP、Tool 均不得复制业务规则。硬规则确定性执行，所有关键决策返回 `reason_code` 和 `evidence`。
- 未核验候选不入正式库或确定性决策；动态状态保留 `Snapshot`、`Diff`、`CompetitionEvent`；自动重规划保留前后版本、触发事件和证据。

## Open Architecture Risks

- 来源发布的截止日期与实际生效日期可能不同；数据模型需要分别记录观测时间与规则生效时间，具体冲突处理留待相应阶段确定。
- 赛事页面变化不一定代表规则变化；监控必须经核验和差异归一化，避免误触发重规划。
- AgentArts 尚未开放，Adapter 契约须在接入阶段以实际平台能力验证，同时保持核心逻辑隔离。
