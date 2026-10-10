# Backend

**Stage status: P2 and P3 COMPLETE; next: P4 Tool Layer.** The current ingestion
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
and result schemas, stable metadata, and structured error codes. The example
`ListEditionTracksTool` accepts an injected `CompetitionRepository`; it has no
JSON Adapter, Seed, Raw, Manifest, network, or LLM dependency. Its output wraps
formal Domain tracks without copying Domain fields. Run its focused tests from
`backend/` with `.\.venv\Scripts\python -m pytest tests/tools`.

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
