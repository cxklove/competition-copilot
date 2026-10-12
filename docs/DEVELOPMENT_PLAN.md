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
P8 baseline scope is finished; adaptive planning remains future work.

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
complete below. P10 Event interpretation is implemented below; P11 Replanning remains future work. Text/rules semantic diff and additional
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
P9.5 Monitor and P10 Event interpretation are implemented below; P11 Replanning remains future work. P9 is FROZEN.

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
P9.5 below; Event, impact and Replanning remain future work. P9 Final Review
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
  business Event; P11 owns impact/severity/affected plans/user actions, PlanDiff,
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
  the reviewed Event Engine semantics. NEXT: P11 — Adaptive Replanning (NOT STARTED).
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
refetch sources, rebuild Snapshots, recompute Diff or regenerate Events. P11 is not started.

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
-> future P11 Impact / Replanning
```

Deferred: Event persistence, EventRepository, cross-run dedup, subscription,
notification, severity, Impact Analysis, plan impact, Adaptive Replanning (P11),
Agent, MCP and Frontend. P11 will consume Events + StudentProfile + existing
CompetitionPlan + necessary planning context and produce Impact Analysis,
Affected Plan scope, Replanning Decision and Plan Diff. P11 must not fetch sources,
rebuild Snapshots, recalculate Diff or regenerate Events; implementation is not started.

## P11 — Adaptive Replanning

- **Goal:** 根据赛事事件评估影响并生成可审计的个人计划差异。
- **Status:** NEXT after P10 CLOSED / FROZEN; NOT STARTED。
- **Inputs:** canonical CompetitionEvent、existing CompetitionPlan、StudentProfile、必要 planning context；不重新抓官网、构造 Snapshot、计算 Diff 或生成 Event。
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
