# Development Plan

## P11 Adaptive Replanning - Phase Closure

Status: CLOSED. Final Review: PASS. Frozen: YES / FROZEN FOR DOWNSTREAM USE.
P12 Agent: CLOSED_FROZEN; Final Review: REVIEW_PASS. P13 is CLOSED_FROZEN; Final Review: REVIEW_PASS; production deployment remains deferred to P16.
Canonical phase-status source: `docs/DEVELOPMENT_PLAN.md`; this document must agree.

| Phase | Scope | Status |
|---|---|---|
| P11 | Adaptive Replanning | CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE |
| P11.1 | Adaptive Replanning Contract | CLOSED / FROZEN |
| P11.1.2 | Canonical Plan Reference Serialization Compatibility Fix | CLOSED / FROZEN |
| P11.2 | Deterministic Event Impact Analysis | CLOSED / FROZEN |
| P11.3 | Replanning Decision + Affected Scope | CLOSED / FROZEN |
| P11.3.5 | Structured Replanning Input | CLOSED / FROZEN |
| P11.4 | Deterministic Plan Revision + PlanDiff | CLOSED / FROZEN |
| P11.4.2 | Plan-Level Replanning Resolution | CLOSED / FROZEN |
| P11.5 | Real Adaptive Replanning Integration | CLOSED / FROZEN |
| P12 | Agent | CLOSED_FROZEN |
| P13 | MCP + AgentArts MCP compatibility | CLOSED_FROZEN; P13.0-P13.6 REVIEW_PASS |

### Frozen authority map

- P11.1: typed result Contract authority, including controlled mixed-scope/status Diff extensions.
- P11.1.2: canonical PlanReference compatibility, not a new business authority.
- P11.2: Event impact authority.
- P11.3: ReplanningDecision + AffectedPlanScope authority.
- P11.3.5: structured authorized WHAT-to-change authority, including explicit coverage resolution.
- P11.4 / P11.4.2: deterministic authorized revision execution authority.
- P11.5: real-component integration proof only; no new business authority.

### Frozen safety semantics

1. Impact is tri-state: NO_PLAN_IMPACT / UNDETERMINED / AFFECTS_PLAN.
2. Missing represented Plan dependency -> UNDETERMINED, never proven no-impact.
3. Decision precedence: any AFFECTS_PLAN -> REPLAN; else any UNDETERMINED ->
   UNDETERMINED; else -> KEEP_CURRENT_PLAN. No voting or severity score.
4. AffectedPlanScope describes WHERE; it is not a RevisionInstruction/operation.
5. Reason code is neither structured evidence nor approval authority.
6. Structural changes require typed explicit revision authority/evidence and exact
   Plan/version/before-state preconditions; no Event-to-Plan mutation guessing.
7. PARTIAL cannot masquerade as COMPLETE; partial structural execution rejects.
   COMPLETE requires explicit coverage authority AND semantic compatibility.
8. KEEP -> unchanged Plan, identity/version/metadata, and empty PlanDiff.
9. UNDETERMINED -> unresolved input and no speculative revision; distinct from KEEP.
10. Confirmed TARGET_TRACK_REMOVED + REPLAN + original whole-plan scope may be
    resolved operationally by explicitly approved draft/active -> cancelled.
11. Cancellation does not choose another track or erase the Event. Preserve target
    identity, needs, audit, horizon and historical milestones; no automatic deletion.
12. Revision is atomic, before Plan immutable, and PlanDiff derives from actual
    validated before/after. Status-only cancellation declares no milestone change.
13. Full Event -> Impact -> Decision -> original Scope -> authorized Resolution ->
    Input -> Authority -> before/after Plan -> PlanDiff lineage is required.
14. Legitimate sourced P8 Plans retain source_item/typed URLs and support deterministic
    PlanReference, stable audit JSON and legacy identity. Explicit AnyUrl serialization
    retains original UTC/key/sequence/enum rules; unknown types still reject.
15. P11 Domain services have no Repository access, persistence or network side effects.
16. No LLM/Agent owns P11 business authority; downstream orchestration must delegate
    impact, decisions, authority validation and execution to deterministic services.

### Integration proof and resolved evolution history

P11.5 validates all three offline production-component paths:
- Proven no-impact -> KEEP -> NO_REVISION_REQUIRED -> unchanged Plan + empty Diff.
- Missing dependency -> UNDETERMINED -> UNRESOLVED -> no speculative revision.
- Controlled TRACK_MEMBERSHIP_CHANGED / target removal -> AFFECTS_PLAN -> REPLAN ->
  explicit COMPLETE coverage -> HUMAN_APPROVED active -> cancelled -> actual status Diff.

Repository-backed target data is real local Seed; controlled changes/approval are
TEST-ONLY scenarios, not official historical events or a claim that Huawei removed
a track. Final Review PASS; exit criteria 16/16 PASS; validation: 1824 tests, 0 skipped,
Ruff PASS, Diff Check PASS. P11.5 commit: 5394316; sourced-reference fix: bf792fc.
Earlier reason/evidence, mixed-scope, revision-input and whole-plan capability
blockers are resolved by controlled evolution. The sourced HttpUrl Final Review
defect is resolved by P11.1.2. Detailed historical rationale below is retained;
none of these historical blockers is an open P11 issue.

### Deferred scope and P12 boundary

P11 does not implement automatic replacement-track selection, automatic Eligibility/
Recommendation/SkillGap reruns, new PlanningNeed derivation from Events, Plan save/
replacement, Event history persistence, cross-run dedup persistence, scheduler/polling,
notification, Agent, MCP or frontend. Severity/impact scoring remains deferred.
Target-added impact has no complete cancellation policy. No supersession/replacement
relation or arbitrary Plan status machine is implied by the existing status enum.

P12 is CLOSED_FROZEN. Injected model proposals and explicit human replies are validated; the isolated Runtime Adapter reuses the same core graph. The Agent may understand natural-language intent,
select tools/workflows, orchestrate, clarify, explain and collect explicit approval.
It must not own Eligibility, Recommendation scoring, SkillGap, Event impact,
ReplanningDecision or revision execution rules; must not turn PARTIAL into COMPLETE,
bypass Revision Authority or mutate Plans directly. Approval collection submits
structured inputs through an authorized boundary; Domain remains the business authority.


## Phase status ownership and lifecycle

`docs/DEVELOPMENT_PLAN.md` is the single canonical phase-status source of truth.
`backend/README.md` and `docs/ARCHITECTURE.md` must mirror it.
From P12 onward use: NOT_STARTED -> IMPLEMENTED_AWAITING_REVIEW ->
REVIEW_PASS -> CLOSED_FROZEN. BLOCKED requires a concrete blocking reason.
Git commit status is proved by Git history, not a Markdown lifecycle state;
do not add commit-waiting states or status-only commit loops. Existing completed
P12.0 status and frozen P0-P11 historical labels remain unchanged. P12 overall
stays IN_PROGRESS until its Final Review and Closure gates are satisfied.
A blocked phase uses BLOCKED with its concrete blocking reason; resolved reasons
may remain as explicitly resolved history. Every state transition must update all
three documents together; conflicting current states are not permitted. This is a
simple documentation convention, not a new runtime/status-management system.


## 执行约束与阶段关口

按 P0 → P16 顺序交付；本文件中的目录和文件均为未来阶段的预计位置，不代表 P0 要创建它们。每个阶段只修改该阶段所需文件。所有业务判断留在 Domain Service，Repository 只做数据访问，Tool 只通过 Application/Domain Service 与抽象 Repository/Gateway 使用能力。硬约束必须可复现，关键决策返回 `reason_code` 和 `evidence`；新功能同时提交自动化测试。AgentArts thin Runtime Adapter compatibility starts at P12.7-P12.8; P16 owns production deployment and hardening.

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

- **Status:** **P2 Ingestion & Verified Data Pipeline — COMPLETE**. P2 Integration Test：PASS；P2 Final Review：PASS。已形成 12 份 Raw Fixture 和 **12 Verified Competition Seeds**，同时支持 Seed 1.0 与 1.1。下一阶段为 **P3 Repository**。
- **已完成的数据链：** `External Source → Raw → Normalize → Validate → Candidate → Human Approval → Source Verification → Verified Seed`。Raw、候选、人工批准和已核验 Seed 保持独立；结构校验通过不会自动批准或核验来源。
- **已完成的批量流程：** `Raw Batch → Batch Audit → Human Review → Raw SHA256 Binding → Dry-run → Explicit Execute → Verified Seed → Idempotence → Audit`。Human Review Manifest 保存明确决定，执行器默认 dry-run；重复执行对一致 Seed 返回 `already_materialized`，不覆盖冲突 Seed。
- **P2 ingestion scope is frozen.** 除非发现真正的 ingestion Contract defect，不直接回到 P2 扩展 CompetitionStage、Eligibility、TeamRule、MentorRule、InstitutionQuota、Judging / Awards、Dynamic State、Competition Digital Twin 或 CompetitionEvent；这些归属未来 Domain / Application 阶段。
- **延期的真实数据信号：** multi-stage schedule、stage-specific eligibility、team rule、mentor limit、institution quota、nested track / sub-item hierarchy、dynamic state 和 fact-level multi-source provenance 目前保留为 Raw-only 证据，均不是 P2 blocker。
- **时间政策：** 来源明确写出时区的完整钟点可结构化为 `source_explicit`；经人工确认的中国大陆本地业务钟点可用 `Asia/Shanghai` 和 `jurisdiction_default` 记录解释依据。Date-only 不补钟点，month range 不补日期，multi-stage schedule 不压成虚假 Edition TimeWindow；国际或跨境 scope 不明时不自动推断时区。
- **Track 语义：** 仅将官方顶层赛道、顶层大类或经人工确认的最高层竞赛类别建为 `CompetitionTrack`。赛项、赛题、Problem、初赛 / 复赛 / 决赛、地区、机器人角色、评审组别和 participant category 不自动升级。Zero Track 与 Many Track 已由真实数据验证；One Track 未观察到，但 Contract 支持，属于非阻塞覆盖缺口。
- **P3 输入边界：** 正式业务数据从 **Verified Seed** 读取，不以 `data/raw` 为正式数据源。P3 正常读取 Competition 数据不需要 Human Review Manifest 或 `raw_payload`；Manifest 属 ingestion audit layer。核心读取模型为 `Competition`、`CompetitionEdition`、`CompetitionTrack`、`SourceMetadata` 和 `TimeWindow`。

- **Goal:** 独立建立可审核、可追溯的少量赛事样本。
- **Inputs:** P1 Schema、公开赛事来源、人工审核标准。
- **Main Deliverables:** `External Source → Raw → Normalize → Validate → Candidate → Human Approval → Source Verification → Verified Seed` 流程及审核记录；关键事实含 `source_url`、`source_type`、`observed_at`、`verification_status`。
- **Files/Modules Delivered:** `data/raw/`、`data/review/`、`data/seed/` Artifact，`backend/competition_copilot/ingestion/` 生产逻辑，`backend/scripts/` CLI 与 `backend/tests/` 自动化测试。
- **Tests Required:** 格式转换、缺失来源、重复候选、审核拒绝和未经验证数据隔离测试。
- **Acceptance Criteria:** 种子数据能从来源复核；未验证的 `CompetitionCandidate` 不能进入正式数据或确定性决策。此阶段可用审阅后的文件数据，不依赖 P3 数据库层。
- **Explicitly Out of Scope:** 全网爬虫、自动审核、生产数据库和推荐逻辑。

### P2 Sample 4 — Multi-source Investigation

- **Sample 4 Multi-source Investigation = COMPLETE**：对中国国际大学生创新大赛 2026、华为ICT大赛 2026、中国大学生计算机设计大赛 2026、中国大学生工程实践与创新能力大赛 2027、RoboMaster 2026、挑战杯创业计划竞赛 2026、全国大学生智能汽车竞赛、中国研究生创新实践系列大赛 2026，共 8 个代表性真实赛事进行了 Current-Schema Single-Source Challenge。
- **Finding:** `NO CURRENT-SCHEMA MULTI-SOURCE CANDIDATE FOUND`。当前 P2 Seed 必需的结构化事实主要是 `Competition.name`、`CompetitionEdition.name`、`CompetitionEdition.year`、`CompetitionTrack.name`；单一官方年度通知或赛事官方页面通常足以支持这些身份与名称事实。
- **Current Schema Multi-source Support = NOT REQUIRED**：跨来源事实主要涉及 Eligibility、Team Rule、Track Detailed Rule、Judging、Awards、Quota 和 Dynamic State；这些仍属 Raw-only 或未来 Domain 范围，不能据此要求当前 Seed 支持多来源。
- **Future Multi-source Requirement = DEFERRED**：未来需求并未取消。**Future Revisit Trigger =** 当 Eligibility、Team Rule、Track Detail 或 Dynamic State 被提升为正式结构化 Domain 时，重新评估逐事实来源归属和多来源核验需求。
- **Sample Artifact Decision:** 本次调查不创建 Sample 4 Raw 或 Seed，也不修改当前 Domain、Schema 或现有 Seed 契约。

## P3 — Repository Layer

- **Goal:** 用只读抽象接口查询 Verified Seed 中的正式 Domain 数据。
- **Inputs:** P1 模型、P2 Verified Seed（1.0 / 1.1）及其已核验状态约束；不以 Raw 或 Human Review Manifest 作为正式赛事读取输入。
- **Status:** **P3 Repository Layer — COMPLETE**。P3 Repository Integration Test：PASS；P3 Final Review：PASS。下一阶段为 **P4 Tool Layer**。
- **正式读取边界：** 上层依赖只读 `CompetitionRepository`，返回 `Competition`、`CompetitionEdition`、`CompetitionTrack`。当前 Infrastructure Adapter 为 `JsonSeedCompetitionRepository`，正式输入是 Verified Seed，支持 Seed 1.0 / 1.1；JSON 不是 Repository Contract 的永久存储要求。
- **最终查询语义：** 未知实体或父实体抛出 `RepositoryEntityNotFoundError`；已存在父实体没有子实体时返回 `[]`。Competition 按 ID 升序，Edition 按 `(year, id)` 升序，Track 保留 Seed 中的审核顺序。
- **冻结范围：** P3 repository scope is frozen。不得为 Search、Eligibility、Recommendation、Agent、MCP、Skill Gap 或 Planner 随意扩展基础 Contract；仅真正的数据访问 Contract defect 可以重新打开 P3。
- **P4 交接：** P4 通过抽象 `CompetitionRepository` 读取正式数据，测试可使用 fake / in-memory Repository；不得直接依赖 JSON Adapter、`data/seed`、Seed Envelope、Raw 或 Human Review Manifest。未来数据库 Adapter 可实现同一接口而不改变上层读取契约。
- **延期事项：** keyword / fuzzy search、按年份或状态筛选、截止时间查询、分页、数据库持久化、缓存 / 刷新、热重载和 Repository 写入 API，均按后续真实 Tool / Application 需求设计，不属于 P3 blocker。
- **Main Deliverables:** 只读 Repository Interface、JSON Verified Seed Adapter 及 Domain 映射；Raw 与 Manifest 不参与正式查询。
- **Files/Modules:** `backend/competition_copilot/repositories/` 接口、`backend/competition_copilot/infrastructure/repositories/` Adapter、`backend/tests/repositories/` 与 `backend/tests/integration/` 测试。
- **Tests Required:** 接口契约、查询语义、错误处理、Seed 版本兼容和真实数据集集成测试。
- **Acceptance Criteria:** 上层只依赖接口；Repository 和 Adapter 均不计算资格、评分或其他业务规则。
- **Explicitly Out of Scope:** Domain 决策、Agent 调用和 Tool 编排。

## P4 — Tool Layer

- **Goal:** 为未来 Agent/MCP 建立稳定、可独立调用的业务能力入口。
- **Inputs:** P1 模型、P3 Repository Interface、Application 用例边界。
- **Status:** **P4 Tool Layer — COMPLETE**。P4.1 Tool Contract、P4.2 Competition Read Tools、P4.3 Error & Serialization Semantics、P4.4 Tool Integration Test 和 P4 Final Review 全部 PASS。下一阶段为 **P5 Eligibility**。
- **正式只读 Tool：** `ListCompetitionsTool`、`GetCompetitionTool`、`ListCompetitionEditionsTool`、`GetCompetitionEditionTool`、`ListEditionTracksTool`、`GetCompetitionTrackTool`。未来 Application / Agent / MCP 通过 Tool 调用抽象 `CompetitionRepository`，获取正式 Domain；Tool 不依赖 JSON Adapter、Seed Envelope、Raw 或 Manifest。
- **稳定契约：** metadata、经验证的输入、结构化 `ToolResult`、机器可判断的错误码、JSON 序列化与 Schema、Repository 构造注入、只读及确定性语义。无效输入返回 `INVALID_INPUT`；Repository 未找到实体或父实体返回 `NOT_FOUND`；已存在父实体的空子集合成功返回 `[]`。JSON 测试覆盖 aware datetime、partial `TimeWindow`、`SourceMetadata`、空列表、顺序与 Artifact 隔离。
- **真实集成：** `Verified Seed → JsonSeedCompetitionRepository → CompetitionRepository → Competition Read Tools → ToolResult → JSON`；P4.4 PASS，数据集数量不是 Tool Contract。
- **冻结范围：** **P4 Competition Read Tool scope is frozen.** 不得为 Eligibility、Recommendation、Search、Skill Gap、Planning、Agent 或 MCP 随意修改六个 Read Tool 的基础 Contract；仅真正的 Tool boundary defect 可以重新打开 P4。Search、模糊名称解析、年份/状态筛选、截止时间查询、Eligibility、Recommendation、Skill Gap、Planner、Agent 编排及 MCP/API 传输均为未来能力，不是 P4 未完成项。
- **P5 交接：** Eligibility 建立独立的 Domain/Application 业务能力；硬约束判断须 deterministic、auditable、explainable、testable，不由 LLM 判定，也不塞入当前 Competition Read Tools。
- **Main Deliverables:** Tool 请求/响应契约和已审核赛事检索入口；后续功能阶段扩展对应 Tool。
- **Files/Modules:** 当前 Tool Contract 位于 `backend/competition_copilot/tools/`，测试位于 `backend/tests/tools/`；未来 Application 用例按需要新增。
- **Tests Required:** 参数、错误、抽象依赖、独立调用和无具体基础设施依赖测试。
- **Acceptance Criteria:** Tool 只通过 Application/Domain Service 与抽象 Repository/Gateway 使用能力；不依赖具体 Web、数据库、Agent SDK 或第三方基础设施。
- **Explicitly Out of Scope:** Agent Runtime、MCP 服务、资格或推荐公式。

## P5 — Deterministic Eligibility Engine

- **Goal:** 对核验过的赛事规则执行硬资格判断。
- **Status:** **P5 Eligibility — COMPLETE**。P5.1 Eligibility Domain & Contract、P5.2 Deterministic Eligibility Rule Engine、P5.3 Real Competition Eligibility Evaluation、P5.4 Eligibility Integration Test 及 P5 Final Review 全部 PASS。下一阶段为 **P6 Recommendation**。
- **正式能力：** `EligibilityStatus` 为 `ELIGIBLE`、`INELIGIBLE`、`UNKNOWN`；`EligibilityRule` / `RuleEvaluation` 保留逐条审计。`EligibilityRuleEngine` 顺序执行所有规则，按 `INELIGIBLE > UNKNOWN > ELIGIBLE` 聚合。独立的结构化 `EligibilityPolicy`、`EligibilityPolicyProvider` 与 `CompetitionEligibilityEvaluator` 已接入首批真实规则和真实集成测试。
- **硬约束语义：** 缺画像必要事实为 `UNKNOWN / PROFILE_DATA_MISSING`；缺结构化规则或 Policy 为 `UNKNOWN / RULE_DATA_MISSING`；明确违反规则为 `INELIGIBLE`。只有全部适用硬规则明确满足且覆盖完整，才可判为 `ELIGIBLE`。`PARTIAL` Policy 的已知规则满足加覆盖缺口为 `UNKNOWN`，已知违反加覆盖缺口仍为 `INELIGIBLE`。
- **数据与审计边界：** P5 Policy 位于独立的 `data/eligibility/`，与 Seed、Raw、Review Manifest 分离；Runtime 不读取 Raw 或 Manifest，Application 不直接读取 Seed。Decision 保留最终状态、规则 ID 与逐条状态、reason codes、画像和官方约束证据及系统覆盖缺口；系统覆盖评估不冒充官方来源。当前验收快照为 12 份 Seed、12 个 Competition、12 个 Edition、33 个 Track，2 份 Policy（0 COMPLETE、2 PARTIAL）；数量不是永久 Contract。
- **冻结范围与 P6 交接：** **P5 Eligibility scope is frozen.** P5 仅判断官方硬资格约束，包括学生身份、学历、院校、团队、地区/国籍及官方资质要求；技能、兴趣、经验、获奖概率、偏好、学习成本和排名属于 P6 及后续软匹配能力。Recommendation、Skill Gap、Planning、Agent 和 MCP 不得重新实现 P5 状态、硬规则、聚合优先级、缺失数据或覆盖语义；仅真正的 Eligibility contract / semantic defect 可重新打开 P5。P6 必须消费 P5 结果：`INELIGIBLE` 不能被高推荐分数改为可参加，`UNKNOWN` 不能伪装成确认合格，`ELIGIBLE` 可进入正常软匹配。
- **后续数据 / Domain 需求：** 研究生入学状态、全日制/在读状态、Team Context、团队人数与构成、同校/跨校条件、更多赛事 Policy 和规则类型均属未来能力；现有未确认资格保守返回 `UNKNOWN`，不是 P5 退出阻碍。
- **Inputs:** 学生画像、已验证赛事事实、规则版本。
- **Main Deliverables:** 可复现的资格规则、缺失信息处理、结构化 Policy、可审计 EligibilityDecision 和真实集成测试；Eligibility Tool 留待后续能力阶段。
- **Files/Modules:** `backend/competition_copilot/domain/eligibility*.py`、`backend/competition_copilot/application/eligibility.py`、`backend/competition_copilot/infrastructure/eligibility_policy_json.py`、`data/eligibility/` 与对应 Domain、Application、Integration tests。
- **Tests Required:** 满足、不满足、边界值、缺失/冲突事实、规则版本与相同输入同结果测试。
- **Acceptance Criteria:** 每项资格结论都有稳定 `reason_code` 和来源可追溯的 `evidence`；LLM 不判定硬规则。
- **Explicitly Out of Scope:** 个性化排序、技能诊断和自然语言猜测资格。

## P6 — Competition Matching / Recommendation Engine

- **Goal:** 在资格过滤后给出可解释的个性化排序。
- **Current status:** **P6 Recommendation — COMPLETE.** P6.1 Recommendation Domain & Contract — PASS; P6.2 Soft Suitability Scoring Engine — PASS; P6.3 Competition Candidate Ranking — PASS; P6.4 Recommendation Integration Test — PASS; P6 Final Review — PASS. 下一阶段：**P7 Skill Gap**。
- **P5 边界：** Recommendation 显式携带 P5 `EligibilityDecision` 并校验目标一致。`INELIGIBLE` 只能是 eligibility blocked，不能用高分覆盖；`UNKNOWN` 只能保留资格不确定性；`ELIGIBLE` 才允许正常软适配度结果，但并不自动等于推荐。缺少软画像信息不等于资格不合格。P6 处理技能、兴趣、经验和偏好等软信号，不能重新判断硬资格。
- **Inputs:** P5 资格结果、学生偏好、已验证赛事事实、评分规则版本。
- **Main Deliverables:** Recommendation Domain Contract、`RecommendationContext`、`RecommendationEvaluation`、`RecommendationStatus` / `RecommendationReasonCode`、validated immutable snapshots、确定性分项软评分、可用分项加权聚合、缺失软信号语义、资格感知三桶排序及真实集成测试。Application 编排、candidate discovery 和推荐 Tool 留待后续阶段。
- **Files/Modules:** P6.1 契约位于 `backend/competition_copilot/domain/recommendation.py`，合成测试位于 `backend/tests/domain/test_recommendation.py`；Application、Tool 模块留待后续阶段确定。
- **P6.2 modules:** `backend/competition_copilot/domain/recommendation_scoring.py` and `backend/tests/domain/test_recommendation_scoring.py`.
- **P6.3 modules:** `backend/competition_copilot/domain/recommendation_ranking.py` and `backend/tests/domain/test_recommendation_ranking.py`. Empty input is valid; duplicate targets fail-fast before sorting. Ranking contracts are immutable and preserve existing eligibility, scores and audit. Application, Tool and optional Top-K read views remain future work.
- **P6.4 acceptance:** `backend/tests/integration/test_p6_recommendation_integration.py` dynamically loads real Seed/Policy artifacts. It verifies real INELIGIBLE, partial/missing-policy UNKNOWN, synthetic eligible high/low/unavailable soft scoring, separated ranking buckets, cross-target rejection, duplicate rejection, full audit/JSON, repeatability and read-only Raw/Manifest-independent execution. Current real policies are partial, so synthetic confirmed eligibility is explicitly test-only and never persisted.
- **Tests Required:** 资格排除、并列排序、权重边界、缺失偏好、稳定性及理由证据测试。
- **冻结范围：** **P6 Recommendation scope is frozen.** Skill Gap、Planner、Agent、MCP 和 Frontend 不得重新实现或覆盖 P5 eligibility semantics、P6 RecommendationStatus、scoring、missing signal 或 ranking bucket semantics；仅真正的 P6 contract / semantic defect 可重新打开 P6。
- **Deferred capabilities:** real competition skill mapping、interest / goal / experience signals、resource cost、更多评分 component、candidate discovery service、Top-K UI view 和 learned ranking 属未来能力，不是 P6 未完成 blocker；任何后续评分或排序仍须遵守冻结语义。
- **Acceptance Criteria:** 不合资格项不进入可报名推荐；相同版本化输入排序相同，返回 `reason_code` 和 `evidence`。
- **Explicitly Out of Scope:** Agent 自行评分、未经验证的赛事推荐和备赛计划。

## P7 — Student Profile & Skill Gap

**Status: FROZEN.** P7 is finished. P7.1 and its student-evidence follow-up,
P7.2, P7.3A, P7.3B.2, P7.3B.5 and P7.4 passed their reviews; the source audits,
candidate scan and P7.3B.4 human approval are recorded. P7 Final Review PASS.
StudentProfile Domain already exists and is consumed as Skill Gap input. This
phase delivered Skill Requirement, Student Skill Evidence, deterministic gap
evaluation and real integration; it did not implement profile ingestion.

### Frozen capabilities

- SkillRequirement Contract with REQUIRED / DESIRED and specified / unspecified proficiency.
- RequirementCoverage MISSING / PARTIAL / COMPLETE, independent of threshold completeness.
- Requirement Presence Evidence, optional Requirement Proficiency Evidence, and Student Skill Evidence.
- Immutable SkillGapContext, SkillGapItem, multi-reason uncertainty and SkillGapDecision snapshots.
- Pure deterministic SkillGapEngine, evaluating all requirements and retaining complete audit.
- SkillRequirementProvider and read-only JsonSkillRequirementProvider with exact lookup.
- Reviewed real SkillRequirementSetEnvelope artifact and real Skill Gap integration.

### Frozen semantics and boundaries

- Missing Requirement data differs from a known Requirement with unspecified threshold.
- required_level=None means known requirement, but proficiency threshold unspecified;
  it is not missing requirement, optionality, a lowest level or SkillLevel.UNKNOWN.
- Missing StudentSkill differs from BEGINNER / zero; UNKNOWN differs from GAP and SATISFIED.
- PARTIAL cannot confirm NO_GAP. NO_GAP requires COMPLETE, all thresholds specified,
  all relevant StudentSkill known, and every REQUIRED/DESIRED requirement satisfied.
- Known GAP takes precedence over partial coverage, unknown thresholds and missing student data.
- P7 REQUIRED denotes core capability, not hard participation eligibility. P5 is the
  sole hard eligibility authority; skill mismatch never directly means INELIGIBLE.
- P6 score, ranking and eligibility buckets remain frozen and are not recomputed by P7.
- P7 generates no learning resources, study plans, milestones, schedules, priorities or plan diffs.
- CompetitionRepository reads data/seed; SkillRequirementProvider reads data/skill_requirements.
  P7 runtime does not read Raw, review manifests, eligibility policies, network or LLM.

### Reviewed real data and integration

The current snapshot includes at least one reviewed real artifact:
`data/skill_requirements/comap-mcm-2027.json`, exact COMAP MCM 2027 Edition target,
track=None, skill mathematical-modeling. REQUIRED is a human-reviewed structured
interpretation, not a COMAP official enum. Official presence provenance is separate
from system interpretation. required_level is unspecified, proficiency evidence is
empty and coverage is PARTIAL; no complete COMAP requirement-set claim is made.
Artifact counts are not frozen and further data may be independently reviewed.

P7.4 verified real Repository + real Requirement Provider + reviewed artifact +
synthetic validated StudentProfile / canonical Student Skill Evidence +
SkillGapContext + SkillGapEngine -> auditable SkillGapDecision. Known ADVANCED
student skill remains UNKNOWN because the threshold is unspecified; missing skill
retains both uncertainty reasons. Both overall results are UNDETERMINED with
PARTIAL coverage. These results, synthetic student fixtures and limited reviewed
data are intentional, not phase blockers. Closure baseline snapshot: full suite
1104 passed, 0 skipped; Ruff and diff check PASS. Counts are not lasting invariants.

### Closure and next-phase input

P7 Skill Gap scope is frozen. SkillRequirement / RequirementCoverage / unspecified
proficiency semantics, evidence fact binding, Context / Item / Decision, engine
aggregation, Provider exact lookup and JSON Provider missing semantics are frozen.
Future phases must not silently change P7 for Planner convenience. A real defect
requires a separate P7 reopening and independent Review.

P8 may consume SkillGapDecision: known per-item GAP under GAP_IDENTIFIED can be an
explicit learning need; UNKNOWN is an uncertainty / information-acquisition need,
not automatically a learning gap or satisfied capability. NO_GAP must not create
unsupported remedial tasks. Preserve PARTIAL coverage and unknown items even when
other items establish a gap. Do not reinterpret UNKNOWN as GAP or SATISFIED,
PARTIAL as COMPLETE, or REQUIRED as an Eligibility hard rule.

### Deferred items (not P7 blockers)

More competition requirements; full Skill taxonomy; cross-artifact Skill governance;
formal proficiency mapping policy and additional official threshold sources;
Huawei child-target/subtrack modeling; real Student data and profile ingestion;
Learning Resource mapping; Planner; Monitor / Event / Replanning; Agent / MCP / Frontend.

Next phase: P8 — Competition Planner. P8.1 Contract status is recorded below;
later planning stages do not change the frozen P7 semantics.

## MVP 1 — 决策与诊断验收关口

用一组可复核的学生画像和已审核种子赛事，经 Application/Tool 完成检索、资格检查、排序、技能差距与学习资源建议；核验硬规则可复现、候选隔离和所有关键结果的理由与证据。记录端到端场景测试结果及未覆盖风险。此关口不新增代码范围，也不要求 Web 或 Agent。

## P8 — Competition Planner

**Status: FROZEN.** P8 deterministic baseline planning scope is finished.
P8.1/P8.2/P8.3/P8.4 and P8 Final Review PASS. Delivered stages:

1. P8.1 Plan Domain Contract
2. P8.2 Deterministic Planning Inputs
3. P8.3 Baseline Plan Builder
4. P8.4 Real Integration
5. P8 Final Review

P8.1 evolves existing `domain/plan.py` CompetitionPlan and PlanMilestone instead
of creating replacements. Existing statuses/version/timestamps and milestone
fields remain; snapshots and collections are now immutable. Plan gains exact
optional track_id, optional TimeWindow planning_horizon, planning_needs and a
small SkillGapPlanningAudit (target/coverage/status/reasons). PlanningNeed has
only SKILL_IMPROVEMENT or UNCERTAINTY_RESOLUTION and retains the relevant validated
P7 SkillGapItem/evidence, not an entire duplicated SkillGapDecision.

Only a confirmed GAP item can justify improvement. UNKNOWN supports information
acquisition, never skill deficiency; coverage uncertainty uses an item-free need
with the explicit missing/partial reason. NO_GAP allows zero needs and milestones.
Milestone purpose derives from source_need_id and the referenced need; no duplicate
kind enum or priority policy. An absent source_need_id preserves general/manual
P1 milestones without asserting a P7-backed skill action. Unknown deadlines and
partial horizon bounds remain unknown; no deadline-selection/default policy.
Caller retains the source decision and supplies faithful audit/item projections;
target existence and Competition/Edition/Track parent checks belong to validated
input preparation. Contract checks exact source target agreement, unique IDs,
known need references, source status/reason consistency and explicit timing bounds.

`backend/tests/domain/test_planning_contract.py` covers synthetic contract semantics,
audit, immutable snapshots and serialization. Existing P1 plan tests reflect tuple
collections/new serialized fields; no P7 file changes. The P8.1 Contract performs
no mapping/building; the later stages below implement those capabilities.

P8.2 adds pure `domain/planning_inputs.py` PlanningInputDeriver and synthetic
`backend/tests/domain/test_planning_inputs.py`. derive accepts a validated P7
SkillGapDecision and returns an immutable tuple of PlanningNeed. GAP maps to
SKILL_IMPROVEMENT; UNKNOWN to UNCERTAINTY_RESOLUTION; SATISFIED to no item need.
Both uncertainty reasons stay in a single skill need; all relevant source facts,
requirement type and evidence are copied from the P7 item, not recreated.
PARTIAL/MISSING each append one separate requirement-set uncertainty need with
source_item=None and its existing coverage reason. COMPLETE adds no coverage need;
NO_GAP has no remediation need. Item order is preserved before the coverage need.
Stable IDs encode exact target/scope/skill/type without random/time/hash identity.
source_audit returns a faithful existing SkillGapPlanningAudit projection.
No Plan/Milestone, timing policy, content/strategy, score, LLM/network, resources,
Repository/Provider, P5/P6 logic or Replanning is implemented. P8.1 and P7 models
remain unchanged; real integration is documented in P8.4 below.

P8.3 adds pure `domain/baseline_plan_builder.py` BaselineCompetitionPlanBuilder:
target + PlanningNeed tuple + optional horizon + explicit student/creation metadata
+ supplied P8.2 audit -> CompetitionPlan. Nonempty needs require the source audit;
empty plans may omit it as allowed by P8.1. One need produces one unscheduled
milestone with a source_need_id and deterministic template, retaining type/scope,
input order, source facts and audit. All three need cases are represented without
learning content, resources, uncertainty strategy, timing or duration estimates.
Horizon bounds pass through; existing DRAFT/version 1 and PENDING defaults apply.
No priority scoring, P7 reinterpretation, P5/P6 logic, LLM/network, Agent,
Digital Twin or Replanning. Stable canonical SHA-256 IDs include machine facts,
ordered needs, horizon and explicit metadata, excluding evidence display prose;
milestone IDs are plan-scoped. Target/audit and canonical P8.2 need target mismatch
fail fast; real target existence/parent validation remains caller responsibility.
`backend/tests/domain/test_baseline_plan_builder.py` tests mixed/empty plans,
identity/input changes, timing pass-through, source links, validation and immutable
JSON snapshots. P8.1/P8.2/P7 contracts and real data are unchanged;
P8 baseline scope is finished; P11 adaptive planning is CLOSED / FROZEN below.

P8.4 adds `backend/tests/integration/test_p8_real_planning_integration.py` only,
with docs. Real COMAP MCM 2027 is loaded through Repository and reviewed
mathematical-modeling requirements through Provider. TEST-ONLY SYNTHETIC known
and missing student cases pass through actual SkillGapEngine, PlanningInputDeriver
and BaselineCompetitionPlanBuilder. Unknown threshold + PARTIAL coverage remains
visible end to end as skill and requirement-set uncertainty needs/milestones;
missing student adds a second reason in the same skill need. No fake improvement,
satisfaction, timing or study content is introduced. The integration dynamically
checks need/milestone counts without fixing total artifact count, preserves real
provenance and supplied student evidence, and checks serialization, stable IDs,
full-pipeline determinism, cross-case isolation, immutable/read-only inputs and
outputs, offline Seed/requirement-only reads and missing-target semantics.
No production/model/artifact or earlier-phase changes. No P5/P6 execution,
resources, priority/duration, LLM/Agent/MCP, Digital Twin/Event/Replanning.
P8.4 Review and P8 Final Review PASS. P8 status is FROZEN.

### P8 Closure and frozen capabilities

Frozen: Planning Domain Contract, exact Planning Target, PlanningNeed and its two
types, need scope (source_item present = SKILL; absent = REQUIREMENT_SET), reused
TimeWindow planning horizon, deterministic SkillGapDecision-to-Need mapping,
coverage uncertainty mapping, baseline builder, one Need -> one Milestone policy,
stable Need/Plan/Milestone IDs, timing non-invention and baseline service purity.
PlanningNeed answers why an action is needed, not how to learn or resolve it.
Milestones retain source_need_id and express only addressing confirmed improvement
or uncertainty. They do not prescribe courses, checks, contacts or learning steps.

P7 is the sole Skill Gap authority. P8 does not compare student/required levels or
recompute gap conclusions. GAP -> SKILL_IMPROVEMENT; UNKNOWN ->
UNCERTAINTY_RESOLUTION, never SKILL_IMPROVEMENT or SATISFIED; SATISFIED -> no
remediation need. PARTIAL/MISSING remain requirement-set uncertainty, distinct
from skill uncertainty and without fake skill IDs. COMPLETE itself adds no need.
Dual item uncertainty stays in one skill need with both machine-readable reasons.

Unknown, partial and full horizons are supported. No deadline selection, default
duration, milestone dates, effort estimate or equal time splitting occurs. Empty
needs allow zero milestones; no fake preparation is generated. P8 does not run
P5 or alter eligibility; REQUIRED skill is not a hard eligibility condition.
P8 does not score/rank/select competitions or alter P6. Selected target comes
from upstream. P1 LearningResource remains independent: no resource selection,
course/website/book/video recommendation, day/week plan, learning sequence,
practice workload, course ordering, priority or time allocation is implemented.
P8 is a deterministic planning core: LLM=NO, Agent=NO, Network=NO.

Current reviewed integration snapshot: comap-mcm / comap-mcm-2027 / track=None,
mathematical-modeling, REQUIRED human-reviewed structured interpretation,
required_level=None, coverage=PARTIAL. This is not an official REQUIRED enum or
complete COMAP requirement set. Synthetic validated Student A has a known level,
but unknown threshold still gives UNKNOWN/UNDETERMINED. Student B lacks the skill
and retains REQUIREMENT_PROFICIENCY_UNSPECIFIED + STUDENT_SKILL_DATA_MISSING.
Both result in skill and requirement-set uncertainty milestones, no improvement.
The integration fabricates no GAP, satisfaction, learning task, date or priority.
Artifact counts and competition coverage are not frozen; more independently
reviewed real inputs may be added. Closure-time snapshot: 1191 passed, 0 skipped,
Ruff/diff check PASS; test counts are not architectural invariants.

Runtime composition reads data/seed through Competition Repository and
data/skill_requirements through Requirement Provider. No Raw, Review Manifest,
Eligibility Policy, network or LLM is read by this P8 integration chain.
Frozen semantics and identities must not be silently changed by later phases.
A genuine defect requires explicit P8 reopening and independent Implementation /
Review. P9 and P12 must consume these results without reinterpreting need semantics.

### Deferred items (not P8 blockers)

More real requirement data; real Student ingestion; Learning Resource mapping /
resource recommendation; priority/deadline policy; duration estimation; detailed
action strategy / study plans; Digital Twin; Monitor; Event Engine; Impact Analysis;
Replanning / Plan Diff; Agent / MCP / Frontend. Limited real data, PARTIAL coverage,
unspecified thresholds and synthetic integration students are intentional inputs.

Next phase: P9 — Competition Digital Twin, followed by P9.5 Monitor,
P10 Event Engine, P11 Adaptive Replanning and P12 Agent. No future-stage capability
is implemented by this Closure.

## P9 — Competition Digital Twin

**Status: FROZEN.** P9 deterministic Digital Twin core is finished.
P9.1, P9.1.1, P9.2, P9.3 and P9.4 passed Review and are committed;
P9 Final Review PASS. Next: P9.5 — Competition Monitor.
P9 answers what changed in Competition/Edition/Track
dynamic state, using Snapshot/Diff/version concepts; it does not enhance
Planner, reinterpret P8 Needs/Plans, directly modify CompetitionPlan or Replan.
CompetitionPlan remains stable downstream state. Event -> Impact -> Replanning
belongs to P11; P10 owns Diff -> Event. Future P12 Agent handles intent, tool selection, multi-step
orchestration, clarification and explanation; it must not reimplement Eligibility,
Recommendation, Skill Gap or frozen Planning rules.

- **Goal:** 分离赛事静态知识与动态状态，并建立状态版本链。
- **Inputs:** 已审核赛事 identity、结构化动态观察事实及来源元数据；P1 CompetitionEvent 保留给 P10。
- **Main Deliverables:** 不可变 Snapshot、typed Diff 和可追溯观察版本；P9 Diff 不是 Event。
- **Files/Modules:** `backend/competition_copilot/domain/digital_twin.py` 定义纯 Domain Contract；`backend/tests/domain/test_digital_twin.py` 覆盖模型 invariant。
- **Tests Required:** 版本递增、快照不可变、Diff 准确、来源关联和静默覆盖拒绝测试。
- **Acceptance Criteria:** 观察版本及低层差异可追溯，不静默覆盖；后续接受动态状态变化时由 P10 关联 CompetitionEvent，保留 Snapshot / Diff / Event 完整审计链。
- **Explicitly Out of Scope:** 自动抓取、定时监控和自动重规划。

### P9.1 — Digital Twin Domain Contract (Review PASS, committed)

Only contracts and synthetic Domain tests are implemented. Generic
`CompetitionTarget` holds competition/edition IDs and optional track ID; existing
phase-specific requirement/planning targets are not reused or modified.
ID-only parent/existence validation belongs to P9.2.

`CompetitionSnapshot` requires explicit snapshot ID and aware observation time,
with typed `CompetitionDynamicState`: registration window, competition window
and complete edition track membership (stable sorted unique ID tuple).
Per-field observations distinguish KNOWN_VALUE, KNOWN_ABSENT and UNKNOWN.
Unknown != known absent; missing/null/source silence must map to UNKNOWN.
Known empty track membership differs from unknown membership. Known facts require
verified per-field SourceMetadata. Existing TimeWindow permits partial bounds;
missing endpoints remain unknown, not absent. Capture time is distinct from
observed competition/registration dates and must not precede source observation.

`SnapshotDiff` retains directed before/after ID/target/time references and typed
whole-window, window-endpoint and membership changes. Same target,
chronological references and unique changed fields are validated. P9.1.1 Contract
Follow-up passed Review and is committed: reflexive same-snapshot zero-change
comparison is valid only for identical reference metadata and empty changes.
The same ID with conflicting metadata or nonempty changes is invalid; distinct
snapshot IDs may still have empty changes. VALUE_CHANGED requires
different known values; PRESENCE_CHANGED requires known presence/absence;
transitions involving UNKNOWN are OBSERVATION_STATE_CHANGED, never fact addition
or deletion. A missing endpoint within a known partial window remains UNKNOWN;
endpoint discovery is also an observation change. Known set-to-set comparison
can later identify added/removed IDs;
unknown membership cannot assert either. Same dynamic state at different observed
times can have different snapshot IDs and an empty Diff.

Snapshots, references, observed facts and Diff collections are immutable and JSON
serializable. Snapshot ID generation is deferred to P9.2 canonical machine input;
no current-time or random defaults are present. No Repository access, comparison
algorithm, Network, LLM, Event, impact or Plan/Replanning capability is implemented.
P2–P8 remain frozen.

P9.2 implements baseline Snapshot creation; P9.3 implements Diff computation
below. P9 integration and Final Review passed; P9.5 Monitor implementation is
complete below. P10 Event interpretation is implemented below; P11 Replanning is CLOSED / FROZEN below. Text/rules semantic diff and additional
structured facts are deferred.

### P9.2 — Competition Snapshot Builder (Review PASS, committed)

`application/competition_snapshots.py` consumes only the P3
`CompetitionRepository` interface and P9.1 Domain Contract. The caller supplies
an edition-level target and explicit timezone-aware `observed_at`. Repository
not-found errors remain target errors; an edition with a different competition ID
fails fast. Track-level building is deferred because current `CompetitionTrack`
has no independent structured dynamic facts. The P9.1 track target remains valid
for later independently observed track state.

The builder maps non-null Edition registration/competition `TimeWindow` values to
KNOWN_VALUE, including partial windows; `None` maps to UNKNOWN, never
KNOWN_ABSENT. P3 `list_tracks(edition_id)` is a complete child query: an empty
result maps to KNOWN_VALUE(empty tuple), not UNKNOWN. Membership uses only stable
track IDs; the P9.1 Contract sorts them and rejects duplicates. Known window
facts retain verified Edition `SourceMetadata`. Known membership retains verified
Edition and Track sources; missing/unverified provenance causes an explicit
error, never a fabricated source. Source `observed_at` is preserved separately
from the caller's snapshot time. There is no repository representation of an
explicitly absent window, so the builder does not emit KNOWN_ABSENT.

The snapshot ID uses SHA-256 over canonical machine target, UTC observation time
and typed dynamic state JSON (including actual source metadata). Equal inputs
produce equal IDs/JSON; a changed observation time or dynamic state changes ID.
Names/descriptions and other static display fields are excluded. Builder output
is immutable and JSON serializable; Repository inputs remain unchanged.
Synthetic Application tests and a read-only real Seed Repository smoke test
cover COMAP MCM 2027 and a verified zero-track Edition without freezing global
dataset counts.

P9.2 is a repository-backed baseline observation. Production code does not read
Seed files directly, use Network/LLM/Agent/MCP, choose status/deadlines, compare
snapshots, generate Diff/Event, monitor sources or replan. P9 integration passed;
P9.5 Monitor and P10 Event interpretation are implemented below; P11 Replanning is CLOSED / FROZEN below. P9 is FROZEN.

### P9.3 — Deterministic Snapshot Diff (Review PASS, committed)

`domain/snapshot_diff_engine.py` provides the pure `SnapshotDiffEngine.compare`
service, consuming only two validated CompetitionSnapshots. P9.1/P9.1.1 and
P9.2 production contracts are unchanged. Same target and chronological references
are required. Same exact snapshot returns a valid zero-change Diff; same ID with
inconsistent metadata or content is rejected. Distinct snapshots with the same
fact state also produce empty changes; capture time, ID and provenance-only
differences are not competition fact changes. Provenance-change diff is deferred.

UNKNOWN -> known value/absence and known -> UNKNOWN use OBSERVATION_STATE_CHANGED;
known value <-> explicitly absent uses PRESENCE_CHANGED. Whole-window observation
transitions produce only a whole-field record. Two known windows compare start/end
individually: missing boundaries become unknown endpoint observations, known
datetime changes use VALUE_CHANGED. There is no earlier/later business meaning.

Two known track sets use one frozen TrackMembershipChange VALUE_CHANGED record
with canonical before/after IDs, preserving exactly which members were added or
removed. No per-member enum or duplicate field records are added. Unknown ->
known tracks and known tracks -> UNKNOWN produce one observation change, never
member additions/removals. Known empty sets retain their distinct semantics.
Order is registration start/end (or whole field), competition start/end (or whole
field), then membership. Outputs are immutable, audit-preserving and JSON stable.
SnapshotDiff has no diff_id field; identity remains its directed references.

Diff is low-level structural change only: Diff != Event, Diff != Impact and
Diff != Replanning. No Repository/Builder, Network, Monitor, LLM, Agent, MCP,
planning or business impact is used. P9.4 integration is described below;
P9 Final Review PASS and P9 is FROZEN.

### P9.4 — Real Digital Twin Integration (Review PASS, committed)

`tests/integration/test_p9_real_digital_twin_integration.py` exercises real
Verified Seed -> JsonSeedCompetitionRepository -> Snapshot Builder -> baseline
Snapshot -> SnapshotDiffEngine. COMAP MCM 2027 is the explicit baseline fixture;
Huawei ICT 2026 supplies known nonempty membership. Fixed aware times keep the
pipeline deterministic. Real same-state observations at two times have different
snapshot IDs and zero Diff; a real snapshot compared with itself also has zero Diff.

Later modified observations are explicitly TEST-ONLY CONTROLLED fixtures, not
official historical updates or live monitoring. Window/membership observation
loss yields observation-state changes, not fact/member removal. Optional known
window-value and membership modifications use verified manual test-fixture
metadata at example.invalid, never rewritten official provenance. Controlled IDs
are fixed test-case references tied to the baseline ID, not a second production
identity algorithm. Tests also cover known empty versus unknown membership,
reverse time, cross-target rejection, audit preservation and JSON/immutability.
Network and non-Seed data access are blocked; Repository/data remain read-only.
Production code and frozen phases are unchanged. P9 can represent, build and
compare structured observations. Source observation/Monitor is implemented in
P9.5 below; P10 Event and P11 impact/Replanning are CLOSED / FROZEN below. P9 Final Review
PASS; P9 is FROZEN.

### P9 Closure — FROZEN

P9 freezes the typed CompetitionSnapshot, SnapshotReference, target, dynamic
state and per-field provenance contracts; ObservationState KNOWN_VALUE,
KNOWN_ABSENT and UNKNOWN; and UNKNOWN != KNOWN_ABSENT. P9.1.1 freezes identical
reference + empty changes as valid; same ID with conflicting metadata or same
snapshot with nonempty changes is invalid. Distinct observations of equal state
also yield zero Diff; observed_at alone is not a factual change.

P9.2 freezes Repository None -> UNKNOWN, never KNOWN_ABSENT; known [] tracks ->
known empty immutable set; explicit aware snapshot observed_at separate from
source observed_at; deterministic machine-based Snapshot identity; and read-only
Repository baseline construction. Whole-field UNKNOWN differs from a known
partial TimeWindow: missing start/end boundaries are endpoint uncertainty.
Known empty membership differs from UNKNOWN; only known/known sets support
member add/remove. Track-level building remains deferred without independent facts.

P9.3 freezes knowledge-state versus fact-state transitions, whole-window versus
endpoint changes, canonical field identity and deterministic change order.
UNKNOWN -> known means observation gained; known -> UNKNOWN means observation
lost. Different known values mean structured VALUE_CHANGED. Known tracks ->
UNKNOWN never means all removed; UNKNOWN -> known tracks never means all added.
SnapshotDiff is low-level only, without Event/impact/urgency/notification/replan
semantics. P9.4 completed the real Seed -> Repository -> Builder -> Snapshot ->
Diff chain with explicitly test-only later fixtures, not official historical updates.
Real provenance is preserved; P9 neither verifies websites nor fabricates sources
or changes verification status. No Network, Monitor, LLM, Agent or planning runs.

These semantics and implementation contracts are frozen. Future defects require
explicitly reopening P9, then separate Implementation -> Review -> commit.
Closure-time validation snapshot: 1335 passed, 0 skipped; Ruff and diff check PASS.
This test count is not a permanent invariant.

Deferred at P9 closure (Monitor/source fetch subsequently implemented in P9.5):
live source monitoring, HTTP/crawler, scheduler/periodic polling,
content freshness policy, retry/backoff, semantic rule-text diff, provenance-only
diff, CompetitionEvent, Impact Analysis, notification, Adaptive Replanning,
Agent, MCP and Frontend. These do not block P9 closure.

## P9.5 — Competition Monitor

**Status: CLOSED / FROZEN. P9.5.1–P9.5.4 COMPLETED / Review PASS / committed; P9.5 Final Review PASS — READY TO CLOSE.**
The documentation consistency follow-up resolved the previous blocker; Final
Review re-run passed. This Closure freezes the deterministic one-shot Monitor
core. P10 followed Closure; its completed implementation status is recorded below.
Monitor observes official sources, produces
structured observations and new P9 Snapshots. It must reuse frozen Snapshot,
UNKNOWN/KNOWN_ABSENT, identity and Diff semantics. Event interpretation belongs
to P10; impact and Adaptive Replanning belong to P11.

The implemented core is one-shot and deterministic:

```text
Approved Official Source -> Official Source Observation Adapter
-> SourceObservationResult -> One-shot Monitor -> CompetitionSnapshot
-> P9 Snapshot Diff Engine -> SnapshotDiff -> MonitorCheckResult
```

Completed capabilities: stable Monitor Contract; explicit aware times and
auditable provenance; source failure distinct from successful UNKNOWN observation;
failure produces no authoritative Snapshot and no Diff; successful UNKNOWN is
supported; KNOWN_ABSENT is never inferred from missing data/failure. Same state
is SUCCESS + zero Diff; changed state is SUCCESS + low-level Diff. One concrete
official Adapter uses deterministic parsing and approved URLs only, with no LLM.
Real component integration passes offline; Repository remains read-only; no Event
or Replanning is generated. Frozen P9 semantics are unchanged.

SnapshotDiff is a low-level structured state change; MonitorCheckResult describes
one check. Neither is CompetitionEvent. P10 consumes existing P9/P9.5 SnapshotDiff
plus necessary target/source context; it does not re-fetch websites, reconstruct
Snapshots or recompute Diff. P11 consumes Events for impact/Adaptive Replanning.

Scheduler and polling loop are NOT IMPLEMENTED and NOT P9.5 EXIT BLOCKERS.
Future scheduler -> invoke the one-shot Monitor; execution policy must preserve
Monitor semantics. Deferred: second competition adapter, multi-source monitor,
periodic scheduler/polling, distributed jobs, retry/backoff runtime policy,
monitor rate limiting policy, Snapshot history persistence, notification, Impact
Analysis/Adaptive Replanning (P11), Agent, MCP and Frontend. P10 CompetitionEvent
interpretation is implemented below and remains outside the P9.5 Monitor boundary.

### P9.5 Closure — Frozen Scope

- Monitor Request target/context, explicit aware observation time, check outcome,
  SourceObservationResult, MonitorCheckResult, typed errors and provenance are frozen.
- FETCH_FAILED, PARSE_FAILED and SOURCE_UNAVAILABLE are check failures, not successful
  UNKNOWN observations. Whole check failure produces no authoritative new Snapshot
  and no SnapshotDiff. Successful observations may contain UNKNOWN tracked facts.
- Missing selector/empty field/timeout/404/parse failure never imply KNOWN_ABSENT;
  confirmed absence remains an explicit sourced assertion under frozen P9.
- One call performs one source observation, then optional current Snapshot/Diff and
  MonitorCheckResult. Success with a baseline and unchanged state returns a valid
  Snapshot plus zero Diff; no change is not failure. Changed state returns low-level
  Diff only. Initial success without baseline has no Diff; failure has neither output.
- The source interface/concrete Adapter returns typed structured observation only;
  it performs no Snapshot comparison, Event interpretation, impact or Replanning.
- Approved fixed official URL/host only, no arbitrary URL fetch, redirects rejected,
  no secrets. Network failure maps to typed failure. Same body/target/explicit time
  yields the same result; no LLM parsing, invented clock times or guessed timezones.
  Temporal policy, source provenance and verification status behavior are frozen:
  HTTP success does not grant verification. Monitor never auto-approves/verifies data.
- Repository/data are read-only. P9 Snapshot, ObservationState, identity, SnapshotDiff
  and formal Diff Engine are reused; no Monitor-specific Snapshot/Diff semantics.
- P9.5.4 proved the real Repository/Builder + concrete Adapter + one-shot Monitor +
  formal Diff chain with fixture HTTP transport. Default tests are offline and
  deterministic; controlled fixtures are not official historical updates. No live
  smoke was added; future smoke must be optional/manual, outside default pytest/CI.
- Scheduler/polling loop is absent; future triggers only invoke the one-shot Monitor
  and preserve its semantics. Snapshot history persistence is absent; future storage
  requires a separate storage/Repository contract, not Monitor Domain fields.
- SnapshotDiff and MonitorCheckResult are not CompetitionEvent. P10 owns Diff ->
  business Event; P11 owns impact/affected scope/authorized revision, PlanDiff,
  milestone updates and Adaptive Replanning. P9.5 has no notification, LLM or Agent.

These semantics are FROZEN. Defects require explicit P9.5 reopening and separate
Implementation -> Review -> commit; Closure does not change production code/tests/data.
Deferred also includes multi-source merge and distributed monitor jobs. Closure-time
validation: 1434 passed, 0 skipped; Ruff/diff check PASS (not a permanent count gate).

### P9.5.1 — Monitor Contract (Review PASS, committed)

`domain/monitoring.py` defines immutable MonitorCheckRequest, SourceObservationResult,
SourceCheckError and MonitorCheckResult. `application/monitoring.py` exposes the
sync execution-model-neutral CompetitionObservationSource Protocol; it has only
`observe(request)`, without Repository writes, transport or scheduling methods.
P9 Target, typed dynamic state, Snapshot/Reference/Diff and SourceMetadata are
reused; P2 source approval is separate from operational source-check outcome.

Request supplies target, explicit aware observed_at, configured source metadata
and optional previous Snapshot. One timestamp suffices; no start/end lifecycle
or clock defaults are added. CHECK_SUCCEEDED requires typed state and no error;
CHECK_FAILED requires a machine-coded error and forbids state. Failure != UNKNOWN
facts. Successful observation may contain UNKNOWN, including all fields unknown.
KNOWN_ABSENT remains an explicit sourced assertion under P9, never inferred from
missing data, selector failure, timeout or HTTP status. FETCH_FAILED, PARSE_FAILED,
SOURCE_UNAVAILABLE and INVALID_OBSERVATION are operational errors, not events.

The single-source observation binds fact sources to declared URL/type/verification
policy. A result must match request target/time/source policy; HTTP success cannot
upgrade verification. Known facts still satisfy frozen P9 provenance validation.
MonitorCheckResult retains request/observation audit without duplicate outcome
fields: outcome derives from observation. Success requires the supplied matching
Snapshot and, when baseline exists, a Diff with matching references. Initial checks
have no Diff; failed checks have neither new Snapshot nor Diff. Zero-change and
reflexive Diff are successful checks. These validators do not build or compare.

P9.5.2 orchestration and P9.5.3 source adapter are described below. The Contract
adds no network/HTTP parsing, retry/timeout, scheduler/poll loop, Repository
mutation, Event, notification, impact, Replanning or LLM/Agent/MCP.
P9 and P2–P8 remain frozen; P9.5 is CLOSED / FROZEN.

### P9.5.2 — One-shot Competition Monitor (Review PASS, committed)

`application/monitor_checks.py` provides OneShotCompetitionMonitor.check(request).
It calls the injected CompetitionObservationSource exactly once and validates
the typed result. Source failure returns MonitorCheckResult with the original
error, no new Snapshot and no Diff. Successful observation is bound to request
target/time/source policy before Snapshot construction; contract violations raise.
Success may contain partial or fully UNKNOWN state, without being fetch failure.

The current Snapshot uses the public P9 validated constructor and the existing
pure P9.2 `_snapshot_id` helper to preserve canonical identity. No Repository
builder/query is invoked and no ID algorithm is duplicated or modified. Snapshot
time/provenance come from the successful observation, not from baseline metadata.
The formal P9.3 Diff Engine performs all fact comparison. Same-state success
returns zero Diff; changed state returns typed low-level Diff; same exact identity
also follows P9.1.1 zero-diff semantics. Initial checks without baseline have no Diff.

Only deterministic fake-source tests are used. They verify failure never constructs
Snapshot/ID or calls Diff, success/UNKNOWN/known-value/track cases, binding safety,
provenance, one-call behavior, deterministic JSON and immutability. No Repository
writes, persistence, retry, scheduler, loop, HTTP/parser, Event, notification,
impact, Replanning, LLM/Agent/MCP is added. P9/P9.5.1 remain unchanged.
P9.5.3 source adapter is described below; P9.5 is CLOSED / FROZEN.

### P9.5.3 — Official Source Observation Adapter (Review PASS, committed)

Candidate audit used reviewed Repository Edition.source, not remembered/search URLs:

| Target | Approved URL/host | Available reviewed dynamic scope |
| --- | --- | --- |
| comap-mcm / comap-mcm-2027 | contest.comap.com/undergraduate/contests/mcm/instructions.php | Partial registration and full contest window; source-explicit EST |
| c4-big-data-challenge / c4-big-data-challenge-2026 | nercbds.tsinghua.edu.cn/bdc/szsm.html | Registration window; reviewed jurisdiction policy needed |
| china-graduate-math-modeling / china-graduate-math-modeling-2026 | cpipc.acge.org.cn/cw/contestNews/detail/4/2c9080189dcfa24e019dddacc24a1314 | Registration/contest windows; notification text and jurisdiction policy |
| huawei-ict / huawei-ict-2026 | e.huawei.com/cn/talent/ict-academy/#/ict-contest?compId=85132018 | Known tracks; reviewed windows remain unknown; fragment-based source route |

COMAP was selected: its approved official instructions expose a bounded 2027
dates-and-times list with explicit EST, matching the reviewed fixed UTC-05:00
policy. `infrastructure/comap_observation.py` implements CompetitionObservationSource
for exactly comap-mcm-2027, track=None, and the exact HTTPS URL. An injected
ComapPageFetcher separates HTTP from deterministic parsing. The default stdlib
fetcher performs one bounded HTTPS read with redirects/proxies disabled; no URL
argument, secrets, retry or third-party dependency is introduced.

Parser recognizes the instructions title and exact schedule heading/list, then
parses only Registration Deadline, Contest Starts and Contest Ends. Registration
start and track inventory are unsupported/UNKNOWN; problem labels are not tracks.
Missing optional facts, date-only facts and omitted/unreviewed zones remain UNKNOWN.
Malformed/wrong-year/root/duplicate/unsupported labeled structures fail parsing.
EST clocks are source-explicit fixed UTC-05:00, never guessed DST/jurisdiction.
HTTP failure yields typed check failure, not unknown facts or known absence.
Provenance uses supplied check time and preserves configured verification status;
unverified known facts fail INVALID_OBSERVATION, without verification upgrade.

Offline tests use a minimal synthetic HTML fragment whose DOM shape/date facts
match the audited source/reviewed Seed. Tests block network and cover parser,
HTTP failures, date/zone/absence safety, unsupported target/URL, redirects, bounded
responses, provenance and deterministic JSON. No default live smoke test is added.
No Snapshot/Diff/Monitor result construction, Repository write, universal crawler,
scheduler, Event/impact/Replanning or LLM parsing is added. Frozen P9/P9.5.1/P9.5.2
remain unchanged. P9.5.4 integration is described below; P9.5 Final Review PASS.

### P9.5.4 — Real Competition Monitor Integration (COMPLETED, Review PASS, committed)

Offline integration tests use the real Repository/Builder for COMAP MCM 2027,
the concrete official Adapter with fixture-only HTTP transport, OneShot Monitor
and its formal P9 Diff Engine. No Fake ObservationSource or duplicated parser/
Monitor logic is used; production code and real data remain unchanged.

The real known-empty track baseline differs from the Adapter's UNKNOWN track
coverage. First check must report observation-state loss, never track removal.
Case A uses the first production Monitor output as the next baseline for repeated
same-fixture success + zero Diff. This is explicitly a controlled offline state
case, not a live no-change claim. Further cases cover successful missing optional
window, controlled boundary VALUE_CHANGED, timeout/connection failure, parse
failure, unsupported real target, reverse time and deterministic immutable JSON.
Track changes are NOT_APPLICABLE; the Adapter scope is not expanded.

Source failures return no Snapshot/Diff; successful observations return both.
Real baseline provenance is preserved and fixture observation source mapping
retains verification policy without automatic upgrade. Fixtures are test-only,
not official historical evidence. Default tests block network and protect data
from writes. Optional manual live smoke is not added and is never a required CI
path. No persistence, scheduler/polling, Event, impact, notification, Replanning,
LLM or Agent. P9/P9.5.1/P9.5.2/P9.5.3 and earlier phases remain frozen.
P9.5 Final Review PASS; P9.5 is CLOSED / FROZEN. NEXT: P10 Event Engine.

- **Goal:** 一次显式调用完成确定性来源观察、Snapshot/Diff 和 MonitorCheckResult。
- **Inputs:** 稳定 target、批准 source metadata、显式 aware observed_at、可选 previous Snapshot。
- **Main Deliverables:** Monitor Contract、one-shot Monitor、一个 concrete official Adapter、offline real-component integration；输出 SourceObservationResult、Snapshot、SnapshotDiff、MonitorCheckResult。
- **Files/Modules:** `backend/competition_copilot/domain/monitoring.py`、`application/monitoring.py`、`application/monitor_checks.py`、`infrastructure/comap_observation.py` 及对应测试。
- **Tests Required:** 成功/失败/UNKNOWN、zero/change Diff、target/time/provenance、安全和确定性集成测试。
- **Acceptance Criteria:** Source failure 不生成 Snapshot/Diff；成功观察遵循 frozen P9 semantics；不修改 Repository/data；无变化也是成功；低层 Diff 不生成 Event。
- **Explicitly Out of Scope:** scheduler/polling、持久化、通用爬虫、自动入库、CompetitionEvent（P10）、Impact/Replanning（P11）。

## P10 — Competition Event Engine

- **Status:** CLOSED / FROZEN. P10.1–P10.4 COMPLETE / REVIEW PASS / COMMITTED.
  Documentation follow-up Review PASS; P10 Final Review re-run PASS. Closure freezes
  the reviewed Event Engine semantics. P11 — Adaptive Replanning follows;
  its current P11.1 Contract implementation status is recorded below.
- **Goal:** SnapshotDiff → primitive CompetitionEvent[] → canonical CompetitionEvent[]。
- **Inputs:** P9/P9.5 已产生的 validated SnapshotDiff、必要 target/source context 和显式 aware detection time；不重新抓网页、构造 Snapshot 或计算 Diff。
- **Main Deliverables:** 受控演进的 Event Contract、确定性 primitive mapping、batch-local canonical aggregation/dedup、完整 lineage 和 offline real-component integration。
- **Files/Modules:** `backend/competition_copilot/domain/event.py`、`event_engine.py`、`event_aggregation.py`，对应 domain tests 和 `backend/tests/integration/test_p10_real_event_integration.py`。
- **Tests Required:** registration/competition window、track membership、observation coverage、zero Diff、fact/observation separation、aggregation/dedup、target/source-Diff separation、time/identity/lineage、顺序无关性和失败集成测试。
- **Acceptance Criteria:** P10.2 one low-level change → one primitive Event；P10.3 related primitives → canonical Events；identity deterministic、lineage complete，dedup 仅在 supplied batch 内。
- **Explicitly Out of Scope:** subscription/notification/delivery、EventRepository/history persistence、cross-run suppression、severity/Impact/Replanning、Agent/LLM。

Current generated EventTypes are REGISTRATION_WINDOW_CHANGED,
COMPETITION_WINDOW_CHANGED, TRACK_MEMBERSHIP_CHANGED and OBSERVATION_COVERAGE_CHANGED.
Legacy material/rule Event enums remain compatibility-only, not current mapping scope
or exit requirements. Future factual expansion must first evolve the corresponding
Snapshot/Diff Contract, then separately extend Event mapping; P10 cannot exceed P9 authority.

Subscription = NOT IMPLEMENTED; Notification = NOT IMPLEMENTED. Neither is a P10
exit blocker. Deferred: EventRepository, event history persistence, cross-run duplicate
suppression, subscription, notification, severity, Impact Analysis, plan impact,
Adaptive Replanning (P11), Agent, MCP and Frontend.

SnapshotDiff changes=() → primitive Events=() → canonical Events=(); no NO_CHANGE_EVENT
or heartbeat. FACT CHANGE produces factual Events; knowledge changes produce
OBSERVATION_COVERAGE_CHANGED. KNOWN → UNKNOWN is coverage loss, not fact removal.
Aggregation requires the same target, full source Diff, EventType/category and canonical
field family. Unique source changes remain auditable through Diff and before/after
Snapshot references. Identity uses canonical lineage, never random UUID, Python hash,
wall-clock-only identity or human summary. Time is observation/detection context,
not an unproven business occurrence time. Event != Diff; Event != Impact/Replanning.

NEXT: P11 — Adaptive Replanning. Its inputs are canonical CompetitionEvent,
StudentProfile, existing CompetitionPlan and necessary planning context. P11 must not
refetch sources, rebuild Snapshots, recompute Diff or regenerate Events. P11.1 Contract status is below.

### P10.1 — Competition Event Domain Contract (Review PASS, committed)

Audit found `domain/event.py` CompetitionEvent with P1 id, competition_id,
edition_id, event_type, optional occurred_at, required aware observed_at/source,
optional description. It had eight legacy types, mutable Event objects and no
Diff lineage. References were only `test_event.py` and the P1 planning-model
integration test; no production consumer or Event Engine was found.

Controlled evolution reuses that model, adding registration_window_changed,
competition_window_changed, track_membership_changed and
observation_coverage_changed. Legacy enums/construction/JSON shape are retained
for historical records, not generated by current P10. New Event objects are frozen;
assignment/model_copy(update=...) is deliberately unsupported. No current consumer
mutated Events. No parallel Event model or severity/impact/student/workflow is added.

Stable target reuses P9 CompetitionTarget via existing IDs plus optional track_id.
P10 types require source_diff (validated SnapshotDiff) and nonempty unique canonical
source_change_fields. P9 has no diff_id/change_id: embedded directed references and
selected typed changes provide auditable lineage without changing P9. Full Diff
provenance is retained; compatibility source must equal one source in selected
changes. EventCategory is derived: factual types FACT_CHANGE, coverage type
OBSERVATION_CHANGE, legacy types unclassified. Validators reject mismatched
target/type/field/kind, empty lineage or fabricated source. They validate supplied
events; they do not map a Diff to events or aggregate changes.

One supplied event can select multiple canonical changes, including window start/end.
Collections are immutable and ordered window/start/end/membership. P10 identity is
SHA256 over event type, directed Snapshot references/target and selected typed changes
with UTC canonical instants; detection time and display description are excluded.
`competition_event_identity` is a pure Contract identity primitive, not an Event
Engine or dedup service. Supplied P10 id must match it. observed_at means explicit
aware detection time >= after observation; occurred_at must be None for P10 because
Diff cannot establish business effective time. Legacy time meanings remain intact.

P9/P9.5 produce SnapshotDiff; P10 interprets it as business CompetitionEvent;
Event != Diff != Impact/Replanning. P10.1 only defines Contract. Offline tests cover
legacy compatibility, four types, presence/knowledge separation, multiple selected
changes, identity/time/provenance safety, immutability and stable JSON. Frozen P9,
P9.5 and P2–P8 code/tests are unchanged. P10.2 mapping is described below;
P10.3 batch aggregation/dedup is described below; no Repository/network/LLM/Agent or P11
logic is added by the Contract.

### P10.2 — Deterministic Diff to Event Engine (Review PASS, committed)

`domain/event_engine.py` CompetitionEventEngine.interpret(source_diff,
detected_at=<explicit aware datetime>) is a pure Domain Service. Input is validated
SnapshotDiff only; output is immutable tuple[CompetitionEvent, ...]. It never
recomputes Diff, reads Repository/Monitor or fetches sources. Zero Diff -> zero Events.

Exact canonical field mapping uses P9's actual start_at/end_at paths. VALUE_CHANGED
and PRESENCE_CHANGED map registration fields -> REGISTRATION_WINDOW_CHANGED,
competition fields -> COMPETITION_WINDOW_CHANGED, membership -> TRACK_MEMBERSHIP_CHANGED.
OBSERVATION_STATE_CHANGED always maps OBSERVATION_COVERAGE_CHANGED, including
partial endpoints, UNKNOWN <-> known sets and UNKNOWN <-> known absence. No false
fact addition/removal. Unrecognized field/kind fails; frozen P9 currently prevents
such values at construction. Iteration follows fixed P9 window/start/end/membership
order, also normalizing manually supplied unordered valid changes without mutation.

One low-level change -> one Event. Two registration boundaries produce two events
with the same type but distinct deterministic IDs/selected fields; no cross-change
grouping. Event reuses full input Diff and exactly one source_change_fields entry,
P10.1 identity helper/validated constructor/target. Representative source is the
first after source, otherwise first before source; all evidence remains in Diff.
No new provenance or verification claim. detected_at cannot precede after observation;
occurred_at remains None. No system clock. P10.1 excludes detection time from ID.

Tests cover zero/reflexive Diff, factual window/membership/presence transitions,
knowledge transitions, lineage, ordering, identity, time, immutable input/output
and JSON. Frozen P10.1/P9/P9.5/P2–P8 code/tests are unchanged. No aggregation,
cross-call duplicate suppression, Repository/persistence, network, severity,
impact, notification, Replanning, LLM or Agent is added by this primitive Engine.
P10.3 normalization is described below; P10 is CLOSED / FROZEN after Final Review PASS.

### P10.3 — Event Aggregation / Canonical Dedup (Review PASS, committed)

`domain/event_aggregation.py` CompetitionEventAggregator.normalize(events) is a
pure stateless Domain Service: immutable P10 Event tuple -> immutable canonical
Event tuple. P10.2 remains one low-level change -> one primitive Event; P10.3
groups related Events without remapping ChangeKind/EventType or recalculating Diff.
Empty input returns empty; a single Event preserves its semantics/identity/time.
Already canonical single-family P10 Events are also supported for normalization.

Key: stable target + full canonical source Diff lineage + EventType + exact
top-level field family. Registration and competition start/end merge within their
family. Observation coverage merges within a family only; registration versus
membership coverage stays separate, as do fact/observation types, targets and
different Diffs/cycles. P9 carries track addition/removal together in one immutable
membership before/after record and rejects duplicate field records. The track
test preserves both set differences in one Event, not two invented source changes.

Exact batch duplicates collapse; same ID with different content is rejected.
Generated canonical ID conflicts across distinct groups are also rejected.
Overlapping selected lineage is unioned uniquely in P10.1 canonical field order.
Differing detection times within a group are rejected, never resolved by min/max.
Equivalent aware instants normalize to UTC representation without changing meaning
or inputs. Output orders target, directed Diff times/references/full lineage,
registration/competition/membership family, FACT_CHANGE before OBSERVATION_CHANGE,
then type. Human text and random IDs never determine grouping or output order.

Aggregated IDs reuse P10.1 identity over all selected fields; start-only and
start+end differ. Representative display/source metadata comes from the member
with earliest canonical selected-field tuple, while all evidence remains in Diff.
No new provenance/verification claims. Mixed-family input Events are rejected;
normalization does not split/reinterpret them. Legacy P1 Events are not inputs.

Tests cover grouping/separation, duplicates/overlap/conflicts, permutations,
determinism, metadata, immutable inputs/outputs and JSON. P10.1/P10.2/P9/P9.5 and
earlier code/tests stay frozen. Dedup is supplied-batch only; repeated calls still
return canonical Events. No EventRepository, history/persistence, cross-run
suppression, network, severity, impact, notification, Replanning, LLM or Agent.
P10.4 real Monitor Diff -> primitive -> canonical integration is described below;
P10 implementation is complete and CLOSED / FROZEN.

### P10.4 — Real Competition Event Integration (COMPLETE, Review PASS, committed)

`tests/integration/test_p10_real_event_integration.py` composes actual production
Repository -> SnapshotBuilder -> concrete COMAP Adapter -> OneShot Monitor -> P9
Diff -> P10.2 primitive Events -> P10.3 canonical Events. Only HTTP transport/body
is replaced with the approved minimal synthetic fixture and controlled variants.
No manual baseline, Diff, Monitor result, Event mapping/grouping or lineage is
used as integration authority. Default tests block network/DNS and guard read-only
Seed access. Controlled fixtures are not official historical/current website claims.

Real baseline has known-empty tracks; Adapter has UNKNOWN track coverage. First
check retains that observation change. A second same-fixture check uses the actual
Monitor output as previous observation and proves SUCCESS + zero Diff -> zero
primitive/canonical Events. The real baseline is never altered to force zero Diff.
Registration start+end and factual track cases are NOT_APPLICABLE: frozen Adapter
supports registration end only and no track inventory. Additional registration
end-only test verifies its supported fact event. Competition start+end fixture
proves two low-level changes -> two primitive -> one canonical Event with both
source changes. Adapter scope is not expanded.

Successful missing registration produces observation coverage, not factual removal.
Registration/track coverage from real baseline remains two separate canonical
Events. Fetch/parse failures return no Snapshot/Diff and stop before P10 calls,
with no Events. Repeated complete chains verify IDs/order/JSON and unchanged
Repository/Snapshot inputs; reversed primitive order gives identical canonical
output. Tests audit stable target, before/after references, selected typed changes,
source provenance, explicit aware detection time, immutability and serialization.

Production code and frozen P10.1/P10.2/P10.3/P9/P9.5/P2–P8 tests/data are unchanged.
No live smoke/network, Event persistence, stateful dedup, severity/impact, student/
plan dependency, notification, Replanning, scheduler, LLM or Agent. P10 Final
Review re-run passed after documentation follow-up; all 19 exit criteria PASS.
P10 is CLOSED / FROZEN. Closure changes documentation only.

### P10 Closure — Frozen Scope

Frozen: CompetitionEvent / CompetitionEventType, stable target, source Diff and
source change lineage, explicit aware detection time, deterministic identity,
immutability and stable serialization. Generated scope is the four current types
above; eligibility rules, awards, quota, judging, mentor rules and material/rule
changes are not supported structured Diff/Event facts.

Frozen processing: FACT CHANGE → factual Event; observation/knowledge change →
OBSERVATION_COVERAGE_CHANGED, never factual removal. Zero Diff → zero Events.
P10.2 one change → one primitive Event; P10.3 groups by same target, full source
Diff, EventType/category and canonical field family. Different targets, Diffs,
families and fact/observation Events never merge. Dedup is stateless/batch-local
only; time conflicts and same-ID content conflicts reject. Canonical ordering,
all unique source change lineage and lineage-sensitive deterministic identity
are frozen. No random UUID, Python hash, wall-clock or human text identity.
Event time is approved detection/observation context, not actual business occurrence.

Canonical Event → source SnapshotDiff → selected low-level Changes → before/after
Snapshot references is auditable. P10 consumes Diff only; no official-source fetch,
Snapshot construction or Diff recalculation. Events are competition-level and
student-independent; no severity/risk, affected student/plan or Impact semantics.
Event != Impact; Event != Replanning. P10 never mutates CompetitionPlan, generates
PlanDiff or triggers Planner. No EventRepository/DB/history persistence or cross-run
suppression; future storage needs independent design. No notification, Network,
LLM or Agent. P9/P9.5 and earlier Contracts remain frozen.

Future P10 defects require explicit reopen P10 → Implementation → Review → commit.
Closure validation: 1536 passed, 0 skipped; Ruff/diff check PASS (a closure-time record).

```text
Official Source -> P9.5 Monitor -> CompetitionSnapshot -> P9 SnapshotDiff
-> P10.2 Primitive Events -> P10.3 Canonical Events (CompetitionEvent)
-> P11 Impact / Replanning
```

Deferred: Event persistence, EventRepository, cross-run dedup, subscription,
notification, severity, Impact Analysis, plan impact, Adaptive Replanning (P11),
Agent, MCP and Frontend. P11 consumes Events + StudentProfile + existing
CompetitionPlan + necessary planning context and produce Impact Analysis,
Affected Plan scope, Replanning Decision and Plan Diff. P11 must not fetch sources,
rebuild Snapshots, recalculate Diff or regenerate Events; P11.1 Contract status is below.

## P11 — Adaptive Replanning

- **Goal:** 根据赛事事件评估影响并生成可审计的个人计划差异。
- **Status:** CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE. All P11 subphases are CLOSED / FROZEN; P12 is CLOSED_FROZEN; Final Review is REVIEW_PASS; Closure is CLOSED_FROZEN.
- **Inputs:** canonical CompetitionEvent、existing CompetitionPlan、StudentProfile、必要 planning context；不重新抓官网、构造 Snapshot、计算 Diff 或生成 Event。
- **Main Deliverables:** `CompetitionEvent → Impact Analysis → Affected Plan → Replanning → Plan Diff`；保存 `before`、`after`、`trigger_event`、`trigger_event_id`、`reason_code`、`evidence`。
- **Files/Modules Expected:** `backend/domain/replanning/`、相关 `backend/application/` 与 `backend/tools/`、`backend/tests/replanning/`。
- **Tests Required:** 无影响、多计划影响、时间冲突、重复事件幂等、前后版本与证据链测试。
- **Acceptance Criteria:** 受影响计划可定位，Diff 可解释可追踪；重复事件不产生重复重规划，旧计划仍可查看。
- **Explicitly Out of Scope:** Agent 自行改写规则、自动报名及前端可视化。

### P11.1 Adaptive Replanning Contract - CLOSED / FROZEN

`domain/replanning.py` adds result Contracts only. P8/P10/P9/P9.5 remain frozen;
no engine, Plan mutation, planner rerun or persistence is implemented by this Contract.

P8 audit: CompetitionPlan has id/student/competition/edition/optional track,
planning_horizon, skill_gap_audit, planning_needs, status/version, milestones and
created_at/updated_at. PlanMilestone has id/title/description, optional start_at/
due_at/estimated_hours, dependency_ids, status, source_need_id. PlanningNeed has
id/kind/reason_codes/optional source_item. All are immutable/serializable.
No priority/resources or Event/window dependency references exist; milestone
dependency_ids do not bind source windows. Baseline creates one unscheduled
milestone per need; optional supplied timing does not establish Event dependency.
Plan/milestone IDs are supplied by Contract; baseline IDs use SHA256, need IDs
canonical target/kind/skill tuples. No frozen identity/schema changes.

EventImpactAnalysis outcomes: AFFECTS_PLAN / NO_PLAN_IMPACT / UNDETERMINED. Exact
PlanReference includes target/student/version/update time/milestone IDs/content
digest; typed ReplanningEvidence references Event/Plan/milestones/source fields,
with full provenance retained in Event. No StudentProfile copy is stored. Shared
Evidence's required display message/scalar value does not fit these typed references.
Missing plan dependency != no impact. Relevant windows without dependency are
UNDETERMINED, even if milestone dates happen to coincide. A supplied factual track
dependency can be validated against the Plan's explicit track and Event membership
lineage. Target mismatch (competition/edition or disjoint explicit tracks) only
permits NO_PLAN_IMPACT with TARGET_MISMATCH. Edition/track mixed scopes are context
compatible, not automatically affected. OBSERVATION_COVERAGE_CHANGED remains
information uncertainty; no automatic replan/factual removal.

AffectedPlanScope distinguishes KNOWN-empty, KNOWN-affected, PARTIALLY_RESOLVED
known refs with unresolved remainder, and pure UNRESOLVED; references plan_id
and canonical milestone IDs/whole-plan scope. ReplanningDecision outcomes:
REPLAN / KEEP_CURRENT_PLAN / UNDETERMINED. Multiple unique Event IDs are ordered
canonically; supplied analyses preserve evidence. Confirmed impact requires REPLAN,
but REPLAN does not create a revised Plan or guarantee revision representability.
No-impact permits KEEP and empty PlanDiff; unresolved decisions can also leave
the exact old Plan unchanged.

PlanDiff holds before/after immutable P8 Plans, supplied typed milestone-collection
change, decision and trigger/reason/evidence lineage. First structural scope is
milestone collection only; no invented Plan fields. Unsupported target/student/
needs/audit/horizon/status changes reject. Empty Diff reuses the same Plan;
changed Diff requires REPLAN, next version and deterministic revised-plan-v1
identity over exact before reference + ordered supplied after milestones.
Identity helper is serialization only, not a revision/Diff engine. Evaluation
time is explicit/aware, never auto-now. No severity/score, workflow/notification,
Repository/Network/LLM/Agent or P5/P6/P7/P8 algorithm duplication.

Tests lock tri-state results, missing-dependency uncertainty, target/observation
safety, typed evidence, known-empty/unresolved scope, no-op and supplied structural
Diff, multiple trigger ordering/duplicates, identity/time, immutability and stable JSON.
P11.2 INPUT READY: Event + StudentProfile + Existing CompetitionPlan -> impact
analysis, using explicit reasons/evidence; P11.2 implementation is described below.

P11.1 safety follow-up passed re-review and is frozen. NO_PLAN_IMPACT requires verifiable structured
negative evidence: explicit target mismatch, or known/known factual membership with
the Plan target track preserved before/after and a cited track_membership reference.
Reason code alone and known-empty scope cannot prove no impact. UNRELATED_TRACK_CHANGE
names the preserved-track basis; NO_RELEVANT_PLAN_ELEMENT is accepted only with an
already verified negative basis. Missing window dependencies → UNDETERMINED;
same-target observation uncertainty → UNDETERMINED. Typed target-track removal/addition
cannot be overridden by contradictory positive/negative reasons. No-impact cannot
coexist with positive dependency evidence. Outcome compatibility is checked against
typed lineage before accepting reasons. This validates supplied results only, with
no Event Impact Analyzer or Replanning Engine. Legitimate negative evidence still
permits KEEP_CURRENT_PLAN + empty PlanDiff.

```text
Official Source -> P9.5 Monitor -> SnapshotDiff -> P10 CompetitionEvent
-> P11 Event Impact Analysis -> Replanning Decision -> Affected Plan Scope
-> Revised CompetitionPlan -> PlanDiff
```

## MVP 2 — 自适应计划验收关口

使用受控赛事变更，从 Snapshot 经 Diff、CompetitionEvent、影响分析到 Plan Diff 完成端到端演示；验证来源、审核、版本、事件幂等及 `before`/`after`/`trigger_event_id`/`reason_code`/`evidence` 全链路。记录场景测试结果及已知风险。此关口不新增代码范围，也不要求 Agent 或 Web。

### P11.2 Deterministic Event Impact Analysis - CLOSED / FROZEN

`domain/event_impact_analyzer.py` CompetitionEventImpactAnalyzer is a pure Domain
Service: validated CompetitionEvent + StudentProfile + existing CompetitionPlan +
explicit aware evaluated_at -> EventImpactAnalysis only. It directly reuses frozen
P11.1 outcomes, scope, ReplanningReasonCode and ReplanningEvidence. Student identity
must match Plan; no profile copy or profile text/skill heuristic participates.

Target relevance first: different competition/edition or disjoint explicit tracks
-> NO_PLAN_IMPACT / TARGET_MISMATCH / known-empty scope, including observation Events.
Mixed edition/track scope does not prove mismatch. Same-target registration/competition
window changes -> UNDETERMINED / PLAN_DEPENDENCY_NOT_REPRESENTED; optional dates and
milestone prose do not create dependencies. Observation knowledge lost/became known
-> UNDETERMINED / OBSERVATION_ONLY_EVENT, not factual removal.

Factual membership uses Event's existing typed source_changes. Target-track removal,
including mixed removed/added sets -> AFFECTS_PLAN / TARGET_TRACK_REMOVED. Target
preserved in both known sets with unrelated changes -> NO_PLAN_IMPACT /
UNRELATED_TRACK_CHANGE. Target-track added -> AFFECTS_PLAN / PLAN_DEPENDENCY_MATCHED,
explicitly mandated by frozen P11.1; this is the approved exception to uncertain-added
fallback. Edition Plan or track absent from both sets -> UNDETERMINED. No Contract change.

Positive/negative/uncertain evidence must support outcome. Affects scope is known
whole-plan target impact without guessing milestone IDs; no-impact scope known-empty;
uncertainty unresolved. Output passes normal P11.1 constructor with explicit time,
Event/Plan references, typed source-field evidence and canonical ordering. Inputs are
revalidated/detached and not mutated; output is immutable and JSON stable. No Impact ID.
No Repository/Network/LLM/Agent, hidden facts, independent SnapshotDiff input,
Event regeneration, decision engine, Plan revision/Diff, Planner rerun, P5/P6/P7 calls,
score/severity, notification or persistence. Frozen phases are unchanged.

Tests cover mismatch precedence, missing dependency, observation/fact separation,
membership removal/addition/preservation/absence, safe scope, evidence, explicit time,
student identity, no text heuristic, input preservation, determinism and serialization.
P11.3: EventImpactAnalysis[] + Existing Plan + explicit context ->
ReplanningDecision + canonical AffectedPlanScope, without Event reinterpretation,
P10 invocation or website access. P11.3 implementation is described below; P11 is CLOSED / FINAL REVIEW PASS / FROZEN.

### P11.1 Adaptive Replanning Contract - CLOSED / FROZEN (controlled evolution history; resolved)

P11.3 exposed two confirmed Contract limitations: no known affected refs plus
unresolved remainder, and REPLAN rejected mixed confirmed/uncertain impacts.
Explicit controlled reopening evolved existing models only; no P11.3 Service was
added by that Contract change. Current Service implementation is documented below.
ScopeState gains PARTIALLY_RESOLVED with known milestone IDs and/or whole-plan
impact plus unresolved remainder. No new serialized flag; derived property reads
the state. KNOWN-empty and pure UNRESOLVED remain distinct. Partial-empty rejects.
Known affected refs need Plan membership and reference evidence; no milestone guessing.

Formal action precedence: any AFFECTS_PLAN -> REPLAN; otherwise any UNDETERMINED ->
UNDETERMINED; all NO_PLAN_IMPACT -> KEEP. Mixed REPLAN must retain all analyses,
known scope union and unresolved remainder (including partial confirmed scope).
Whole-plan impact may coexist with unknown detail. REPLAN without confirmed impact,
KEEP with uncertainty/impact, UNDETERMINED with confirmed impact, incomplete scope
or contradictory reasons reject. Mixed reason: CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER;
pure confirmed reason: CONFIRMED_PLAN_IMPACT, with existing STRUCTURAL_REVISION_SUPPORTED
accepted for compatible old constructors. Existing no-impact/uncertainty reasons remain.

Old Scope fields/KNOWN/UNRESOLVED JSON and compatible pure Decision constructors
remain valid. Intentional migration: AFFECTS -> UNDETERMINED Decision no longer
parses under formal precedence; later revision handling owns representability.
No Decision/Scope ID is introduced; semantic state/reason/lineage differences remain
explicit in stable JSON. NO_PLAN_IMPACT structured negative evidence is not weakened.
Contract tests cover mixed milestone/whole-plan scope, uncertainty retention, precedence,
reason compatibility, source ordering/duplicates, old payloads, immutability and JSON.
That Contract evolution added no P11.3 Service, decision generation, revision or Diff computation;
P11.2/P8/P10/P9/P9.5 are unchanged. P11.4 implementation is documented below, Review PASS / committed / frozen.

### P11.3 Replanning Decision + Affected Scope - CLOSED / FROZEN

Pure Domain `domain/replanning_decision_service.py` ReplanningDecisionService.decide:
immutable ImpactAnalysis tuple + existing CompetitionPlan + explicit aware evaluated_at
-> ReplanningDecision with canonical AffectedPlanScope. Reuses frozen P11.1 result
model. No Decision/Analysis ID exists; canonical trigger Event ID keys supplied lineage.
Exact duplicates normalize within batch; same key/different content rejects.
All analyses bind exact caller Plan target/student/version/content; no hidden reads.

Precedence: any confirmed AFFECTS_PLAN -> REPLAN; else any UNDETERMINED ->
UNDETERMINED; all proven NO_PLAN_IMPACT -> KEEP_CURRENT_PLAN. Empty input rejects.
Service never inspects EventType/changes/summary to redo impact. P11.2 is sole
authority. All unique analyses, trigger events and evidence are retained, canonical
by trigger ID. No-impact analyses contribute neither refs nor unresolved remainder.

Scope union: confirmed milestone IDs unique/sorted; any whole-plan impact remains.
Resolved confirmed -> KNOWN affected; confirmed + uncertain/partial scope ->
PARTIALLY_RESOLVED; only uncertainty -> UNRESOLVED; all no-impact -> KNOWN-empty.
Unknown never becomes known-empty. Reasons follow frozen confirmed/mixed/uncertain/
no-impact semantics. Normal constructor validates output. UTC canonicalization of
aware input representations preserves meaning and order independence; no auto-now.

Tests cover all precedence combinations, milestone union, partial/whole-plan
uncertainty, exact Plan conflicts, duplicate/conflicting analyses, permutations,
time, serialization, immutability, input preservation and no impact/Event rerun.
No new Plan, mutation, PlanDiff, Planner/P5/P6/P7 calls, severity/score, Repository,
persistence, notification, Network, LLM or Agent. Frozen Contract/Analyzer unchanged.
P11.4 input boundary: Plan + Decision + Scope + impact lineage + explicit planning context
-> revised Plan + PlanDiff, without Event/Impact re-analysis. P11 is CLOSED / FINAL REVIEW PASS / FROZEN.

### P11.3.5 Structured Replanning Input - CLOSED / FROZEN

P11.4 guard: Decision/Scope supplies WHY/WHERE, not approved WHAT-to-change.
`domain/replanning_input.py` adds immutable typed ReplanningInput,
UpdateMilestoneInstruction and RevisionAuthority. No application/revision/Diff service.
Current PlanDiff supports milestone collection change, retaining target/student/
needs/audit/horizon/plan-status and explicit identity/version metadata semantics.
MVP instructions support same-ID UPDATE_MILESTONE.due_at only, with full supplied
expected-before/after. No inferred date, content or need generation. ADD/REMOVE/
REPLACE and all other milestone field updates are deferred; target/need/audit/
horizon/plan-status replacement requires separate design/reopen where necessary.

Preconditions: exact PlanReference (ID/version/target/content), exact old milestone,
source Decision fingerprint and explicit HUMAN_APPROVED references (approval,
approver, instruction source, aware approved_at). Caller supplies authenticated
authority context; Domain checks references/binding, not a human workflow or
external approval lookup. No fictional deterministic revision rule is implemented.
Instructions must target known affected refs unless whole-plan scope applies;
need refs remain existing, dependency IDs exist, horizon/time constraints hold.

Input states machine-distinct: EXECUTABLE, PARTIALLY_EXECUTABLE, UNRESOLVED,
NO_REVISION_REQUIRED. KEEP permits empty no-revision only; UNDETERMINED permits
empty unresolved only; REPLAN without instructions is unresolved, never executable.
Resolved milestone scope fully covered can execute; partial scope/missing coverage
retains partial status. Whole-plan impact stays conservatively partial even with
individual operations, since complete resolution is unproven. Pure unresolved
scope rejects structural instruction. No affected -> remove default.

Atomic desired-after batch; no sequential operation policy. One update per milestone;
duplicate/conflicting updates and unsupported operations reject. Approval time binds
Decision context and precedes explicit supplied_at. Canonical milestone order and
derived SHA256 instruction/input IDs include typed authority/preconditions/after state;
source Decision fingerprint binds exact lineage. No random ID/current clock.
All models/collections are immutable and JSON stable. IDs are derived properties,
not extra serialized fields. Tests prove explicit authorized update, safe statuses,
scope/identity/version/before/authority conflicts and frozen PlanDiff expressiveness.

P11.4 now consumes executable approved due_at updates without guessing WHAT,
while preserving existing Plan context; IMPLEMENTED / AWAITING FINAL RE-REVIEW.
No P8/P10/P11.1/P11.2/P11.3 changes, persistence, notification, LLM or Agent.

## P12 - Agent Framework, Orchestration & AgentArts Runtime Compatibility

- **Status:** CLOSED_FROZEN. P12.0 REVIEW_PASS (baseline commit 73d3d71); P12.1 REVIEW_PASS; P12.2 REVIEW_PASS; P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS.
- **Framework:** LangGraph; supporting LangChain Core; Domain schema Pydantic 2.
- **MVP:** one platform-neutral orchestrator Agent plus deterministic capabilities.
- **Goal:** Natural Language -> Intent -> Clarification -> Capability Selection ->
  Tool/Application Orchestration -> explicit Approval -> deterministic Domain Authority
  -> evidence-grounded Explanation. Agent has no business authority.
- **Scope:** core contract/state, approved capability facade, bounded orchestration,
  model-assisted intent/selection, clarification/approval, explanation, thin Runtime
  Adapter and offline/local-runtime parity. No ReAct loop, supervisor architecture,
  replacement Domain rules, MCP or frontend implementation within P12.
- **Canonical status source:** this file; README/ARCHITECTURE must mirror it.

### P12 frozen scope and downstream handoff

P12 is CLOSED_FROZEN after Final Review PASS. P12.0-P12.8 are REVIEW_PASS;
the baseline commit remains 73d3d71 and implementation provenance is in Git history.
Frozen scope: typed Agent contracts/state, Capability Facade, LangGraph orchestration,
safe LLM routing, clarification, explicit human approval, P11 authority bridge,
evidence-grounded explanation, AgentArts Runtime Adapter, real end-to-end integration
and local/runtime semantic parity. Domain authorities retain business truth; explicit
human approval retains mutation authorization. P1-P11 frozen semantics are unchanged.

| Deferred stage | Owned scope | Status |
|---|---|---|
| P13 | MCP + AgentArts MCP compatibility | CLOSED_FROZEN |
| P14 | Frontend + Runtime invocation compatibility | CLOSED_FROZEN |
| P15 | Evaluation + Local/AgentArts semantic parity evaluation | NOT_STARTED |
| P16 | Production AgentArts deployment/hardening: ARM64 image, SWR, IAM, Secrets, MaaS configuration, observability backend, scaling and load testing | NOT_STARTED |

These are downstream roadmap responsibilities, not incomplete P12 deliverables.
Gate F remains DEFERRED_WITHOUT_BLOCKER; no production deployment, durable session,
MCP or frontend readiness is claimed. Closure changes documentation/status only.

### P12 subphase completion

| Subphase | Goal / deliverable | Current status | Compatibility acceptance |
|---|---|---|---|
| P12.0 Framework & AgentArts Compatibility Baseline | Framework/rationale, adapter boundaries, dependency/package plan, gates and roadmap | REVIEW_PASS | Official baseline documented; existing core tests preserved; no runtime certification |
| P12.1 Agent Contract & State | Platform-neutral AgentRequest/AgentState/AgentResponse and stable references/errors | REVIEW_PASS | A/B/C; typed public JSON, explicit context, no RequestContext in core |
| P12.2 Agent Capability / Tool Facade | Approved capabilities mapped to existing Tool/Application authorities | REVIEW_PASS | A/B/C/D; no duplicate P5-P11 decisions or concrete Adapter imports |
| P12.3 LangGraph Orchestration Graph | Bounded explicit nodes/edges and state inspection, no free-running loop | REVIEW_PASS | A/B/D/E; stable node names; resolve/import-test agent dependency lock |
| P12.4 LLM Intent + Safe Tool Selection | Intent/selection interface, capability allowlist and output validation | REVIEW_PASS | A/B/C/D/E/G; provider behind injected interface; deterministic fixture models in default tests |
| P12.5 Clarification + Human Approval | Explicit clarification/approval states, trusted-state resume and stale-input safety | REVIEW_PASS | A/B/C/D/E/G/H; text is not approval; no business mutation before authorized input |
| P12.6 Evidence-grounded Explanation | Explain deterministic reason/evidence without inventing facts or new decisions | REVIEW_PASS | A-I (F deferred); evidence/reference fidelity, uncertainty and errors retained |
| P12.7 AgentArts Runtime Adapter | AgentArtsRuntimeApp entrypoint/context isolation around same Agent core | REVIEW_PASS | A-J; optional SDK; JSON human continuation and semantic parity; F production deferred |
| P12.8 Real Agent + AgentArts Compatibility Integration | Real deterministic capability chains and local/adapter semantic parity | REVIEW_PASS | A-L assessed; real authorities, fake models, JSON human continuation and lifecycle parity; F production deferred |
| P12 Final Review | Full tests, boundary/authority/approval/evidence/parity/compatibility inventory | REVIEW_PASS | A-L evidence and deferred live-deployment gates explicit |
| P12 Closure | Documentation-only CLOSED/FROZEN after Final Review PASS | CLOSED_FROZEN | Synchronized status and clear P13 handoff |

P12.0 implemented the design baseline and is committed. P12.1 implements contracts/state
only; P12.2 now implements the capability facade. P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.0 added no Agent contract;
P12.1 now adds typed interaction contracts and immutable snapshots. P12.3 implements a bounded StateGraph over those contracts/facade. P12.4 adds optional injected structured intent proposals, with no live provider configured and no
MCP, probe or cloud deployment is implemented; P12.5 now supplies approval collection/resume.
P12 overall CLOSED_FROZEN records completed implementation and Final Review PASS;
P13-P16 retain independent implementation, review and closure gates.

### AgentArts compatibility gates (apply at each relevant P12 stage)

| Gate | Required evidence | P12.0 disposition |
|---|---|---|
| A Core Independence | Core Agent tests/imports work without AgentArts SDK; P2-P11 untouched | Baseline defined; existing core independence verified; future Agent core not implemented |
| B JSON Compatibility | AgentRequest/public state/AgentResponse/Tool results convert to runtime-safe JSON | Defined; actual Agent schemas/roundtrip tests start P12.1 |
| C Runtime Adapter Boundary | SDK/RequestContext stay outside core; adapter only delegates | Architecture/engineering rule defined; adapter starts P12.7 |
| D Platform Parity | Same request/deterministic dependencies -> semantic-equivalent response/reasons/evidence | Defined; model outputs fixed/replayed for comparison; integration starts P12.8 |
| E Observability Readiness | Stable named nodes support tracing without business logic in probe | Reserved names defined; no probe/OTel code in P12.0 |
| F Deployment Readiness | Linux ARM64 build, project Python >=3.11, dependency pins, container and runtime verified before deployment | Defined; actual ARM64/runtime execution NOT_TESTED, production validation P16 |

Node names: intake, intent, clarification, route, tool_execution, approval,
result_validation, explain. Approval must gate any effectful execution. Later graph
routing uses approved typed capabilities; Domain remains business truth.
Passing a documentation baseline does not mean all deployment gates have run.
SDK/core support and production build assumptions are sourced in Architecture.

### Dependency/packaging decision

P12.0 left pyproject.toml, requirements.lock and the Windows venv unchanged.
LangGraph and LangChain Core were selected with installation deferred to P12.3.
P12.3 now adds an optional agent extra and a separately resolved exact agent lock,
without full LangChain/provider bundles; record import/install/full-regression evidence.
P12.7 adds the optional AgentArts SDK with an isolated overlay extending the Agent lock; production deployment remains deferred to P16. No SDK must be needed to import/test the core.
The SDK's Python 3.10+ minimum does not lower backend's >=3.11 requirement.
Windows supports core development; Ubuntu 22.04 ARM64 is the production build target.
No P12.0 dependency smoke is claimed for absent packages; no failing placeholder test.
When packages are created under agents/ or infrastructure/agentarts/, update explicit
setuptools package enumeration, dependency locks and accurate README commands together.

### P12.1 implementation and exit criteria

Status: REVIEW_PASS; P12 overall CLOSED_FROZEN. P12.0 REVIEW_PASS
(baseline commit 73d3d71), P12.2 REVIEW_PASS; P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.1 commit
status is proved by Git history, not by this documentation state.

Delivered: competition_copilot.agents/contracts.py and state.py, focused tests under
backend/tests/agents/, explicit setuptools package registration and synchronized docs.
All IDs are required caller-owned IDs/references, not random/clock-derived values.
Existing P11 PlanReference and P4 ToolResult are reused. No unified project contract
schema-version convention exists; this phase adds no arbitrary per-model versions.

Exit criteria: minimal/optional-context AgentRequest; known and UNKNOWN intent;
typed clarification reason/fields; explicit APPROVE/REJECT proposal/response matching;
immutable coherent workflow snapshots; reference-only capability proposal and results;
typed audit/reason/evidence/source/decision/Plan/Event linkage; business-negative result
can complete workflow without Agent failure; explicit aware times; JSON serialization,
roundtrip and stable reference ordering; no provider/platform dependencies; frozen
P2-P11 full regression and lint pass. Constructors check snapshot consistency, not
transition history or external artifact existence. Actual graph reducers/edges,
reference retrieval, authentication/approval provenance, P11 authority conversion and
Tool routing remain later subphases; no structural Domain execution is implemented.

| AgentArts gate | P12.1 evidence / status |
|---|---|
| A Core Independence | PASS: contracts/state import and test with SDK absent |
| B JSON Compatibility | PASS: all public envelopes/snapshots support standard JSON and validated roundtrip |
| C Runtime Boundary | PASS: dict/JSON input; no Runtime-specific constructor or RequestContext |
| D Platform Parity | PASS at contract boundary: no paths/platform handles or platform fields; actual adapter parity deferred |
| E Observability Contract | PASS: request/intent/status/invocation/approval/outcome refs; reserved node vocabulary preserved |
| F Deployment | DEFERRED / NOT_APPLICABLE_YET: no image/runtime/graph execution in this phase |

P12.1 added no new dependencies, model/LLM, StateGraph, Tool facade/execution, long-term memory,
Runtime Adapter, MCP, cloud/network operation or persistence. P5-P11 authority remains
frozen. P12.1 Review PASS; P12.2 now implements the separately documented facade boundary.

### P12.2 implemented capability inventory and exit criteria

Status: REVIEW_PASS. P12 overall CLOSED_FROZEN; P12.1 REVIEW_PASS;
P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. Git history, not a Markdown
commit lifecycle state, proves commits.

Actual inventory: P4 six Competition read Tools over CompetitionRepository; P5
CompetitionEligibilityEvaluator + EligibilityRuleEngine + policy provider interface;
P6 RecommendationScoringEngine/RecommendationRankingEngine (prepared contexts/scorers);
P7 SkillGapEngine and SkillRequirementProvider; P8 PlanningInputDeriver +
BaselineCompetitionPlanBuilder; P9 CompetitionSnapshotBuilder Application +
SnapshotDiffEngine; P9.5 OneShotCompetitionMonitor + CompetitionObservationSource;
P10 CompetitionEventEngine + CompetitionEventAggregator; P11
CompetitionEventImpactAnalyzer, ReplanningDecisionService, ReplanningInput/authority/
resolution contracts and PlanRevisionService. No production composition root/factory
was found; existing integration tests compose these dependencies explicitly.

Classification A ALREADY_AGENT_SAFE: P4 reads, P5 Eligibility Application, P9 repository
Snapshot builder. Classification B DOMAIN_ONLY: P6 scoring/ranking, P7 gap, P8 derivation/
builder, P9 Diff, P10 Event engine/aggregator, P11 Impact/Decision/Revision. They are exposed
only behind the typed facade with temporary internal Domain delegation, never directly
to Agent. Classification C NOT_AGENT_EXPOSABLE_YET: official-source monitoring pending
approved source/Gateway/permission composition. Input/authority preparation is an
internal P12.5 bridge, and P12.6 explanation is a Graph projection, not selectable
facade capabilities. Existing Monitor Application remains
valid and unchanged; deferral does not assert a defect in it.

| Capability ID | Underlying authority | Access | Explicit approval | Agent exposure |
|---|---|---|---|---|
| list_competitions | P4 ListCompetitionsTool | READ | NO | EXPOSED |
| get_competition | P4 GetCompetitionTool | READ | NO | EXPOSED |
| list_competition_editions | P4 ListCompetitionEditionsTool | READ | NO | EXPOSED |
| get_competition_edition | P4 GetCompetitionEditionTool | READ | NO | EXPOSED |
| list_edition_tracks | P4 ListEditionTracksTool | READ | NO | EXPOSED |
| get_competition_track | P4 GetCompetitionTrackTool | READ | NO | EXPOSED |
| check_eligibility | P5 CompetitionEligibilityEvaluator | DECISION | NO | EXPOSED |
| get_recommendations | P6 scoring + ranking; caller-prepared eligibility/scorer policy | DECISION | NO | EXPOSED |
| analyze_skill_gap | P7 SkillGapEngine | DECISION | NO | EXPOSED |
| build_plan | P8 PlanningInputDeriver + baseline builder | DECISION (derived in-memory Plan) | NO | EXPOSED |
| build_competition_snapshot | P9 Repository-interface Snapshot Application | READ | NO | EXPOSED |
| diff_competition_snapshot | P9 SnapshotDiffEngine | DECISION | NO | EXPOSED |
| derive_competition_events | P10 engine + aggregator | DECISION | NO | EXPOSED |
| analyze_event_impact | P11.2 Analyzer | DECISION | NO | EXPOSED |
| decide_replanning | P11.3 Decision Service | DECISION | NO | EXPOSED |
| revise_plan (APPLY_APPROVED_PLAN_REVISION) | P11.3.5/11.4.2 contract + P11.4 service | MUTATING (returned revised Plan only) | YES; formally authorized P11 input | EXPOSED |
| check_competition_changes / official-source monitor | P9.5 Monitor/Source interface | External observation | Source permission policy needed | DEFERRED |
| prepare_replanning_input / authority conversion | P11 structured contract | Authorization boundary | YES | INTERNAL P12.5 bridge; not an agent-selectable capability |
| explain_replanning | Referenced P11 result + bounded explanation | Explanation | NO | NOT_EXPOSED; P12.6 Graph consumes existing receipts without a separate capability |

No speculative capability ID is added for deferred preparation or monitoring adapters.
The facade is a fixed 16-capability set, not an AgentIntent mapper or dynamic registry.
Inputs reuse CapabilityInvocationRequest and generic typed CapabilityArguments bound to
its arguments_ref; metadata contains input schema JSON and formal result type. IDs are
caller-owned invocation/artifact references; JSON Pointer qualification is projection,
not a new generated ID scheme or persistence store. Invalid/missing correlation IDs
reject at the syntax boundary without inventing a response ID. Unsupported capabilities
return UNSUPPORTED_CAPABILITY; invalid payloads return INVALID_INPUT; missing injected
dependencies return DEPENDENCY_UNAVAILABLE. Domain rejection produces EXECUTION_REJECTED,
never an alternate business result or guessed tool.

AgentCapabilityResult preserves original typed results, source metadata and producer
reason/evidence refs. INELIGIBLE/UNKNOWN/NO_GAP/KEEP are successful capability execution.
SUCCESS and ERROR are exclusive. Revision consumes exact before Plan + validated
ReplanningInput + explicit time; Agent ApprovalResponse cannot substitute for it.
Formal P11 input carries Decision/Scope/Resolution/authority transitively. All authority,
partial scope, version, semantic compatibility and actual before/after checks stay P11.
The facade adds no scoring/threshold/impact/preference/status-transition business rules.

Exit criteria: exact inventory/metadata; deterministic explicit dispatch; unknown/deferred
capability rejection; all six real Repository-backed read Tools; real P5 Application
and three Eligibility outcomes; P6 confirmed/uncertain/blocked; P7 gap/no-gap/unknown;
real P8 sourced COMAP planning; P9 observation safety; P10 Event and P11 tri-state/
precedence preservation; valid approved cancellation and missing-authority/partial/
stale-version rejection; no provider/infrastructure coupling; reference fidelity;
JSON/roundtrip and source/evidence Pointer resolution; P12.1/P4/P5-P11 regressions.
Controlled Events/approvals/policies are test scenarios, not official historical claims.

| AgentArts gate | P12.2 status |
|---|---|
| A Core Independence | PASS: SDK absent, facade imports/tests work |
| B JSON Compatibility | PASS: typed argument schemas/metadata/results and standard JSON roundtrip |
| C Runtime Boundary | PASS: adapter need not know Repository/Domain implementations; core sees facade |
| D Platform Parity | PASS at invocation boundary: fixed inputs/dependencies, no platform/runtime branches |
| E Observability | PASS: invocation/capability/source-request/status/result-ref correlation; no OTel code |
| F Deployment | DEFERRED: pure Python addition, no new/native dependencies; actual ARM64/image gate remains later |

P12.2 added no Graph, model, Agent routing, approval workflow, Runtime Adapter, MCP,
persistence, notification or scheduler. No live source/network call is exposed.
P12.2 Review PASS; commit status is proved by Git history. P12.3 now implements the
separately documented deterministic graph; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS.

### P12.3 actual graph implementation and exit criteria

Status: REVIEW_PASS. P12 overall CLOSED_FROZEN; P12.1/P12.2 REVIEW_PASS;
P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.3 Review PASS; commit status is proved by Git history.

Audited authority models: AgentState (request/intent/status/invocation/tool_result/
clarification/approval/audit/final_response/error), AgentRequest, AgentResponse,
CapabilityInvocationRequest and AgentCapabilityResult. Facade entrypoint is execute,
with static discovery list_capabilities. Actual package convention is agents/ (plural).
No parallel AgentState or AgentResponse is introduced. P12.1 gains only additive
CAPABILITY_INVOCATION/CAPABILITY_ARGUMENTS clarification fields and workflow error
CAPABILITY_EXECUTION_FAILED; existing values and validations remain unchanged.

Delivered graph.py: build_competition_copilot_graph(facade) -> real compiled LangGraph,
wrapped by CompetitionCopilotGraph.invoke(GraphInput) -> AgentResponse. GraphInput is
an immutable technical envelope around AgentState, with explicit caller-owned
clarification_id/result_ref, optional typed argument-artifact JSON and caller-prepared
ApprovalRequest. Private channels hold the validated State plus receipt/branch/response;
services/Facade stay closure-injected outside serializable channels. tool_execution is
the only external capability boundary and invokes Facade once; no Domain or Repository
service is directly called by the graph.

Paths: START -> intake -> intent -> route -> tool_execution -> result_validation ->
explain -> END. UNKNOWN goes intent -> clarification -> END. Missing invocation/required
structural fields goes route -> clarification -> END. Valid unanswered approval proposal
goes route -> approval -> END. Unsupported routing and invalid receipt/invocation errors
produce typed FAILED response without retry/fallback. Clarification and approval wait
are normal non-terminal outcomes. If required proposal refs/time are absent, request
MISSING_APPROVAL_CONTEXT clarification instead of inventing a valid ApprovalRequest.
Already structured approval State may pass only workflow readiness; formal P11 authority
and semantic validation remain at Facade/Domain. No approval collection, authentication,
proposal-to-input authorization conversion, second-turn resume or persistent checkpoint.

Node names are exactly intake/intent/route/clarification/approval/tool_execution/
result_validation/explain. Conditional edges are explicit. Caller supplies intent and
invocation; no user_message inference, keyword routing, multi-step capability planning
or model. Error vs successful business-negative/uncertain result remains distinct.
Result audit refs are retained; explain is a stable completion template, not business
reasoning. Terminal States cannot restart; validated immutable State replacement and
updates streaming support deterministic path/response/JSON and before-State safety.

Dependency baseline: optional agent extra pins LangGraph 1.2.15 / LangChain Core 1.6.10;
requirements-agent.lock pins all 32 resolved optional distributions over unchanged core
requirements.lock. Editable install and pip check pass. Existing setuptools build
requirement is installed explicitly for this managed venv's build_meta isolation issue;
it is not a new Agent runtime dependency. No provider/AgentArts package is installed.
Transitive checkpoint/prebuilt/SDK/LangSmith libraries are dependencies, not active
saver/ReAct/cloud features. Public wrapper disables ambient tracing; stream is offline
inspection, not telemetry. Graph tests require agent extra; core-only installs can skip
that optional module while P2-P12.2 remain independent. Full graph validation uses extras
and requires zero skips.

Exit criteria: build/compile without network/model/AgentArts; known structured READ path;
UNKNOWN/no-keyword guessing; missing-target/selection clarification; unsupported-capability
rejection; explicit proposal wait with no mutation or implicit authority; formal P11
input still rejects an Agent APPROVE substitution; real P4 seed-backed read and real
P5 INELIGIBLE/UNKNOWN remain COMPLETED; invocation errors FAILED; receipt correlation;
evidence/ref preservation; immutable input and validated deltas; repeated path/JSON;
standard request/State/response JSON boundary; existing P12.1/P12.2/P4/P5-P11 regressions.
Controlled proposals/data are test fixtures, not official historical events.

| AgentArts gate | P12.3 status / evidence |
|---|---|
| A Core Independence | PASS: graph builds/imports/runs without AgentArts SDK |
| B JSON Compatibility | PASS: GraphInput wrapping AgentState and existing AgentResponse; typed per-run receipt channels, no service handles |
| C Runtime Boundary | PASS: future adapter only normalizes request/context to core input and projects AgentResponse; no Domain service knowledge |
| D Platform Parity | PASS at graph boundary: no OS/CWD/ARM branches; caller inputs/dependencies control semantics |
| E Observability | PASS: stable eight node names and deterministic updates stream; no OpenTelemetry/export code |
| F Deployment | DEFERRED: native dependencies exist but ARM64 CPython 3.11 binary-only resolution passes; actual Linux/image/runtime execution remains untested |

Wheel feasibility dry-run covers native orjson/ormsgpack/uuid-utils/xxhash/PyYAML/
zstandard and the locked dependency closure. It is not a target-environment/container
certification; Linux markers/install/runtime and deployment require later gates.
P12.4 alone begins natural-language LLM intent + safe capability selection. No LLM,
ReAct, AgentArts adapter, MCP, persistence/store, memory or scheduler in P12.3.

### P12.4 actual intent routing implementation and exit criteria

Status: REVIEW_PASS. P12 CLOSED_FROZEN; P12.1/P12.2/P12.3 REVIEW_PASS;
P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.4 Review PASS; commit status is proved by Git history. Canonical phase status remains this document.

Delivered agents/routing.py (IntentModel, IntentModelInput, IntentRoutingProposal,
RoutingProposalValidator, JSON-safe validation outcome and static safety map),
agents/model.py (injected LangChain Core structured-output bridge), agents/prompts.py
(one bounded routing prompt), and optional model integration in the existing intent
node. Existing AgentState/AgentResponse and Facade contracts remain authorities.
GraphInput adds only optional caller-owned routing invocation/arguments references.
Facade adds reusable syntax-only argument validation; execution/delegation is unchanged.
No P4-P11 production code or business semantics change. No new dependencies or lock
changes: the reviewed P12.3 agent extra supplies all framework abstractions.

LLM proposes. Validator approves routing. Domain decides truth. Caller-known intent
bypasses LLM. One untrusted proposal is schema/whitelist/compatibility/context validated
before routing. Explicit context cannot be overwritten; model targets are never used
as parameters. Caller-prepared typed argument artifacts and IDs are required; missing
context/ambiguity/compound requests clarify. Invalid output, hallucinated capability,
conflicting targets or model failure stop without fallback/retry or secret-bearing
exception text. All model-originated mutation proposals stop for formal approval context.
Natural-language yes never grants approval; P12.5 owns actual approval workflow.
P12.6 implements bounded LLM explanation with deterministic grounding and fallback.

Exit criteria: real Graph/Facade READ selection from a fake structured model; eligibility
intent delegates to real P5 and negative/uncertain results remain completed; missing
competition/student/prepared recommendation/plan context clarifies; P6 execution uses
caller-prepared contexts, not model ranking; UNKNOWN/ambiguity/compound request stops;
invalid schema/enums/extra business/approval/reasoning fields and hallucinated capabilities
reject; intent incompatibility and explicit-context conflict reject; mutation injection
never executes; structured replay bypasses model; exception secrets do not reach public
response/state; schema/prompt bridge tested offline; JSON roundtrip and deterministic
fixture response/path; P12.1-P12.3 and P4-P11 full regression preserved.

| AgentArts gate | P12.4 status / evidence |
|---|---|
| A Core Independence | PASS: no AgentArts SDK/provider package required |
| B JSON Compatibility | PASS: proposal/catalog/validation/State/Response roundtrip |
| C Runtime Boundary | PASS: adapter injects model through composition, no routing rules |
| D Platform Parity | PASS at core boundary: same schema/validator/graph for all models |
| E Observability | PASS: named intent node, request/proposal/validation/invocation/result correlation; no hidden reasoning or telemetry export |
| F Deployment | DEFERRED: no new dependencies/native risk; actual provider/Linux/runtime deployment untested |
| G Model Injection Compatibility | PASS: optional IntentModel factory parameter; no concrete client/key/environment import side effects |

Gate G applies to P12.4 and downstream model/runtime integration: runtime/composition
must inject the model through the core interface, with provider configuration, timeout
and credentials outside public contracts. Fake and live adapters share validation rules.
No online model is called in this stage. Default fixtures block network and require no
keys. Live provider smoke is not added; deployment/SDK/provider certification is deferred.

P12.4.1 controlled follow-up fixes B1: matching proposal targets now resolve against
caller-owned nested P6 contexts instead of an empty outer payload. Bounded identity
projection merges matching values, rejects conflicting students/outer constraints,
and preserves distinct recommendation candidate scopes. Proposal values remain
assertions only. Real P6 matching-target and conflict regressions are added.
P12.4 Review retry PASS; status REVIEW_PASS.

### P12.5 actual human interaction implementation and exit criteria

Status: REVIEW_PASS. P12 CLOSED_FROZEN; P12.1-P12.4 REVIEW_PASS;
P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.5 Review PASS; commit status is proved by Git history.

Delivered human_contracts.py (typed clarification replies/choices/proposals and HumanResume),
human_interactions.py (requested-field merge, explicit consent/binding validators, P11
authority bridge), minimal State/Graph integration and an optional injected structured
LangChain clarification interpreter. Existing ClarificationRequest, ApprovalRequest,
ApprovalResponse, AgentState, AgentResponse and Capability Facade are reused. Approval
resolution_ref becomes optional for P11 milestone batches without a scope resolution;
cancellation still requires formal COMPLETE resolution under frozen P11 validation.

run_turn returns response plus caller-managed trusted continuation; resume accepts one
typed or natural-language human reply. No persistent checkpointer/session store is
installed. Clarification merges only requested missing fields and records reply refs;
partial/ambiguous replies remain pending. Model proposals can select only unique
caller-owned read choices with matching message labels, never invent IDs or approval.
Structured replies bypass models. Approval uses typed responses or a bounded full-message
consent/rejection rule, with exact pending/request/Plan/version/action/scope binding.
The bridge consumes a caller-prepared valid P11 proposal, verifies fresh explicit
approval and rebinds authority while retaining the same semantic operations/coverage.
New authority-dependent IDs are normal P11 identities. Actor/current Plan/time come
from a trusted runtime/application boundary. Authentication and durable replay storage
are not claimed. Completed continuation cannot resume; original pending snapshot replay
is not a cross-process consumption ledger.

Exit criteria: real P4 clarification/resume; wrong/unrequested/conflicting/partial replies;
structured and offline fake-interpreted natural clarification; no model-created IDs;
exact approved/rejected/ambiguous response handling; wrong/cross-request/stale approval
rejection; REPLAN without consent never executes; KEEP/UNKNOWN never request speculative
mutation approval; caller execution Plan mismatch rejects; scope expansion/fake authority
injection does not approve; real P11.5 controlled target removal -> AFFECTS -> REPLAN ->
COMPLETE cancellation proposal -> Agent ApprovalRequest -> explicit APPROVE -> new P11
authority -> Facade -> active/cancelled actual PlanDiff. Identical REJECT leaves Plan
active. Before Plan remains immutable; events/Decision/proposal/response/authority/Diff
audit links and deterministic JSON continuation are retained. Controlled events are test
scenarios, not official historical changes. P12.6 alone adds LLM final explanation.

| AgentArts gate | P12.5 disposition |
|---|---|
| A Core Independence | PASS: no AgentArts/provider SDK required |
| B JSON Compatibility | PASS: pending State, GraphTurn/GraphInput, replies and responses roundtrip |
| C Runtime Boundary | PASS: JSON reply plus trusted runtime continuation, no adapter business rules |
| D Platform Parity | PASS at core boundary: same validators/bridge/graph, no OS branches |
| E Observability | PASS: clarification/approval resolution nodes and correlated reply/authority/result refs |
| F Deployment | DEFERRED: no new dependencies; Linux/runtime deployment remains untested |
| G Model Injection | PASS: optional HumanResponseInterpreter; no model decides consent |
| H Human-in-the-loop Continuation | PASS: explicit JSON-safe continuation and next reply, no globals or object handles |

Gate H applies to downstream Runtime/frontend/evaluation: continuity uses the same
core interaction rules. Durable session storage, authenticated transport and replay
ledgers require later deployment gates, not local process globals.

### P12.7 actual Runtime Adapter implementation and exit criteria

Status: REVIEW_PASS. P12 CLOSED_FROZEN; P12.1-P12.6 REVIEW_PASS;
P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. Commit provenance is recorded in Git history.

The isolated `integrations/agentarts` package contains typed transport envelopes,
SDK-free adapter logic and official SDK app wiring. `AgentArtsRuntimeApp` registers
an async `@app.entrypoint`; the existing graph is invoked once in a worker thread.
Existing request/response, continuation and human reply contracts are reused.
Injected trusted application bindings authorize opaque continuation references and
provide caller-owned arguments/actor/current Plan/time. Client state and runtime
context do not establish identity, consent or authority. No durable session is claimed.

Validation: 35 P12.7 targeted tests and 2140 full-suite tests passed, zero skipped;
Ruff, pip check and diff check passed in the SDK-enabled Python 3.12 environment.
Exit evidence includes actual SDK 0.1.6 import/app construction/public invocation,
invalid payload and sanitized errors, core import with SDK blocked, JSON reconstruction,
local/runtime parity, real P5 negative/unknown results, P11 approval/reject and stale/
wrong/cross-request protection, and grounded explanation/fallback with no duplicate
execution. Default tests do not access cloud/network or require AK/SK.

| AgentArts gate | P12.7 disposition |
|---|---|
| A Core Independence | PASS: only app wiring imports SDK; blocked-SDK subprocess invokes core |
| B JSON Compatibility | PASS: request/response and pending human continuation roundtrip |
| C Runtime Boundary | PASS: official app -> thin adapter -> same graph |
| D Platform Parity | PASS: direct and Runtime core response equality |
| E Observability | PASS: stable graph node tracing retained; no secret/error prose logged |
| F Deployment Readiness | DEFERRED_WITHOUT_BLOCKER: development smoke only; P16 target validation remains |
| G Model Injection | PASS: routing/explanation/interpreter remain injected in core composition |
| H Human Continuation | PASS: trusted JSON reconstruction and current binding revalidation |
| I Explanation Grounding | PASS: same context builder/validator/fallback |
| J Runtime Semantic Parity | PASS: same requests/dependencies produce equivalent core responses |

Dependency strategy: optional `agentarts` extra and `requirements-agentarts.lock`
overlay extend frozen Agent/core locks. Official SDK mandatory dependencies include
MCP/Docker/identity libraries, without implementing those project capabilities.
Python >=3.11 remains the project target (SDK >=3.10); verified interpreter is 3.12.
Native portability inventory: cryptography/cffi/pymongo/rpds-py/simplejson/httptools/
watchfiles plus existing Agent binary dependencies. pywin32 is Windows-conditional;
Linux uvloop is not pinned by this Windows development resolution. No x86-only
project assumption or CUDA requirement is added, but Linux ARM64 wheel/build/runtime
verification is deferred to P16. No production Dockerfile, launch, SWR/IAM/MaaS
configuration, secrets, autoscaling or deployment observability backend is added.
P12.8 integration expansion is REVIEW_PASS; P16 remains Production Deployment & Hardening.

### P12.6 actual explanation implementation and exit criteria

Status: REVIEW_PASS. P12 CLOSED_FROZEN; P12.1-P12.5 REVIEW_PASS;
P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12.6 Review PASS; commit status is proved by Git history.

Delivered `agents/explanation.py`: immutable ExplanationContext/GroundingEvidence,
bounded ExplanationDraft, injectable ExplanationModel, deterministic context builder,
ExplanationGroundingValidator and capability-specific fallback. Graph explain evolves
without topology changes; pending/rejected approval projection uses the same boundary.
The optional LangChain Core adapter and central prompt add no provider dependency.

LLM only composes supplied sentence variants and citations. This first version does
not validate arbitrary natural-language paraphrases: exact conclusion/fact variants,
fact order, reason codes, result/citation whitelists and required uncertainty are
checked deterministically. Domain alone owns Eligibility, ranking/score/buckets,
SkillGap, PlanningNeeds/Milestones, observation/fact classification, Impact, Decision,
Approval authority and PlanDiff. Existing refs/source URL/type/observed_at/verification,
before/after/trigger/approval lineage are retained; full payloads/user messages/free
evidence prose/secrets are excluded from model context. Display details are bounded;
all audit refs remain, and contexts over 64 KiB skip the model. Chinese fallback is
deterministic and does not claim fresh facts from observation timestamps.

Exit criteria: real P5 INELIGIBLE/UNKNOWN through Graph -> Facade -> authority -> fake
ExplanationModel -> grounded AgentResponse; P6 bucket/rank/score/order preservation;
P7/P8 uncertainty/actual needs/milestones; P9/P10 observation vs fact separation; P11
KEEP/UNDETERMINED/no-op vs actual revision; pending/rejected approval and approved
controlled cancellation with actual PlanDiff. Fabricated evidence/source/reasons,
conflicting status/operation, omitted uncertainty and malformed drafts fall back.
Model timeout cannot fail successful business execution or repeat mutation. JSON,
immutable caller state, deterministic output, offline provider independence and
P12.1-P12.5/frozen authority regressions are required. P12.7 alone adds Runtime Adapter.

| AgentArts gate | P12.6 disposition |
|---|---|
| A Core Independence | PASS: no AgentArts SDK or concrete provider dependency |
| B JSON Compatibility | PASS: context/draft/rendering and existing response roundtrip |
| C Runtime Boundary | PASS: inject model, reuse core grounding/fallback rules |
| D Platform Parity | PASS at core boundary: same projection/validator/Graph |
| E Observability | PASS: typed context/model/grounding/fallback events in graph updates |
| F Deployment | DEFERRED: no dependency changes; runtime/ARM64 image not deployed |
| G Model Injection | PASS: separate injectable ExplanationModel Protocol |
| H Human Continuation | PASS: P12.5 clarification/approval resume safety retained |
| I Explanation Grounding Parity | PASS: future Runtime must reuse authoritative context, validator and fallback |

### P12.8 actual integration and P12 Final Review evidence

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1-P12.7 REVIEW_PASS.
P12 Final Review REVIEW_PASS; P12 Closure CLOSED_FROZEN; P13 CLOSED_FROZEN.

Delivered public `agents.agent.CompetitionCopilotAgent` request entry and the outer
`composition.build_seed_agent` factory. Local and Runtime use the same graph/Facade/
authorities and explicit caller-prepared inputs. Repository construction stays
outside Agent; no hard rule, scoring formula, authority or grounding policy changed.
No integration-required compatibility fix to existing core semantics was needed.

| Final Review evidence | Location / acceptance |
|---|---|
| Agent contracts / JSON | existing tests/agents/test_agent_contracts.py |
| Capability Facade / authorities | existing test_agent_capability_facade.py |
| LangGraph / stable nodes | existing test_agent_orchestration_graph.py; new discovery trace test |
| Routing whitelist / untrusted proposals | existing test_agent_intent_routing.py; new model failure/authority injection chain |
| Clarification / approval / bridge | existing test_agent_human_interactions.py; new test_agent_human_flow_integration.py |
| Explanation grounding / fallback | existing test_agent_explanation.py; new source-to-Runtime lineage tests |
| SDK app / import isolation | existing test_agentarts_runtime.py; new formal-composition SDK endpoint test |
| Real seed P4/P5/P6/P7/P8/P9/P10 | new test_agent_real_integration.py |
| Controlled P11 Event/Impact/REPLAN/cancel | new human-flow test; frozen P11.5 fixture, not official history |
| Lifecycle parity / architecture | agent_e2e_support.py comparator; test_agent_e2e_architecture.py |

Real mainline P5 policies produce a definite negative and UNKNOWN; P6 preserves
uncertain/blocked buckets, never promotes partial policy to confirmed. A supplemental
complete-policy fixture is explicitly controlled test input evaluated by real P5
for P6 confirmed coverage; no hand-created eligibility result substitutes for the
mainline. COMAP reviewed skill requirements retain unspecified proficiency; real
P7 -> P8 produces uncertainty-resolution needs/milestones/audit. All data files
(seed/raw/manifests/policies/requirements) remain unchanged. Models are deterministic
fakes and external network is blocked. P9/P10 exposure is unchanged; P9.5 source
monitor is NOT_EXPOSED_BY_DESIGN and is not unlocked for integration.

Clarification tests cover missing target, structured/NL reply from real read choices,
wrong ID and resume. Approval tests cover pending/no mutation, explicit approve,
reject, stale/wrong/cross-request rejection, actual PlanDiff and authority/evidence
lineage, plus explanation failure after revision without re-execution. Each turn
has at most one Facade call, approved mutation exactly one. Before Plan is immutable.
Parity compares all core response fields and receipt content; only transport wrapper,
continuation and named transport correlation metadata are excluded. Pending JSON is
reconstructed through trusted application bindings, without global/session storage.

| AgentArts gate | P12.8 disposition |
|---|---|
| A Core Independence | PASS: core SDK import isolation retained |
| B JSON Compatibility | PASS: request/response, human continuation and nested refs |
| C Runtime Boundary | PASS: same composed public core entry |
| D Platform Parity | PASS: real-authority receipts and core responses agree |
| E Observability | PASS: stable node path captured without a second trace policy |
| F Deployment | DEFERRED_WITHOUT_BLOCKER: ARM64/cloud/P16 gates unchanged |
| G Model Injection | PASS: fake routing/explanation/interpreter explicitly injected |
| H Human Continuation | PASS: Local/Runtime structured and NL clarification; approval/reject |
| I Explanation Grounding | PASS: same authoritative context/draft/validator/fallback |
| J Runtime Semantic Parity | PASS: read, clarification, approval and explanation |
| K End-to-End Agent Parity | PASS: full lifecycle semantics excluding named transport metadata |
| L Authority Preservation | PASS: P5-P11 and explicit human approval lineage retained |

P12.8 adds no dependency or schema changes, MCP/frontend, persistent store, memory,
production deployment or production image. P16 still owns ARM64/SWR/IAM/Secrets/MaaS,
observability backend, scaling/load tests and production hardening.

Validation: 35 new targeted integration/architecture tests PASS; full suite 2175
passed, zero skipped, including P12.1-P12.7 and relevant frozen P4-P11 regressions.
Ruff and diff check PASS. Final Review confirmed 2175 passed, zero skipped;
Gates A-E/G-L PASS, Gate F DEFERRED_WITHOUT_BLOCKER. Closure finalizes documentation/status only.

## P13 - MCP Adapter & AgentArts MCP Compatibility

- **Status:** CLOSED_FROZEN; P13.0-P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12 remains CLOSED_FROZEN.
- **Goal:** Competition Copilot as an MCP **server**, projecting individually approved
  P12.2 capabilities through a standard external protocol boundary. No Agent redesign.
- **Authority:** MCP tool call -> typed projection -> Capability Facade -> existing
  Application/Tool/Domain authorities. No direct Domain execution or Repository access
  from an MCP adapter; explicit outer composition injects the dependency tree.
- **Scope:** Tools only, dual-protocol compatibility, stateless business execution,
  Streamable HTTP and offline AgentArts Gateway compatibility. No external MCP
  consumption, arbitrary MCP client, web search, Resources or Prompts.
- **Boundary:** P12.7 Runtime executes the complete Agent/Graph; P13 Gateway-facing
  tools call the Facade without AgentRequest, Graph, routing/explanation model or
  natural-language intent parsing. Both paths preserve the same Domain truth.

### P13 subphase roadmap and exit boundaries

Lifecycle: NOT_STARTED -> IMPLEMENTED_AWAITING_REVIEW -> REVIEW_PASS; BLOCKED when
required, CLOSED_FROZEN only after closure. Commit provenance stays in Git, not in
Markdown lifecycle states. P13.0 does not implement P13.1 or later deliverables.

| Subphase | Deliverable / exit boundary | Status |
|---|---|---|
| P13.0 MCP Protocol & AgentArts Compatibility Baseline | Audit, protocol/transport/exposure policy, compatibility matrix, gates and roadmap; no server/handlers | REVIEW_PASS |
| P13.1 MCP Tool Exposure Contract | Individually reviewed allowlist, concrete stable tool names, typed input/output projection and registry contract | REVIEW_PASS |
| P13.2 MCP Server Core & Tool Catalog | Explicit official Python SDK integration/dependency decision, server construction and deterministic tools/list | REVIEW_PASS |
| P13.3 Safe Tool Execution & Result Mapping | tools/call -> Facade only; typed result/error projection and business-negative preservation | REVIEW_PASS |
| P13.4 Streamable HTTP & Protocol Compatibility | Stateless business execution; test 2025-11-25 and 2026-07-28 public SDK paths with equal authority results | REVIEW_PASS |
| P13.5 AgentArts Gateway Compatibility | Local Gateway-compatible discovery/call/negotiation/schema/result tests; no production cloud resources | REVIEW_PASS |
| P13.6 Real MCP Integration & Authority Preservation | Real repository/P5-P11 calls through admitted tools; Runtime/MCP authority parity, mutation-denial and data integrity | REVIEW_PASS |
| P13 Final Review | Whole-phase protocol, authority, exposure, compatibility, regression and documentation audit | REVIEW_PASS |
| P13 Closure | Documentation/status finalization after Review PASS | CLOSED_FROZEN |

### P13.0 protocol and transport baseline

Checked against official documentation and installed metadata on 2026-10-19:

- `MCP_UPSTREAM_BASELINE = 2026-07-28`.
- `AGENTARTS_MCP_COMPATIBILITY_VERSION = 2025-11-25`.
- These are documentation-level integration settings, not new Domain constants or
  implemented negotiation. Protocol versions must never enter Domain/Application/Tool.
- The [upstream release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  establishes a sessionless core. The [2025 lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
  uses initialization/version negotiation. Keep both paths at the protocol edge;
  neither may change capability execution or use MCP session IDs as business IDs.
- [AgentArts Gateway configuration](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_024.html)
  currently lists versions through 2025-11-25; do not claim 2026-07-28 support there.
  A modern-only target is insufficient for AgentArts compatibility.
- Streamable HTTP is the required remote path; stdio is optional local development/
  testing. Legacy HTTP+SSE is not primary. A Streamable HTTP response carrying SSE
  is not the separate legacy SSE transport.

| Compatibility target / feature | Protocol / policy | Expected acceptance (not implemented support) |
|---|---|---|
| Local modern MCP client | 2026-07-28 | SUPPORTED target; tests required P13.4 |
| AgentArts Gateway | 2025-11-25 | REQUIRED COMPATIBILITY; tests required P13.4/P13.5 |
| Streamable HTTP | Remote primary transport | REQUIRED |
| stdio | Development / local testing | LOCAL_DEV_OPTIONAL |
| Legacy SSE | Separate legacy transport | NOT_PRIMARY |
| MCP Tools | Explicit approved registry only | IN_SCOPE |
| MCP Resources | No registration/advertisement | OUT_OF_SCOPE |
| MCP Prompts | No registration/advertisement | OUT_OF_SCOPE |
| MCP Sampling | No client model inference requests | NOT_USED |
| MCP Elicitation | No MCP clarification/approval bridge | NOT_USED |
| Roots / protocol Logging | No new architecture dependency on deprecated features | NOT_USED |
| External MCP consumption / web search | Server-side capability projection only | OUT_OF_SCOPE |

Business execution is stateless: same tool name + typed arguments + injected
dependencies must reach the same Facade and equivalent result on both protocol
paths. Inputs must be self-contained; no sticky worker, server-side conversation,
pending-approval cache or in-memory MCP business session is allowed. Any legacy
handshake state remains an SDK transport concern. `Mcp-Session-Id` cannot become
student_id, plan_id, Agent session, user identity, approval request or authority.

### Capability audit and exposure policy

Audit source: `agents.contracts.CapabilityId`, actual `AgentCapabilityFacade.list_capabilities()`
and static Facade dispatch. IDs below are **existing capability IDs, not MCP tool
names**. At the P13.0 audit, exposure was unimplemented. The P13.1 contract below
now records individual admission; no MCP runtime catalog or execution exists yet.

| Existing capability | Access | Agent exposed | Approval required | Existing authority |
|---|---|---|---|---|
| list_competitions | READ | YES | NO | P4 ListCompetitionsTool -> Repository interface |
| get_competition | READ | YES | NO | P4 GetCompetitionTool -> Repository interface |
| list_competition_editions | READ | YES | NO | P4 ListCompetitionEditionsTool -> Repository interface |
| get_competition_edition | READ | YES | NO | P4 GetCompetitionEditionTool -> Repository interface |
| list_edition_tracks | READ | YES | NO | P4 ListEditionTracksTool -> Repository interface |
| get_competition_track | READ | YES | NO | P4 GetCompetitionTrackTool -> Repository interface |
| build_competition_snapshot | READ | YES | NO | P9 CompetitionSnapshotBuilder |
| check_eligibility | DECISION | YES | NO | P5 CompetitionEligibilityEvaluator / EligibilityRuleEngine |
| get_recommendations | DECISION | YES | NO | P6 RecommendationScoringEngine / RecommendationRankingEngine |
| analyze_skill_gap | DECISION | YES | NO | P7 SkillGapEngine |
| build_plan | DECISION | YES | NO | P8 PlanningInputDeriver / BaselineCompetitionPlanBuilder |
| diff_competition_snapshot | DECISION | YES | NO | P9 SnapshotDiffEngine |
| derive_competition_events | DECISION | YES | NO | P10 CompetitionEventEngine / CompetitionEventAggregator |
| analyze_event_impact | DECISION | YES | NO | P11 CompetitionEventImpactAnalyzer |
| decide_replanning | DECISION | YES | NO | P11 ReplanningDecisionService |
| revise_plan | MUTATING | YES | YES | P11 PlanRevisionService; P12.5 approval bridge in Agent workflow |
| check_competition_changes | N/A: no Facade metadata | NO | N/A | Enum-only/deferred aggregate; no handler |
| explain_replanning | N/A: no Facade metadata | NO | N/A | Not selectable; P12.6 Graph explanation remains internal |

P9/P10 capabilities listed above really are exposed; do not incorrectly mark them
deferred. P9.5 monitoring/source acquisition is not exposed and stays NOT_MCP_EXPOSED.
No protocol phase may unlock a currently deferred capability by bypassing the Facade.

Required policy: `MCP_EXPOSED` is an explicit reviewed subset of the P12.2 approved
capabilities. READ and DECISION are candidates only; each must establish a safe
external typed projection and preserve its prerequisites/evidence lineage. In
particular, a caller-supplied prior decision or status is not authoritative merely
because its JSON validates. Withhold capabilities without a reviewed safe projection.
MUTATING is NOT_MCP_EXPOSED by default: specifically `revise_plan` is excluded.
Approval-required metadata alone does not make a capability MCP-safe. No approve=true,
MCP elicitation/sampling or authenticated/admin caller can replace explicit P12.5
approval or create P11 authority. Authentication != Human Approval != P11 Authority.
Any future mutation admission requires a separate trusted authorization transport
design and Review; it is not part of the initial P13 policy.

### Tool contract / execution requirements for later phases

- P13.1 chooses concrete stable machine-safe tool names and explicit mappings to
  capability IDs. No AgentIntent tools, Python handler/class/module names, decorated
  function scanning, filesystem discovery or automatic registry export.
- Use typed capability input or a reviewed typed MCP projection, with generated
  Pydantic JSON Schema. No handwritten parallel schema or arbitrary kwargs/callables.
  IDs/correlation and required context need explicit deterministic projection, not
  inference from message text, client metadata or transport sessions.
- Output projects the existing AgentCapabilityResult/canonical data/audit only:
  preserve execution status, result/reason/evidence/source refs and error category.
  Prefer structuredContent plus a JSON text representation where compatibility
  requires it; never a second McpEligibilityResult/business-decision authority.
- INELIGIBLE, UNKNOWN, NO_GAP and KEEP_CURRENT_PLAN remain successful tool execution
  when the Facade succeeds. Invalid/unsupported calls, missing context, unavailable
  dependencies and execution failure are errors; exact protocol/tool error mapping
  is a P13.3 contract, with sanitized messages and no secret/stack-trace exposure.
- MCP performs no LLM calls, natural-language routing, explanation, Graph invocation,
  business decisions, repository queries or business file reads. P12 Runtime retains
  complete Agent clarification/approval/resume; a missing MCP input is not MCP approval.
- Future package placement is an isolated MCP integration adapter beside the existing
  Runtime adapter; composition injects Facade dependencies outside both. No package,
  endpoint, server, handler or tool registry implementation is created in P13.0.

### SDK strategy and Gateway compatibility acceptance

Local metadata: Python project >=3.11; optional AgentArts SDK 0.1.6 already brings
official `mcp==2.3.0` and `mcp-types==2.3.0` through requirements-agentarts.lock.
Those installed transitive dependencies do not mean project MCP support exists.
The installed public version registry lists both target protocol eras; this is an
audit observation, not a dual-protocol execution test. No dependency changes now.
The [official Python v2 SDK](https://py.sdk.modelcontextprotocol.io/v2/) is the current
stable candidate. P13.2 must explicitly select/integrate/pin it using the existing
optional-dependency/lock strategy, keeping one consistent version with the Runtime
overlay. Do not invent competing dependency truth or force MCP onto core-only users.

Public SDK [legacy-client support](https://py.sdk.modelcontextprotocol.io/v2/run/legacy-clients/)
describes serving both eras and stateless HTTP; use public APIs and prove the selected
installed version in P13.2/P13.4 tests. No private transport imports, protocol patching,
custom negotiation or assumption that an old FastMCP example matches current v2.

The [AgentArts MCP Target contract](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_063.html)
requires tool capability/discovery. Gateway readiness requires standard tools/list,
tools/call, compatible negotiation and Streamable HTTP with JSON-safe input/results.
The Gateway guide currently restricts methods to initialize/tools/list/tools/call/ping,
does not accept batches or tool tasks, omits some tools/list metadata including
annotations/outputSchema/$schema/icons, and returns gateway responses as event streams.
P13.4/P13.5 must test this restricted path, schema usability, result/error fidelity and
JSON/text fallback where necessary. Do not claim Gateway preserves unsupported metadata
or supports the modern protocol. No custom auth, cloud provisioning or deployment is
implemented; production auth/IAM/secrets/image/scaling remain P16 responsibilities.

### Independent MCP compatibility gates

These are **DEFINED / NOT_YET_VALIDATED**, not runtime PASS claims at P13.0.
Existing P12 AgentArts A-L gates remain frozen and are a different gate family.

| MCP gate | Required evidence | Planned validation |
|---|---|---|
| A Capability Authority | Explicit MCP subset of P12.2 approved capabilities; no invented handlers | P13.1-P13.3/P13.6 |
| B Tool Schema Safety | Typed JSON-safe schemas/results; required context and evidence retained | P13.1-P13.4 |
| C Mutation Isolation | Mutation absent from catalog and calls rejected; auth/flags cannot approve | P13.1-P13.3/P13.6 |
| D Protocol Compatibility | AgentArts-compatible 2025-11-25 path actually works | P13.4/P13.5 |
| E Modern Compatibility | Same server boundary admits 2026-07-28 clients without business branching | P13.2/P13.4 |
| F Stateless Execution | Self-contained input; no MCP session business state or sticky execution dependency | P13.4/P13.6 |
| G Runtime/MCP Authority Parity | Same Facade/data/reason/evidence/Domain truth; compare capability results, not Agent prose | P13.3/P13.6 |
| H AgentArts Gateway Readiness | Local tools/list/tools/call/Streamable HTTP/negotiation/schema/result compatibility | P13.5/P13.6 |

P13.0 exit evidence is the audit/design/matrix/roadmap above plus unchanged P1-P12
regressions. Server/cloud compatibility itself is deferred to the listed phases,
not silently counted as tested or deployed. P13.1 contracts are recorded below.

P13.0 validation: full pytest 2175 passed, zero skipped; Ruff and diff check PASS.
Only README/ARCHITECTURE/DEVELOPMENT_PLAN changed; no production/test/dependency/data
change, MCP server, endpoint, SDK reconfiguration, cloud resource or commit.

### P13.1 MCP Tool Exposure Contract

Status: REVIEW_PASS. P13 remains CLOSED_FROZEN; P13.0 REVIEW_PASS.
P13.2/P13.3 are REVIEW_PASS; P13.4 is REVIEW_PASS; P13.5 REVIEW_PASS; P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12 stays CLOSED_FROZEN.

SDK-free contracts live in `competition_copilot/integrations/mcp/`: `contracts.py`
owns typed transport envelopes/schema generation; `registry.py` owns explicit
immutable definitions and exclusions. Package metadata includes this directory;
no dependencies were added. No MCP server, registration, RPC handler or HTTP path.

`McpToolDefinition` records stable name, CapabilityId, description, upstream access,
payload model, canonical result projection, approval metadata, exposure and mutation
policy, and authority source. `McpToolRegistry` stores frozen ordered tuples,
validates every admitted mapping against public Facade metadata/schema and rejects
duplicate names, duplicate capability aliases, invalid names, incomplete policy,
schema/access drift and mutation admission. Schema access returns fresh sorted
JSON objects, without rewriting required fields or array order. This registry is
server policy, never caller-supplied authorization or user-dependent discovery.

`McpToolInput[ExistingPayload]` requires caller-owned invocation_id,
source_request_id, CAPABILITY_ARGUMENTS arguments_ref, TOOL_RESULT result_ref and
unchanged typed payload. IDs never come from MCP sessions or identity metadata.
All inputs forbid extra fields. No business defaults, lookup, generated IDs or
approval flags are added. Aware time normalization follows existing contracts.
These fields define syntax; refs are not trusted merely because their shape passes.

`McpToolResult` contains exactly one canonical `AgentCapabilityResult` or a typed
pre-invocation error category. Canonical errors remain in the receipt; normal
INELIGIBLE/UNKNOWN/UNDETERMINED results remain successful execution. No Domain
result is copied into a parallel MCP truth model. Full payload, audit result/reason/
evidence/source refs, HttpUrl and aware datetimes survive JSON serialization.
Transport-only errors: INVALID_ARGUMENTS, UNKNOWN_TOOL, MISSING_CONTEXT,
CAPABILITY_NOT_EXPOSED, EXECUTION_FAILURE. No arbitrary exception prose. The mapping
to MCP wire errors/isError is deliberately deferred to P13.3.

#### Reviewed capability exposure matrix

Each payload/result below is the existing upstream contract, not a new business
model. All admitted outputs use the common McpToolResult canonical receipt envelope.
P4 inputs/outputs carry their existing List/Get names; no schemas are handwritten.

| CapabilityId | Access / Agent exposed | MCP exposed / stable tool name | Payload -> canonical data | Authority | Mutation risk / reason |
|---|---|---|---|---|---|
| list_competitions | READ / YES | YES / competition_list | ListCompetitionsInput -> ListCompetitionsOutput | P4 ListCompetitionsTool | NON_MUTATING / APPROVED |
| get_competition | READ / YES | YES / competition_get | GetCompetitionInput -> GetCompetitionOutput | P4 GetCompetitionTool | NON_MUTATING / APPROVED |
| list_competition_editions | READ / YES | YES / competition_editions_list | ListCompetitionEditionsInput -> ListCompetitionEditionsOutput | P4 ListCompetitionEditionsTool | NON_MUTATING / APPROVED |
| get_competition_edition | READ / YES | YES / competition_edition_get | GetCompetitionEditionInput -> GetCompetitionEditionOutput | P4 GetCompetitionEditionTool | NON_MUTATING / APPROVED |
| list_edition_tracks | READ / YES | YES / competition_tracks_list | ListEditionTracksInput -> ListEditionTracksOutput | P4 ListEditionTracksTool | NON_MUTATING / APPROVED |
| get_competition_track | READ / YES | YES / competition_track_get | GetCompetitionTrackInput -> GetCompetitionTrackOutput | P4 GetCompetitionTrackTool | NON_MUTATING / APPROVED |
| build_competition_snapshot | READ / YES | YES / competition_snapshot_build | BuildSnapshotInput -> CompetitionSnapshot | P9 CompetitionSnapshotBuilder | NON_MUTATING / APPROVED |
| check_eligibility | DECISION / YES | YES / eligibility_check | CheckEligibilityInput -> EligibilityDecision | P5 CompetitionEligibilityEvaluator | NON_MUTATING / APPROVED |
| get_recommendations | DECISION / YES | NO / none | RecommendCompetitionsInput -> RecommendationRankingResult | P6 scoring/ranking | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| analyze_skill_gap | DECISION / YES | NO / none | AnalyzeSkillGapInput -> SkillGapDecision | P7 SkillGapEngine | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| build_plan | DECISION / YES | NO / none | BuildPlanInput -> CompetitionPlan | P8 deriver/builder | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| diff_competition_snapshot | DECISION / YES | NO / none | DiffSnapshotsInput -> SnapshotDiff | P9 SnapshotDiffEngine | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| derive_competition_events | DECISION / YES | NO / none | DeriveEventsInput -> EventBatch | P10 engine/aggregator | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| analyze_event_impact | DECISION / YES | NO / none | AnalyzeEventImpactInput -> EventImpactAnalysis | P11 impact analyzer | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| decide_replanning | DECISION / YES | NO / none | DecideReplanningInput -> ReplanningDecision | P11 decision service | NON_MUTATING / TRUSTED_ARTIFACT_BOUNDARY_REQUIRED |
| revise_plan | MUTATING / YES; approval required | NO / none | ApplyApprovedRevisionInput -> PlanRevisionResult | P11 revision service / P12.5 bridge | MUTATING_NOT_EXPOSED / MUTATING_REQUIRES_HUMAN_FLOW |
| check_competition_changes | N/A / NO | NO / none | No Facade handler | Deferred aggregate | N/A / UPSTREAM_CAPABILITY_NOT_EXPOSED |
| explain_replanning | N/A / NO | NO / none | No Facade handler | Internal P12 explanation | N/A / UPSTREAM_CAPABILITY_NOT_EXPOSED |

READ review: six P4 operations read formal repository data through Tools; P9 builder
reads formal observations through existing Application composition. Snapshot building
does not persist. Eligibility accepts explicit profile facts/target only; P5 fetches
policy and decides truth. These eight contracts accept no caller-authored prior
decision/snapshot/plan authority. Caller profile assertions remain explicit inputs,
not authenticated verified identity or new official competition facts.

Other DECISION inputs require caller-prepared eligibility, requirements, snapshots,
diffs, events or plans. A trusted artifact admission/resolution design is not yet
available at MCP boundary; shape validation alone is insufficient. They are withheld,
not silently weakened, auto-exported or newly disabled in P12. Future admission
requires explicit contract review. P9.5 monitoring has no CapabilityId/handler and
stays excluded. Approval/clarification/routing/context/explanation helpers are not
tools. Authentication or model calls never grant approval; no mutation exception.

| MCP Gate | P13.1 evidence / disposition |
|---|---|
| A Capability Authority | PASS at contract level: explicit upstream subset; metadata/schema drift rejected |
| B Tool Schema Safety | PASS at contract level: typed envelopes, preserved fields, JSON schemas/roundtrips |
| C Mutation Isolation | PASS: mutation absent; attempted admission rejected |
| D AgentArts Protocol | DESIGN_PASS_RUNTIME_DEFERRED; protocol execution P13.4/P13.5 |
| E Modern Protocol | DESIGN_PASS_RUNTIME_DEFERRED; protocol execution P13.4 |
| F Stateless Execution | PASS at contract level: self-contained inputs, no MCP business session |
| G Runtime/MCP Authority Parity | DESIGN_PASS_INTEGRATION_DEFERRED; same Facade mapping, execution parity P13.6 |
| H Gateway Readiness | DESIGN_PASS_TRANSPORT_DEFERRED; SDK-specific wire/schema adaptation P13.2-P13.5 |

Contract tests cover explicit mappings, immutable/deterministic ordering and schemas,
duplicates/aliases, upstream subset, mutation/deferred rejection, required/unknown
fields, no internal/approval/session inputs, canonical time/URL/source/evidence and
real P5 INELIGIBLE/UNKNOWN receipt roundtrips. No server starts or RPC calls.

P13.1 validation: 25 targeted contract tests PASS; with P12.2 Facade regression,
57 passed. Full suite 2200 passed, zero skipped (including P12 Agent/Runtime and
frozen P1-P11 regressions); Ruff and diff check PASS. No P12 production changes,
business/source data changes, SDK dependency changes, server or cloud deployment.

### P13.2 MCP Server Core & Tool Catalog

Status: REVIEW_PASS. P13 CLOSED_FROZEN; P13.0/P13.1 REVIEW_PASS;
P13.3 REVIEW_PASS; P13.4 REVIEW_PASS; P13.5 REVIEW_PASS; P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12 remains CLOSED_FROZEN.

`integrations/mcp/server.py` isolates official SDK imports and exposes
`build_mcp_server(registry=None)` plus `to_sdk_tool(definition)`. Construction
creates no connection, port, credentials, business dependency or business session.
There is no module-level server instance, app startup or eager package export.
It uses the official [public low-level Server API](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server/)
to publish the existing exact schemas without decorator-generated tool definitions.
`on_list_tools` projects only the P13.1 registry tuple, preserving its eight names,
descriptions, ordering and full input/output schemas. Every request receives fresh
SDK models/schemas; client edits cannot alter later catalogs. No titles, annotations,
provider prompts, mutation hints or other metadata are invented.

At the P13.2 exit baseline, the call boundary was disabled (superseded by P13.3 below): known names returned an error result with
text `NOT_IMPLEMENTED_P13_3`, never success or a fabricated McpToolResult. Unknown,
excluded, typo and internal names return public MCP INVALID_PARAMS / UNKNOWN_TOOL.
No argument is interpreted, echoed or delegated. This is a stub, not P13.3 result/
execution mapping. No Facade execute, Graph, Repository, Domain authority or model
is called by the server. SDK protocol context is ignored and never becomes business
context. There is no application session/cache/persistence or reflection dispatch.

#### SDK dependency and local smoke strategy

- Selected official `mcp==2.3.0`, already installed with the P12.7 environment;
  the current installed SDK supports the public Server / Client / Tool APIs used.
  `mcp-types==2.3.0` stays aligned. SDK integration is now intentional, not inferred
  from an AgentArts transitive dependency. No provider or cloud SDK was added.
- `pyproject` adds optional `mcp` extra only. `requirements-mcp.lock` owns MCP SDK
  pins and its resolved dependencies over the existing core lock. It does not
  require LangGraph or AgentArts. `requirements-agentarts.lock` includes this shared
  overlay instead of repeating those pins; versions are unchanged. The Agent lock
  stays unchanged. Dependency tests reject conflicting versions across includes
  and verify active pins against installed metadata.
- Project minimum remains Python >=3.11. This is a CPython 3.12 Windows development
  resolution, not an ARM64 certification. Windows pywin32 is conditional; native
  dependency portability and production images remain P16 gates.
- Public `Client(server)` runs in-process for tests; no stdio entrypoint is needed
  in this phase. Tests use real SDK tools/list and disabled/unknown call requests,
  not direct calls to our list handler. No external network or credentials.
- Installed SDK era metadata and official v2 guidance remain the compatibility
  selection evidence. These in-process tests do not certify 2025-11-25 / 2026-07-28
  HTTP negotiation or AgentArts Gateway compatibility. P13.4/P13.5 retain those gates.
  No Streamable HTTP app, stdio loop, remote connection or production deployment.

| MCP Gate | P13.2 disposition |
|---|---|
| A Capability Authority | PASS: actual SDK catalog comes only from P13.1 approved registry |
| B Tool Schema Safety | PASS: full typed schemas retained through SDK catalog JSON |
| C Mutation Isolation | PASS: no mutation/internal tools listed; all execution disabled |
| D AgentArts Protocol | SERVER_CORE_READY_PROTOCOL_TEST_DEFERRED |
| E Modern Protocol | SERVER_CORE_READY_PROTOCOL_TEST_DEFERRED |
| F Stateless Execution | PASS: no business session or business state in server/catalog |
| G Runtime/MCP Authority Parity | CATALOG_MAPPING_PASS_EXECUTION_DEFERRED |
| H Gateway Readiness | CATALOG_READY_TRANSPORT_DEFERRED |

Tests cover public SDK construction/listing, registry/schema fidelity, injected
metadata, mutation/internal absence, every known tool disabled, unknown names,
determinism across fresh instances and independent SDK connections, detached JSON,
dependency/import boundaries and local Graph execution with SDK imports blocked.
The P13.1 static test now limits its SDK-free rule to the frozen contract modules;
the new architecture test separately enforces server-only SDK imports.

Validation: 22 new server/architecture tests PASS; with P13.1 contracts and P12.2
Facade regression, 79 passed. Full suite 2222 passed, zero skipped, including P12
Agent/Runtime and frozen authority regressions. Ruff and diff check PASS. No real
network/cloud/model calls, business execution or source-data changes were required.

### P13.3 Safe Tool Execution & Result Mapping

Status: REVIEW_PASS. P13 CLOSED_FROZEN; P13.0-P13.2 REVIEW_PASS.
P13.4 REVIEW_PASS; P13.5 REVIEW_PASS; P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P12 remains CLOSED_FROZEN.

The SDK-free `integrations/mcp/execution.py` adds frozen `McpToolDispatcher` and a
deterministic execution guard. `build_mcp_server(registry=None, facade=None)` now
accepts an explicitly composed P12.2 Facade; missing dependencies fail closed.
No default Repository/data paths, profiles, targets or IDs are invented. Import
and server construction still do not execute capabilities or access network.

Execution chain:

```text
SDK tools/call -> exact registry lookup -> upstream/mutation policy guard
-> typed McpToolInput validation -> controlled CapabilityArguments projection
-> injected Facade metadata guard -> CapabilityFacade.execute (once)
-> typed receipt / correlation validation -> McpToolResult -> SDK CallToolResult
```

The guard independently checks formal P12.2 metadata and injected Facade metadata:
exposed flag, access, approval, mutation policy, capability availability and payload
schema must agree. Even a deliberately corrupted registry cannot admit revision
by disguising MUTATING as READ. Caller arguments cannot supply capability_id,
approve/admin flags, invocation intent, session identity or extra fields. Required
fields remain required. Prior decision/snapshot/plan capabilities stay withheld
under the frozen exposure matrix; no additional tools are admitted.

Compatibility detail: the frozen CapabilityInvocationRequest requires AgentIntent.
A fixed internal label per admitted CapabilityId supplies this legacy field; it
does not recognize intent, select capabilities, parse text or invoke Graph. Caller
input never chooses this label. All business IDs and artifact refs come unchanged
from explicit arguments. Only the existing Facade executes business authorities.
There is no AgentRequest, routing/explanation model, Domain implementation import,
Repository query, natural-language merge or approval bridge in the MCP path.

`map_tool_result_to_mcp` in the isolated SDK server module serializes the existing
McpToolResult as structured_content and deterministic JSON text. No second business
result models, summaries or recomputed outcomes. is_error derives only from transport
error or canonical CapabilityStatus.ERROR, never Eligibility/SkillGap/Replanning
status. INELIGIBLE/UNKNOWN are successful calls; UNDETERMINED/NO_GAP/KEEP would likewise
remain unchanged in any canonical success receipt, but their currently withheld
capabilities are not newly exposed. Full result identity, data, audit reasons,
evidence/source refs, source URL/type/observed_at/verification and timezones survive.

Error mapping reuses the frozen P13.1 contract; tool names/input/output schemas/order
and descriptions remain unchanged, including the existing error enum:

| Condition | Safe response |
|---|---|
| Unknown/unlisted name, including guessed capability ID or mutation name | UNKNOWN_TOOL; SDK INVALID_PARAMS protocol error, preserving P13.2 behavior |
| Missing/invalid/extra arguments or non-JSON-compatible input | INVALID_ARGUMENTS; structured error, zero Facade executions |
| Mutation/approval-required, disabled exposure, metadata/schema drift or unavailable composition | CAPABILITY_NOT_EXPOSED; structured error, zero executions |
| Canonical Facade ERROR receipt | Preserve canonical category/IDs/refs; is_error=true, error prose normalized to its stable code |
| Unexpected exception, malformed/mismatched receipt or mapper failure | EXECUTION_FAILURE; no exception text, paths or secrets; no replay |

No MCP business state, result cache, conversation or retry loop. One call executes
Facade at most once; mapping failure never re-executes business work. Independent
client calls remain independent, not durable idempotent sessions. Transport context
and metadata are ignored, including admin/approved/session-like fields. HTTP,
protocol-era compatibility, Gateway connectivity and production remain deferred.

| MCP Gate | P13.3 disposition |
|---|---|
| A Capability Authority | PASS: explicit registry -> sole existing Facade execution |
| B Schema Safety | PASS: strict typed input, canonical JSON structured/text result |
| C Mutation Isolation | PASS: catalog exclusion plus independent execution guard |
| D AgentArts Protocol | EXECUTION_READY_PROTOCOL_DEFERRED |
| E Modern Protocol | EXECUTION_READY_PROTOCOL_DEFERRED |
| F Stateless Execution | PASS: arguments/dependencies only, metadata independent |
| G Authority Parity | PASS for direct Facade vs MCP canonical result; full lifecycle extension P13.6 |
| H Gateway Readiness | EXECUTION_READY_TRANSPORT_DEFERRED |

Tests use real SDK Client(server) calls, real seed Repository/P4/P5/P9 and fake
failures only for boundary cases. They verify P5 INELIGIBLE/UNKNOWN direct-Facade
parity, all admitted reads, strict inputs, capability/approval/name injection,
registry corruption, mutation count zero, valid count one, receipt mismatches,
safe exceptions, mapper failure without replay, JSON, unchanged catalogs and
independent sessions with transport metadata. No dependency or seed/policy changes.

Validation: 63 new dispatcher/SDK integration cases plus one new architecture check;
combined MCP/P12.2 targeted regression 143 passed. Full suite 2286 passed, zero
skipped, including relevant P4-P11 and frozen P12 regressions. Ruff and diff check
PASS. Registry and input/output contract schemas are unchanged; no P13.4 work,
cloud/Gateway resources, new dependency or git commit.

### P13.4 Streamable HTTP & Protocol Compatibility

Status: REVIEW_PASS. P13 remains CLOSED_FROZEN; P13.0-P13.3 REVIEW_PASS.
P13.5 REVIEW_PASS; P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P12 remains CLOSED_FROZEN.

The canonical targets are the reviewed P13.0 matrix, not a new version decision:
modern `2026-07-28`, AgentArts compatibility `2025-11-25`. `integrations/mcp/http.py`
records those target constants and exposes `build_streamable_http_app(server)`.
It calls the official SDK public `Server.streamable_http_app` with
`stateless_http=True, json_response=True`, returning the SDK ASGI app/lifespan at
`/mcp`. No custom JSON-RPC parser, negotiation patch, FastAPI business API, session
store, retry wrapper or production server startup. Dependencies/locks are unchanged.

One core Server, Registry, Dispatcher and result mapper serve both eras. Versions,
handshake/discover, HTTP headers/content types and protocol context stay at the SDK
transport edge. The business path is still the frozen P13.3 Facade projection.
No protocol versions enter Agent/Application/Domain/Tool input or business results.
SDK default localhost Host/Origin checks remain enabled; no production auth/CORS/
IAM/rate-limit policy is added. Authentication never becomes approval authority.

Actual public SDK clients over HTTP verify:

| Path | Public client behavior | Verified result |
|---|---|---|
| AgentArts-compatible | Client(..., mode="legacy") initialize handshake | negotiated 2025-11-25; tools/list and read/decision calls PASS |
| Modern | Client(..., mode="auto") server/discover | negotiated 2026-07-28; tools/list and read/decision calls PASS |
| Unsupported version | public session.send_discover("2099-01-01") | SDK HTTP 400 / -32022 Unsupported protocol version; zero executions |

Client traces assert actual initialize/discover and subsequent version headers;
this is protocol execution evidence, not merely SDK version metadata or schema tests.
No client requests are routed to the in-process direct dispatcher for HTTP tests:
they use official streamable_http_client and httpx2.ASGITransport with the SDK app.
The same core's direct local Client path is retained for parity comparison.

Stateless HTTP produces no Mcp-Session-Id responses, including legacy requests.
Caller-supplied session headers cannot supply a missing student or override explicit
IDs. Transport metadata, admin/approved hints and session-like values never reach
business context. Two concurrent independent client calls retain their own student,
request and authoritative eligibility result. No conversation, approval or last
result is stored. SDK protocol negotiation/hosting state is not business state.

HTTP 200 is retained for normal P5 INELIGIBLE/UNKNOWN and typed argument-error tool
results; transport/protocol failures remain distinct. Result structured JSON and
deterministic text preserve canonical status, identities, reasons/evidence/source
refs, HttpUrl, source metadata and aware timestamps. Capture time offset input also
roundtrips through existing UTC normalization. Mutation/internal/unknown calls fail
closed and malformed requests return safe SDK errors. No new exposed capability.

Parity compares every Tool field for catalogs and complete McpToolResult plus
is_error for execution. Exclusions are only HTTP headers, JSON-RPC envelopes and
catalog protocol/cache metadata; no business field is ignored. Both protocols and
the local path return equal canonical P5 receipts. Each HTTP tools/call executes
Facade once; initialization/discovery/list never execute it. A controlled response
loss after execution propagates the SDK's ReadError inside ExceptionGroup; the
caller has unknown execution outcome and neither transport wrapper nor server
retries business execution. No recovery/idempotency claim is made.

Tests run entirely in-process ASGI with socket connect/bind/DNS blocked after OS
event-loop initialization. `http://localhost:0` is a logical test URL, not a bound
port or remote endpoint. No internet, cloud, credentials, stdio server or production
daemon. JSON response mode is ordinary MCP transport, not LLM token/business SSE
streaming. Production hosting/ARM64/auth/scaling/hardening remain P16.

| MCP Gate | P13.4 disposition |
|---|---|
| A Capability Authority | PASS: same Registry -> Dispatcher -> Facade |
| B Tool Schema Safety | PASS: complete HTTP catalog schemas equal frozen registry/local catalog |
| C Mutation Isolation | PASS: no mutation catalog entry; HTTP attempts rejected with zero executions |
| D AgentArts Protocol Compatibility | PASS: actual 2025-11-25 initialize/list/call over HTTP |
| E Modern Compatibility | PASS: actual 2026-07-28 discover/list/call over HTTP |
| F Stateless Execution | PASS: no protocol session business state |
| G Authority Parity | PASS: local/HTTP share unchanged Facade receipts and frozen P13.3 authority path |
| H Gateway Readiness | TRANSPORT_PROTOCOL_READY_GATEWAY_TEST_DEFERRED |
| I Protocol Semantic Parity | PASS: modern/AgentArts-compatible complete business receipts equal, excluding only protocol envelopes |
| J Transport Isolation | PASS: HTTP/session/protocol metadata cannot supply identity or approval |

MCP Gates I/J extend the independent MCP gate family; they do not replace frozen
P12 AgentArts gates with the same letters. P13.5 will test Gateway-specific contract
constraints; no real AgentArts Gateway/MCP Target is connected or provisioned here.

Validation: 29 HTTP compatibility cases plus one new protocol-edge architecture
check; HTTP/architecture targeted run 35 passed. Combined MCP/P12.2 targeted
regression 173 passed. Full suite 2316 passed, zero skipped; Ruff and diff check
PASS. No change to P13.1-P13.3 Registry/Dispatcher/mapper/contracts, frozen P12 or
Domain authorities, dependency locks or source data. No cloud resources or commit.

### P13.5 AgentArts Gateway Compatibility

Status: REVIEW_PASS. P13 CLOSED_FROZEN; P13.0-P13.4 REVIEW_PASS.
P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12 remains CLOSED_FROZEN.

Frozen target: 2025-11-25, Streamable HTTP, initialize -> tools/list -> typed schema
ingestion -> tools/call. Every call is self-contained; protocol sessions are not
business sessions. P12.7 Runtime hosts the full Agent/Graph; Gateway calls approved
capabilities through Registry -> Dispatcher -> Facade, without Agent/LLM execution.

The [Gateway restrictions](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_024.html)
and [MCP Target contract](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_063.html)
were rechecked on 2026-10-19 without changing P13.0 targets. The local test profile
uses initialize/list/call (ping remains allowed), no batch/tasks, and models omitted
tools/list annotations/outputSchema/$schema/icons. Gateway-facing responses use
text/event-stream; this does not turn the Target into a legacy SSE endpoint.

Test-only `mcp_gateway_support.py` wraps the real `/mcp` Target using official SDK
clients and an SDK Server as a forwarding fixture. SDKs own both HTTP/protocol
boundaries. The fixture discovers upstream tools rather than owning another registry,
forwards each call once, and omits unsupported catalog metadata. It is a restricted
contract model, not a Huawei implementation/emulator or evidence of cloud acceptance.
No new production adapter, endpoint, auth implementation or dependency is necessary.

All discovered input schemas remain equal to P13.1, pass Draft 2020-12 validation,
and retain nested types/refs, enums, required fields and extra-forbidden policy.
The SDK's already locked jsonschema dependency is used only in tests. Catalogs and
canonical SHA-256 fingerprints remain equal across repeat discovery and caller
identity headers. No mutation, approval workflow or Agent internal tools are added.

The unchanged P13.3 mapper supplies canonical structured receipts and matching JSON
text. Tests additionally remove structuredContent conservatively to verify the JSON
text fallback; this is a loss-tolerance test, not a claim that Huawei drops that field.
No outputSchema or optional metadata is required for result truth. Gateway read,
P5 INELIGIBLE/UNKNOWN and snapshot calls preserve complete canonical result identity,
reasons, evidence/source refs, source URLs/metadata and aware UTC serialization.

Gate K compares complete canonical receipts and is_error across direct Facade,
local MCP, modern HTTP and the Gateway-compatible profile. Exclusions are only
protocol envelopes/HTTP metadata and unsupported discovery metadata; no canonical
business field is excluded. Each legitimate call executes the Facade once; direct
Facade comparison is a separate explicit call on independent dependencies. Unknown,
mutation, approval and injected-argument attempts execute it zero times.

Gate L proves fake auth/admin/model-selection/session/user hints cannot supply
student/plan identity, human approval, mutation authority or Domain truth. Independent
connections share the same Target core/dependencies with fresh SDK transport hosts
(SDK lifespans are single-use). Missing context stays invalid, previous students do
not fill later calls, and errors retain safe codes without exception text. No retry,
result cache, sticky session, conversation state or new business dispatch is added.

| MCP Gate | P13.5 disposition |
|---|---|
| A Capability Authority | PASS: same approved Registry/Dispatcher/Facade |
| B Tool Schema Safety | PASS: discovery ingestion and JSON receipts |
| C Mutation Isolation | PASS: absent from catalog, denied on call |
| D AgentArts Protocol | PASS: frozen 2025-11-25 path retained |
| E Modern Compatibility | PASS: P13.4 regression and four-path parity |
| F Stateless Execution | PASS: self-contained calls and metadata isolation |
| G Authority Parity | PASS: same Facade canonical results |
| H AgentArts Gateway Readiness | PASS at local protocol/tool contract level |
| I Protocol Semantic Parity | PASS: modern/Gateway-compatible receipts equal |
| J Transport Isolation | PASS: metadata cannot supply business context |
| K AgentArts Gateway Semantic Parity | PASS: Facade/local/modern/Gateway canonical equality |
| L Gateway Authority Isolation | PASS: identity/auth/model/session cannot authorize business mutation |

MCP K/L extend the independent MCP gate family, not the frozen P12 AgentArts gates.
Default tests block socket connect/bind/DNS and use only in-process ASGI. Real Gateway
smoke: NOT_RUN; no safe preconfigured cloud test environment was used. It is optional,
not a default test dependency or exit blocker. No credentials, Target/account IDs,
cloud resources, public hosting, Gateway SDK pollution or production config added.
P16 retains deployment/auth/IAM/SWR/Secrets/hardening. P13.6 is REVIEW_PASS.

Validation: 25 Gateway contract tests passed; combined MCP/P12.2 regression 198
passed; full suite 2341 passed, zero skipped. Ruff and diff check PASS. Only two
new integration test files and three documentation files changed. No production
code, registry, dispatcher, mapper, dependency lock, frozen authority or seed/policy
data changed; no cloud resource, real Gateway smoke or git commit.

### P13.6 Real MCP Integration & Authority Preservation

Status: REVIEW_PASS. P13 CLOSED_FROZEN; P13.0-P13.5 REVIEW_PASS.
P13 Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P14 CLOSED_FROZEN. P12 CLOSED_FROZEN.
This is integration evidence, not P13 Final Review or phase closure.

No new MCP surface or business implementation. The same eight P13.1 tools and
schemas remain frozen. Real tests use `composition.build_seed_agent`: formal
JsonSeedCompetitionRepository/data/seed, JsonEligibilityPolicyProvider/data/eligibility,
P4 tools, real P5-P11 deterministic authorities and one Capability Facade. MCP
server/HTTP/Gateway fixtures receive that very Facade instance; Agent and the
AgentArts Runtime Adapter retain the formal Graph path. No MCP-to-Graph shortcut.

`test_mcp_authority_parity.py` exercises every admitted tool, with P5 negative and
UNKNOWN cases, across direct Facade, public Agent, Runtime Adapter, local MCP,
modern HTTP, AgentArts-compatible HTTP and the P13.5 Gateway profile. Complete
AgentCapabilityResult JSON is equal, including execution/business status, IDs,
reasons, evidence/source refs and source metadata. Comparison excludes only Agent
wording/workflow envelopes and transport metadata, never canonical receipt fields.
MCP calls do not increase routing/explanation model counts. Models are deterministic
offline fixtures only on the Agent path; no real model/cloud is called.

Official policy coverage is partial: legitimate real results include INELIGIBLE
and UNKNOWN. No synthetic positive EligibilityResult or policy completion is used
to claim official eligibility. Real P9 snapshot remains read-only and explicitly
caller-timed, with aware UTC JSON normalization. P9 diff, P9.5 monitoring and P10
event tools remain NOT_EXPOSED_BY_DESIGN. The exposed P9 snapshot is not a mutation.

Recommendation/SkillGap/Plan Build remain NOT_EXPOSED through MCP. Supplemental
tests run real P5-derived contexts through Agent/P6 scoring/ranking, actual repository
and skill requirements through P7, and that actual decision through P8 planning.
P6 soft scoring inputs remain explicitly test-only fixtures from the existing P12
harness; no production weights or decisions are invented. The same composed Facades
then deny guessed MCP calls for all three withheld authorities without executing them.
Planning creates a canonical result only; no persistence or mutation is introduced.

`test_mcp_real_integration.py` covers all four MCP paths with mutation/approval/name
guesses, capability/approval-request argument injection, invalid context and sanitized
internal exceptions. Invalid calls execute no Facade; legitimate calls execute once,
with no automatic retry. Gateway admin/auth/user/session hints neither authorize
revision nor fill missing student/plan context. Concurrent independent inputs retain
their own student/request/result; successive competition reads retain explicit IDs.
Catalog/schema remain stable after attacks. Existing P13.3/P13.4 regressions retain
the distinction between canonical business negatives, tool failures and transport loss.

`mcp_real_support.py` blocks sockets/DNS after Windows event-loop setup and hashes
all data files before/after every new real integration case. Seed, policy and skill
requirements are immutable. No DB/Redis/session/conversation/approval store, new
dependency, production code change, cloud resource or credential is added.

| MCP Gate | P13.6 disposition |
|---|---|
| A Capability Authority | PASS: unchanged admitted Registry -> Dispatcher -> Facade |
| B Tool Schema Safety | PASS: unchanged schemas and JSON receipts |
| C Mutation Isolation | PASS: catalog absence and zero execution on attacks |
| D AgentArts Protocol Compatibility | PASS: legacy HTTP/Gateway and P13.4 regression |
| E Modern Compatibility | PASS: modern HTTP and P13.4 regression |
| F Stateless Execution | PASS: independent calls and concurrency isolation |
| G Runtime/MCP Authority Parity | PASS: actual Agent/Runtime receipts equal MCP receipts |
| H AgentArts Gateway Readiness | PASS at local protocol/tool contract level |
| I Protocol Semantic Parity | PASS: complete modern/legacy receipt equality |
| J Transport Isolation | PASS: session/header metadata cannot supply identity |
| K Gateway Semantic Parity | PASS: Gateway/local/HTTP/Facade canonical equality |
| L Gateway Authority Isolation | PASS: no auth/model/session mutation authority |
| M End-to-End Authority Preservation | PASS: all entries retain the same composed deterministic authority lineage |
| N Cross-entry Semantic Consistency | PASS: complete canonical receipts equal across all entries |

MCP M/N extend the independent MCP gates, not the frozen P12 AgentArts gate family.
Real Gateway smoke remains NOT_RUN and is optional; the local profile is not Huawei
cloud acceptance. Deployment/auth/IAM/SWR/Secrets remain P16. No P14 work or commit.

Validation: 19 new P13.6 integration cases passed; combined P13.1-P13.6/P12.2/P12.8
targeted regression 231 passed. Full suite 2360 passed, zero skipped, including P12
routing/approval/explanation/Runtime and P4-P11 regressions. Ruff and diff check PASS.
Only three new test/support files and three documentation files changed; production
code, dependency locks, Registry/Dispatcher/mapper and official data are unchanged.

### P13 closure and frozen scope

P13 = CLOSED_FROZEN. P13.0-P13.6 = REVIEW_PASS.
P13 Final Review = REVIEW_PASS. P13 Closure = CLOSED_FROZEN.
Final Review verified a clean committed tree, all seven phase commits, 2360 passing
tests with zero skipped, Ruff PASS and diff check PASS. Closure changes docs/status only.

Frozen scope includes the MCP compatibility baseline, explicit tool exposure contract,
official SDK server core, deterministic tools/list, safe tools/call execution,
structured canonical result mapping, Streamable HTTP, modern 2026-07-28 and
AgentArts-compatible 2025-11-25 protocol support, local AgentArts MCP Gateway contract
compatibility, real integration, authority preservation and cross-entry semantic
consistency. MCP Gates A-N pass within their documented scope; Gateway acceptance
is local protocol/tool contract evidence, not a real cloud deployment claim.

Frozen MVP is Tools only. Resources, Prompts, Sampling and Elicitation are not P13
capability surfaces. MUTATING capabilities remain absent from MCP catalogs and
execution. Explicit Human Approval stays in the P12 Agent workflow. MCP session IDs,
transport authentication, Gateway identity/model selection and metadata cannot grant
business, human approval or mutation authority. All entries share P12.2 Capability
Facade and existing deterministic Domain authorities, with no persistent business session.

Deferred scope is downstream work, not incomplete P13:

| Phase | Deferred scope | Status |
|---|---|---|
| P14 | Frontend + Runtime invocation compatibility | CLOSED_FROZEN |
| P15 | Evaluation + Local/AgentArts semantic parity evaluation | NOT_STARTED |
| P16 | Production AgentArts deployment/hardening; production IAM, SWR, Secrets, observability, scaling, load testing and security hardening | NOT_STARTED |

Real Gateway smoke remains NOT_RUN and optional. No production resources, durable
MCP business sessions, MCP mutation support or frontend implementation are claimed.
P12 remains CLOSED_FROZEN; P4-P12 frozen semantics are unchanged.

## P14 - Agent-native Frontend & Runtime Invocation Compatibility

- **Status:** CLOSED_FROZEN; P14.0-P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12/P13 remain CLOSED_FROZEN.
- **Goal:** evidence-grounded user journey via stable API/AgentRequest/AgentResponse.
- **Deliverables:** Workspace/Discover/Journey/Profile interfaces and compatible local/runtime invocation.
- **Acceptance:** evidence, clarification/approval/resume and errors survive transport; API/UI never invent Domain truth.
- **Deferred:** social/team marketplace, automatic registration/payment/submission.

### P14 subphase roadmap and exit boundaries

Canonical status is this document. Lifecycle remains NOT_STARTED ->
IMPLEMENTED_AWAITING_REVIEW -> REVIEW_PASS; whole-phase closure is CLOSED_FROZEN.
Commit provenance stays in Git. Baseline definitions do not claim later deliverables.

| Subphase | Deliverable / exit boundary | Status |
|---|---|---|
| P14.0 Frontend & Runtime Invocation Compatibility Baseline | Existing frontend/runtime audit; architecture, contract/security baseline, gates and roadmap only | REVIEW_PASS |
| P14.1 Runtime Invocation Client Contract | Shared typed invocation/resume transport interface, controlled public projections, schema generation/validation strategy and fake client tests | REVIEW_PASS |
| P14.2 Frontend App Shell & Conversation State | Initialize the selected empty-directory stack; shell, conversation/input, workflow/loading/error state with fake Runtime client | REVIEW_PASS |
| P14.3 Clarification + Human Approval UX | Explicit clarification, APPROVE/REJECT, safe resume and HITL boundary | REVIEW_PASS |
| P14.4 Grounded Result / Evidence / PlanDiff Rendering | Structured canonical artifacts, explanation, reasons, evidence/sources and supplied diff presentation | REVIEW_PASS |
| P14.5 Local Runtime Invocation Integration | Trusted local composition/hosting of existing P12 invocation handler; safe browser projections, authorized continuation/artifact resolution and real Agent calls | REVIEW_PASS |
| P14.6 AgentArts Runtime Invocation Compatibility | Same client contract through configured AgentArts transport; local compatibility tests, no required production cloud deployment | REVIEW_PASS |
| P14.7 Real Frontend E2E & Cross-runtime Parity | Discovery/eligibility/clarification/recommendation/skill-gap/plan/approval/reject/error/fallback flows and key Local/AgentArts semantic comparisons | REVIEW_PASS |
| P14 Final Review | Whole-phase frontend/contract/HITL/transport/authority audit | REVIEW_PASS |
| P14 Closure | Status/documentation finalization after Final Review PASS | CLOSED_FROZEN |

### P14.0 audit and compatibility baseline

The following inventory records the baseline before P14.1; current contract/tooling
evidence is recorded in the P14.1 section below.

P13 closure gate PASS: P13 CLOSED_FROZEN, P13.0-P13.6 REVIEW_PASS, Final Review
REVIEW_PASS and Closure CLOSED_FROZEN. No P12/P13 production contracts are changed.

#### Existing frontend inventory

Audit on 2026-10-19 found `frontend/` empty: no package.json, lockfile, src/public,
framework configuration, README, app entry, API client, pages or components. Current
UI state is EMPTY (the P14.0 README adds documentation only). Existing framework,
language, package manager, dev/build commands and test framework: NONE/NOT_AVAILABLE.
Existing frontend lint/test/build scripts cannot be run because no manifest exists.
Available local tools are Node v24.14.1 and npm 11.11.0; no install is performed.

Because the directory is empty, select a minimal React + TypeScript + Vite client,
with npm/package-lock as the planned package manager/lock strategy. The
[official Vite guide](https://vite.dev/guide/) provides the react-ts template.
Versions, actual scripts, lint and test choices are verified/pinned during P14.2
initialization, not invented here. P14.1 can define SDK-free client contracts first.
No framework/package files, UI, codegen toolchain or test framework are initialized.

#### Public P12 contract inventory (actual source, not a new UI business schema)

| Contract/source | Existing fields and constraints |
|---|---|
| agents.contracts.AgentRequest | request_id, user_message; optional conversation_id; context with explicit student_id/profile_ref/competition_id/edition_id/track_id/plan_ref. Context IDs and exact Plan reference must agree |
| agents.contracts.AgentResponse | request_id, intent, outcome, message, optional clarification/approval_request/error, audit, plan_refs. No embedded generic capability-result payload |
| WorkflowStatus | Enum includes RECEIVED, NEEDS_CLARIFICATION, READY_TO_ROUTE, WAITING_FOR_APPROVAL, READY_TO_EXECUTE, COMPLETED, FAILED; AgentResponse accepts only NEEDS_CLARIFICATION/WAITING_FOR_APPROVAL/COMPLETED/FAILED with matching payload |
| ClarificationRequest | clarification_id, source_request_id, reason, fields, question |
| human_contracts.ClarificationResponse | clarification_id, source_request_id, nonempty values, aware submitted_at; values support explicit target/student/plan/intent/invocation/arguments references/context, never inferred by UI |
| ApprovalRequest | approval_request_id, source_request_id, invocation_id, action, summary, before_plan, optional proposed_after_plan, decision/scope/resolution/input/instruction refs, audit and aware created_at |
| ApprovalResponse | approval_request_id, source_request_id, decision APPROVE or REJECT, aware submitted_at, optional comment. This is a submission, not authorization |
| HumanMessage | interaction_id, source_request_id, text, aware submitted_at; not an automatic approval shortcut |
| AuditReferences / ResultReference | Canonically ordered results and reason references; ReferenceKind includes EVIDENCE, SOURCE, PLAN_DIFF, approval and clarification refs. PlanReference preserves plan_id/version/content_digest/target |
| domain.replanning.PlanDiff | Canonical before/after Plans, decision, evaluated_at, changes and optional status_change; trigger_event_ids derive from the decision. Render only when authorized artifacts supply it; UI never computes it |
| AgentState / GraphInput / HumanResume | Internal workflow/arguments/authority context. HumanResume's approved_by_ref/current_plan/executed_at are trusted server inputs, never browser authority fields |

All contracts use extra-forbidden validated Pydantic models and canonical JSON/time
handling. Frontend consumes these contracts; it does not recreate Domain decisions,
AgentState or a parallel FrontendEligibilityResponse/UiRecommendationDecision.

#### Actual P12.7 runtime and local hosting inventory

- Public local core: `CompetitionCopilotAgent.invoke(AgentRequest) -> AgentResponse`;
  `run_turn/resume` keep internal GraphInput/GraphTurn at the server boundary.
- Pure transport entry: `AgentArtsRuntimeAdapter.invoke(payload)`, with injected
  trusted RuntimeBindings. `app.create_app(adapter)` builds official AgentArtsRuntimeApp
  and an async @app.entrypoint. Its SDK-local `/invocations` route is already tested
  in-process. There is no standalone configured local frontend runtime server or
  default authorized bindings/resolver; P14.0 creates none. MCP `/mcp` is separate.
- Runtime input is `AgentArtsInvocationEnvelope`: either `{"request": <AgentRequest>}`
  or `{"continuation_ref": "authorized-reference", "clarification": <ClarificationResponse>}`,
  with `approval` or typed `message` as alternatives. New request and resume are
  exclusive; resume requires exactly one reply. A `query`-only body is not this contract.
- Runtime output is `AgentArtsInvocationResult`: response: AgentResponse OR error:
  RuntimeError, plus continuation: GraphInput exactly for pending clarification/approval.
  Absent optional fields may serialize as null. Runtime error codes are
  INVALID_RUNTIME_PAYLOAD, CORE_VALIDATION_ERROR, CORE_EXECUTION_ERROR,
  RUNTIME_DEPENDENCY_ERROR. AgentResponse.error remains a separate core error category.
- The handler ignores RequestContext for identity/consent/evidence; JSON serialization
  uses existing Pydantic contracts. No transport metadata becomes business input.

**Browser projection gaps identified, with implementation deferred:** the current
runtime continuation is an internal GraphInput, not an opaque reference returned to
the browser. Never expose/generate frontend types for that full object. P14.1 must
define a minimal controlled presentation/transport projection; P14.5 must retain
pending state at an authorized trusted boundary and return a scoped opaque handle,
then resolve/revalidate it for the existing continuation_ref input. The handle is
not authorization. Use the same rule for Local and AgentArts; keep P12 core unchanged.
No durable/session database or refresh-resume guarantee is introduced by this baseline.

AgentResponse carries audit/result/PlanDiff refs, not all canonical result bodies or
source metadata. P14.1/P14.4/P14.5 must define authorized, minimal presentation access
to existing canonical artifacts/receipts at the invocation composition boundary.
Do not assume an artifact lookup API exists, replay capabilities to rebuild results,
parse explanation text, call MCP, or invent missing evidence/diffs. Missing/unavailable
artifacts remain visibly unavailable. No extra business API is designed here.

#### Invocation and transport baseline

Conceptual `RuntimeInvocationClient.invoke(AgentRequest) -> AgentResponse`, with
explicit resume support preserving the public HITL contracts and safe continuation
handle. Runtime errors/continuation metadata stay in typed transport outcomes; the
formal interface and projection names are P14.1 work, not implemented classes.
LocalRuntimeTransport and AgentArtsRuntimeTransport share this contract and error
taxonomy. LOCAL/AGENTARTS select transport only, never business UI branches.

The frontend primary path is Runtime -> P12 Adapter -> Agent -> Graph -> Facade.
P13 MCP remains for structured MCP consumers/Gateway; no frontend tools/list/tools/call
path replaces Agent workflow. Neither transport creates a second business dispatcher.

Official high-code [ExecuteRuntime](https://support.huaweicloud.com/api-agentarts/InvokeRuntime1.html)
uses POST `/runtimes/{runtime_name}/invocations`. The
[routing contract](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_131.html)
preserves application bodies/responses; the actual Competition Copilot envelope
above remains authoritative. Verified 2026-10-19. Runtime name/base URL/optional
endpoint selection are injected transport/deployment configuration, not hardcoded
production names or Domain fields. Authorization and X-Hw-Agentarts-Session-Id are
platform transport concerns; no key/token is embedded in a browser bundle.

P14 allows Browser -> trusted backend/BFF -> AgentArts Runtime. Direct browser-to-cloud
is not presumed safe. Transport authentication is distinct from Human Approval and
P11 authority. Public config may expose mode/local URL/display settings; AK/SK,
API keys, service tokens, Authorization secrets never belong in VITE_/NEXT_PUBLIC_/
PUBLIC_ variables, source, localStorage or browser-generated authority. Production
credential provisioning, auth/IAM/routing/security policies remain P16.

P12 currently returns one awaited JSON result; streaming baseline is
NON_STREAMING_PRIMARY. Platform streaming capability does not define a P12 token or
event schema. Streaming is OPTIONAL/DEFERRED; no fake character timers or P12 changes.

#### UX, evidence and session safety

NEEDS_CLARIFICATION renders clarification.question/fields/reason and submits explicit
ClarificationResponse values against the same source_request_id/clarification_id.
No silent target/profile guess. WAITING_FOR_APPROVAL renders the supplied action,
summary, exact Plan version/scope/refs/audit, and available authoritative impact/diff.
APPROVE and REJECT must be distinct explicit actions; closing a panel, continuing,
sending a message or ambiguous text never approves. UI submits ApprovalResponse;
only server/core validates pending ID, actor, scope, action, version and P11 bridge.
Browser cannot set HUMAN_APPROVED, approved_by_ref or execution authority.

There is no public REJECTED WorkflowStatus. A validated reject currently completes
normally (COMPLETED, retained audit); UI preserves the explicit submitted REJECT and
matching structured response/audit. It must not derive rejection from message text or
invent a new Domain status. Rejected/stale/tampered input validation failures stay errors.

Separate business outcomes (INELIGIBLE/UNKNOWN/UNDETERMINED/NO_GAP/KEEP_CURRENT_PLAN),
clarification, approval wait, valid rejection, Agent errors, runtime invocation errors,
network/transport errors and invalid-response/contract errors. AgentResponse.outcome,
typed interaction payload and authoritative artifacts drive rendering; no regex/text
routing on message. Retry is an explicit transport concern, never automatic replay
of approval/mutation or an assumption that connection loss means no execution.

P14 MVP plans conversation/input, workflow status, clarification panel, approval panel,
structured results, reasons/evidence/sources and error/retry surfaces. P14.4 renders
only provided canonical source_url/source_type/observed_at/verification_status and
actual PlanDiff before/after/trigger/reason. Existing grounded explanation is display
content; frontend makes no new LLM call, score, eligibility, gap, plan or diff decision.
Raw JSON dumps are development debug only, not the final UI experience.

UI history is current-page presentation state, not long-term Agent memory, an approval
ledger or Domain history. Browser/AgentArts session IDs are correlation only, never
student/competition/plan/approval IDs. Returned handles, structured context and all
browser submissions are client-controlled and revalidated server-side. No durable
resume on refresh is claimed; lost/expired context must be reported explicitly.

#### Contract generation and compatibility evidence strategy

Backend Pydantic is the contract source of truth. P14.1 should export a deliberately
selected public JSON Schema set and generate TypeScript types with controlled
validation/fixtures; safe view models may rename/wrap presentation fields without
duplicating business models. Do not generate AgentState/GraphInput/HumanResume or
maintain a drifting handwritten Domain interface. No codegen dependency is added now.
Contract mismatches fail visibly; no guessed fields or complex version negotiation.

Local and AgentArts comparison fixes AgentRequest, trusted dependencies and continuation
context. Compare outcome, canonical business artifacts, reasons/evidence/source refs,
Plan identity/diff, clarification/approval and errors. Only HTTP envelope details,
correlation/session IDs, timing and Gateway metadata may differ; they cannot change
business semantics. P14.7 proves key flows; P15 owns systematic metrics/benchmarks,
formal evaluation and quality regression, not P14.0.

| Frontend Gate | Required acceptance | Planned evidence |
|---|---|---|
| A Presentation Authority | UI never recomputes P5-P11 truth | P14.2/P14.4/P14.7 |
| B Contract Fidelity | Public request/response/HITL semantics preserved | P14.1/P14.5-P14.7 |
| C HITL Integrity | Explicit clarification/approval/reject; no browser authority | P14.3/P14.7 |
| D Runtime Transport Isolation | Local/AgentArts differences stay in adapters | P14.1/P14.5/P14.6 |
| E Runtime Semantic Parity | Same input/context yields equivalent authoritative outcomes | P14.6/P14.7 |
| F Evidence Grounding | Only authoritative supplied artifacts/reasons/sources rendered | P14.4/P14.7 |
| G Client Security | No production secrets or browser-created approval authority | P14.1/P14.3/P14.6 |
| H Session Isolation | UI/transport sessions are not Domain identity/trusted state | P14.3/P14.5-P14.7 |
| I Error Semantics | Business/HITL/Agent/runtime/transport/contract outcomes distinct | P14.1-P14.7 |
| J Deployment Boundary | Invocation compatibility only; production hardening remains P16 | P14.6/P14.7 |

Gates A-J are DEFINED / IMPLEMENTATION_EVIDENCE_DEFERRED at P14.0; no UI/runtime PASS
is claimed. They are independent from frozen P12 AgentArts and P13 MCP gate families.
P16 retains production AgentArts deployment, IAM/auth, Secrets, ARM64/SWR, observability,
scaling, rate limiting, load/security hardening and cost controls. P15/P16 remain
NOT_STARTED. No frontend implementation, new runtime endpoint, cloud connection,
feature, test framework, dependency or commit is part of P14.0.

Validation: backend full suite 2360 passed, zero skipped; Ruff and diff check PASS.
Frontend existing lint/test/build: NOT_AVAILABLE (no package.json/scripts). Only
DEVELOPMENT_PLAN, ARCHITECTURE, backend README and the new frontend baseline README
changed; no production code, tests, dependencies, runtime routes or UI files added.

### P14.1 Runtime Invocation Client Contract

Status: REVIEW_PASS. P14.0 remains REVIEW_PASS; P14.2 REVIEW_PASS;
P14.3 is REVIEW_PASS; P14.4 REVIEW_PASS; P14.5 REVIEW_PASS; P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12/P13 remain CLOSED_FROZEN.

The previously empty frontend now has a contract-only TypeScript/npm toolchain,
not a React/Vite app or UI. Versions are locked; Node's test runner supplies offline
fake transport tests, TypeScript checks types and Prettier checks formatting.
The build script is type checking only, not a frontend bundle. No runtime endpoint,
fetch adapter, live Local/AgentArts invocation or production authentication is added.

RuntimeInvocationClient.invoke(AgentRequest) -> Promise<AgentResponse> validates
JSON projection and response before UI consumption. resume uses the existing typed
P12 clarification/approval/message envelope; exchange also exposes the safe opaque
continuation_ref transport handle. RuntimeTransport separates mechanics from
semantics; LocalRuntimeTransport and AgentArtsRuntimeTransport are interfaces, with
FakeRuntimeTransport returning presets and recording calls. AUTO_RETRY=OFF;
NON_STREAMING_PRIMARY. AbortSignal cancellation never means approval REJECT.

Synchronization strategy A: checked-in generated selected Pydantic JSON schemas,
TypeScript types and P12-validated fixtures. scripts/export_frontend_contracts.py
regenerates them; --check and backend tests detect drift offline. No parallel
business contracts, Domain models, internal AgentState/GraphInput/HumanResume,
MCP or generic-client AgentArts SDK dependency. Ajv/ajv-formats validate strict JSON
schemas without defaults/coercion/unknown-field removal; relational guards preserve
response/request identity, public outcomes, interaction and audit lineage.

PublicRuntimeResult is a controlled hosting projection: unchanged P12 response OR
RuntimeError plus continuation_ref for pending HITL. Internal raw continuation is
rejected (completed null is accepted). The trusted P14.5 hosting layer still must
retain, scope, authorize and resolve pending GraphInput; no such implementation or
durable session promise is claimed. Browser refs/replies confer no trust. Server/core
continues to validate actor, request/approval IDs, exact Plan/version/scope/action.

AgentResponse supplies refs, not embedded business results/evidence/source/PlanDiff
bodies. Fixtures preserve those public refs, canonical aware timestamps and URL
strings. Negative-result fixtures are preset public response messages/audit refs,
not new business enums or computed decisions. Actual artifact rendering/access
remains P14.4/P14.5. Core FAILED is a valid AgentResponse; safe runtime error envelopes
become RUNTIME_ERROR. TRANSPORT_ERROR, CONTRACT_ERROR and ABORTED remain separate
from HITL, normal rejection and business outcomes. Unknown versions/shapes fail closed.

Public config only selects mode/baseUrl/runtimeName; no credentials, arbitrary headers
or identity/approval metadata. Transport metadata is never merged into AgentRequest
or AgentResponse. No environment-specific business behavior, automatic ID generation,
client approval authority or business calculation. Real transport security stays P16.

Contract-level Frontend Gates A-D and F-J: PASS (no UI/real Runtime claim).
Gate E: CONTRACT_PASS_REAL_RUNTIME_DEFERRED. P14.3/P14.4/P14.5-P14.7 must still
supply explicit UX, artifact rendering and real integration evidence. P15 formal
metrics and P16 deployment/hardening remain NOT_STARTED.

Validation commands and directory responsibilities are in frontend/README.md.
Targeted coverage includes valid/negative/core-failed outcomes, clarification,
APPROVE/REJECT continuations, invalid nested shapes/enums/identity/authority injection,
runtime/transport errors, exactly-one send/no retry, cancellation, concurrent calls,
fake Local/AgentArts parity, metadata isolation, JSON refs/time and contract drift.

Validation before remediation: frontend 28 tests passed (zero skipped), lint PASS, build/typecheck PASS;
backend full suite 2362 passed (zero skipped), targeted contract drift 2 passed;
Ruff, generated-contract --check and git diff --check PASS. No UI, live Runtime
connection, backend production change or Git commit is included.

P14.1 directed remediation completed; subsequent re-review PASS. Status: REVIEW_PASS.
The review's three blockers are addressed in consumer validation/config only:
canonical request IDs before send/comparison, nonblank normalized response messages,
normalized unique milestone IDs, and strict required config types before format checks.
Config whitespace policy is rejection for baseUrl/runtimeName; no implicit coercion,
new auth, endpoint, UI or real Runtime connection. P12/P13 remain unchanged.

Public behavioral validator audit (Pydantic remains authority):

| Public contract | Non-schema behavior / consumer evidence |
|---|---|
| AgentRequest / StableId / AgentResponse.message | Strip using Pydantic Unicode whitespace semantics, reject blank/non-string; canonical IDs used for response correlation without changing caller objects |
| PlanReference (context, approval before/proposed-after, response plan_refs) | Normalize IDs, reject duplicate milestone IDs after normalization, sort; preserve existing aware updated_at offset; response Plan refs remain unique/ordered |
| AgentContract public HITL dates | Aware JSON dates normalized UTC with microsecond precision, without importing internal state |
| ClarificationRequest/Response | Nonempty reply values, unique/sorted fields, request identity; nested public profile string/list/skill-ID structural checks and typed invocation reference/approval-required validation |
| ApprovalRequest/Response | Typed decision/scope/input/instruction refs, unique/sorted instructions, evidence/reason lineage; explicit APPROVE/REJECT, no HUMAN_APPROVED generation |
| AuditReferences / AgentResponse | Unique sorted refs/reasons, bound reason result, allowed outcome/payload and interaction identity consistency |

The exporter derives normalization hints from public field annotations; 47 behavioral
cases obtain expected accept/reject/canonical results from real P12 Pydantic validation.
Both frontend client tests and backend fixture parity tests use those cases, including
empty/whitespace/non-string message/ID, normalized duplicate milestones, malformed
HITL/audit, canonical dates and nested clarification models. Config tests cover missing,
undefined/null/boolean/number/array/object/blank runtimeName and strict LOCAL baseUrl.
No P5-P11 business rule is reproduced. Gate B contract fidelity re-review PASS.

Remediation validation: frontend 86 tests passed, lint/build (typecheck) PASS;
backend behavioral/drift tests 49 passed; full suite 2409 passed, zero skipped.
Ruff, generated --check and git diff --check PASS. Review reproduction inputs now
reject invalid messages/milestones/config and accept canonical request identity.
P14.1 REVIEW_PASS; P14.2 REVIEW_PASS. See P14.3 below for current continuation status;
P14.4 REVIEW_PASS; P14.5 REVIEW_PASS; P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN.

### P14.2 Frontend App Shell & Conversation State

Status: REVIEW_PASS. P14 remains CLOSED_FROZEN; P14.0/P14.1 REVIEW_PASS.
P14.3 is REVIEW_PASS; P14.4 REVIEW_PASS; P14.5 REVIEW_PASS; P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12/P13 CLOSED_FROZEN.

Implemented the previously selected React + TypeScript + Vite single workspace,
retaining npm/package-lock and the Node test runner (tsx supplies JSX loading).
React reducer/hooks provide deterministic local state, without a state library.
jsdom/Testing Library supply offline DOM tests; jsdom is pinned to a version compatible
with existing Node. Build now emits a real Vite bundle; dev/preview bind localhost only.
No runtime endpoint or backend production code changed.

ConversationEntry is a USER/AGENT/SYSTEM presentation record with separate rendering
identity, request association and validated AgentResponse. UI request status
IDLE/SUBMITTING/READY/ERROR is separate from Agent workflow outcome. Structured
outcome/request payloads alone drive completed/HITL/status shells, never explanation
wording. Optional student ID is explicit user context, not a browser/session inference.
New request IDs are UI caller-owned UUIDs, injectable for tests; retry reuses the same
request/ID and does not duplicate the user's entry. No capability selector or decisions.

Pending synchronous lock plus disabled input prevents double invocation; reducer
attempt/request correlation and unmount abort/generation guards discard stale results.
Business negative and core Agent FAILED remain valid responses, distinct from
transport/runtime/contract/abort surfaces. Retry is explicit only; invalid payloads
and internal exceptions never become Agent messages. State is current-page memory
only, without storage or durable resume claims.

At P14.2 delivery, App consumed RuntimeInvocationClient.invoke. Fake presets are composed
at src/demo and src/main, with fixed outcomes independent of user text/context; only
caller identity is rebound for protocol correlation. Developer-only scenario controls
cover completed, negative, clarification, approval and transport/runtime/contract errors.
Production build hides that control but remains fake-driven, not deployed/connected.

At P14.2 delivery, HITL states displayed summaries only; P14.3 below adds typed
continuation controls. P14.4 below adds readonly result/evidence/diff presentation;
real Local/AgentArts invocation remains P14.5/P14.6.
No MCP/client LLM/business rules/secrets/persistent business state; P15/P16 unchanged.

Frontend Gates A-D/F-J: PASS at this shell/fake boundary.
Gate E: CONTRACT_PASS_REAL_RUNTIME_DEFERRED.
Gate K - UI State Determinism: same validated response/actions produce identical
presentation/workflow state; pure reducer and explanation-independence tests PASS.
Gate L - Duplicate Invocation Safety: accidental repeated submit while pending invokes
Runtime once; synchronous double-submit test PASS.

Validation: frontend 103 tests passed (86 P14.1 contract regressions + 17 workspace
and state tests), zero skipped. Lint and Vite build PASS; backend full suite 2409
passed, zero skipped. Ruff, generated contract --check and git diff --check PASS.
Local headless Chrome smoke verified desktop 1440px, narrow 390px (no horizontal
overflow) and a completed fake invocation, without browser exceptions. Temporary
browser/server were closed; screenshots remain ignored local preview artifacts.
No backend production, P12/P13 contract or business changes; no Git commit.

### P14.3 Clarification + Human Approval UX

Status: REVIEW_PASS. P14 CLOSED_FROZEN; P14.0-P14.2 REVIEW_PASS.
P14.4 REVIEW_PASS; P14.5 REVIEW_PASS; P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN.
P12/P13 CLOSED_FROZEN.

Re-audited unchanged P12 public models and P12.7 envelope, including real validators:

| Contract | Actual public fields / boundary |
| --- | --- |
| ClarificationRequest | clarification_id, source_request_id, reason, fields, question; no public choices |
| ClarificationResponse | existing clarification_id/source_request_id, requested values, aware submitted_at |
| ClarificationValues | competition_id/edition_id/track_id, student, plan_ref, intent, invocation, arguments_json; no writable APPROVAL_CONTEXT |
| ApprovalRequest | approval/source/invocation IDs, PLAN_REVISION action, summary, before/optional after PlanReference, decision/scope/resolution/input/instruction refs, audit, aware created_at |
| ApprovalResponse | existing approval_request_id/source_request_id, APPROVE or REJECT, submitted_at, optional comment; no Plan/scope echo or authority field |
| Continuation | continuation_ref plus exactly one real clarification/approval/message; no new AgentRequest, GraphInput, invented token or business defaults |

Implemented requested-field forms with empty initial values, typed/scoped nested JSON
inputs when required, and public-contract validation through the unchanged P14.1
client. Unsupported APPROVAL_CONTEXT stays disabled for trusted-server handling.
Original context is readonly; no client conflict resolution, target inference or
extra values. WAITING_FOR_APPROVAL displays readonly action/Plan version/target and
lineage IDs, with equally visible explicit APPROVE and REJECT buttons. Text/Enter
outside an explicitly focused action never grants approval. No optimistic Plan
mutation/success; authoritative replies alone update workflow presentation.

Workspace now uses RuntimeInvocationClient.exchange to retain its existing safe
public wrapper. Independent interaction snapshot, current-token/proposal comparison,
synchronous consumption, pending lock and existing generation/unmount guards prevent
wrong, stale or repeated continuations. Original request and proposal IDs remain
unchanged, including replacement approvals within the same request. Browser data
remains client-controlled; server/core must revalidate actor, Plan/version/scope and
authorized handle. No full AgentState or trusted browser authority is introduced.

Continuation failures leave execution unconfirmed and consume UI controls; no auto
retry or continuation retry button. Starting a new request invalidates old controls
without claiming rejection/cancellation of the old server workflow. REJECT stays a
normal response. UI timeline expressions are presentation events, never Domain events.
Preset FakeRuntimeTransport sequences cover clarification, APPROVE/REJECT completion
and errors without computing Plan diffs or business decisions. No real Runtime,
MCP, secrets, backend changes, full evidence/PlanDiff UI or production auth/deployment.
Real authorized hosting remains P14.5/P14.6; P15/P16 boundaries are unchanged.

Frontend Gates A-D/F-L: PASS at the fake/UI boundary. Gate E remains
CONTRACT_PASS_REAL_RUNTIME_DEFERRED. New Gate M - HITL Authority Preservation:
collect user expressions only, never create human/mutation/trusted continuation
authority. New Gate N - Continuation Identity Integrity: preserve current request,
proposal and exact Plan/scope/action lineage through the actual public contract,
with stale/replacement/replay guards. Both are covered by targeted offline tests.

Validation: `npm run test:hitl --prefix frontend` 18 passed; full frontend 121 passed,
zero skipped; TypeScript/Prettier lint and Vite build PASS. Backend full suite 2409
passed, zero skipped; Ruff and generated contract `--check` PASS. Headless Chrome
verified desktop 1440px and narrow 390px (scroll width 390px), empty clarification
input, fake clarification completion and normal REJECT completion, with zero browser
exceptions. Preview screenshots/profile remain ignored local artifacts and temporary
browser/server were closed. `git diff --check` PASS. No backend or frozen P14.1 runtime
contract changes, new dependency, real Runtime connection or Git commit.

### P14.4 Grounded Result / Evidence / PlanDiff Rendering

Status: REVIEW_PASS. P14 CLOSED_FROZEN; P14.0-P14.3 REVIEW_PASS.
P14.5 REVIEW_PASS; P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P12/P13 CLOSED_FROZEN.

Actual contract audit:

| Data | Actual shape and presentation boundary |
| --- | --- |
| Public result | AgentResponse.message, workflow outcome, audit.results/reasons, plan_refs; no embedded business result/Evidence/PlanDiff bodies |
| Reasons | ReasonReference(result kind/ref_id, reason_code); Domain results carry canonical reason_codes |
| Evidence | Existing Evidence(code, message, optional field/value/source); P11 ReplanningEvidence carries event/Plan/milestone/source-field refs |
| Sources | SourceMetadata(source_url HttpUrl, source_type, aware observed_at, verification_status verified/pending/rejected) |
| PlanDiff | Complete before/after CompetitionPlan, ReplanningDecision with trigger impacts, evaluated_at, optional milestones collection change and status_change; no per-item ADD/REMOVE/UPDATE operations |
| Uncertainty | Eligibility unknown, SkillGap undetermined, Recommendation uncertainty, Replanning undetermined remain structured business outcomes |

Implemented pure ResultPanel, BusinessStatus, ReasonList, EvidenceList, SourceMetadata
and PlanDiffView. Conversation retains original grounded explanation; result UI never
parses it, re-explains with an LLM, scores candidates, checks eligibility or computes
skill gaps/diffs. Reasons have static wording plus raw-code fallback. Evidence is
escaped data; HTTP(S)-only source links use safe rel attributes. Source type, exact URL,
UTC display plus original aware ISO, and verification status are shown independently.
Missing body/evidence/source remains unavailable rather than invented.

Because P12 publicly returns refs only, P14.4 adds a separate optional readonly
presentation attachment, not another Agent/business API or a change to P14.1 wire
validation: request_id plus exact audit ref/model/value entries. Existing Pydantic
Domain models generate selected schema/types and canonical offline fixtures. The
consumer guard checks structural shape and current request/ref/model binding before
rendering, rejects duplicate/mismatched attachments and clears stale evidence. This
does not establish artifact existence/truth or replicate Domain behavioral validators.
P14.4 originally supplied fake attachments only. P14.5 below now supplies current
canonical receipt snapshots revalidated with original Domain models through local hosting.

PlanDiff renders supplied complete before/after milestone collections with all public
task fields, Plan IDs/versions/status and declared status_change, not a client-computed
per-item classification. Removed tasks stay visible on the before side; added/changed
tasks appear on the after side. Trigger events, reasons, evidence refs and provided
event sources remain linked. Empty/no-op diffs retain their actual unchanged outcome;
plan_refs alone never produce a diff. WAITING_FOR_APPROVAL never renders a final diff
and approve clicks do not fabricate one. Rejection remains a normal response.

Generated fixtures use unchanged Domain constructors and existing backend test
factories offline; they are synthetic data, never official facts or browser business
computation. P14.1 Runtime client/HITL contracts and P12/P13 production code unchanged.
No dependency, storage, real Runtime, MCP, LLM, production deployment or P14.5 work.

Frontend Gates A-D/F-N: PASS at this offline consumer boundary. Gate E remains
CONTRACT_PASS_REAL_RUNTIME_DEFERRED. Gate O - Grounded Rendering Integrity: each
visible claim belongs to current explanation/ref/artifact, without inferred missing
facts. Gate P - PlanDiff Authority Integrity: supplied diff only, no browser comparison.
Gate Q - Source Presentation Safety: untrusted data is escaped and unsafe schemes
are not executable links. All three have targeted offline tests.

Validation: targeted result UI tests 21 passed; full frontend 142 passed, zero skipped.
TypeScript/Prettier lint and Vite build PASS (non-blocking minified chunk-size warning,
about 504 kB / 140 kB gzip). Backend artifact generation/parity cases: 12 passed;
full backend suite: 2421 passed, zero skipped. Ruff, both contract exporters' --check
and git diff --check PASS. Chrome checked the actual fake result/uncertainty/source
and supplied PlanDiff pages; desktop result area expanded for reading, 390px narrow
viewport/scroll width both 390px, two supplied milestone collection panels visible,
zero browser exceptions. Temporary browser/server closed; screenshots/profile are
ignored local artifacts. No P12/P13/P14.1 runtime production changes or Git commit.

### P14.5 Local Runtime Invocation Integration

Status: REVIEW_PASS. P14 CLOSED_FROZEN; P14.0-P14.4 REVIEW_PASS.
P14.6 REVIEW_PASS; P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. P12/P13 CLOSED_FROZEN.
P14.4 was cleanly committed (5b7b68c) before implementation; no commit in this phase.

Audit found no existing local HTTP application or route. The new SDK-free stdlib
loopback adapter exposes only POST /runtime/invoke. It reuses the existing P12.7
pure AgentArtsRuntimeAdapter.invoke directly, not its optional SDK app. Each session
uses build_seed_agent and the real CompetitionCopilotAgent, compiled LangGraph,
same CapabilityFacade, JsonSeed repository and P4-P11 authorities. No second Agent,
capability HTTP endpoints, MCP path or frozen contract/business changes.

LocalRuntimeTransport posts the unchanged P12 envelope once, forwards AbortSignal
and returns the runtime body to the unchanged RuntimeInvocationClient validator.
Composition selects LOCAL through public config; Vite provides a same-origin dev
proxy. Components still depend only on the generic client. An explicit minimal
context section supplies target IDs and optionally the exact public demo PlanRef.
Request IDs normalize through the existing public-contract guard before UI correlation.
Browser/session/transport metadata supplies no business identity or authority.

HTTP delivery separates runtime from an optional readonly presentation attachment;
there is no second AgentResponse. The server projects only exact current audit refs
from real Facade receipts, validates selected original Domain models and never exports
GraphInput, trusted inputs or authority. Actual TOOL_RESULT bodies include P4 details,
P5 eligibility, P6 rankings, P7 skill gaps and P8 Plans. Existing renderers present
source/time/enum/reason/PlanDiff data without recomputing decisions or differences.
Missing artifacts remain unavailable rather than fabricated.

The local developer composition uses deterministic intent proposals and the existing
P12.6 explanation fallback; no external LLM/network/cloud is required. Prerequisite
P5/P7 calls use the same Facade for real P6/P8 prepared inputs. Synthetic profiles,
controlled Event/Plan proposal and generated public PlanRef are explicit local demo
inputs, never official history. Policy absence remains UNKNOWN, not a guessed rule.
Controlled revision requires the selected exact current PlanRef and explicit approval;
P12.5 alone binds fresh authority and P11 alone returns the actual status-change Diff.
REJECT returns normally without mutation. Seed/proposal files remain unchanged.

This is one local development operator, not production or multi-user authorization.
Private canonical continuation frames stay in bounded expiring server memory behind
opaque random single-use handles. Source request/current PlanRef checks and serialized
invocations block stale/cross-request/replayed continuations. Cancellation or a failed
continuation gives no proof of execution outcome and no automatic retry. Current Plan
catalogue/session state is ephemeral and resets at restart; no durable Plan persistence.
HTTP error bodies omit traceback/paths/env/exception repr. Exact dev origins and loopback
binding are supported; production IAM, deployment and hardening remain P16.

Startup: `.\backend\.venv\Scripts\python scripts/run_local_runtime.py` from root;
frontend: `npm run dev --prefix frontend`, with frontend/.env.example copied to
.env.local to select LOCAL. AgentArts transport compatibility is implemented below; production deployment remains P16.

Gates A-D/F-Q retain their consumer/authority boundaries. Gate E is
LOCAL_RUNTIME_PASS_AGENTARTS_DEFERRED. Gate R - Local Runtime Integration Integrity:
client -> Local HTTP transport/adapter -> original pure handler -> real Agent/Graph/
Facade. Gate S - Local End-to-End Semantic Fidelity: captured actual Local responses
replayed through FakeRuntimeTransport retain response and result/HITL rendering
semantics. No production deployment or systematic P15 parity claim.

Validation evidence: backend Local integration 13 tests; frontend Local HTTP/UI
integration 12 tests, including completed, negative, clarification, approval waiting,
APPROVE/REJECT, actual PlanDiff, canonical whitespace request IDs, identities, sources,
aware times, enums, failures, duplicate safety and Fake/Local rendering parity.
Backend full regression: 2434 passed, zero skipped. Full frontend: 161 passed, zero
skipped. TypeScript/Prettier lint, Vite build, Ruff, both frontend contract exporters
and Local fixture --check PASS. Build reports a non-blocking 524 kB chunk warning.
Chrome/Vite-proxy smoke passed discovery, structured clarification and explicit approval
with actual PlanDiff: five expected HTTP POSTs, zero browser exceptions, 390px viewport
and scroll width. Browser fetch receiver binding has an explicit regression assertion.
Temporary browser/backend/Vite processes closed; screenshots remain ignored under tmp/.

### P14.6 AgentArts Runtime Invocation Compatibility

Status: REVIEW_PASS. P14 CLOSED_FROZEN; P14.0-P14.5 REVIEW_PASS.
P14.7 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P12/P13 CLOSED_FROZEN. P15/P16 unchanged.
Entry gate: P14.5 was cleanly committed as 1b0487c and working tree was clean.
No commit made in this phase.

Official contract reverified on 2026-10-20 (API page updated 2026-09-30):
POST /runtimes/{runtime_name}/invocations; runtime name is a 2-48 character path
segment, lower-case letters/digits/hyphen, letter first and alphanumeric last.
Required platform headers are Authorization and X-Hw-Agentarts-Session-Id; this
JSON client also supplies Content-Type/Accept application/json. Optional endpoint
query selects a version. Optional gateway user header is correlation only. Official
MCP session/protocol headers are intentionally unused in this separate HTTP Agent
path; X-Sdk-Content-Sha256 applies to IAM signing, which is not implemented here.
Application-defined request/response bodies pass through; example input/output
fields are not a replacement for P12.7. Official statuses are 200/401/404/500;
403 is also handled as transport authorization failure. HTTP supports JSON and SSE,
but this implementation retains NON_STREAMING_PRIMARY and rejects SSE as a contract
mismatch. Official source links and the full chain are in ARCHITECTURE.md.

Implemented browser AgentArtsRuntimeTransport and composition selection using the
same RuntimeInvocationClient/response/artifact validators. Only public runtime name,
bridge URL and mode enter the bundle. Cloud origin and Bearer credential remain
server-side, with strict validation, secret-free repr and no credential logging.
API Key/OAuth Bearer forwarding is supported; production IAM signing and credential
management remain P16. The bridge accepts only its configured runtime route, uses
existing Local body-drain/origin/parser behavior, validates the P12 envelope and
forwards the original JSON once. No Local implementation file or frozen contract,
Agent/Domain/MCP code changed. No business endpoint, second Agent or business model.

The optional hosted SDK factory reuses P12.7 create_app around the existing private
host, which calls original pure adapter -> CompetitionCopilotAgent -> LangGraph ->
same CapabilityFacade -> P4-P11. Only public runtime/presentation data leaves the
host; opaque handles retain canonical private state. Raw GraphInput is rejected at
the transport boundary. Actor/current Plan/time and new authority stay in P12.5;
cloud Authorization/session/gateway user metadata never supplies them.

Upstream auth/resource/server/network/timeout failures map to stable sanitized
transport codes. No upstream diagnostic/header/secret echo or redirect. Valid
runtime errors remain distinct from business outcomes and contract mismatches.
No auto retry; AbortSignal/timeout do not imply REJECT, UNKNOWN or non-execution.
Uncertain continuation execution is not automatically replayed.

Offline official-shape HTTP harness forwards to real core/authorities. Fixed time
and nonce generation are test-only dependencies; no business outcomes/diffs are
computed by harness. Exact payload, public response, artifacts and rendered parity
cover completed, INELIGIBLE/UNKNOWN/UNDETERMINED, P6/P7/P8, clarification/resume,
approval wait, APPROVE/REJECT and actual authoritative P11 status Diff. Changed
session, consumed handles, normal/HITL duplicate clicks, unknown reason prototype
names, error categories, secret isolation and SDK entrypoint are covered.

Gates A-D/F-S retain boundaries. Gate E: LOCAL_AGENTARTS_RUNTIME_PARITY_PASS at the
official-shape offline compatibility boundary, not a real-cloud/deployment claim.
Gate T - AgentArts Runtime Transport Compatibility: official path/headers and P12
payload pass-through. Gate U - Local / AgentArts Runtime Semantic Parity: exact
responses/grounding/HITL/Diff/presentation under identical dependencies. Gate V -
AgentArts Credential Isolation: credentials remain server-only. Gate W - AgentArts
Session Authority Isolation: metadata grants no Domain/continuation authority.

Validation: frontend AgentArts targeted 15 passed; full frontend 176 passed, zero
skipped; lint/build PASS. Backend AgentArts targeted 34 and Local regression 19
passed together (53). Full backend: 2474 passed, zero skipped. Ruff, exporters
--check and git diff --check PASS. AGENTARTS-mode build/credential-sentinel scan PASS;
Chrome/Vite proxy smoke made five expected loopback gateway POSTs with no browser
exceptions and no 390px horizontal overflow. Browser/backend/Vite processes closed;
screenshots are ignored local artifacts. Default fake build retains its non-blocking
524 kB chunk warning; configured AgentArts build is about 500 kB. No real cloud smoke implemented; default tests require no real credential,
cloud or external network. P14.7 broader acceptance is implemented below; P15 evaluation
and P16 production hardening remain NOT_STARTED.

### P14.7 Real Frontend E2E & Cross-runtime Parity

Status: REVIEW_PASS. P14 CLOSED_FROZEN; P14.0-P14.6 REVIEW_PASS.
P14 Final Review REVIEW_PASS; P14 Closure CLOSED_FROZEN. P12/P13 CLOSED_FROZEN; P15/P16 unchanged.
Entry gate: P14.6 cleanly committed as 012eda3; working tree was clean before work.
No commit made in this phase. Implementation completion does not close P14 or grant
its Final Review/Closure; P14.7 Review PASS does not grant whole-phase closure.

Scope is verification of the existing architecture. No production code, Agent,
Domain service, contract, transport or business algorithm changed. The shared
test-only HTTP harness adds serial reset and Local fault controls, not product
routes; regular requests still use the same real P12.7/Agent/LangGraph/Facade and
P4-P11 authorities. Deterministic time/intent/nonces remain test dependencies.

`frontend/tests/e2e.test.tsx` drives actual Workspace input/send, clarification
and explicit approval/reject controls through both real RuntimeTransport classes
and RuntimeInvocationClient. Its comparator in `tests/e2e/support.ts` includes
complete business identities, payloads, responses/artifacts, conversation entries,
workflow/HITL state and rendered results. Only transport metadata is excluded.

| Scenario | Local | AgentArts-compatible |
|---|---|---|
| Discovery completed | PASS | PASS |
| Eligibility negative | PASS | PASS |
| UNKNOWN / UNDETERMINED | PASS | PASS |
| Recommendation / diagnosis / planning | PASS | PASS |
| Clarification request | PASS | PASS |
| Structured clarification resume | PASS | PASS |
| Approval wait | PASS | PASS |
| Explicit APPROVE | PASS | PASS |
| Explicit REJECT / no fake diff | PASS | PASS |
| Grounded evidence/source metadata | PASS | PASS |
| Actual P11 status PlanDiff | PASS | PASS |
| Contract-invalid response | PASS | PASS |
| Runtime reference validation failure | PASS | PASS |
| HTTP/socket transport failure | PASS | PASS |
| Gateway auth/not-found/timeout | Not applicable | PASS |

The actual controlled P11 fixture supports active -> cancelled status Diff, not
a newly invented milestone change scenario. Full P14.4 renderer regressions retain
the existing milestone collection semantics. Browser requests never send
HUMAN_APPROVED or mutate a Plan; pending approval displays no optimistic final diff.
Normal/clarification/APPROVE/REJECT double actions each make one HTTP invocation.
Explicit adversarial approval replay reaches backend validation and fails closed.
Stale workflow callbacks and edited public plan version/request identity cannot send.

Whitespace request IDs canonicalize before HTTP and correlation. Unknown reasons
__proto__/constructor/FUTURE_REASON_CODE survive both transports safely. Existing
source URL/type/aware timestamp/verification metadata is rendered unchanged.
Hostile evidence/unsafe URL and changed explanation text are explicitly fault-injected
security tests, not Domain-produced conclusions. Status/grounding remains structured.

Independent frontend roots and same transport session do not mix business IDs,
HITL or evidence. Reversed/late delivery, unmount/abort and next-request rendering
do not overwrite current results. No durable browser AgentState/continuation,
automatic retry, MCP shortcut, external LLM/network/cloud or real credential added.

Frontend Gate X - Real Frontend End-to-End Integrity: real frontend actions reach
runtime/Agent/Domain and return to UI. Gate Y - Cross-runtime Workflow Parity:
the shared matrix compares business/HITL/grounding/diff/error semantics. Gate Z -
Cross-runtime Authority Preservation: business truth stays P5-P11 and approval
authority stays P12.5/P11. A-W retain their boundaries; Gate E remains
LOCAL_AGENTARTS_RUNTIME_PARITY_PASS at the offline compatibility boundary.

An installed-Chrome native CDP smoke drives the actual Vite composition/proxy in
both modes, desktop/390px layouts and operable HITL controls. It made 18 expected
POSTs, checked 20 layout states with no horizontal overflow/browser exceptions,
and kept cloud credentials out of browser headers. Screenshots/results are ignored
under tmp/p14-7-e2e. No browser framework/dependency was introduced; jsdom is not
used to claim layout measurements. No real cloud/production deployment performed.

Validation: `npm run test:e2e --prefix frontend` 20 passed; full frontend 196
passed, zero skipped; lint/build PASS. `npm run test:responsive --prefix frontend`
PASS with the installed Chrome and process permission. Backend AgentArts/Local
targeted tests 53 passed; full pytest 2474 passed, zero skipped; Ruff and git diff
--check PASS. The unchanged default bundle retains its non-blocking 524 kB chunk
warning. P14.7 Review PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN.

### P14 Closure - Frozen Frontend and Runtime Boundaries

P14 Frontend + Runtime Invocation Compatibility is completed and CLOSED_FROZEN.
P14.0-P14.7 are REVIEW_PASS; P14 Final Review is REVIEW_PASS; P14 Closure is
CLOSED_FROZEN. P12/P13 remain CLOSED_FROZEN. P15 and P16 remain NOT_STARTED.

Frozen scope includes the typed RuntimeInvocationClient, conversation/app shell,
structured clarification and explicit APPROVE/REJECT, grounded result/evidence/
source/PlanDiff presentation, real Local invocation, AgentArts-compatible trusted
transport and cross-runtime frontend workflow parity. Both transports reuse the
same P12.7 boundary, CompetitionCopilotAgent, LangGraph, CapabilityFacade and P4-P11
authorities; P13 MCP remains an independent capability entrypoint.

Frontend/transport never create business truth, human approval authority or PlanDiff.
P12.5/P11 retain approval/mutation authority; cloud credentials stay server-side,
session metadata grants no identity/authority, and continuations are not retried
automatically. Source/evidence stays untrusted presentation data. Closure does not
claim real-cloud certification, durable workflow storage or production hardening.
P15 owns subsequent evaluation; P16 owns production deployment/IAM/security work.

## Post-P14 Local Demo / End-to-End Integration

**Status: CLOSED / VERIFIED.** This separately verified local demo integration is
complete; it does not reopen P12, P13 or P14, all of which remain CLOSED_FROZEN.
P15 remains NOT_STARTED; readiness is READY_TO_START, not implementation status.

| Completed integration | Verified scope |
|---|---|
| Provider-neutral Cloud LLM | OpenAI / BigModel / DeepSeek; BigModel intent json_mode and temperature 0.1; single-call intent proposal reuse; no automatic retry; backend-only secrets; automated tests remain offline |
| Multi-candidate recommendation | 12 formal candidates; P5 eligibility per candidate and one P6 ranking call; confirmed / uncertain / blocked; verified-skill-overlap-v1 never promotes P5 UNKNOWN through a soft score |
| P7 Skill Gap | Canonical student skill evidence; absent profile facts are unknown, not deficits; PARTIAL requirements with required_level=null remain UNDETERMINED; browser smoke PASS |
| P8 structured planning | Real P7 prerequisite, uncertainty_resolution planning and no invented deadlines; browser smoke PASS |
| Generated PlanRegistry and selection | Full CompetitionPlan storage, exact PlanReference, CAS, history/lineage and same-host cross-request resolution; explicit frontend selection |
| Instruction preparation policy V1 | target-track-removed-cancel-v1; authority-free PlanRevisionProposal; preparation is not authorization; APPROVE-only executable authority; independent REVIEW_PASS |
| Generated Huawei same-plan E2E | Generated P8 Innovation plan -> registry -> controlled observation -> Snapshot / Diff / Event -> P10 AFFECTS_PLAN -> P11 REPLAN -> reviewed policy -> WAITING_FOR_APPROVAL; REJECT has no mutation; APPROVE produces actual draft-to-cancelled PlanDiff, version 1 -> 2; stale/replay/mismatch protections; real browser smoke PASS and independent REVIEW_PASS |

### Verified demo boundaries and handoff

- Huawei Innovation Track removal is a **manual CONTROLLED DEMO OBSERVATION**,
  not a claim that Huawei officially removed the track. Observation provenance
  and retained Snapshot/Diff/Event lineage remain explicit.
- BigModel cloud/browser smoke is local demo validation, not production deployment
  or cloud certification. Production deployment and hardening remain P16.
- Local PlanRegistry is in-memory: generated plans persist across requests only
  within the same host lifetime. Server restart discards generated plans and
  restores the controlled fixture; frontend plan selection is session-scoped.
- These are accepted demo boundaries, not open blockers. Detailed implementation
  and run instructions remain in ARCHITECTURE and the backend/frontend READMEs.
  P15 evaluation may start separately; no P15 implementation is claimed here.

## P15 - Evaluation & Local/AgentArts Semantic Parity

- **Status:** NOT_STARTED.
- **Readiness:** READY_TO_START after verified Post-P14 Local Demo / End-to-End Integration; implementation has not started.
- **Goal:** reproducible hard-rule, workflow, evidence, approval and transport-parity evaluation.
- **Deliverables:** fixed datasets/scripts, replayable model fixtures, failure/risk reports and local/adapter comparison.
- **Acceptance:** semantic results/reasons/evidence match under controlled inputs; no Domain edits to game evaluations.

## P16 - AgentArts Production Deployment & Hardening

- **Status:** NOT_STARTED.
- **Role:** production hardening of the P12.7-P12.8 adapter, not first AgentArts integration.
- **Inputs:** reviewed core/adapter, MCP/UI/parity contracts, official runtime compatibility and deployment configuration.
- **Deliverables:** production runtime, Ubuntu/Linux ARM64 build/deployment and compatible Python/dependency/container pins;
  IAM/least privilege, secrets, MaaS/model configuration, observability/tracing, scaling,
  timeout/retry policies, load testing, security, cost controls and operational rollback.
- **Acceptance:** Gate F and production parity/security/load/cost evidence; runtime changes cannot alter Domain truth.
- **Boundary:** build/platform/runtime concerns stay in adapter/deployment, not Domain/Agent state/Tool contracts.

## Unified Definition of Done

每一阶段在进入下一阶段前完成以下检查：

1. **Implementation complete:** 阶段交付物与验收标准已完成；P0 的“实现”仅指文档。
2. **Tests pass:** 新功能配套正常和关键边界路径的可复现自动化测试并通过；纯文档阶段完成规定的审阅与 `git diff --check`。
3. **Documentation updated:** 受影响的架构、Schema、运行或测试命令已同步更新。
4. **Stage review completed:** 按阶段 Acceptance Criteria 审阅，并记录结论与遗留项。
5. **No unrelated changes:** 仅修改当前阶段及任务相关文件，不顺带重构或格式化。
6. **Known risks documented:** 记录数据来源、规则覆盖、平台依赖等已知风险、影响及后续处理阶段。

### P11.4 Deterministic Plan Revision + PlanDiff - CLOSED / FROZEN


P11.3 determines whether/where; P11.3.5 supplies approved WHAT; P11.4 only
VALIDATES/APPLIES the approved batch. Affected scope never implies an operation.
No automatic Event-to-milestone mutation, generated content, new Need or Planner call.

`domain/plan_revision_service.py` PlanRevisionService.revise(before, replanning_input,
executed_at=<explicit aware datetime>) returns immutable PlanRevisionResult.
The result contains original ReplanningInput (including approval references and
instruction IDs), and frozen PlanDiff; result.after exposes its CompetitionPlan.
Input carries exact Decision/Scope/Impact/Event lineage transitively, without a
second authority or re-analysis. Approval authenticity remains the trusted caller's
responsibility, as in P11.3.5; execution does not reassess approval business merits.

KEEP + NO_REVISION_REQUIRED reuses unchanged Plan and empty Diff (no ID/version/time
change). UNDETERMINED + UNRESOLVED also leaves Plan unchanged with empty Diff, retaining
UNDETERMINED Decision and scope lineage; it is not a proven KEEP. REPLAN with missing
or PARTIALLY_EXECUTABLE input rejects execution. No known subset is applied while
uncertainty remains, including whole-plan inputs conservatively marked partial.

Only EXECUTABLE approved UPDATE_MILESTONE.due_at is applied. Revalidate exact Plan
ID/version/content, expected-before, Decision binding, scope, authority chronology,
conflicts and allowed fields through normal frozen constructors. Final dependency
inventory is additionally checked for all milestones, including untouched legacy ones.
All instructions succeed atomically or no result is produced. No in-place mutation.
Preserve existing milestone order and unaffected content, PlanningNeeds, audit,
target/student, horizon, Plan status and created_at. Reuse frozen revised_plan_identity,
next version rule and explicit UTC executed_at for updated_at. No random/current clock.

Construct valid after Plan first, then compare actual before/after milestone collections.
PlanDiff contains exactly one PlanMilestonesChange for changed collection, or none
for safe no-op. This frozen granularity retains unchanged context inside collection
snapshots; no invented per-milestone ADD/REMOVE records. No-op UPDATE is rejected by
P11.3.5; REPLAN cannot fabricate an empty-diff success. No ADD/REMOVE/REPLACE support.

The receipt preserves revision input/authority provenance without extending frozen
PlanDiff, alongside Decision/Impact/Event lineage. Normal constructor validation,
immutable nested tuples, deterministic identity and stable JSON are tested. No
Repository, persistence, notification, Network, LLM, Agent or MCP. Frozen contracts
and services remain unchanged. P11 is CLOSED / FINAL REVIEW PASS / FROZEN; P11.5: Real Adaptive
Replanning Integration (implemented, Review PASS / committed, below).


### P11.4.2 Plan-Level Replanning Resolution - CLOSED / FROZEN

Controlled reopen only: P11.1 PlanDiff, P11.3.5 inputs and P11.4 execution.
P11.2/P11.3/P8/P10 production semantics are unchanged. P8 PlanStatus already has
 draft/active/completed/cancelled/superseded, but had no transition policy.
This phase defines only explicit approved draft/active -> cancelled, for verified
TARGET_TRACK_REMOVED. completed/superseded cancellation and cancelled no-op reject.
Target changes and supersession/replacement semantics remain deferred.

Plan cancellation means this particular Plan is no longer executable. It does not
mean withdrawal from the Competition, restoration of the track, erasure of the
Event, or selection of a replacement track. Preserve target identity, needs, audit,
horizon, historical milestones and created_at. No recommendation/gap/eligibility
rerun, generated content, persistence, Network, LLM, Agent or MCP.

UpdatePlanStatusInstruction carries exact expected PlanReference/version/content,
expected-before status, desired cancelled status, source Decision fingerprint,
original AffectedPlanScope and reused HUMAN_APPROVED RevisionAuthority references.
ReplanningInput adds optional plan_status_instruction and scope_resolution.
Cancellation cannot be combined with milestone edits in this first policy.

AuthorizedScopeResolution is immutable, with COMPLETE/PARTIAL/UNRESOLVED states,
explicit typed coverage, original scope, canonical instruction/milestone refs,
Plan/Decision binding and authority. Impact scope describes WHERE; resolution
specifies authorized executable coverage; instruction specifies WHAT; Diff records
actual changes. COMPLETE cancellation requires one exact authorized status instruction,
whole-plan confirmed removal impacts only, and no unresolved impacts/remainder.
Normal EventImpactAnalysis validation verifies typed removal lineage; execution
consumes that validated evidence without reinterpreting Events or SnapshotDiff.
Human approval cannot override semantic incompatibility. Target-added impacts have
no complete cancellation policy and reject. Milestone-only target-invalidation
edits remain PARTIAL, including explicit partial coverage; fake COMPLETE rejects.
Original impact, scope and uncertainty lineage is retained, never replaced.

P11.4 revalidates all inputs, executes only EXECUTABLE batches atomically, constructs
normal CompetitionPlan, then computes Diff from actual states. PARTIAL/UNRESOLVED
REPLAN still reject. KEEP and UNDETERMINED safe no-op behavior is unchanged.
PlanDiff adds optional immutable PlanStatusChange(before_status, after_status).
Status-only cancellation has no milestone change declaration. Full collection
snapshots still provide unchanged context for actual milestone revision.
The schema can distinguish empty, milestone and status change; simultaneous
status/milestone revision is deliberately rejected by this initial cancellation policy.

Reuse revised-plan-v1 identity derivation with status included when it actually
changes, version + 1, preserved created_at and explicit aware UTC execution time
for updated_at. Existing milestone identity derivation and input IDs without new
options remain unchanged. Old payloads parse; serialization schema adds nullable
status_change / plan_status_instruction / scope_resolution fields. Receipt retains
full resolution/instruction/approval payload alongside Diff/Event/Impact/Decision.

Real offline production probes in test_plan_level_revision.py use Repository targets,
P8 Builder, controlled test-only Event Engine lineage, unchanged Analyzer/Decision,
explicit human-approved fixture cancellation, normal input/resolution constructors,
and real Revision Service. Draft and active paths produce cancelled after Plan plus
actual status Diff, without substituted milestone scope. Controlled events and
approvals are test fixtures, not official historical changes or automatic rules.
Tests cover preconditions, fake complete, partial rejection, wrong impact, terminal
states, original context preservation, immutable JSON and determinism.
P11.5 integration is implemented, Review PASS / committed, as described below. P11 remains
CLOSED / FROZEN; P12 is CLOSED_FROZEN; Final Review is REVIEW_PASS; Closure is CLOSED_FROZEN. No P12 work or git commit in this Closure.


### P11.5 Real Adaptive Replanning Integration - CLOSED / FROZEN

`backend/tests/integration/test_real_adaptive_replanning.py` proves the frozen
production-component chain, offline by default. No business orchestration service
or new rule is introduced. Real JsonSeedCompetitionRepository supplies huawei-ict /
huawei-ict-2026 / huawei-ict-2026-innovation Domain context. A minimal synthetic
StudentProfile and explicitly supplied existing uncertainty Need/audit context feed
real P8 BaselineCompetitionPlanBuilder. Active status is prepared with a normal
CompetitionPlan constructor (P8 supplied metadata), retaining baseline identity,
needs and milestones. No Eligibility/Recommendation/SkillGap rerun or duplicate
Planner implementation. This is not a new requirement-data inference.

Controlled membership/window Events, Snapshot references and approval references
are TEST-ONLY deterministic scenarios. They do not claim official historical changes
or actual removal of the Seed track. Local Seed is read-only and byte-identical after
tests. Socket connection/DNS guards reject network access; no live official fetch.
Every Event is produced by real P10 Engine, impact by real P11.2 Analyzer, Decision
and scope by real P11.3 Service, input/authority/resolution by normal P11.3.5/P11.4.2
constructors, and after Plan/Diff by real P11.4 Revision Service. No validator bypass.

Validated paths:
1. Unrelated track membership change with target preserved -> NO_PLAN_IMPACT ->
   KEEP_CURRENT_PLAN -> known-empty scope / NO_REVISION_REQUIRED -> unchanged
   Plan, ID/version/metadata and empty Diff with complete trigger lineage.
2. Same-target registration window change, dependency not represented ->
   UNDETERMINED impact / decision -> unresolved scope/input -> unchanged Plan and
   empty Diff retaining uncertainty. This is machine-distinct from proven KEEP.
3. Typed target-track removal -> AFFECTS_PLAN / TARGET_TRACK_REMOVED -> REPLAN /
   original whole-plan scope -> explicitly approved COMPLETE cancellation coverage
   -> UPDATE_PLAN_STATUS active -> cancelled -> actual revised Plan / status Diff.
   Target/student, horizon, audit, needs and historical milestones remain unchanged.
   No replacement track, deadline guessing or automatic instruction generation.

COMPLETE is approved operational cancellation, not erasure of the impact or track
restoration. Human approval cannot bypass semantic compatibility. Milestone-only
whole-plan target-removal edits stay partial and execution rejects; target-added
cancellation and missing approval evidence reject. Approved fixture values are
explicit, not derived from Event summary or milestone text.

Each main path executes twice with identical Event/impact/decision/scope/input/after/
Diff JSON and identities; typed JSON roundtrips cover all outputs and COMPLETE
resolution. Multiple-impact input permutations preserve canonical complete lineage.
Before Plan and Student serialization stay unchanged. PlanDiff is the actual Service
result, never a manually substituted expected Diff. No persistence, active-Plan
replacement, Scheduler, Notification, Network, LLM, Agent or MCP.

P11 Adaptive Replanning functional chain is complete for the supported paths;
P11.5 is CLOSED / FROZEN; P11 is CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE.
Exit criteria 16/16 are covered by this integration and frozen phase regressions.
P12 input is ready at the deterministic contract boundary; no autonomous or model-based workflow is implemented.
A future Agent may collect explicit approvals and submit typed inputs through an
authorized boundary; it cannot recompute impact/decisions, bypass resolution or
mutate Plans directly. Frozen production semantics remain unchanged.


### P11.1.2 Canonical Plan Reference Serialization Compatibility Fix - CLOSED / FROZEN

Historical P11 Final Review found this sourced P8 Plan defect, now resolved by P11.1.2:
PlanningNeed.source_item (SkillGapItem) retains nested HttpUrl source evidence;
Plan JSON serialization worked but PlanReference digest raised TypeError.
Controlled follow-up extends only the canonical serialization boundary for the
explicit Pydantic AnyUrl family (including HttpUrl/AnyHttpUrl), using its formal
JSON URL representation. No default=str, repr or arbitrary-object fallback.
Existing UTC datetime, enum, collection and sorted-key semantics are unchanged;
previously unsupported types still reject. Pre-fix URL-free digest/identity
constants are retained. No P8 schema, evidence deletion or P11 business-rule change.

Focused tests reuse the existing real P8 COMAP planning chain without copying it
or removing source_item. Both student fixtures cover reference equality, Plan JSON
roundtrip, Analyzer/Decision lineage and safe unresolved revision/Diff serialization.
Typed URL construction is offline, without URL accessibility checks or DNS/network.
P11.5 is IMPLEMENTED / REVIEW PASS / COMMITTED (5394316).
This compatibility defect is resolved by committed P11.1.2 (bf792fc).
P11 Final Review retry PASS; P11 is CLOSED / FROZEN. P12 is CLOSED_FROZEN; Final Review is REVIEW_PASS; Closure is CLOSED_FROZEN.
The original follow-up made no git commit; Closure is a documentation-only update.
