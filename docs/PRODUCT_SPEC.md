# Competition Copilot — Product Spec

> 状态：保留 P0 产品愿景，现同步 Post-P14 PX0 / Design = DOCUMENTED。
> 已验证 Local Demo 基线与未来产品方向分别说明；阶段状态以 DEVELOPMENT_PLAN 为准。
> P12–P14 CLOSED_FROZEN；P15 NOT_STARTED；PX1 / PX2 Core CLOSED_VERIFIED。

## Product Vision

Competition Copilot 是面向高校学生的竞赛全生命周期决策与成长平台：从发现赛事、核验资格、比较选择，到诊断技能、制定计划，并在赛事变化后持续调整。普通竞赛信息网站侧重静态展示；本产品将有来源的赛事事实、确定性业务规则、个人计划与动态事件连接成可追踪的决策闭环。Agent 负责理解意图、调用能力和解释结果，不凭对话生成赛事事实或资格结论。产品的 Schema、数据接入、业务逻辑、Agent 架构和界面均独立设计，不依赖或复制其他平台的源码、前端代码或私有整理数据。

## Target Users

| 第一版用户 | 主要需求 |
| --- | --- |
| 高校本科生 | 根据年级、专业、技能和可用时间找到适合的赛事，明确资格与备赛起点。 |
| 高校研究生 | 核对学历、研究方向、队伍等限制，比较多场赛事的投入与时间冲突。 |

第一版以学生本人管理个人 Journey 为主；指导教师、主办方和学校管理者不是独立角色。

## Core User Problems

- **找比赛：** 信息分散，届次、赛道、截止日期和来源难以核对。
- **判断适合与选择：** 多场赛事目标、技能匹配和时间成本不同，缺少可解释的比较。
- **判断资格：** 学历、年级、队伍等硬条件容易被误读；资料不足时需要明确提示待补充。
- **技能缺口：** 不清楚当前能力与目标赛道要求之间的差距及学习顺序。
- **时间规划：** 难将报名、材料、学习、作品和提交节点拆成可执行任务。
- **变化后调整：** 规则、材料或截止日期变化后，既有计划不会自动识别影响并给出修订依据。

## Core User Journey

以下为目标旅程；页面化、关注状态与长期保存仍按 PX 路线推进，不能据此视为已实现。

1. 学生建立画像，填写学历阶段、学校、专业、技能、目标和可用时间；缺失字段保持“未知”。
2. Agent 通过 Tool 从**已核验的正式赛事数据**中给出初步发现列表；此时不宣称最终资格或正式排名。
3. 确定性资格服务逐一检查赛事届次和赛道的硬条件，返回通过、不通过或信息不足，以及 `reason_code` 和 `evidence`。
4. 学生比较后端返回的资格已确认、资格尚待确认、资格受限候选及其排序依据。资格 UNKNOWN 不因 soft score 晋升为 ELIGIBLE；缺少评分信号不解释为不适合。
5. 系统对照赛道要求分析技能差距，并给出与缺口对应、可追溯的学习资源。
6. 系统通过真实技能诊断 prerequisite 生成 PlanningNeed / Milestone 结构化计划；日期不足时不猜 deadline。Task / Action Item 与执行型任务体验属于未来独立设计。
7. 学生将赛事及计划加入个人 Journey；系统保存计划版本。
8. 系统监控该赛事的已核验动态状态，保存新旧 `Snapshot`，计算 `Diff`，识别 `CompetitionEvent`。
9. 正式服务产生 Impact / ReplanningDecision，适用的 Application policy 准备无执行 authority 的 proposed operation。用户查看依据并明确拒绝或批准；Preparation != Authorization。
10. 只有通过审批与精确当前计划校验的执行才返回 actual `PlanDiff`，展示 `before`、`after`、`trigger_event_id`、`reason_code` 和 `evidence`，并保存版本 lineage；拒绝不产生修改。

## Core Product Capabilities

| 能力 | 输入与行为 | 用户可见结果 |
| --- | --- | --- |
| **Discover** | 检索已核验赛事，区分赛事、届次和赛道；提供官方来源、关键日期和限制条件。 | 可筛选的赛事发现结果及来源，不混入待审核候选数据。 |
| **Decide** | P5 提供资格结果，P6 按既有语义分桶、评分/排序；未知条件不推断为通过，缺信号不编分。 | 资格状态、正式推荐顺序、稳定 `reason_code` 与依据。 |
| **Diagnose** | 对照赛道技能要求和学生画像，识别已具备、待提升与未知技能，并关联学习资源。 | 可追踪的技能差距、优先级与资源建议。 |
| **Plan** | 通过技能诊断准备 PlanningNeed / Milestone，保留要求与时间不确定性。 | `CompetitionPlan`、精确引用与版本；通用编辑、Task / Action Item 不作为当前已实现能力。 |
| **Monitor** | 对已知赛事持续获取状态，保留 `Snapshot`、可比较 `Diff` 和事件；变化须核验。 | 变化内容、发现时间、来源与验证状态。 |
| **Replan** | 对已核验事件分析影响，针对受影响计划生成新版本；保留审计记录。 | 清晰的 `Plan Diff`、触发事件和调整原因。 |

## MVP Scope

- **MVP 1（P7 能力关口）：** 学生画像、经过人工核验的有限赛事样本、检索、确定性资格检查、匹配推荐、技能差距和学习资源建议；这是后端决策闭环，不预设 Agent 或前端已完成。
- **MVP 2（P11 能力关口）：** 在 MVP 1 上加入结构化计划、个人 Journey 所需的计划状态、Competition Digital Twin、监控、事件识别、影响分析和可审计重规划；可用受控、可重复的来源变化样例验证。
- **当前交付与后续范围：** Post-P14 Local Demo / Same-plan E2E 已验证核心闭环；现有 LangGraph orchestrator、确定性能力、MCP 与 AgentArts-compatible adapter 继续复用，不人为拆分业务 Agent。PX 负责后续产品体验；P15 仅负责独立评测，仍未开始；P16 负责生产部署与 hardening。页面设计不代表生产系统已交付。

赛事样本须覆盖本科生与研究生、至少一种明确不符合资格的情况、至少一种资料不足的情况，以及至少一次经核验的规则或日期变化。规模保持可人工核验，不以全网覆盖为目标。

## Non-Goals

第一版不提供自动报名、自动缴费、自动提交比赛作品、大型社交或组队平台、无限规模全网竞赛爬虫、替代官方赛事通知，以及完整高校教务管理系统。学生仍须以赛事官方通知完成最终确认和实际操作。

## Post-P14 Product Experience Design

### 产品入口与信息架构

Competition Copilot 定位为**高校竞赛全生命周期决策与成长平台**。
默认入口为 Dashboard；Copilot 是独立工作区，也是贯穿业务页的智能入口。
自由聊天与 explicit actions 并存，复用同一 Runtime → Agent / LangGraph →
CapabilityFacade → Application / Domain 路径；页面不直接调用 Domain 或 Repository。
技术 identity 保留在高级详情，用户通过权威记录的名称与版本进行显式选择。

| 页面 | 职责 |
| --- | --- |
| **首页 / Dashboard** | 我是谁、当前关注对象、正在执行什么、下一步可做什么；聚合真实状态与待处理事项。 |
| **赛事中心 / Competition Center** | Search / Browse、赛事卡片及单项赛事详情，复用正式已核验数据。 |
| **我的赛事 / My Competitions** | 持续跟踪显式关注/选择的赛事及产品生命周期；关注记录和持久化仍需后续设计。 |
| **我的能力 / My Profile / Skills** | 基本资料、能力及来源、兴趣/目标、可投入时间与缺失资料。 |
| **备赛计划 / Plans** | Current Plan、里程碑时间线、状态、版本、证据与变更历史。 |
| **赛事动态 / Competition Updates** | Digital Twin 变化、Before / After、Event、Impact 与来源。 |
| **Decision / Approval Center** | 待你确认的建议、影响范围及审批记录；是否提升为一级导航后续决定。 |
| **Copilot** | 对话、明确操作、补充信息和有依据的解释，承接所在页面已选择的 context。 |

首批一级导航为：首页、赛事中心、我的赛事、我的能力、备赛计划、赛事动态、Copilot。
按 PX1–PX6 逐步交付，不将尚未实现页面呈现为已有业务功能。

### 四层体验与三项创新

| 体验层 | 关注内容 | 产品承载 |
|---|---|---|
| My Status | 当前用户、赛事、计划、能力与待办 | Dashboard / Current Context Panel |
| My Decisions | Discovery、Eligibility、Recommendation、Skill Gap | 赛事中心 / 详情 / 我的能力 |
| My Actions | Plan、Milestone；未来 Task / Action Item | 我的赛事 / 备赛计划 |
| Change & Adaptation | Twin、Event、Impact、Replanning、Approval、PlanDiff、版本历史 | 赛事动态 / 审批中心 / 计划历史 |

| 核心创新 | 产品映射 |
|---|---|
| Constraint-aware Competition Decision | Competition Detail、资格核验、推荐与技能诊断；硬约束和未知状态不被软匹配覆盖 |
| Competition Digital Twin | Competition Updates、变化历史、Before / After 与 Evidence |
| Event-driven Adaptive Planning | Plan、Impact、Approval、actual PlanDiff 与 Version History |

### Dashboard 与 Current Context

Dashboard 区域包括欢迎 / Current User、Current Competition、Current Plan、
Recommendation Summary、Profile Completeness、Recent Competition Change、
Pending Approval、Next Suggested Action。每个区域标明数据来自哪个已有结构化结果、
显式选择或服务端状态，以及当前 session / host 的适用范围。
没有权威数据或安全读取路径时显示 Empty / 不可用，不写死赛事数量、待办数或进度。
“下一步”只提供与已有状态相符的操作入口，不代替业务建议或推断执行结论。
Profile Completeness 在规则完成独立设计前只列已知/缺失字段，不显示猜测百分比。

Current Context Panel 展示当前学生、赛事、届次、赛道、计划；选择来自已验证记录。
`student_id / competition_id / edition_id / track_id / plan_ref` 为内部 identity，
不作为普通用户主输入。保留 exact PlanReference，不自动切换计划、不重算 digest/version；
context 与缺失字段仍由 Runtime/Core 重新校验，展示层不能宣布已满足。

### Competition Detail

页头展示 Competition Title、Edition、Track、Verified Source、Observed Time。
操作为判断资格、分析技能差距、生成计划，以及未来关注赛事；关注写入/读取契约未建立前
不能宣称已保存。Tabs 为赛事概览、参赛资格、技能要求、时间节点、赛道、证据来源、变化历史。
选择用名称表达并绑定真实 identity；空日期、不可用技能要求与无历史均显示真实缺失状态。
Detail 复用 P3–P7 能力，Plan action 继续经过真实 P7 prerequisite 与 P8。

### My Profile / Skills

呈现教育信息、专业、年级、兴趣、目标、每周可投入时间、技能能力、技能来源与缺失资料。
自评必须标明“自评”，不能升级为外部核验。missing profile data / skill record != skill deficit；
required_level=null != satisfied，PARTIAL != COMPLETE。画像完整度需先明确字段范围、
适用条件、缺失含义与规则版本，再独立审核；UI 不自行估算百分比。
画像编辑与持久化路径如无现有正式支持，列为待设计，不因页面存在而假定可用。

### My Competitions 与 Planning

拟议赛事产品生命周期为：关注 → 评估中 → 准备参赛 → 备赛中 → 已提交 → 已结束，
另有“已放弃”。这是待评审的用户跟踪状态模型，不代表已实现状态机，也不自动改变
Eligibility、CompetitionPlan.status 或 Approval。没有记录时展示空态。

Plan Workspace 展示 Current Plan、Timeline、Status、Version、Evidence、Change History
与 PlanDiff。当前结构为 CompetitionPlan → PlanningNeed / Milestone；未来才可能扩展
Task / Action Item，须独立 Domain 设计与评审。保留后端 milestone 顺序；无日期不猜日期，
不伪造进度、任务或第二阶段。草案/执行中/已取消等中文状态仅翻译后端状态。

### Competition Updates、Approval 与版本历史

赛事动态展示 Snapshot Before → After、Diff、CompetitionEvent、来源、观察时间及核验状态。
Impact 的用户语义是“不影响当前计划 / 暂无法判断 / 影响当前计划”，对应既有
NO_PLAN_IMPACT / UNDETERMINED / AFFECTS_PLAN；raw enum 留在审计中，不创造新的业务状态。
没有事件或影响结果就不推断“未发生变化”或“没有影响”。

“待你确认”展示触发原因、当前精确计划、建议修改、影响范围和 Evidence，并提供拒绝/批准。
Preparation != Authorization；用户点击后仍由后端绑定可信 actor、exact current plan、
scope、request/invocation 与 single-use continuation。前端不构造 mutation authority。
只有 authorized execution 返回 actual PlanDiff 后才显示已修改；拒绝不产生修改。

Version History 复用 PlanDiff / lineage，展示 v1 Initial Plan、后续真实版本及其 before、after、
trigger、reason、evidence、approval。仅在审批记录存在时标注 Human Approved，不从文案推断。
Huawei track removal 始终标识 manual controlled demo observation，不声称真实官方删除；
BigModel browser smoke 是 local demo validation，非生产部署。Local PlanRegistry 仍为
in-memory，generated plans 重启后不持久化；页面不得暗示长期保存或跨会话恢复。

### Evidence Design Language 与全局状态

统一呈现层级：**Conclusion → Explanation → Evidence → Advanced Audit**。
默认显示结论与解释；“查看证据”按来源聚合、允许视觉去重；高级详情完整保留
reason_codes、source URL/type、verification_status、observed_at、result_ref、evidence_ref
以及适用的版本、策略和全部原始引用。折叠/聚合不删除 provenance，也不产生新的结论。

统一状态设计为 Empty、Loading、Success、Unknown、Blocked、Error、Waiting For Approval、
Stale。Unknown 不当作失败或通过，Blocked 以权威限制说明，Stale 引导显式重选最新计划，
Waiting For Approval 不宣称执行成功；错误区分业务限制与传输故障，不自动 retry。
Loading 必须对应当前真实任务，例如“正在分析参赛资格”“正在核验赛事要求”
“正在生成备赛计划”，不得在后台没有执行时虚报进度或完成状态。

### PX Roadmap 与非目标

PX0 Design = DOCUMENTED；PX1 Product Shell & Dashboard / PX2 Core = CLOSED_VERIFIED；
PX2.1 = REVIEW_COMPLETE；PX2.2 = REVIEW_PASS；PX2 Product Detail Enrichment = DEFERRED（非阻塞）；
PX3 My Profile / Skills、PX4 My Competitions & Planning、PX5 Events / Approval / Version、
PX6 Guided Demo & Reliability = PLANNED。
范围和验收门槛统一维护在 [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md#post-p14-product-experience-upgrade-px)。
已有 explicit actions 可在 PX6 复用，但不代表 Scenario Selector、Runtime Health、
Demo Reset、Notification UX 已实现；reset 不得在未获服务端确认时宣称业务状态已重置。

PX 不顺带实施 P15、新 scorer、数据库、实时爬虫、自动报名、Task Domain、
Notification Backend、权限系统或审批 authority 变更。任何确需新 Domain/状态/接口的工作，
先进行独立设计与审核。PX0 为设计文档；PX1 已交付壳层、首页、只读上下文与独立
Copilot；PX2 已激活 Competition 级浏览和详情，但 Edition/Track、完整规则/要求与历史读取
仍被正式 read path 缺口阻塞。其余业务页面仍是 Coming Soon，不代表完整产品或持久化已实现。

## Trust and Safety Principles

- 官方来源优先；官方规则与通知优先于模型解释。遇到来源冲突、过期或信息不足时显示不确定状态，并引导核对原文。
- 外部数据先进入 `CompetitionCandidate`，经规范化、校验和人工审核后才进入正式赛事库；未经验证的候选数据不得作为确定性决策依据。
- 每条赛事关键事实保留 `source_url`、`source_type`、`observed_at`、`verification_status`；资格、推荐、诊断和重规划返回 `reason_code` 与 `evidence`。
- Agent 只能使用 Tool 提供的已核验事实及业务结果，不编造赛事事实，也不决定硬资格或实现评分公式。
- 动态状态不得静默覆盖；保存 `Snapshot`、`Diff`、`CompetitionEvent`。自动重规划保存变更前后、触发事件和证据，供学生追溯。

## Success Criteria

比赛版以可复现的端到端场景验收，而非页面数量衡量：

1. 本科生或研究生可从建立画像走到选择赛事、技能诊断、结构化计划并加入 Journey；Agent 与页面展示同一业务结果。
2. 资格检查能区分通过、不通过和信息不足；同一版本化输入重复运行得到同一结论，且每项关键决策都有 `reason_code` 与 `evidence`。
3. 推荐先过滤硬约束，再按可解释分数排序；未审核的 `CompetitionCandidate` 不进入正式推荐或硬规则判断。
4. 技能差距关联明确赛事要求、学生侧证据与未知状态；计划保留 PlanningNeed / Milestone 和可信日期，可追踪版本。Task/执行型依赖是未来独立验收目标，不是当前实现声明。
5. 至少一个经过核验的赛事变化形成 `Snapshot`、`Diff`、`CompetitionEvent`，触发影响分析与 Replanning；`Plan Diff` 可查看前后方案、触发事件和证据。
6. 上述场景有自动化评测或测试记录，关键路径和边界情况可重复验证。
