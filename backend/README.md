# Backend

**Stage status: P2, P3, P4, P5, and P6 COMPLETE; P6.1/P6.2/P6.3/P6.4 and P6 Final Review PASS.**
**P7 — Student Profile & Skill Gap: FROZEN; P7 Final Review PASS.**
P7.1 and the student-evidence follow-up, P7.2, P7.3A, P7.3B.2,
P7.3B.5 and P7.4 passed review; P7.3B.4 received human approval.
StudentProfile Domain already exists and supplies input. P7 finished requirements,
evidence, deterministic diagnosis and real integration, not student ingestion.
**P8 — Competition Planner: FROZEN; P8.1–P8.4 and P8 Final Review PASS.**
Deterministic baseline planning scope is finished.
**P9 is IN PROGRESS; P9.1 Review PASS, P9.2 Snapshot Builder IMPLEMENTED, awaiting Review.**
The Diff Engine is not implemented. The current ingestion
dataset contains 12 Raw fixtures and 12 Verified Seeds. Raw files are ingestion
evidence; Verified Seeds are the formal business input for **P3 Repository**.
Normal competition reads in P3 need neither Raw payloads nor Human Review
Manifests, which remain part of the ingestion audit trail. The P2 ingestion
scope is frozen unless a genuine ingestion contract defect is found.
The P3 repository scope is frozen unless a genuine data-access contract defect
is found. P3 Repository Integration Test and P3 Final Review both passed.

This directory contains the Python package (`competition_copilot`), domain
models (`competition_copilot/domain`), and unreviewed external data models
(`competition_copilot/ingestion`). Tests live under `tests/domain` and
`tests/ingestion`. `RawCompetitionData` keeps source values before normalization
or review. `CompetitionCandidate` holds provisional parsed data and validation
issues separately from official competition data. Neither record is an input to
eligibility, recommendation, or planning.

`competition_copilot/repositories/` defines read-only access contracts for
verified Domain facts. `CompetitionRepository` returns Domain models, never
ingestion artifacts. Competition lists use ascending ID order; edition lists
use ascending `(year, id)` order; Track lists preserve the reviewed order for
their edition. Unknown entity lookups and unknown parents in relation queries
raise `RepositoryEntityNotFoundError`; existing parents with no children return
`[]`. Adapters must reject duplicate entity IDs and return detached models.
Storage adapters are outside this interface package and are not part of P3.1.

P3.2 adds `competition_copilot/infrastructure/repositories/`, whose current
`JsonSeedCompetitionRepository` adapter eagerly reads a supplied directory of
verified Seed JSON files. It exposes only detached Domain models and needs no
Raw fixtures or Human Review Manifests for normal reads. JSON Seed files are
the current infrastructure source, not a permanent storage requirement of the
Repository interface.

P4 competition reads depend on the abstract `CompetitionRepository`, not on
`JsonSeedCompetitionRepository`, `data/seed`, `CompetitionSeedEnvelope`, Raw
fixtures, or Human Review Manifests. P4 tests can inject a fake or in-memory
repository without filesystem access. A future database adapter can implement
the same interface without changing the upper-layer read contract. Search,
filtering, pagination, refresh, and write APIs remain future requirements.

P4.1 adds `competition_copilot/tools/`: a `Tool` Protocol with Pydantic input
and result schemas, stable metadata, and structured error codes. P4.2 provides
six read-only Competition, Edition, and Track tools, including the original
`ListEditionTracksTool`. Each accepts an injected `CompetitionRepository` and
has no JSON Adapter, Seed, Raw, Manifest, network, or LLM dependency. Outputs
wrap formal Domain models without copying Domain fields. Run focused tests from
`backend/` with `.\.venv\Scripts\python -m pytest tests/tools`.

P4.3 tests confirm that all six Tool results and errors have stable JSON
serialization, concrete input/output schemas, and round-trip behavior, including
nested Domain timestamps and source metadata. P4.4 integration tests the real
Verified Seed to Repository to six Tool to JSON path. P4 Integration Test and
Final Review passed. The six Competition Read Tool contracts are frozen unless
a genuine Tool boundary defect is found; P5 eligibility rules belong in a
separate deterministic Domain/Application capability.

P5.1 starts the separate `competition_copilot.domain.eligibility` contract for
deterministic hard eligibility constraints. It defines explicit student/target
context, pure rule evaluations, reusable decision evidence, and three outcomes:
`ELIGIBLE`, `INELIGIBLE`, and `UNKNOWN`. Missing profile or official rule data
remains `UNKNOWN`; rule aggregation and real structured eligibility data are
separate P5 work. No existing Competition Read Tool performs eligibility checks.

P5.2 adds `competition_copilot.domain.eligibility_engine`. It evaluates each
supplied applicable rule once in caller order, preserves the full audit trail,
and aggregates `INELIGIBLE > UNKNOWN > ELIGIBLE`. An empty rule set yields
`UNKNOWN / RULE_DATA_MISSING`; duplicate IDs, mismatched rule targets, and rule
exceptions fail as evaluation errors. The caller remains responsible for
supplying a complete applicable rule set. Real rules and data integration are
separate from the P5.2 engine.

P5.3 adds `competition_copilot/application/` for eligibility orchestration,
`competition_copilot.domain.eligibility_policy` for structured, source-backed
facts, and a read-only JSON policy adapter in Infrastructure. P5 policies live
in `../data/eligibility/`, separate from Verified Seeds. Runtime eligibility
reads formal Competition Domain entities through `CompetitionRepository` and
P5 policies through `EligibilityPolicyProvider`; it never parses Raw or review
manifests. The first two real policies are partial: they support a confirmed
education-level rule while unmodeled enrollment and team conditions keep a
positive overall decision `UNKNOWN`. Missing policy is also `UNKNOWN`.

P5.4 real integration and P5 Final Review passed. The current acceptance snapshot
has 12 Verified Seeds, 12 Competitions, 12 Editions, 33 Tracks, and two P5
policies (zero complete, two partial); these counts are not contract invariants.
`EligibilityDecision` preserves target, final status, ordered rule evaluations,
machine-readable reason codes, profile and official constraint evidence, and
system coverage gaps. A coverage assessment never claims official provenance.
Missing profile facts yield `UNKNOWN / PROFILE_DATA_MISSING`; missing structured
rules or policy yield `UNKNOWN / RULE_DATA_MISSING`. A confirmed hard-rule
violation yields `INELIGIBLE`; `ELIGIBLE` requires every applicable hard rule
to be satisfied and policy coverage to be complete. Known satisfaction plus a
partial-policy gap remains `UNKNOWN`, while a known violation remains
`INELIGIBLE`. Runtime reads neither Raw nor review manifests; Application
accesses Seed only through the abstract Competition Repository.

**P5 Eligibility scope is frozen.** P5 handles official hard participation
constraints, not skill fit, interests, experience, winning probability,
preferences, learning cost, or ranking. P6 consumes P5 eligibility before
soft suitability and recommendation: a high score cannot override
`INELIGIBLE`, and `UNKNOWN` must remain visibly unconfirmed. Recommendation,
Skill Gap, Planning, Agent, and MCP must not reimplement P5 status, hard rules,
aggregation, missing-data, or policy-coverage semantics. Only a genuine
eligibility contract or semantic defect reopens P5. Graduate admission,
full-time/enrollment status, team context and rules, and more competition
policies remain future data/domain work; uncertainty remains `UNKNOWN`.

P6.1 starts `competition_copilot.domain.recommendation`, a pure, single-candidate
contract reviewed and frozen. `RecommendationContext` verifies
Competition/Edition/optional Track relationships and requires a matching P5
`EligibilityDecision`. `RecommendationEvaluation` reuses `DecisionResult` and
`Evidence`, preserves the P5 result, and separates recommendation status from
eligibility status. An ineligible target is blocked without a soft score; an
unknown eligibility result remains explicitly uncertain, even if its
soft score is high. Eligible targets can be recommended, not recommended, or
left without a suitability conclusion when soft profile data is missing.
Optional scores and score components are limited to 0–1 soft suitability, not
eligibility confidence, winning probability, or competition success probability.
P6.1 defines no scoring formula, weights, ranking,
Top-K, repository access, Tool, network, or LLM use. Domain tests use only
synthetic models; scoring and ranking are separate P6 capabilities described below.

P6 recommendation models are immutable snapshots with tuple collections. Shared
Domain inputs are validated into detached, frozen P6 views; the eligibility view
inherits P5 fields and invariants and preserves its full audit. Later mutation
of the original P5 decision or target objects cannot change the recommendation.
Create a new validated snapshot for a different result; unvalidated copy updates
are rejected.

P6.2 adds `competition_copilot.domain.recommendation_scoring`: a pure,
single-candidate `RecommendationScoringEngine` with injected `SuitabilityScorer`
components and `WeightedSuitabilityScorer` configuration (default weight 1.0).
Available positive-weight components use an active-weight average; unavailable
signals return None and are audited rather than scored zero. Zero-weight results
remain in component audit. Missing all active signals leaves eligible suitability
undetermined. Ineligible targets bypass scorers and stay blocked; unknown
eligibility stays uncertain even with a high score. The default threshold 0.5
is a deterministic MVP heuristic, with equality recommended only for eligible
targets. Decision evidence preserves configured weights, unavailable IDs,
`weighted-average-v1`, threshold, and component evidence in execution order.
Configuration/result violations and scorer exceptions raise
`RecommendationScoringError`, never a missing-data result. There are currently
no structured competition skill requirements, so tests inject synthetic scorers;
no real skill mapping is guessed. No repository, ranking, Top-K, LLM, or network
is introduced, and P6.1/P5 contracts remain unchanged. From the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_recommendation_scoring.py`.

P6.3 adds `competition_copilot.domain.recommendation_ranking` with
`RecommendationRankingEngine.rank(evaluations)`. The frozen
`RecommendationRankingResult` contains tuple fields `confirmed`, `uncertain`,
and `blocked`. Confirmed and uncertain entries compose the full existing
evaluation with bucket-local ranks starting at 1. Numeric scores sort descending,
None scores follow all numeric scores, and exact ties use ascending competition,
edition, and optional track IDs (None track is an empty string for ordering).
Blocked candidates only have target-ID reporting order and no normal rank.
The stable policy ID is `eligibility_buckets_score_desc_target_id_v1`.
Result validation rejects misplaced buckets, inconsistent ranks, invalid order,
and duplicate targets. The engine rejects duplicate targets before sorting;
empty input returns a valid empty result. It preserves input evaluations and
does not rescore, re-evaluate eligibility, discover candidates, query repositories,
truncate Top-K, or use LLM/network. From the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_recommendation_ranking.py`.

P6.4 tests the full real Repository + Policy + P5 eligibility + P6 scoring/ranking
chain in `tests/integration/test_p6_recommendation_integration.py`. Soft signals
are explicit test-only fixtures, and synthetic ELIGIBLE decisions for real targets
exercise normal recommendation without claiming official confirmed eligibility.
Real partial/missing policies remain uncertain; real violations remain blocked.
Tests dynamically discover artifacts and verify mixed buckets, complete audit,
JSON, target integrity, determinism, and read-only Raw/Manifest-independent execution.
P6.4 and P6 Final Review passed. From the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p6_recommendation_integration.py`.

**P6 Recommendation scope is frozen.** P5 hard eligibility answers whether a
student may participate; P6 soft suitability answers whether the target suits
the student when eligibility permits or remains uncertain. INELIGIBLE cannot be
overridden by a score; UNKNOWN is not confirmed eligible; ELIGIBLE is not
automatically recommended. Uncertain ranks are provisional within their bucket,
never confirmed recommendation ranks. P6 Domain has no Repository,
Infrastructure, Tool, Seed, Raw, Manifest, filesystem, network, or LLM dependency.
Evaluation, RankingResult and RankedRecommendation are validated immutable
snapshots; changes require a newly validated result.

Skill Gap, Planner, Agent, MCP and Frontend must not reimplement or override P5
eligibility or P6 recommendation status, scoring, missing-signal and ranking-bucket
semantics. Only a genuine P6 contract / semantic defect reopens P6. Real skill
mapping, interest/goal/experience signals, resource cost, additional components,
candidate discovery, Top-K UI views and learned ranking are deferred capabilities.

P7 compares student skills with formal required/desired skills after target
selection, without recalculating eligibility, recommendation scores or ranking.
Competition currently lacks complete structured skill requirements. P7 must
establish a Skill Requirement / Expected Skill data contract or explicitly report
that missing required-skill data prevents a fully determined gap; competition
names and descriptions must not be used to guess skills. The conceptual flow is
`Eligibility → Recommendation → Selected Competition Target → Skill Gap → Learning / Planning`.

P7.1 adds pure contracts in `competition_copilot.domain.skill_gap`: exact
Edition/Track `SkillRequirementTarget`, REQUIRED/DESIRED `SkillRequirement`,
`SkillRequirementSet`, `SkillGapContext`, `SkillGapItem` and `SkillGapDecision`.
Skill identity and ordinal proficiency reuse `Skill.id` / `SkillLevel`; there is
no numeric gap or overall readiness score. Verified requirement source evidence
is separate from student evidence and system analysis audit. `SkillGapContext`
explicitly carries immutable `student_skill_evidence`; each relevant known skill
requires supplied evidence matching its canonical STUDENT_SKILL field and level.
Missing/UNKNOWN skills need no fake evidence; irrelevant skills need no evidence,
while any supplied additional or multiple-source evidence must match the profile.
Coverage is explicit
COMPLETE/PARTIAL/MISSING, retained in the decision's requirement set. Empty data
means MISSING, not no gap. Missing student skill facts produce UNKNOWN items,
not zero ability. NO_GAP requires complete coverage and all declared required
and desired skills known satisfied; a known gap can retain partial coverage or
other unknown student facts. Duplicate skills and cross-target data are rejected.

P7 snapshots and tuple collections are immutable and detach shared inputs,
including frozen views of reused Evidence. Construct new validated snapshots
for changed results. Validators reject inconsistent supplied conclusions; P7.1
does not compute gaps, run eligibility/recommendation, match learning resources
or build plans. It adds no Repository, provider, real requirement artifact,
filesystem, network or LLM dependency. Structured requirements must not be
guessed from competition names/descriptions. Synthetic contract tests run from the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_skill_gap.py`.

P7.2 `domain.skill_gap_engine.SkillGapEngine.evaluate(SkillGapContext)` returns a
validated immutable `SkillGapDecision`. Exact skill IDs match profile facts;
BEGINNER < INTERMEDIATE < ADVANCED is an explicit ordinal ordering, with UNKNOWN
unranked. Every requirement is evaluated in supplied order, preserving its type
and source evidence plus all matching supplied student evidence. Missing student
skills are UNKNOWN, never zero; missing requirements are UNDETERMINED, never no gap.
A known REQUIRED or DESIRED gap produces GAP_IDENTIFIED even with PARTIAL coverage
or other unknown skills. PARTIAL coverage cannot confirm NO_GAP; only COMPLETE
with all declared skills known satisfied can. Reasons and a deterministic system
analysis audit are retained. Contract errors fail atomically rather than becoming
business uncertainty. There is no skill guessing, readiness score, provider,
Repository, planning, eligibility/recommendation, network or LLM dependency.
Engine tests: `.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_skill_gap_engine.py`.

P7.3 adds `domain.skill_requirement_artifact.SkillRequirementSetEnvelope`, the
`application.skill_requirements.SkillRequirementProvider` abstraction and
`infrastructure.skill_requirement_json.JsonSkillRequirementProvider`. Storage is
`data/skill_requirements/`; `comap-mcm-2027.json` is the first reviewed real artifact,
authorized by P7.3B.4 human approval and authored in P7.3B.5 after official source
re-verification. Only mathematical-modeling is included, with unspecified threshold
and PARTIAL coverage. REQUIRED is human-reviewed structured interpretation, not an
official enum or P5 eligibility rule. No level or skill was guessed.
P7.4 integration and P7 Final Review passed; P7 status is FROZEN.

Envelopes version the unchanged P7.1 RequirementSet and resolve IDs through a
minimal embedded catalog of immutable views of existing Skill models. Evidence
must retain canonical REQUIREMENT binding and verified official provenance.
Coverage is explicit; completeness needs source review, never successful parsing.
Review/coverage notes are system assessments. Source review must separately prove
skill membership, type interpretation and any specified level; schema validation
cannot do that. Unspecified thresholds have presence evidence only.
Provider loads atomically in filename order, rejects duplicates/conflicts/invalid
artifacts and reads only local requirement JSON. `get_requirements(c, e, track)`
returns an immutable RequirementSet or None for no exact artifact, with no fallback.
None is missing data, never empty COMPLETE. Target existence and parent relationships
are validated against Repository by smoke tests/future orchestration, not Provider.
`list_artifacts()` exposes immutable version/catalog/review audit snapshots.
No students, gap computation, Raw/Manifest/Seed reads, Repository coupling, LLM,
network, Tool or planning are added to Provider.

P7.3 tests from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_skill_requirement_artifact.py backend/tests/infrastructure/test_skill_requirement_json.py backend/tests/integration/test_p7_skill_requirement_data.py`.
Real provenance/target smoke now executes against the reviewed COMAP artifact;
directory load and real Repository missing-target checks also run. A dedicated
test guards the exact approved one-skill scope, null threshold and empty level evidence.

P7.3B.2 resolves the audited known-requirement/unspecified-threshold Domain mismatch.
`SkillRequirement.required_level` explicitly accepts null for unspecified threshold,
distinct from missing requirements and StudentSkill.UNKNOWN. Mandatory
`presence_evidence` binds `requirements.<skill_id>.present = true`; `evidence`
remains threshold provenance and must be empty for null, matching and nonempty for
known level. Both channels reuse shared Evidence and verified source semantics.
Envelope validation keeps official provenance on both; Provider architecture is
unchanged. No legacy level fact is silently converted into a presence assertion.

Coverage COMPLETE can coexist with unspecified threshold. SkillGapItem now uses
immutable `reason_codes`, with requirement uncertainty before student uncertainty
when both apply. UNKNOWN can retain a known student level and its supplied evidence
when the threshold is unspecified; student provenance is not relaxed. Only both
known levels are compared. Known GAP wins over uncertainty; otherwise unspecified
threshold means UNDETERMINED. NO_GAP requires COMPLETE, every threshold specified
and every student fact known satisfied. System audit version is SKILL_GAP_ANALYSIS_V2.
The tenth/eleventh-edition and subtrack target gaps remain unresolved. P7.3B.2
added no real artifact; P7.3B.5 separately authors the approved COMAP artifact.
No skill or proficiency guessing is added by these artifact stages.


### P7.4 Real Skill Gap Integration

`backend/tests/integration/test_p7_skill_gap_integration.py` loads exact COMAP MCM
2027 Competition/Edition snapshots through the real Seed Repository and the
reviewed requirement through JsonSkillRequirementProvider. Students are explicitly
TEST-ONLY SYNTHETIC. Student A supplies ADVANCED mathematical-modeling and matching
canonical evidence; Student B supplies no such record/evidence. Since the real
threshold is null, both items are UNKNOWN; B retains both uncertainty reasons.
Both overall decisions are UNDETERMINED with PARTIAL coverage, never a confirmed
real gap or satisfaction. Official presence provenance and supplied student facts
survive the complete Context/Engine/Decision chain and JSON round-trip.

Run from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p7_skill_gap_integration.py`.
Tests check determinism, read-only models/artifacts, output immutability and a
missing exact real target. Reads are restricted to Seed and skill requirements;
no Raw/Manifest/eligibility-policy access, network, LLM, eligibility/recommendation
execution or planner. Production code and real artifacts are unchanged.
P7.4 Review and P7 Final Review passed. P7 status is FROZEN.

### P7 Closure and frozen scope

P7 Skill Gap scope is frozen. Frozen capabilities include SkillRequirement,
REQUIRED/DESIRED type, MISSING/PARTIAL/COMPLETE coverage, specified/unspecified
thresholds, requirement presence/proficiency and student evidence channels,
canonical fact binding, multi-reason uncertainty, immutable Context/Item/Decision,
deterministic SkillGapEngine aggregation, SkillRequirementProvider exact lookup
and JsonSkillRequirementProvider None-for-missing semantics, reviewed artifacts
and real integration. Runtime Repository/Provider perform data access only;
Engine accesses neither adapter, filesystem, network nor LLM.

Missing requirement data differs from a known requirement with unspecified
threshold. required_level=None means the latter only. Missing StudentSkill is
not BEGINNER / zero. UNKNOWN is neither GAP nor SATISFIED. PARTIAL cannot yield
NO_GAP; NO_GAP needs COMPLETE, all thresholds specified, all relevant students
known and all requirements satisfied. Known GAP takes precedence over uncertainty.

P5 is the sole hard eligibility authority: P7 REQUIRED denotes core skill
capability, not a participation restriction, and skill mismatch never directly
yields INELIGIBLE. P7 does not recompute P6 score, ranking or eligibility buckets.
It creates no resources, study plan, milestone, schedule, priority or plan diff.

P8 can consume SkillGapDecision: known GAP under GAP_IDENTIFIED can be a learning
need; UNKNOWN is only an uncertainty / information-acquisition need and cannot
automatically become a learning gap. NO_GAP must not generate unsupported remedial
tasks. Preserve PARTIAL and unknown items alongside any known gap. Future phases
must not reinterpret UNKNOWN as GAP or SATISFIED, PARTIAL as COMPLETE or REQUIRED
as an Eligibility hard rule. A real defect requires separate P7 reopening and Review.

Current reviewed data includes at least one real COMAP MCM 2027 artifact:
mathematical-modeling, REQUIRED human-reviewed structured interpretation,
unspecified threshold, PARTIAL coverage. This is not a complete COMAP skill set
or a determined student gap; neither limited data nor synthetic integration
students are phase failures. Counts are not frozen. Closure baseline snapshot:
1104 passed, 0 skipped; Ruff and diff check PASS, not permanent count invariants.

Deferred: more competition data, full taxonomy, cross-artifact Skill governance,
formal proficiency mapping / official threshold sources, Huawei child targets,
real Student source and profile ingestion, Learning Resource mapping, Planner,
Monitor / Event / Replanning, Agent / MCP / Frontend. See DEVELOPMENT_PLAN for
P8.1–P8.4 and P8 Final Review; the P7 Closure added no P8 functionality.

### P8.1 Planning Domain Contract

Review PASS. Existing CompetitionPlan and PlanMilestone in
`domain/plan.py` retain P1 identities/status/version/timestamps and optional
milestone timing/effort. They now use immutable validated snapshots and tuple
collections. Plan adds optional track_id, existing TimeWindow planning_horizon,
PlanningNeed tuples and a small supplied SkillGapPlanningAudit projection.

PlanningNeedType has SKILL_IMPROVEMENT (confirmed P7 GAP only) and
UNCERTAINTY_RESOLUTION (UNKNOWN or explicit missing/partial coverage). Relevant
SkillGapItem snapshots preserve reasons, levels, requirement type and provenance;
the full Decision is not duplicated. Caller retains the original decision and
supplies faithful projections. Milestones reference need IDs for purpose, without
a second kind enum; general/manual P1 milestones remain possible with no need ID.
NO_GAP allows an empty plan. No gap comparison, action generation, deadline
selection/default, priorities, resources, P5/P6 logic, Replanning or LLM/network
is added. Target existence/parent integrity remains a caller responsibility;
the contract rejects disagreement with the supplied P7 target and invalid references.
P7 semantics are unchanged. Planner Engine is not implemented.

P8.1 tests from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_planning_contract.py backend/tests/domain/test_plan.py backend/tests/domain/test_competition_plan.py backend/tests/domain/test_planning_event_integration.py`.

### P8.2 Deterministic Planning Inputs

Review PASS. `domain/planning_inputs.PlanningInputDeriver.derive`
accepts only validated SkillGapDecision and returns tuple[PlanningNeed, ...].
GAP -> SKILL_IMPROVEMENT; UNKNOWN -> UNCERTAINTY_RESOLUTION; SATISFIED -> no item
need. Dual uncertainty preserves both reasons in one need; overall GAP_IDENTIFIED
does not hide unknown items. PARTIAL/MISSING append one separate coverage need
(source_item=None), while COMPLETE itself adds none. NO_GAP returns an empty tuple.
source_audit returns the existing SkillGapPlanningAudit with exact source fields.

Item order is preserved, followed by coverage uncertainty. Stable IDs use exact
target, tagged scope, optional skill ID and type encoded as canonical JSON, never
display labels/random/time/hash(). Source items, type, levels, reasons and evidence
are preserved; no provenance is invented. P8.1 and P7 contracts are unchanged.
No Plan/Milestone, timing, learning content, resolution strategy, priority/score,
resources, P5/P6 evaluation, Repository/Provider, network/LLM, Agent or Replanning
is added by P8.2. Baseline building is documented below; P8 scope is FROZEN.

Targeted command from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_planning_inputs.py`.

### P8.3 Baseline Competition Plan Builder

Review PASS. `domain/baseline_plan_builder.BaselineCompetitionPlanBuilder`
consumes validated planning target, PlanningNeed tuple, optional TimeWindow and
explicit student_id/aware created_at. Pass the matching P8.2 source_audit for
nonempty needs, as required by CompetitionPlan. No P7 Decision is consumed.
One need becomes one milestone, preserving need order and source_need_id.
Purpose follows the referenced need; titles use deterministic templates for
improvement, skill uncertainty and requirement-set uncertainty. No concrete
learning content or resolution strategy is generated. Empty needs produce zero
milestones. Existing DRAFT/version 1 and PENDING defaults are reused.

Horizon is preserved; milestone start/due/estimated_hours remain None. Plan IDs
are versioned SHA-256 of canonical machine inputs, including ordered need facts,
target/student, explicitly supplied created_at, audit and horizon, excluding
evidence display prose. Material input changes change identity; milestone IDs
are plan-scoped (plan ID + need ID). No clock/random/hash() identity is used.
Target/audit and canonical P8.2 need target mismatch reject; general P8.1 IDs have
no embedded target and depend on the caller's matching audit. Output preserves
all needs/evidence through normal frozen validation. P8.1/P8.2/P7 are unchanged.
No scheduling/deadline/priority/duration/resource policy, P5/P6 logic, LLM/network,
Agent, Digital Twin or Replanning is added. P8 baseline scope is FROZEN.

Targeted command from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_baseline_plan_builder.py`.

### P8.4 Real Planning Integration

Review PASS. `backend/tests/integration/test_p8_real_planning_integration.py`
loads COMAP MCM 2027 through real JsonSeedCompetitionRepository and its reviewed
PARTIAL mathematical-modeling requirement through JsonSkillRequirementProvider.
TEST-ONLY SYNTHETIC known/missing student profiles and canonical student evidence
enter SkillGapContext -> SkillGapEngine -> PlanningInputDeriver -> baseline Builder.
Needs/plans are actual service outputs, not manually constructed substitutes.

The official threshold remains unspecified. Known ADVANCED skill still gives
UNKNOWN item / UNDETERMINED overall; missing skill retains both uncertainty reasons.
Both cases produce a skill uncertainty need and a separate requirement-set
uncertainty need, preserved as linked uncertainty milestones. No confirmed real
gap, satisfaction or improvement is invented. Horizon=None; fixed aware test
creation metadata keeps IDs stable, and milestones have no dates/effort/content.
Official provenance and supplied student facts survive Decision/Need/Plan audit.

Tests cover full-pipeline repeatability, cross-student isolation, JSON/immutability,
input/artifact read-only behavior and missing/wrong exact target lookups. Project
data reads are limited to Seed and skill requirements; network connections reject.
No Raw/Manifest/eligibility-policy reads, P5/P6 evaluation, LLM/Agent/MCP, resources,
detailed study plan, priority/duration, Digital Twin/Event or Replanning is added.
Production code, frozen contracts and real artifacts remain unchanged.
P8 Final Review PASS; P8 status is FROZEN.

Targeted command from repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p8_real_planning_integration.py`.

### P8 Closure and frozen scope

Frozen: Planning Domain Contract / exact target, PlanningNeed/PlanningNeedType,
skill vs requirement-set scope, existing TimeWindow horizon, P7-to-Need mapping,
coverage uncertainty mapping, Need identity, baseline builder, one Need -> one
Milestone, Plan/Milestone identity, timing non-invention and service purity.
Need scope uses source_item present/absent; milestone purpose follows its linked
source_need_id. All snapshots remain immutable and JSON serializable.

P7 is the sole gap authority; P8 never recomputes student vs required level.
GAP -> SKILL_IMPROVEMENT; UNKNOWN -> UNCERTAINTY_RESOLUTION, never confirmed gap,
improvement or satisfaction; SATISFIED -> no remediation. PARTIAL/MISSING are
requirement-set uncertainty, distinct from skill uncertainty and never fake skill
identities. COMPLETE itself adds none. Need describes why an action is needed;
baseline milestone does not prescribe how to learn or resolve uncertainty.
One need yields one milestone in input order; empty needs allow zero milestones.

Unknown/partial/full horizons are allowed, but no automatic deadline/dates, duration,
effort estimate or equal time splitting is performed. No resources, courses,
websites/books/videos, day/week plans, learning sequence, practice workload,
course ordering, time allocation, priority or detailed action strategy is generated.
P8 does not run P5 or change eligibility. REQUIRED skill is not a hard eligibility
condition. P8 does not rerun P6 scoring/ranking/target selection; target is already
selected upstream.
LLM=NO, Agent=NO, Network=NO; P8 is a deterministic planning core.

Current reviewed real integration snapshot: comap-mcm / comap-mcm-2027 / track=None,
mathematical-modeling, REQUIRED human-reviewed structured interpretation,
required_level=None, coverage=PARTIAL. Known student A still yields UNKNOWN /
UNDETERMINED; missing student B preserves threshold-unspecified and student-missing
reasons in one skill need. Both retain a separate requirement-set need and linked
uncertainty milestones, without fake improvement or timing. Synthetic profiles
are test-only; source provenance and interpretation remain distinct. Data/competition
counts are not frozen. Closure-time test snapshot: 1191 passed, 0 skipped, Ruff /
diff check PASS; these counts are not permanent Architecture invariants.

The real chain uses Repository -> data/seed and Requirement Provider ->
data/skill_requirements; no Raw, Review Manifest, Eligibility Policy, network or
LLM. Frozen P8 contracts/policies must not be silently changed for later stages;
a real defect requires explicit reopening and independent Implementation/Review.

Deferred: more real requirements/Student ingestion, resource mapping/recommendation,
priority/deadline/duration policy, detailed strategy/study plans, Digital Twin,
Monitor, Event Engine, Impact Analysis, Replanning/Plan Diff, Agent/MCP/Frontend.
Next is P9 Digital Twin -> P9.5 Monitor -> P10 Event Engine -> P11 Adaptive
Replanning -> P12 Agent. P9 observes competition dynamic state; it does not enhance
Planner, reinterpret Needs/Plans, directly change Plan or Replan. CompetitionPlan
stays stable downstream state; Event -> Impact -> Replanning belongs to P10/P11.
P12 may handle intent, tool choice, orchestration, clarification and explanation,
but cannot reimplement Eligibility/Recommendation/Skill Gap/Planning rules.
This Closure implements no future-stage functionality.

`CompetitionNormalizer` requires explicit competition, edition, and track IDs
plus a source type on raw input. It accepts only integer years and ISO datetimes
with a timezone (`YYYY-MM-DDTHH:MM:SSZ` or an explicit offset). It returns
provisional domain models with pending source verification; ambiguous dates raise
`NormalizationError` and no approval is performed.

`RawCompetitionData.temporal_provenance` optionally records a reviewed IANA
timezone, its basis (`source_explicit` or `jurisdiction_default`), minute/second
precision, and the supporting source text for each structured time field. Each
entry requires a non-null aware time whose offset matches that zone at the local
clock time. The Raw fixture and its SHA256 binding carry the human review of a
`jurisdiction_default`; the normalizer never infers a timezone from names,
language, or URLs. Date-only, month ranges, and stage schedules are not promoted
to structured clock times.

`CompetitionCandidateValidator` reads a candidate and optionally supplied known
competition and edition IDs. It returns recorded and newly found structural
issues without changing the candidate, contacting external sources, or approving
the data.

Human review uses `approve_candidate`, `reject_candidate`, or `mark_duplicate`
with an explicit timezone-aware review time. Approval checks validator errors;
it is never inferred from passing validation. `approved_bundle` returns detached
models from an approved candidate and does not write to storage.

Source verification is a separate explicit action in `ingestion/verification.py`.
It requires an approved candidate, a matching approved bundle, an aware review
time, and a nonblank note. It returns detached verified copies and an immutable
`SourceVerificationRecord`; the original approved bundle remains pending.

`ingestion/seed.py` reads existing version 1.0 Seeds and builds version 1.1
Seeds. Version 1.1 retains the structured time's reviewed timezone provenance
without copying Raw-only `source_text`. Its
builder accepts an approved candidate, a verified bundle, the validator's issues,
and a `data/raw/...` audit reference. `serialize_seed` returns UTF-8 JSON bytes;
`deserialize_seed` validates and restores the same envelope without reading the
Raw fixture or writing a Seed file.

`ingestion/batch_audit.py` performs a read-only audit of top-level Raw and Seed
JSON fixtures. It reuses the existing models, normalizer, and validator; it never
approves candidates, verifies sources, or creates Seeds. `scripts/` contains the
thin command-line entry point for this audit.

`ingestion/review_manifest.py` defines versioned, explicit human approval and
source-verification decisions. Decision timestamps describe when a person made
the decision, not when a later workflow executes it. `compute_file_sha256` and
`validate_raw_binding` bind each entry to the exact reviewed Raw bytes; loading
or validating a manifest does not execute approval, verification, or Seed creation.

`ingestion/review_executor.py` rechecks the manifest's Raw hash, rebuilds and
validates each candidate, and checks all three identity fields before acting on
explicit decisions. It continues checking later entries after one entry fails.
The CLI is a dry-run by default; only `--execute` calls the existing review and
verification actions and writes verified Seeds. A matching existing Seed reports
`already_materialized` without rewriting it; a conflicting Seed fails without
being overwritten. Manifest decision times remain separate from workflow
execution times.

`pyproject.toml` is the source of truth for direct dependencies.
`requirements.lock` records the exact versions of the verified development
environment, including transitive dependencies.

From `backend/` in PowerShell, with Python 3.11 or newer installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

From the repository root, audit the current fixtures with:

```powershell
.\backend\.venv\Scripts\python backend\scripts\audit_fixtures.py
```

Pass `--raw-dir` and `--seed-dir` to audit another pair of fixture directories.
The command returns 0 when all discovered inputs pass, or 1 for load,
normalization, validation-error, Seed, or ID-collision failures. Warnings and
Raw fixtures without a Seed do not cause failure.

From the repository root, inspect a review manifest without writing a Seed:

```powershell
.\backend\.venv\Scripts\python backend\scripts\execute_reviews.py data\review\gcxl-engineering-practice-innovation-2027.json
```

Add `--execute` only when the recorded human decisions should be applied. The
command reports `planned`, `executed`, `held`, `rejected`, `failed`, and
`already_materialized` counts and returns 1 if any entry fails. Verified Seeds
are written to `data/seed/<Raw basename>`.

There is no application start command yet. To build a wheel:

```powershell
.\.venv\Scripts\python -m pip wheel . --no-deps --wheel-dir dist
```

## P9.1 Digital Twin Domain Contract

P9.1 passed Review and is committed; P9 is still in progress. The
`competition_copilot.domain.digital_twin` module defines an immutable generic
competition/edition/optional-track target, explicit timezone-aware observation
snapshots, typed dynamic facts and a directed typed SnapshotDiff contract.
Current observed fields are edition registration/competition windows and the
complete edition track ID set. Existing `TimeWindow` and per-field
`SourceMetadata` are reused. Verified known facts distinguish KNOWN_VALUE from
explicit KNOWN_ABSENT; missing data is UNKNOWN. A known empty track set is not an
unknown set. A partial known window retains unknown endpoints.

Diff changes distinguish known value/presence changes from observation-state
changes, including endpoints inside partial TimeWindow values. UNKNOWN becoming
KNOWN_VALUE means information was obtained; it is not
evidence that the competition added a fact. The supplied before/after references
must identify the same target in observation order. The contract does not compute
changes or validate them against stored snapshots; that belongs to P9.3.

P9.1.1 Contract Follow-up supports reflexive same-snapshot zero-change comparison.
The same snapshot ID is valid only with otherwise identical reference metadata
and empty changes. Conflicting metadata or nonempty changes under the same ID
are invalid; distinct snapshots can still have empty changes.

P9.2 constructs baseline snapshots and validates ID-only target relationships
using Repository facts. P9.3 will compute deterministic Diff. P9.5 Monitor, P10 Event
interpretation and P11 Replanning remain future work. `CompetitionEvent` is
unchanged. P9.1 uses no Repository, Network, LLM, Agent or Plan logic.

Run its synthetic contract tests from the repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_digital_twin.py
```

## P9.2 Repository-backed Snapshot Builder

`competition_copilot.application.competition_snapshots.CompetitionSnapshotBuilder`
reads a verified Competition, Edition and complete Track list through the P3
`CompetitionRepository` interface. The caller supplies an edition-level
`CompetitionTarget` and timezone-aware `observed_at`. Missing targets and wrong
parent relationships fail explicitly. Track-level building is deferred until
independent track dynamic facts are available; P9.1 still supports track targets.

Edition `None` windows map to UNKNOWN; an existing full or partial `TimeWindow`
maps to KNOWN_VALUE. `list_tracks(edition_id) == []` maps to a known empty track
set. The builder emits no KNOWN_ABSENT because the Repository has no explicit
absence fact. Known fields require actual verified Edition/Track source metadata;
missing provenance fails instead of being invented. Snapshot time does not
overwrite source `observed_at`.

The stable snapshot ID hashes canonical machine target, UTC observation time and
typed dynamic state including provenance. Display names are excluded. The
builder neither modifies Repository data nor reads Seed files directly. This is
a Repository baseline observation without live monitoring, Network, LLM,
Diff, Event or Replanning. P9 remains in progress.

Run the P9.2 tests from the repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_competition_snapshot_builder.py backend/tests/integration/test_p9_snapshot_builder_smoke.py
```
