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


## Recommendation data foundation fixture

`recommendation_demo.json` contains a manually defined **LOCAL DEMO FIXTURE**,
`local-recommendation-demo`, and four formal edition identities for data-readiness
tests. It is not a real student and provides no consent or eligibility authority.
Its applied-mathematics skill fact is fixed, self-assessed synthetic data; it is
not generated from candidate scores, an LLM or a competition-name mapping.
The runtime adds this profile without replacing the existing undergraduate,
graduate or unknown profiles. Only skills are designated matching inputs for verified-skill-overlap-v1;
major/interests/goals/available hours are not scored.

The curated set is a review/test scope, **not a runtime candidate filter**.
Normal recommendation still evaluates all 12 formal candidates. This fixture defines no scorer, weight or scoring-policy version; the separate
Domain verified-skill-overlap-v1 component consumes its explicit skill records.
Exact requirement-ID overlap/non-overlap is only a data-condition check: an
absent skill is unknown ability, not a mismatch score. Partial requirements and
unspecified proficiency remain uncertain. Restart Local Runtime to load the
additional server-owned profile; select its ID through the existing explicit
request context. Existing runtime/frontend contracts are unchanged.

### Explicit student skill evidence

The fixture also supplies `student_skill_evidence`: typed declarations binding
student ID, exact skill ID and self-assessment to the existing Domain `Evidence`
field/value contract. These are explicitly declared simulated profile facts,
with `source=null`; they assert no official or external skill verification.
Application preparation validates identity, level and self-assessment before
Local Runtime supplies the facts to P7, including P8's real P7 prerequisite.
No evidence is generated for undeclared or absent skills. A relevant known skill
without explicit evidence still fails P7's existing completeness validation.
COMAP's unknown required proficiency and PARTIAL coverage remain undetermined;
C4's absent profile skill record remains unknown ability, not a deficit.

## Generated Huawei controlled observation

`generated_huawei_observation.json` is an explicit **CONTROLLED DEMO OBSERVATION**,
not an official announcement or claimed Huawei historical change. Its manual
`example.invalid` source and exact track target describe a test scenario in which
Innovation is removed from the observed membership set. `verification_status=verified`
means the synthetic fixture is explicitly accepted as controlled input, not that
Huawei actually removed a track. No official source is attached to the change.

The Application preparer checks before-membership against the formal Repository
baseline, retains unchanged window observations, constructs new manual snapshot
identities, then uses the real Diff/Event/Impact/Decision services and accepted
instruction preparation policy. It binds a freshly generated P8 plan, never the
old `controlled_revision.json` before plan. Missing skill requirements remain
MISSING/UNDETERMINED. Snapshots and history are in memory and reset with the host.
