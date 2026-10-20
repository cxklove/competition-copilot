# Controlled Local Runtime data

`controlled_revision.json` is a synthetic, server-owned P11 proposal for local
development only. It is **not** an official competition change, real student record
or actual human consent. It never enters `data/seed` or an ingestion pipeline.

The fixture uses existing P8/P11 test constructors with real seed target identities,
fixed 2020 chronology and unchanged Domain validators. It contains an internal
preparation/provenance snapshot required by the existing P12.5 proposal contract.
The actual explicit APPROVE action must still traverse P12.5's authority bridge;
only that new bound authority can execute through P11. Browser delivery exposes
only the public PlanRef, ApprovalRequest and permitted result/evidence/PlanDiff data,
never this internal proposal or authority object.

Regenerate/check from repository root:

```powershell
.\backend\.venv\Scripts\python scripts/export_local_runtime_fixture.py
.\backend\.venv\Scripts\python scripts/export_local_runtime_fixture.py --check
```

The same generator produces `frontend/src/demo/local-plan.json`, the exact public
PlanReference for explicit selection. The runtime validates this selection against
the server's current Plan reference. Runtime execution never edits these files.
Restarting the local server resets this controlled scenario and invalidates every
opaque continuation handle. No durable business history or production auth exists.
