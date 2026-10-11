# Backend

**Stage status: P2, P3, P4, and P5 COMPLETE; P6.1/P6.2/P6.3 PASS; P6.4 Integration PASS.** The current ingestion
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
contract reviewed and frozen; P6 is not complete. `RecommendationContext` verifies
Competition/Edition/optional Track relationships and requires a matching P5
`EligibilityDecision`. `RecommendationEvaluation` reuses `DecisionResult` and
`Evidence`, preserves the P5 result, and separates recommendation status from
eligibility status. An ineligible target is blocked without a soft score; an
unknown eligibility result remains explicitly uncertain, even if a future
soft score is high. Eligible targets can be recommended, not recommended, or
left without a suitability conclusion when soft profile data is missing.
Optional scores and score components are limited to 0–1 soft suitability, not
eligibility probability. P6.1 defines no scoring formula, weights, ranking,
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
truncate Top-K, or use LLM/network. P6 remains incomplete. From the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_recommendation_ranking.py`.

P6.4 tests the full real Repository + Policy + P5 eligibility + P6 scoring/ranking
chain in `tests/integration/test_p6_recommendation_integration.py`. Soft signals
are explicit test-only fixtures, and synthetic ELIGIBLE decisions for real targets
exercise normal recommendation without claiming official confirmed eligibility.
Real partial/missing policies remain uncertain; real violations remain blocked.
Tests dynamically discover artifacts and verify mixed buckets, complete audit,
JSON, target integrity, determinism, and read-only Raw/Manifest-independent execution.
P6 is not COMPLETE until P6 Final Review. From the repository root:
`.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p6_recommendation_integration.py`.

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
