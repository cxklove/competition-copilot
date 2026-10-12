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

## P7 — Student Profile + Skill Gap

- **P7.3B.2 follow-up (implemented, pending review):** Authorized minimal evolution after real-source audit: a requirement can be known while `required_level=None` explicitly means unspecified threshold. Every fact requires verified canonical presence evidence; only specified thresholds carry proficiency evidence. Coverage completeness is independent of proficiency completeness. Item reason_codes are immutable, unique and canonically ordered, retaining both unspecified threshold and missing student facts. Engine compares only known thresholds/known students, preserves student provenance, and keeps known GAP precedence. NO_GAP requires COMPLETE plus all specified thresholds and known satisfied skills. P7.3A Provider architecture remains unchanged; envelope validation extends its official evidence gate to presence. No real artifacts or target changes; edition/subtrack/source-review blockers remain. No P7.4 or P7 COMPLETE claim.

- **P7.1 evidence input follow-up:** `SkillGapContext.student_skill_evidence` is an immutable snapshot of supplied STUDENT_SKILL facts. Relevant known profile skills require matching canonical skill/level evidence. Missing or UNKNOWN skills need no fabricated evidence; unrelated profile skills do not require it. Every supplied extra or multiple-source fact must match an existing known profile skill. Shared StudentSkill/StudentProfile/Evidence remain unchanged; P7.2 engine and P7.3 provider are not implemented by this fix.

- **Current status:** **P7 started; P7.1 Contract and evidence-input follow-up PASS; P7.2 Deterministic Skill Gap Engine PASS. P7.3 schema/Provider implemented, real data BLOCKED BY REAL SKILL REQUIREMENT SOURCE GAP.** P7 is not COMPLETE. No P7.4 implementation. Pure Domain contracts live in `backend/competition_copilot/domain/skill_gap.py`; synthetic tests live in `backend/tests/domain/test_skill_gap.py`.
- **P7.3 deliverable and blocker:** `domain/skill_requirement_artifact.py` adds a strict immutable versioned SkillRequirementSetEnvelope reusing P7.1 facts and existing Skill snapshots for exact ID resolution; `application/skill_requirements.py` defines SkillRequirementProvider; `infrastructure/skill_requirement_json.py` provides atomic, read-only local JSON loading with exact targets, deterministic discovery, fail-fast errors and None for missing artifacts. `data/skill_requirements/` has documentation and zero real JSON artifacts: current reviewed project facts do not establish skill/type/exact proficiency. No guessed facts or unsupported COMPLETE coverage. Review/coverage notes remain system assessment. Synthetic schema/Provider tests and real Repository missing-target smoke are implemented; real artifact provenance/target smoke explicitly skips until reviewed data exists. Frozen P7.1/P7.2/P2-P6 remain unchanged. No runtime network, LLM, Raw/Manifest/Seed parsing, student data or gap computation in Provider. Reviewed source facts and stable skill identities must be supplied before P7.3 can pass.
- **P7.2 deliverable:** `backend/competition_copilot/domain/skill_gap_engine.py` implements `SkillGapEngine.evaluate(SkillGapContext) -> SkillGapDecision`; synthetic tests are in `backend/tests/domain/test_skill_gap_engine.py`. Exact skill ID matching, explicit ordinal ordering, all-requirement evaluation in supplied order and evidence preservation. Missing student skill != zero; missing requirement != no gap; PARTIAL cannot confirm NO_GAP, but known REQUIRED/DESIRED gaps remain GAP_IDENTIFIED with partial coverage or other unknown skills. Errors fail atomically; no readiness score, skill guessing, provider, Repository, planning, eligibility/recommendation logic, network or LLM is added.
- **P7.1 semantics:** Exact Edition/Track targets, REQUIRED/DESIRED requirements referencing `Skill.id` and existing `SkillLevel`, verified source evidence, explicit COMPLETE/PARTIAL/MISSING coverage, separate per-item requirement/student evidence, and immutable Context/Item/Decision snapshots. Missing requirements != no gap; missing student skills != zero skill. NO_GAP requires COMPLETE and all declared skills known satisfied; GAP_IDENTIFIED can coexist with PARTIAL coverage or other unknown student skills. Coverage is retained in the nested RequirementSet. No numeric gap/readiness score, eligibility/recommendation logic, resource matching, planning or real artifacts are added.
- **P6 handoff:** 目标 Competition / Track 确定后，比较 Student skills 与正式 Competition required / desired skills，产生 `SkillGap`。P7 不重新判断 eligibility、计算 recommendation score 或排列 candidates。概念链：`Eligibility → Recommendation → Selected Competition Target → Skill Gap → Learning / Planning`。
- **Data risk:** 当前 Competition Domain 尚无完整 structured skill requirements。P7 必须先建立正式 Skill Requirement / Expected Skill 数据 Contract，或明确表达缺少 required skill data 时 gap cannot be fully determined；禁止从 competition name / description 猜测所需技能。
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
