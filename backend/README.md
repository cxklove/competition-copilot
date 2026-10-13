# Backend

**Stage status: P2, P3, P4, P5, and P6 COMPLETE; P6.1/P6.2/P6.3/P6.4 and P6 Final Review PASS.**
**P7 — Student Profile & Skill Gap: FROZEN; P7 Final Review PASS.**
P7.1 and the student-evidence follow-up, P7.2, P7.3A, P7.3B.2,
P7.3B.5 and P7.4 passed review; P7.3B.4 received human approval.
StudentProfile Domain already exists and supplies input. P7 finished requirements,
evidence, deterministic diagnosis and real integration, not student ingestion.
**P8 — Competition Planner: FROZEN; P8.1–P8.4 and P8 Final Review PASS.**
Deterministic baseline planning scope is finished.
**P9 — Competition Digital Twin: FROZEN; P9.1/P9.1.1/P9.2/P9.3/P9.4 and P9 Final Review PASS.**
**P9.5 — Competition Monitor: CLOSED / FROZEN; P9.5.1–P9.5.4 completed,
Review PASS and committed; P9.5 Final Review re-run PASS.** Documentation follow-up
resolved the earlier blocker. **P10 — Competition Event Engine: CLOSED / FROZEN;
P10.1–P10.4 COMPLETE / REVIEW PASS / COMMITTED; documentation follow-up Review PASS
and P10 Final Review re-run PASS.** **P11 IN PROGRESS: P11.1 controlled mixed-impact
evolution Review PASS / committed / frozen; P11.2 Analyzer Review PASS / committed /
frozen. P11.3 Decision + Scope Service Review PASS / committed / frozen.
P11.3.5 Structured Replanning Input Contract IMPLEMENTED / REVIEW PASS / COMMITTED / FROZEN FOR DOWNSTREAM USE.**
P11.4 Plan Revision + PlanDiff IMPLEMENTED / AWAITING FINAL RE-REVIEW; P11.5 NOT IMPLEMENTED / NEXT PHASE.
Scheduler/polling is not implemented and is not an exit blocker. The current ingestion
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
stays stable downstream state; Diff -> Event belongs to P10, while
Event -> Impact -> Replanning belongs to P11.
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

P9.1 passed Review and is committed; P9 is FROZEN. The
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
using Repository facts. P9.3 computes deterministic Diff. P9.5 Monitor is implemented
below; P10 Event interpretation is implemented through P10.1–P10.4, while
P11 Impact Analysis / Adaptive Replanning remains future work. `CompetitionEvent` is
unchanged by P9.1; its controlled P10.1 evolution is documented below. P9.1 uses
no Repository, Network, LLM, Agent or Plan logic.

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
Diff, Event or Replanning. P9 is FROZEN.

Run the P9.2 tests from the repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_competition_snapshot_builder.py backend/tests/integration/test_p9_snapshot_builder_smoke.py
```

## P9.3 Deterministic Snapshot Diff

`domain.snapshot_diff_engine.SnapshotDiffEngine.compare(before, after)` consumes
validated snapshots only. Same exact snapshot returns a valid empty Diff; distinct
observations of the same fact state also yield zero changes. Target mismatch,
reverse time and same-ID metadata/content conflicts are rejected. Observation
time, snapshot ID and provenance-only changes do not create fact changes;
provenance-change diff is deferred.

UNKNOWN -> known and known -> UNKNOWN are observation changes. Whole-window
transitions remain one record; two known windows compare start/end boundaries.
Known track set changes retain one typed before/after set record, preserving
added/removed IDs. Known tracks -> UNKNOWN is not track removal, and unknown ->
known tracks is not member addition. Fixed field order keeps output deterministic.
Diff != Event, Diff != Impact and Diff != Replanning. No Repository, Monitor,
Network, LLM or Agent is used. P9 is FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_snapshot_diff_engine.py
```

## P9.4 Real Digital Twin Integration

The real chain uses Verified Seed -> JsonSeedCompetitionRepository -> Snapshot
Builder -> baseline Snapshot -> Diff Engine. Explicit COMAP MCM 2027 fixtures
verify two real same-state observations and reflexive comparison both yield zero
Diff. Huawei ICT 2026 covers real known membership. Later modified observations
are TEST-ONLY CONTROLLED fixtures, not official historical updates or Monitor
output. Known synthetic value/set changes have explicit manual fixture provenance
at example.invalid; official source metadata is never rewritten to support them.
Observation loss remains knowledge loss, not fact/member removal.

Tests use fixed aware times, validated constructors and deterministic case IDs;
check serialization, audit, immutability and safety; block Network/non-Seed data
reads and leave Repository/data unchanged. Production code is unchanged. P9
represents/builds/compares observations. Source observation/Monitor is implemented
in P9.5 below; Event, impact and Replanning remain future work. P9 Final Review
PASS; P9 is FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p9_real_digital_twin_integration.py
```

## P9 Closure — FROZEN

Snapshot/Reference, typed dynamic state/provenance, ObservationState, target/time/
identity, Repository mapping and low-level Diff contracts are frozen. UNKNOWN !=
KNOWN_ABSENT; Repository None -> UNKNOWN; known [] tracks -> known empty set.
Whole-field UNKNOWN differs from a known partial TimeWindow. Explicit aware
snapshot observation time does not rewrite source observed_at; Snapshot IDs are
deterministic machine identities. Same identical reference + empty changes is
valid; same ID with conflicting metadata or nonempty changes is invalid. Distinct
observations of equal fact state also yield zero Diff; time alone is not a fact change.

Unknown/known transitions are observation gained/lost, not fact additions/removals.
Different known values are structured value changes. Only known/known track sets
support member add/remove. P9.3 freezes canonical field/change order. P9.4 real
baselines preserve official provenance; controlled later fixtures are test-only,
not official historical updates. P9 does not verify websites, fabricate sources,
alter verification, generate Events, inspect Plans or replan. LLM/Agent/Network = NO.

Future defects require explicit P9 reopening and Implementation -> Review -> commit.
At P9 closure P9.5 was next; its implemented core is documented below, reusing
frozen observation/identity/Diff semantics. Periodic polling/scheduler/refresh,
freshness/retry/backoff, semantic rule-text/provenance diff, P11 impact/
notification/Replanning, Agent/MCP/Frontend remain deferred. Closure-time snapshot:
1335 passed, 0 skipped; Ruff/diff check PASS (not a permanent test-count invariant).

## P9.5 Monitor Core — CLOSED / FROZEN

P9.5.1–P9.5.4 are COMPLETED / Review PASS / committed; Final Review re-run PASS.
Closure freezes the deterministic one-shot Monitor core. P10 Contract status is below.

```text
Approved Official Source -> Official Source Observation Adapter
-> SourceObservationResult -> One-shot Monitor -> CompetitionSnapshot
-> P9 Snapshot Diff Engine -> SnapshotDiff -> MonitorCheckResult
```

Completed capabilities: stable immutable Monitor Contract, explicit aware time/
provenance, failure distinct from successful UNKNOWN, failure -> no authoritative
Snapshot/no Diff, successful UNKNOWN and protected KNOWN_ABSENT, deterministic
one-shot Monitor, same state -> SUCCESS + zero Diff, changed state -> SUCCESS +
low-level Diff, one concrete official Adapter with deterministic parsing/no
arbitrary URL/no LLM, real offline integration and read-only Repository. No
Event or Replanning leakage. SnapshotDiff is low-level structured change;
MonitorCheckResult is one check result. Neither is CompetitionEvent.

Implemented P10 consumes existing P9/P9.5 SnapshotDiff plus
necessary target/source context, without re-fetching websites, reconstructing
Snapshots or recomputing Diff. P11 owns Event -> Impact / Adaptive Replanning.

Scheduler/polling loop: NOT IMPLEMENTED, NOT P9.5 EXIT BLOCKERS. Future scheduler
invokes the one-shot Monitor and preserves its semantics. Deferred: second
competition adapter, multi-source monitor, periodic scheduler/polling, distributed
jobs, retry/backoff runtime policy, monitor rate limiting policy, Snapshot history persistence, notification,
Impact Analysis/Adaptive Replanning (P11), Agent, MCP,
Frontend. P10.1 Contract and P10.2 Engine are documented below.

### P9.5 Closure — Frozen Scope

- Frozen: Monitor Request target/context, outcome, SourceObservationResult,
  MonitorCheckResult, typed failures, explicit aware observation time and provenance.
- Fetch/parse/source-unavailable failure != successful UNKNOWN. Failed check has
  no authoritative new Snapshot and no Diff; successful observation may contain
  UNKNOWN facts. Missing selector/empty field/timeout/404/parse failure never means
  KNOWN_ABSENT, which remains an explicit sourced assertion under frozen P9.
- One call -> one source observation -> optional Snapshot/Diff -> MonitorCheckResult.
  With a baseline, unchanged state is SUCCESS + valid Snapshot + zero Diff; changed
  state is SUCCESS + low-level Diff. Initial success has no Diff; failure has neither
  output. No infinite loop, scheduler or daemon.
- Adapter maps approved source to typed observation only, without Snapshot Diff,
  Event, impact or Replanning. Fixed official URL/host, no arbitrary URL fetch,
  redirects rejected, no secrets. Network failures remain typed check failures.
- Same body/target/explicit time -> same result. No LLM parsing, invented clock
  times or timezone guessing; frozen temporal policy is retained. Official source
  provenance is preserved; HTTP success never upgrades verification.
- Monitor is read-only: no Repository/Seed mutation, auto-approval or auto-verification.
  It reuses P9 Snapshot, ObservationState, identity, SnapshotDiff and formal Diff Engine;
  no Monitor-specific Snapshot/Diff semantics.
- Real Repository + Builder + concrete Adapter + Monitor + Diff composition is proven
  by P9.5.4. Default tests stay offline/deterministic. Controlled fixtures are not
  official historical changes. No live smoke is added; future smoke must be optional/
  manual and outside default pytest/mandatory CI.
- Scheduler/polling is absent; future trigger invokes the one-shot Monitor without
  changing semantics. Snapshot history persistence is absent; future storage needs
  a separate storage/Repository contract, not Monitor Domain fields.
- SnapshotDiff and MonitorCheckResult are not CompetitionEvent. P10 owns business
  event mapping; P11 owns impact/severity/affected plans/user actions, PlanDiff,
  milestone updates and Adaptive Replanning. P9.5 has no notification, LLM or Agent.

All listed scope/security/interface/failure/parser/provenance/one-shot semantics
are FROZEN. Defects require explicit P9.5 reopen -> Implementation -> Review ->
commit. Multi-source merge and distributed monitor jobs remain deferred too.
Closure-time validation: 1434 passed, 0 skipped; Ruff/diff check PASS (historical
validation count, not a permanent invariant).

## P9.5.1 Monitor Contract — Review PASS, committed

`domain.monitoring` defines immutable MonitorCheckRequest, SourceObservationResult,
MonitorCheckResult, MonitorCheckOutcome and SourceCheckError. The Application
CompetitionObservationSource Protocol exposes one `observe(request)` capability,
with stable P9 target, explicit aware observation time, source metadata and optional
baseline Snapshot. It adds no HTTP/async framework or Repository write dependency.

Source check failure != fact UNKNOWN. Failure requires a typed error and forbids
state/new Snapshot/Diff; successful typed observation may contain UNKNOWN facts.
Known absence must be explicitly sourced, never inferred from missing selectors,
timeouts or HTTP errors. Source URL/type/verification policy is bound to the
request; a check cannot upgrade verification. All P9 fact/provenance semantics
remain frozen. Success requires a matching supplied Snapshot and a matching Diff
when a baseline exists; zero changes are success. These are validators, not a
Snapshot builder or Diff orchestration implementation.

P9.5.2 orchestration and P9.5.3 adapter are described below. The Contract adds no live network,
parsing, retry/backoff, scheduling/polling, Repository mutation, Event, impact,
notification, Replanning, LLM or Agent. P9.5 is CLOSED / FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_monitoring.py
```

## P9.5.2 One-shot Competition Monitor — Review PASS, committed

`application.monitor_checks.OneShotCompetitionMonitor(source).check(request)`
calls the injected ObservationSource once. Failure preserves the typed error and
returns no new Snapshot or Diff. Success binds target/time/source policy, constructs
the P9 Snapshot using validated state and the existing pure Snapshot ID helper,
then calls the formal P9 Diff Engine if a previous Snapshot exists. It neither
queries Repository nor duplicates Diff/identity rules. Initial checks have no Diff.

Successful UNKNOWN observations are supported. Same state is success with zero
Diff; changed state is success with low-level Diff. Provenance is taken from the
source result without verification upgrade. Fake sources exist only in tests;
orchestration adds no HTTP/parser, scheduler, polling/retry, persistence,
Event, notification, impact or Replanning. The concrete source adapter is described
below. Diff != Event; P9.5 is CLOSED / FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_one_shot_monitor.py
```

## P9.5.3 COMAP Official Observation Adapter — Review PASS, committed

`infrastructure.comap_observation.ComapOfficialObservationAdapter` implements
CompetitionObservationSource for comap-mcm / comap-mcm-2027 / track=None and
https://contest.comap.com/undergraduate/contests/mcm/instructions.php only.
The URL comes from reviewed Repository metadata. Its bounded schedule list has
explicit EST clocks; this is preferable to jurisdiction inference or SPA parsing.

Injected ComapPageFetcher separates parsing from HTTP. The default stdlib client
fetches only that fixed HTTPS URL, rejects redirects, disables environment proxies,
limits body size and performs no retry. No new dependencies or secrets are needed.
Parser uses the instructions title and exact 2027 heading/list, then labeled
registration-end/contest-start/end values. EST is fixed UTC-05:00 under the existing
reviewed policy. Date-only/unknown-zone/optional values stay UNKNOWN without invented
times. Track membership stays UNKNOWN; no label/track inference is implemented.

Fetch and parse failures are typed CHECK_FAILED, not UNKNOWN facts. Known facts
retain P9 validation; verification is preserved, not upgraded. The adapter returns
SourceObservationResult only; no Snapshot/Diff/Event, scheduling or Replanning.
Tests use a documented minimal synthetic fixture and block network. P9.5.4 real
monitor integration is described below; P9.5 is CLOSED / FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/infrastructure/test_comap_observation.py
```

## P9.5.4 Real Competition Monitor Integration — COMPLETED, Review PASS, committed

The integration suite runs real JsonSeedCompetitionRepository and SnapshotBuilder
for COMAP MCM 2027, then the concrete COMAP Adapter, OneShot Monitor and formal P9
Diff Engine. Only HTTP transport is replaced with deterministic synthetic HTML.
Default pytest is offline; no live smoke command/test is added. A manual live
smoke remains optional, outside mandatory CI.

Repository track membership is KNOWN empty, while the Adapter reports UNKNOWN.
First check correctly records coverage loss. The same-state zero-Diff case uses
that Monitor output as the next baseline: success + zero Diff is not failure.
All fixture changes are CONTROLLED OFFLINE FIXTURES, not official historical or
current website claims. Missing optional facts remain successful UNKNOWN; fetch/
parse failure returns no Snapshot and no Diff. Success returns Snapshot + Diff.

Tests cover value changes, provenance/verification, target/time safety,
determinism, serialization, immutable outputs and read-only Repository/data.
No production code changes, persistence, scheduler/polling, Event, impact,
notification or Replanning. Diff != Event; P9.5 Final Review PASS; CLOSED / FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p9_5_real_monitor_integration.py
```

## P10.1 Competition Event Domain Contract — Review PASS, committed

P10 CLOSED / FROZEN; P10.1 COMPLETE / Review PASS / committed. Existing `domain.event`
CompetitionEvent is evolved rather than duplicated. P1 id/target IDs/event_type,
occurred_at/observed_at/source/description and eight legacy enums remain supported;
legacy JSON shape is preserved. Existing usages were Contract/model integration
tests only. Event is now frozen; assignment and model_copy(update=...) no longer
work. Normal legacy construction/serialization remains compatible.

New types: REGISTRATION_WINDOW_CHANGED, COMPETITION_WINDOW_CHANGED,
TRACK_MEMBERSHIP_CHANGED, OBSERVATION_COVERAGE_CHANGED. Derived category is
FACT_CHANGE or OBSERVATION_CHANGE; legacy category remains None. P10 types require
source_diff and nonempty source_change_fields, validated against typed changes,
target and event classification. Existing IDs plus track_id expose P9 typed target.
The embedded Diff carries before/after references and full source evidence; selected
canonical fields support one or multiple underlying changes. source must be reused
from those records, never freshly fabricated. No Diff/change IDs are added to P9.

`competition_event_identity(type, diff, fields)` computes the Contract SHA256 ID
from canonical directed references/target/selected typed changes; validators check
it. Identity excludes detection time/display description. P10 observed_at is explicit
aware detection time, not earlier than after; occurred_at remains None for P10.
Nested values/collections are immutable and stable JSON. No severity, impact,
affected plans/student, status workflow or required summary. Legacy broad enums
are compatibility-only; P10 scope does not expand into rule/award/eligibility facts.

```text
Official Source -> P9.5 Monitor -> Snapshot -> P9 Diff -> SnapshotDiff
-> P10.2 Event Engine -> CompetitionEvent -> future P11 Impact/Replanning
```

Event != Diff, Event != Impact, Event != Replanning. P10.1 defines Contract only;
it adds no Diff mapping, aggregation/dedup engine, Repository access, network,
notification, LLM or Agent. P9/P9.5/P2–P8 remain frozen. P10.2 is described below.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_event.py backend/tests/domain/test_p10_event_contract.py
```

## P10.2 Deterministic SnapshotDiff to Event Engine — Review PASS, committed

`domain.event_engine.CompetitionEventEngine().interpret(diff, detected_at=...)`
accepts only validated SnapshotDiff and explicit aware detection time >= after
observation. Returns immutable tuple[CompetitionEvent, ...]. No current clock,
business occurred_at, source fetch, Repository read or Diff recomputation.

Exact P9 canonical field paths (including start_at/end_at) select factual window/
membership event types for VALUE_CHANGED/PRESENCE_CHANGED. Observation-state
changes always produce OBSERVATION_COVERAGE_CHANGED, including partial endpoints
and unknown track membership. Zero Diff -> zero Events; no change is not an error.

One low-level change -> one Event in P10.2. Two registration boundary changes ->
two distinct deterministic IDs, not aggregation. Fixed canonical ordering and
P10.1 identity/target/lineage/validators are reused. Each Event embeds the original
Diff and selects exactly one canonical source change. Source is first after
provenance, falling back to before provenance; full evidence remains in Diff.
No verification upgrade. Closed P9 field/kind types reject unsupported inputs.

Tests are offline and cover transitions, ordering, lineage, identity, explicit
time, serialization and immutable inputs/outputs. No aggregation, cross-call
dedup, persistence, severity, impact, notification, Replanning, network, LLM or
Agent is added by the primitive Engine. Event != Impact; Event != Replanning.
P10.3 normalization is described below; P10 implementation is complete. Frozen modules are unchanged.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_event_engine.py
```

## P10.3 Event Aggregation / Canonical Dedup — Review PASS, committed

`domain.event_aggregation.CompetitionEventAggregator().normalize(events)` accepts
an immutable tuple of validated P10 Events and returns a canonical immutable tuple.
P10.2 still produces one primitive Event per low-level change. P10.3 groups related
Events by target/full Diff lineage/type/exact field family. Same-family window
start/end combine; observation families and fact/observation types remain separate.
Different targets/Diffs/cycles never merge. Track add/remove are already captured
by one P9 membership before/after change, preserved without inventing extra records.

Exact duplicates collapse within the supplied batch; same-ID different content
and incompatible group detection times reject. Overlapping selected fields are
unique; generated canonical ID conflicts across groups reject as well. Fields are
canonically ordered. UTC representation normalizes equivalent aware
instants without mutating inputs. Aggregated identity reuses P10.1's helper for
all selected lineage. Representative display/source metadata comes from earliest
canonical field tuple; full evidence is retained. Output sorts target/directed
Diff times/references/full lineage, family, fact before observation, then type.

Empty/single Events are supported; already canonical single-family P10 Events
normalize too. Mixed-family and legacy inputs reject, without Event remapping.
No Diff recalculation, Repository, EventRepository/history/persistence, stateful
cross-run suppression, network, severity, impact, notification, Replanning, LLM
or Agent. Same batch tomorrow still returns the same Events. Frozen P10.1/P10.2/
P9/P9.5/P2–P8 are unchanged. P10.4 real integration is described below; P10
implementation is complete. Offline tests cover lineage, conflicts, permutations and stable JSON.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_event_aggregation.py
```

## P10.4 Real Competition Event Integration — COMPLETE, Review PASS, committed

The offline suite runs actual Repository/Builder, concrete COMAP Adapter,
OneShot Monitor/P9 Diff, P10.2 Event Engine and P10.3 Aggregator. Only HTTP response
transport/body is replaced. Minimal controlled fixture changes are not official
historical updates or claims about the current website. Tests block network/DNS
and protect Repository/data from writes; no production code changes.

Initial real baseline known-empty tracks -> Adapter UNKNOWN remains observation
loss. Next same-fixture check uses that production Monitor Snapshot as previous:
zero Diff -> zero primitive -> zero canonical Events. Registration start+end and
factual track cases are NOT_APPLICABLE because the frozen Adapter supports only
registration end and no track inventory. End-only registration is tested; controlled
competition start+end proves 2 primitive Events -> 1 canonical with both changes.

Successful missing facts generate observation Events; different coverage families
stay separate. Fetch/parse failure stops at Monitor, with no Diff and no P10 calls
or Events. Full-chain repeat and reordered primitive inputs produce identical
IDs/order/JSON. Typed lineage traces canonical Events through primitive changes,
Diff and original Snapshot references; provenance and explicit detection time are
preserved. No persistence, cross-run suppression, severity, impact, student/plan
access, notification, Replanning, scheduler, live network, LLM or Agent. P10 Final
Review re-run passed after documentation follow-up; all 19 exit criteria PASS.
P10 is CLOSED / FROZEN. Closure changes documentation only.

P10 input is SnapshotDiff; output is canonical CompetitionEvent[]. Current mapping
supports REGISTRATION_WINDOW_CHANGED, COMPETITION_WINDOW_CHANGED,
TRACK_MEMBERSHIP_CHANGED and OBSERVATION_COVERAGE_CHANGED only. Legacy material/rule
types are compatibility-only. Future scope requires prior Snapshot/Diff Contract
evolution and a separate mapping extension. Event != Diff; Event != Impact/Replanning.
KNOWN -> UNKNOWN means coverage loss, not registration/track removal. Zero Diff
produces zero primitive and canonical Events, with no heartbeat/NO_CHANGE_EVENT.

Aggregation requires the same target, full source Diff, EventType/category and
canonical field family; different targets, Diffs, families and fact/observation
Events remain separate. All unique source changes retain before/after Snapshot
lineage. Identity is canonical/deterministic, never random UUID, Python hash,
wall-clock-only or human-summary based. Time represents approved aware detection
context, not an unproven business occurrence time.

Subscription = NOT IMPLEMENTED; Notification = NOT IMPLEMENTED; neither is a
P10 exit blocker. Deferred: EventRepository, event history persistence, cross-run
duplicate suppression, subscription, notification, severity, Impact Analysis,
plan impact, Adaptive Replanning (P11), Agent, MCP and Frontend. Current dedup is
stateless and batch-local only. P10 does not refetch websites, build Snapshots or
recompute Diff.

P11 — Adaptive Replanning follows P10; its P11.1 Contract is documented below. Inputs are
canonical CompetitionEvent + StudentProfile + existing CompetitionPlan + necessary
planning context. P11 owns severity/risk, student/plan impact, affected milestones
and Adaptive Replanning; it must not refetch sources, rebuild Snapshots, recompute
Diff or regenerate Events.

### P10 Closure — Frozen Scope

Frozen: CompetitionEvent / CompetitionEventType, target, Diff/change lineage,
aware observation/detection time, deterministic identity, immutability and JSON;
four supported EventTypes above; fact/observation classification; one-change
primitive mapping; canonical aggregation key/field-family separation; batch-local
dedup; Event ordering; full unique lineage; Event != Impact/Replanning.
Same-ID content conflicts and incompatible group detection times reject.
Future defects require explicit reopen P10 → Implementation → Review → commit.

P10 only consumes SnapshotDiff. Events are competition-level, not student-specific;
no severity/risk, affected student/plan, Plan mutation, PlanDiff or Planner trigger.
No EventRepository, Event DB or history persistence; future storage needs independent
design. P11 will produce Impact Analysis, Affected Plan scope, Replanning Decision
and Plan Diff from Events and planning context. No P11 code is implemented here.

```text
Official Source -> P9.5 Monitor -> CompetitionSnapshot -> P9 SnapshotDiff
-> P10.2 Primitive Events -> P10.3 Canonical Events (CompetitionEvent)
-> future P11 Impact / Replanning
```

Closure validation: 1536 passed, 0 skipped; Ruff/diff check PASS (closure-time record).

## P11.1 Adaptive Replanning Domain Contract — controlled evolution Review PASS, committed / frozen

`domain/replanning.py` defines immutable supplied-result Contracts only, not impact,
decision, revision or PlanDiff computation engines are added by that module.
P11 IN PROGRESS; P11.2 implementation is described below. P10 Events are upstream
authority; P8 remains baseline Planner authority.

P8 audit: CompetitionPlan fields are id, student_id, competition_id, edition_id,
optional track_id/planning_horizon/skill_gap_audit, planning_needs, status, version,
milestones, created_at and updated_at. PlanMilestone fields are id, title,
description, start_at, due_at, estimated_hours, dependency_ids, status and
source_need_id. PlanningNeed contains id, kind, reason_codes and optional P7
source_item. All are immutable snapshots with stable JSON. Timing/horizon/hours
and statuses exist, but no priority/resources or Event/window dependency references.
dependency_ids are milestone references, not official-date dependencies.
P8 baseline remains one need -> one unscheduled milestone and infers no dates,
resources, priority or additional content. Plan/milestone IDs are caller-supplied
in Contract; baseline builder uses deterministic SHA256 IDs (milestone includes
plan/need IDs); PlanningNeed mapper uses canonical target/kind/skill identity.

EventImpactAnalysis binds a Diff-backed Event, exact PlanReference, student_id,
explicit aware evaluated_at, reason codes, typed reference evidence and scope.
It does not embed StudentProfile. Shared Evidence requires display prose/scalar
facts; P11 uses ReplanningEvidence for typed Event/Plan/milestone/field references,
retaining original source evidence in Event Diff lineage. Outcomes: AFFECTS_PLAN,
NO_PLAN_IMPACT, UNDETERMINED. Missing dependency != no impact. P8's stable Plan
track target can support a factual membership dependency claim; window dates alone
cannot prove impact. Validators reject claims without a changed target track;
they do not infer or evaluate impact. Different competition/edition or different
explicit tracks require NO_PLAN_IMPACT/TARGET_MISMATCH. Edition Event/track Plan
and track Event/edition Plan share context without proving dependency. Observation
coverage is not factual removal and can remain UNDETERMINED.

AffectedPlanScope is KNOWN (possibly empty), PARTIALLY_RESOLVED or UNRESOLVED, with
plan_id, whole_plan and canonical milestone IDs. Partial scope preserves known
refs plus unresolved remainder. Unknown is machine-distinct from known empty.
ReplanningDecision supports REPLAN / KEEP_CURRENT_PLAN / UNDETERMINED,
multiple unique canonical Event triggers, reasons and retained analysis evidence.
Confirmed impact takes decision precedence: any AFFECTS_PLAN requires REPLAN;
otherwise any UNDETERMINED requires UNDETERMINED; all NO_PLAN_IMPACT requires KEEP.
REPLAN requests the next stage, not a promise of a representable revision or a new Plan.
KEEP requires known no impact; pure uncertainty can retain the exact old Plan with empty Diff.

PlanDiff retains immutable before/after CompetitionPlan and decision/trigger/
reason/evidence lineage. Supplied PlanMilestonesChange contains typed before/after
milestone collections; no Diff computation occurs. First structural scope is
existing P8 milestones only, including their actual optional timing/status fields;
target/student/needs/audit/horizon/status stay unchanged. Changed Plan requires
REPLAN, next version, valid explicit timestamps and `revised-plan-v1:` SHA256
identity over exact before reference + ordered after milestones. Identity helper
only serializes supplied inputs; it never builds a Plan. Empty Diff reuses the
exact old Plan. P8/P10 Contracts/serialization remain unchanged.

No impact scoring/severity, notification, persistence, Network, LLM or Agent;
no P5/P6/P7 rule reimplementation or duplicated P8 Planner logic. No Plan mutation,
revision algorithm, planner rerun or active-plan replacement. P11.2 implements
Event + StudentProfile + Existing Plan -> EventImpactAnalysis using these Contracts.

```text
Official Source -> P9.5 Monitor -> SnapshotDiff -> P10 CompetitionEvent
-> future P11 Event Impact Analysis -> Replanning Decision -> Affected Plan Scope
-> Revised CompetitionPlan -> PlanDiff
```

Contract tests cover outcomes/uncertainty, target/track/evidence safety, multiple
triggers, explicit aware time, no-op/changed supplied Diff, identity, immutability
and JSON.

P11.1 safety follow-up passed re-review and is frozen. NO_PLAN_IMPACT requires verifiable
structured negative evidence: target mismatch or factual known/known membership
with the explicit Plan track present both before and after, cited in evidence.
UNRELATED_TRACK_CHANGE describes that proven basis. A reason code, including
NO_RELEVANT_PLAN_ELEMENT, or known-empty scope alone cannot prove no impact.
Missing window dependencies and same-target observation uncertainty remain
UNDETERMINED. Typed target-track removal/addition cannot be overridden by contrary
reason codes. Positive evidence cannot coexist with NO_PLAN_IMPACT; proven negative
evidence cannot masquerade as impact or uncertainty. These are constructor invariants,
not an Analyzer. KEEP + empty PlanDiff remains valid for proven no-impact analyses.
Old no-impact fixtures that asserted no impact for same-target windows without
dependencies now use a proven preserved-track basis; no frozen Contract was changed.

Run:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_contract.py
```

## P11.2 Deterministic Event Impact Analyzer — Review PASS, committed / frozen

`domain/event_impact_analyzer.py` CompetitionEventImpactAnalyzer.analyze(event,
student, plan, evaluated_at=<explicit aware datetime>) is a pure Domain Service.
Input: validated CompetitionEvent + StudentProfile + existing CompetitionPlan +
explicit evaluation context. Output: frozen EventImpactAnalysis only. Student ID
must match Plan student; no profile target exists and no profile prose/skills are
used to infer impact. Mutable StudentProfile is detached/revalidated, not stored.

Precedence: target mismatch -> factual track evidence -> observation uncertainty /
missing dependency. Competition/edition or different explicit track targets give
NO_PLAN_IMPACT / TARGET_MISMATCH with known-empty scope, even for observation Events.
Edition Event / track Plan and track Event / edition Plan are not automatic mismatches.
Window changes remain UNDETERMINED / PLAN_DEPENDENCY_NOT_REPRESENTED even when
milestone titles mention dates or supplied dates coincide. Observation coverage,
including membership lost/became known, is UNDETERMINED / OBSERVATION_ONLY_EVENT,
never factual removal. Factual target-track removal gives AFFECTS_PLAN /
TARGET_TRACK_REMOVED; preserved target with unrelated additions/removals gives
NO_PLAN_IMPACT / UNRELATED_TRACK_CHANGE. Target-track addition gives AFFECTS_PLAN /
PLAN_DEPENDENCY_MATCHED because frozen P11.1 explicitly requires that classification;
the Analyzer does not revise Contract to introduce ambiguous-added semantics.
Edition Plans or absent target membership without a proven transition remain unresolved.

Known impact requires positive typed evidence; known no-impact requires negative
typed evidence. Scope is KNOWN-empty for no-impact, UNRESOLVED for uncertainty,
KNOWN whole-plan target impact with no individual milestone claims for affects.
All outputs use normal P11.1 constructor, exact Event/Plan/source-field references,
explicit aware time and canonical reasons/evidence; no generated Impact ID exists.
No milestone title/description matching or unrelated student heuristics.

No Repository/hidden facts, website access, standalone Diff input/recalculation,
Event regeneration, decision engine, Plan/PlanDiff creation or mutation, Planner,
P5/P6/P7 calls, severity/score, notification, persistence, LLM or Agent. P11.1/P10/
P8/P9/P9.5 stay frozen. P11 remains IN PROGRESS. Implemented P11.3: ImpactAnalysis[] +
existing Plan + explicit context -> ReplanningDecision + canonical AffectedPlanScope;
no need to reinterpret Event, revisit P10 or refetch sources.

### P11.1 Mixed Impact Contract Evolution — Review PASS, committed / frozen

Explicit reopening repaired the P11.3 blocker without a parallel model or Service
in that Contract change. P11.3 Service is documented below.
Existing fields/old KNOWN and UNRESOLVED payloads stay unchanged; ScopeState adds
PARTIALLY_RESOLVED. It requires known milestone refs or whole-plan impact and implies
unresolved remainder. Pure UNRESOLVED has no known refs; KNOWN-empty cannot claim
uncertainty. `has_unresolved_remainder` is a derived property, not another serialized
flag. Refs are unique/canonical/immutable and must bind Plan/evidence.

Decision validates confirmed > unresolved > proven no-impact action precedence.
AFFECTS + UNDETERMINED -> REPLAN retains both analyses and PARTIALLY_RESOLVED scope;
whole-plan impact never erases unresolved detail. NO_IMPACT + UNDETERMINED remains
UNDETERMINED; all no-impact -> KEEP + KNOWN-empty. REPLAN scope preserves all known
confirmed refs and any unresolved analyses/partial confirmed scope. Mixed REPLAN
requires CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER; pure REPLAN accepts new
CONFIRMED_PLAN_IMPACT or existing STRUCTURAL_REVISION_SUPPORTED. Existing NO_PLAN_IMPACT
and IMPACT_UNDETERMINED reasons remain. All trigger/evidence lineage is retained.

Controlled compatibility change: AFFECTS -> UNDETERMINED decision, formerly allowed
for revision limits, now rejects under the mandated precedence; representability
belongs to later revision handling. No-impact safety remains unchanged. No Decision/
Scope ID exists; partial semantics are distinct in JSON. Scope extension and stricter
outcome/reason/scope validators are explicit schema/validation evolution.
P11.2/P8/P10/P9/P9.5 unchanged. P11.3 implementation is below; P11.4 implementation is documented below and awaits final re-review.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_mixed_contract.py
```

## P11.3 Deterministic Replanning Decision + Affected Scope — Review PASS, committed / frozen

`domain/replanning_decision_service.py` ReplanningDecisionService.decide(impacts,
plan, evaluated_at=<explicit aware datetime>) is pure Domain. Input is immutable
tuple[EventImpactAnalysis, ...] + existing CompetitionPlan + explicit context.
Output is the frozen ReplanningDecision; its `.scope` is canonical AffectedPlanScope.
No new result model, Decision/Analysis ID, revised Plan or PlanDiff is introduced.

P11.2 remains sole impact authority. Service uses supplied outcomes/scopes, not
EventType/source changes or milestone prose. Precedence: any AFFECTS -> REPLAN;
else any UNDETERMINED -> UNDETERMINED; else all proven no-impact -> KEEP. Empty
input rejects. All analyses must match the exact caller PlanReference (including
target/student/version/content digest). Trigger Event ID is the frozen unique
lineage key: exact duplicate analyses dedup within this batch, conflicting content
for one key rejects. No cross-run suppression. All unique analyses/evidence remain.

Confirmed milestone refs union uniquely in sorted canonical order; whole-plan
marker is retained. Confirmed + unresolved (or partial confirmed scope) ->
PARTIALLY_RESOLVED; pure uncertainty -> UNRESOLVED; resolved confirmed -> KNOWN
affected; all no-impact -> KNOWN-empty. No-impact contributes no affected refs or
uncertainty. Reasons reuse CONFIRMED_PLAN_IMPACT, CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER,
IMPACT_UNDETERMINED and NO_PLAN_IMPACT. Normal frozen constructor validates all
outcome/reason/scope/lineage consistency. Supplied aware instants normalize to UTC
for order-independent JSON; no auto-now and no input mutation.

No Event re-analysis, Analyzer/Planner/P5/P6/P7 rerun, Plan mutation/new Plan,
PlanDiff computation, severity/score, Repository/persistence, notification, Network,
LLM or Agent. P11.1/P11.2/P8/P10/P9/P9.5 remain unchanged. Tests cover mixed/pure
outcomes, scope union/completeness, plan conflicts, duplicates/identity conflicts,
permutations, time, input preservation, frozen output and JSON.
P11.4 input boundary: existing Plan + Decision + Scope + impact lineage + explicit planning
context -> deterministic Plan Revision + PlanDiff; no Event/Impact re-analysis.
P11.4 is implemented and awaiting final re-review below; P11 remains IN PROGRESS.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_decision_service.py
```

## P11.3.5 Structured Replanning Input Contract - IMPLEMENTED / REVIEW PASS / COMMITTED / FROZEN FOR DOWNSTREAM USE

P11.4's guard found no approved WHAT-to-change authority. `domain/replanning_input.py`
now defines ReplanningInput / UpdateMilestoneInstruction / RevisionAuthority only.
AffectedPlanScope describes WHERE; instructions describe explicit authorized WHAT;
P11.4 APPLY produces Revised CompetitionPlan and actual PlanDiff. No Event-to-Plan mutation guess or
automatic deadline adjustment is introduced.

MVP operation: UPDATE_MILESTONE, same stable milestone ID, explicit due_at change
only. Full expected-before and after PlanMilestone are supplied; all other fields
must match. ADD/REMOVE/REPLACE, title/description/start_at/hours/status/dependency/
source_need_id changes are deferred. Target, PlanningNeeds, audit, horizon and
plan-level status replacement are out of scope. Existing PlanDiff can audit this
update as a typed whole milestone-collection change; no Diff computation is added.

Instruction binds exact PlanReference/version/content, expected-before milestone,
and canonical source Decision fingerprint (P11.1 has no Decision ID). HUMAN_APPROVED
authority requires approval_ref, approved_by_ref, instruction_source_ref and explicit
aware approved_at. Trusted caller supplies authentic approval references; Contract
validates their shape/binding, not external authentication or an approval workflow.
No fictional production deterministic rule is declared. Instructions retain existing
need refs, valid dependency inventory and planning horizon. Approval must follow
Decision evaluation and precede supplied_at; no auto-now.

Statuses: EXECUTABLE for resolved known milestone scope covered by explicit updates;
PARTIALLY_EXECUTABLE for known instructions with remaining coverage/uncertainty;
UNRESOLVED for missing REPLAN instructions or UNDETERMINED decision; NO_REVISION_REQUIRED
for KEEP only. KEEP/UNDETERMINED reject structural instructions. Pure unresolved
scope cannot execute. Whole-plan impact permits individually approved operations
but remains PARTIALLY_EXECUTABLE conservatively, even when all milestone IDs are
targeted; it does not prove every impact resolved. Scope never creates instructions.

Batch is atomic desired-after intent, not ordered in-place mutation. One update per
milestone; exact duplicates/conflicts reject. Canonical order uses milestone ID.
Input/Instruction deterministic IDs are derived properties over typed payloads with
UTC instants; JSON reparse reproduces IDs (IDs are not redundant serialized fields).
No apply service, Plan revision, PlanDiff engine, Repository/persistence, notification,
Network, LLM or Agent. Frozen Plan/PlanDiff/Analyzer/Decision Service are unchanged.
Contract tests include an explicit approved due-date fixture and frozen PlanDiff
compatibility fixture, not a claimed Event-derived deadline rule. P11.4 input is
ready for this narrow executable path. P11.4 is IMPLEMENTED / AWAITING FINAL RE-REVIEW below.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_input_contract.py
```

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_event_impact_analyzer.py
```

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p10_real_event_integration.py
```

## P11.4 Deterministic Plan Revision + PlanDiff - IMPLEMENTED / AWAITING FINAL RE-REVIEW


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
and services remain unchanged. P11 remains IN PROGRESS; NEXT P11.5: Real Adaptive
Replanning Integration (NOT IMPLEMENTED / NEXT PHASE; not entered in this phase).

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_plan_revision_service.py
```
