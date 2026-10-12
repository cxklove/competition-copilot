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

P5.1 的 `domain/eligibility.py` 定义独立的硬资格契约：`EligibilityContext` 显式携带学生和正式 Competition/Edition/可选 Track 快照；纯 `EligibilityRule` 对目标返回带稳定规则 ID、作用层级、reason code 和现有 `Evidence` 的 `RuleEvaluation`。`EligibilityDecision` 复用 `DecisionResult` 的 reason codes 与 evidence，并以 `ELIGIBLE`、`INELIGIBLE`、`UNKNOWN` 表示资格；缺少画像或规则资料属于一等的 `UNKNOWN`，未记录限制不等于已确认没有限制。P5.2 负责已准备规则的确定性聚合，P5.3 再接入真实结构化资格数据和适用规则准备。资格只判断官方硬约束；技能、兴趣和匹配度属于后续推荐或诊断。规则不得读取 Repository、Raw、Manifest、系统时间、网络或 LLM；若未来需要评估时间，须显式作为输入。

P5.2 的 `domain/eligibility_engine.py` 接收已准备好的 Context 与适用规则序列，按输入顺序逐条执行且不提前结束，保留全部逐条结论及原始证据顺序；最终状态按 `INELIGIBLE > UNKNOWN > ELIGIBLE` 聚合。空规则集返回 `UNKNOWN / RULE_DATA_MISSING`。重复规则 ID、规则返回 ID/scope/目标不一致或规则程序异常均为评估错误，不伪装为业务 `UNKNOWN`。调用方仍须保证规则集覆盖正式适用规则；真实规则发现和数据接入不属于 P5.2。

P5.3 引入独立于 P2 Seed 的 `data/eligibility/` 结构化 Policy：每项硬约束保留正式来源，Policy 明示 complete/partial 覆盖状态。Application 使用抽象 `CompetitionRepository` 和 `EligibilityPolicyProvider` 准备目标与规则，再委托 P5.2 Engine；JSON Policy Adapter 仅在 Infrastructure 层读取 P5 Artifact。缺 Policy 为 `UNKNOWN / RULE_DATA_MISSING`；partial Policy 会保留未结构化条件的 UNKNOWN，因此已满足某项学历限制不等于确认整届合格。Runtime 不解析 Raw 或 Manifest。当前首批仅覆盖两个已核验通知中的学历层级事实；在读、全日制、团队及例外资格仍需后续数据模型与结构化规则。

P5.4 已通过真实 Verified Seed → `JsonSeedCompetitionRepository` → `CompetitionRepository`，以及独立 P5 Policy → `JsonEligibilityPolicyProvider` → `EligibilityPolicyProvider` 的集成测试，验证 `CompetitionEligibilityEvaluator`、P5.2 Engine 和可序列化的 `EligibilityDecision` 全链路；P5 Final Review PASS。Decision 保留目标、最终状态、逐条规则 ID/状态、reason codes、画像事实证据、官方约束来源及系统覆盖缺口。系统 coverage assessment 不附官方来源。`PARTIAL` Policy 的已知规则满足加覆盖缺口为 `UNKNOWN`；明确违反加覆盖缺口仍为 `INELIGIBLE`。缺画像信息为 `UNKNOWN / PROFILE_DATA_MISSING`，缺结构化规则或 Policy 为 `UNKNOWN / RULE_DATA_MISSING`；只有全部适用硬规则明确满足且覆盖完整才可判 `ELIGIBLE`。

**P5 Eligibility scope is frozen.** P5 判断官方硬资格约束；技能、兴趣、经验、获奖概率、偏好、学习成本和排名属于 P6 及后续软匹配能力。P6 按 `Eligibility → Soft Suitability → Recommendation / Ranking` 消费 P5 结果，不得重做资格判断：`INELIGIBLE` 不因高分变为可参加，`UNKNOWN` 不伪装成确认合格。Recommendation、Skill Gap、Planning、Agent 和 MCP 不得重新实现 P5 三值状态、硬规则、聚合优先级、缺失数据或 Policy coverage 语义；仅真正的 Eligibility contract / semantic defect 可重新打开 P5。研究生入学状态、全日制/在读状态、Team Context、团队规则及更多 Policy 属未来数据和 Domain 需求，当前保持保守 `UNKNOWN`。

P6.1 在 `domain/recommendation.py` 建立单候选纯 Domain 契约：`RecommendationContext` 携带 StudentProfile、正式 Competition/Edition/可选 Track 快照、稳定 Candidate ID 和 P5 `EligibilityDecision`，构造时拒绝目标或资格结果错配。`RecommendationEvaluation` 复用 `DecisionResult` 的 reason codes 与 `Evidence`，保留原始资格结果；推荐状态与资格状态分离。`ELIGIBILITY_BLOCKED` 对应 P5 `INELIGIBLE`，不携带软分数；`ELIGIBILITY_UNCERTAIN` 对应 P5 `UNKNOWN`，允许将来记录软适配度但不能确认推荐；仅 P5 `ELIGIBLE` 可产生正常推荐或不推荐结果，亦可在软资料不足时保持适配度未确定。可选 0–1 分数只表示软适配度，并需分项证据，不是资格概率。P6.1 不执行评分、权重计算、跨候选排序或 Skill Gap 诊断；这些仍属后续阶段。Contract 不依赖 Repository、Tool、Infrastructure、文件系统、网络或 LLM。

P6.1 的 Context、Candidate、ScoreComponent 和 Evaluation 为不可变快照，P6 自有集合采用 tuple。共享 Domain 输入会转换为经过校验的独立冻结视图；资格视图继承 P5 原有字段、三值状态及校验，并保留完整审计，不重做资格语义。原始 P5 决策、赛事或画像对象的后续修改不会改变已经验证的 P6 快照；不同结果须重新构造合法快照，未验证的 copy update 被拒绝。

P6.2 adds the pure Domain `RecommendationScoringEngine` in `domain/recommendation_scoring.py`. It accepts one prepared context and ordered `SuitabilityScorer` components with finite nonnegative weights (default 1.0). INELIGIBLE bypasses scorers; UNKNOWN remains eligibility uncertain even with a high soft score. Available positive-weight components use `sum(score * weight) / sum(active weight)`. None signals are unavailable, excluded rather than zero-scored; zero-weight results are still audited. No active signals yields undetermined suitability for ELIGIBLE. Evidence records configured weights, missing component IDs, component facts, scoring version `weighted-average-v1`, and threshold. The default threshold 0.5 is a deterministic MVP heuristic; equality recommends only eligible candidates. Duplicate IDs, invalid results and scorer exceptions fail as engine errors. Competition Domain has no structured skill requirements yet: tests inject synthetic scorers, with no guessed real skill mapping. No ranking, Top-K, repository orchestration, LLM or network is introduced. P6.1 and P5 contracts remain unchanged.

P6.3 adds `domain/recommendation_ranking.py`: a pure `RecommendationRankingEngine`
consuming already scored `RecommendationEvaluation` snapshots. The immutable
`RecommendationRankingResult` separates confirmed eligible rankings, eligibility
uncertain rankings, and blocked reporting. Confirmed and uncertain ranks each
start at 1 and are continuous within their bucket. Available scores sort descending;
unavailable scores follow all numeric scores, including zero. Exact ties use
ascending `(competition_id, edition_id, track_id or "")`; scores are never rounded.
Blocked candidates have target-ID order only, without a recommendation rank.
Duplicate targets fail before sorting; empty input returns three empty tuples.
The result validates bucket membership, rank continuity, ordering and uniqueness,
preserves full evaluations without rewriting them, and records stable policy
`eligibility_buckets_score_desc_target_id_v1`. There is no global mixed rank,
rescoring, eligibility re-evaluation, candidate discovery, Top-K truncation,
Repository access, LLM or network. P6.1/P6.2 and frozen earlier contracts stay unchanged.

P6.4 integration acceptance connects real `JsonSeedCompetitionRepository`,
`JsonEligibilityPolicyProvider` and `CompetitionEligibilityEvaluator` to the
production P6 scoring and ranking engines. Soft scores are test-only target-ID
fixtures; synthetic ELIGIBLE decisions test normal paths without changing real
partial policies. Tests preserve nested audit and JSON, verify target integrity,
determinism and read-only execution, and require no Raw/Manifest runtime reads.
No production orchestration or real skill mapping is added. P6.1, P6.2, P6.3,
P6.4 and P6 Final Review all passed; **P6 Recommendation — COMPLETE**.

**P6 Recommendation scope is frozen.** P5 hard eligibility answers whether the
student may participate; P6 soft recommendation evaluates suitability when
eligibility permits or remains uncertain. INELIGIBLE remains blocked, UNKNOWN
cannot become confirmed recommended even with a high score, and ELIGIBLE is not
automatically recommended. Suitability scores express neither eligibility
confidence nor winning / competition success probability. Uncertain bucket ranks
are conditional ordering, not confirmed recommendation ranks.

P6 Evaluation, RankingResult and RankedRecommendation are validated immutable
snapshots; different results require new validated snapshots. P6 Domain depends
on no Repository, Infrastructure, Tool, filesystem, Seed, Raw, Manifest, network
or LLM. Skill Gap, Planner, Agent, MCP and Frontend must not reimplement or
override P5 eligibility semantics or P6 RecommendationStatus, scoring,
missing-signal and ranking-bucket semantics. Only a genuine P6 contract / semantic
defect reopens P6.

Real competition skill mapping, interest/goal/experience signals, resource cost,
additional components, candidate discovery, Top-K UI views and learned ranking
are deferred capabilities, not P6 exit blockers. Next is P7 Skill Gap, comparing
student skills with formal required/desired skills for a selected target; P7
does not recalculate eligibility, recommendation scores or ranking. The flow is
`Eligibility → Recommendation → Selected Competition Target → Skill Gap → Learning / Planning`.
Competition Domain currently lacks complete structured skill requirements. P7
must first establish a Skill Requirement / Expected Skill data contract or
explicitly express that missing required-skill data prevents full gap determination;
competition names and descriptions must not be used to guess required skills.

## 7.1. Skill Requirement & Skill Gap Contract

P7.1 starts the independent skill diagnosis contracts in `domain/skill_gap.py`.
`SkillRequirementSet` binds an exact Edition/Track target, without inherited
requirements. REQUIRED denotes core task skills, not P5 eligibility; DESIRED
denotes beneficial skills. Requirements reference existing `Skill.id` and use
the ordinal `StudentSkill.level` scale (BEGINNER, INTERMEDIATE, ADVANCED).
UNKNOWN cannot serve as a known required level. Each requirement carries reused
`Evidence` with a verified `SourceMetadata`; duplicates for the same skill at
one target, including across types, fail rather than resolve ambiguously.

Coverage COMPLETE/PARTIAL/MISSING is an explicit assessment with a note, not a
consequence of item count or JSON loading. Empty requirements mean MISSING;
they never prove preparedness. `SkillGapContext` validates target relationships
and carries only detached student/competition/requirement snapshots, without
P5/P6 decisions or services. Its immutable `student_skill_evidence` snapshot
uses canonical STUDENT_SKILL fields and values bound to existing profile facts.
Each relevant known StudentSkill needs matching supplied provenance; missing or
UNKNOWN skills need no fabricated evidence. Additional matching facts and multiple
sources are allowed, but orphan or conflicting evidence is rejected.
`SkillGapItem` composes its requirement (identity,
level, type and source evidence), a known or unavailable student level, separate
student evidence, SATISFIED/GAP/UNKNOWN status and machine-readable reason codes.
Missing student facts do not become zero ability or an assumed full gap.

`SkillGapDecision` separates NO_GAP/GAP_IDENTIFIED/UNDETERMINED from coverage
retained in its RequirementSet, and audits every known requirement exactly once.
NO_GAP requires COMPLETE and all declared REQUIRED and DESIRED skills known
satisfied. A known gap, including a desired-skill gap, remains GAP_IDENTIFIED
with PARTIAL coverage or unknown facts about other skills. System analysis audit
is kept separate from requirement provenance and student evidence. All P7-owned
models and collections are frozen snapshots; evidence reuses shared fields in
a detached frozen view. Supplied conclusions are validated for consistency;
no engine calculates gaps or aggregates results in P7.1. No numeric gap,
readiness score, learning schedule or resource matching is defined.

P7 has started, not completed. Real requirements must come from structured,
reviewed data, never target names/descriptions or LLM inference. P7.1 has no
Repository, Infrastructure, Tool, filesystem, network, LLM, eligibility or
recommendation dependency; tests use synthetic data only.

### P7.2 Deterministic Skill Gap Engine

`domain/skill_gap_engine.py` is a pure Domain Service. `SkillGapEngine.evaluate`
consumes and validates a prepared `SkillGapContext`, matches exact skill IDs and
compares explicit ordinal ranks BEGINNER < INTERMEDIATE < ADVANCED. UNKNOWN has
no rank. It evaluates every REQUIRED/DESIRED requirement in supplied tuple order,
retaining requirement facts and every matching student evidence source. No student
provenance is generated from levels; missing facts remain UNKNOWN.

Overall precedence is known gap (including DESIRED) → GAP_IDENTIFIED, otherwise
incomplete coverage or unknown student facts → UNDETERMINED, otherwise COMPLETE
and all declared requirements satisfied → NO_GAP. MISSING requirements produce
empty items and UNDETERMINED; PARTIAL can identify a gap but cannot confirm no gap.
Coverage remains in the RequirementSet alongside the qualitative gap status.
Output uses normal validated immutable snapshots, item/coverage reason codes and
source-free system audit `SKILL_GAP_ANALYSIS_V2`. Errors propagate atomically.
The engine is read-only, deterministic and has no readiness score, skill guessing,
eligibility/recommendation logic, provider, Repository, filesystem, network, LLM
or planning dependency. P7 is not COMPLETE.

### P7.3 Reviewed Skill Requirement Data

`domain/skill_requirement_artifact.py` defines a strict, versioned immutable
`SkillRequirementSetEnvelope` composing the unchanged P7.1 RequirementSet plus a
minimal catalog of existing Skill snapshots. It rejects unresolved/duplicate skill
IDs and requires verified official fact evidence in canonical REQUIREMENT bindings.
Version, review note and explicit coverage assessment are preserved. Review and
coverage notes are system assessment, not attributed official statements. Authoring
must ground skill membership, review type interpretation, support any specified
proficiency and justify any COMPLETE claim; validation alone
cannot prove semantic source support.

`application/skill_requirements.py` defines the read-only SkillRequirementProvider
abstraction; `infrastructure/skill_requirement_json.py` implements it. This adapter
reads `data/skill_requirements/*.json` in filename order, publishes a snapshot only
after full validation and rejects duplicate targets even across versions, malformed
files and conflicting catalog identities. Missing directory is configuration error;
an existing empty directory is valid. Exact queries return RequirementSet or None,
never fuzzy/edition/track/year fallback or empty COMPLETE. Repository validates
target existence and relationships in smoke tests and future orchestration. Domain
and Provider do not run SkillGapEngine or access student data; Provider does not
read Seed, Raw, Manifest, network or LLM and never writes artifacts.

P7.3B.5 authors the first reviewed real artifact, `comap-mcm-2027.json`, after
P7.3B.4 human approval and re-observation of official 2027 MCM rules. Its exact
Edition target has only mathematical-modeling, unspecified threshold and PARTIAL
coverage. REQUIRED is a human-reviewed structured interpretation, not an official
enum or P5 hard eligibility. Presence provenance is official; review/coverage notes
remain system assessment, and no proficiency evidence is created. Real provenance
and Repository target smoke now run. Other targets need independent source review.
No skill/level is inferred from names or descriptions.
P7.4 integration is documented below; P7 COMPLETE is not claimed.

### P7.3B.2 Unspecified Proficiency Follow-up

Real-source audit exposed a known-skill/unspecified-threshold mismatch. P7.1 now
requires explicit `required_level: SkillLevel | None`: null means a known skill
requirement whose proficiency threshold is unspecified, never missing requirement
data or SkillLevel.UNKNOWN. Every requirement has `presence_evidence` asserting
`requirements.<skill_id>.present = true` with verified provenance. Existing
`evidence` remains the proficiency channel: known threshold requires matching
`requirements.<skill_id>.required_level`; null requires an empty proficiency
channel. Presence asserts reviewed membership, not that official wording used
the REQUIRED enum; source facts and type interpretation still need author review.

Coverage completeness and proficiency completeness are independent: COMPLETE may
contain unspecified thresholds and is never downgraded automatically. Item
`reason_codes` is a unique immutable tuple in canonical order: requirement
proficiency unspecified, then student skill data missing, when both apply. Known
student levels/evidence are preserved even for UNKNOWN caused by missing threshold;
student provenance requirements are unchanged. SATISFIED/GAP require both levels
known. Any known gap still yields GAP_IDENTIFIED; otherwise any missing threshold
or student fact yields UNDETERMINED. NO_GAP requires COMPLETE, all thresholds
specified and all skills known satisfied. Empty/MISSING semantics are unchanged.

P7.3A Provider architecture is unchanged; the envelope's official provenance gate
also checks the new presence channel. This is an authorized P7 contract/engine
evolution, reviewed and frozen before P7.3B.5 artifact authoring. No target/subtrack/edition
changes are made. The audited tenth/eleventh-edition mismatch and subtrack gaps
remain separate data gaps; neither P7.3 nor P7 is declared COMPLETE.


### P7.4 Real Skill Gap Integration

`backend/tests/integration/test_p7_skill_gap_integration.py` composes the real
JsonSeedCompetitionRepository and JsonSkillRequirementProvider through their
normal reads of Seed and reviewed requirement artifacts. Exact COMAP MCM 2027
Edition snapshots and the unchanged PARTIAL mathematical-modeling requirement
enter SkillGapContext with TEST-ONLY SYNTHETIC StudentProfile data and canonical
student evidence. No production orchestration service or new semantics are added.

Student A has ADVANCED mathematical-modeling with supplied synthetic evidence;
the item remains UNKNOWN because the real threshold is unspecified. Student B
has no skill record/evidence and retains both threshold-unspecified and
student-data-missing reasons. Both overall decisions are UNDETERMINED, retaining
PARTIAL coverage. Official presence provenance survives Provider, Context and
Engine; student evidence survives where supplied. Tests verify full JSON audit,
determinism, input/file read-only behavior, immutable output and another real
target's None lookup. Data reads are restricted to Seed and skill requirements;
no Raw, Manifest, eligibility policy, network, LLM, P5/P6 engine or planner runs.
P7.4 is ready for review; P7 Final Review has not run and P7 is not COMPLETE.

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
