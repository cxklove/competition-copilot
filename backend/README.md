# Backend

This directory contains the Python package (`competition_copilot`), domain
models (`competition_copilot/domain`), and unreviewed external data models
(`competition_copilot/ingestion`). Tests live under `tests/domain` and
`tests/ingestion`. `RawCompetitionData` keeps source values before normalization
or review. `CompetitionCandidate` holds provisional parsed data and validation
issues separately from official competition data. Neither record is an input to
eligibility, recommendation, or planning.

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
