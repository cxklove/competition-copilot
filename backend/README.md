# Backend

P14 Frontend + Runtime Invocation Compatibility is completed and CLOSED_FROZEN;
P12/P13 remain CLOSED_FROZEN. Local/AgentArts-compatible invocation shares the frozen
runtime/core and business authorities. P15 evaluation and P16 production deployment/
hardening remain deferred. Canonical lifecycle status: docs/DEVELOPMENT_PLAN.md.

## Local Agent Runtime development

After installing the existing `agent` and development extras (no AgentArts SDK
required), run from repository root:

```powershell
.\backend\.venv\Scripts\python scripts/run_local_runtime.py
```

This serves only POST `http://127.0.0.1:8765/runtime/invoke` using Python's standard
library ThreadingHTTPServer. `--port 0` chooses an available loopback port and prints
its URL. `--origin http://127.0.0.1:5173` selects an exact development browser origin
(repeatable); defaults are 127.0.0.1/localhost:5173. The frontend Vite same-origin
proxy is the normal development path; see frontend README and `.env.example`.
Direct browser connections also support CORS using the same exact `--origin`
allowlist: OPTIONS /runtime/invoke permits POST with Content-Type and returns 204
without invoking the runtime. Allowed-origin POST responses and public errors
include the matching Access-Control-Allow-Origin and Vary: Origin. Forbidden origins
receive no allow-origin header; wildcard origins and credentialed CORS are not enabled.
No-Origin non-browser POST behavior is unchanged. Restart the Local server after
updating the HTTP adapter before browser re-smoke.

The transport adapter calls the existing SDK-free P12.7 AgentArtsRuntimeAdapter,
which enters CompetitionCopilotAgent/LangGraph/the same Capability Facade and real
seed/policy authorities. No new Agent or business endpoint exists. The offline
intent proposal model recognizes documented demo phrases only; deterministic P12.6
grounded fallback and P5-P11 authorities supply all factual outcomes. Prepared P5/P7
prerequisites use the same Facade before P6/P8 invocation, never browser computation.

Request JSON remains the existing new-request/structured continuation envelope.
HTTP delivery wraps `runtime` (unchanged public AgentResponse/error plus opaque
continuation_ref when pending) and `presentation` (bound readonly public artifact
data). Internal GraphInput/trusted execution context never leaves the server. Runtime
errors have stable sanitized codes; business negatives are HTTP 200 normal results.

Hosting is an ephemeral, single-authorized-local-operator development boundary,
not production IAM or multi-user authentication. Bounded/expiring single-use handles,
exact P12 request/interaction validation and current Plan refs protect continuations.
Approval validation/execution is serialized; the actor and current Plan come from
server dependencies, never cookies/headers/browser roles. The controlled revision
fixture under `data/local_runtime` is synthetic, uses unchanged P8/P11 constructors,
and is not official history or consent. Only P12.5's explicit bridge grants new
execution authority; P11 produces the actual result. Repository/fixture files are
unchanged, and restarting resets all local pending/current-Plan metadata.

Targeted tests: `.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_local_runtime.py`
from repository root. Frontend `npm run test:local --prefix frontend` launches a real
temporary loopback server and closes it afterwards. External LLM/network/cloud are
not required. AgentArts-compatible invocation is described below; production auth/deployment/hardening
and durable storage remain P16.

## Independent Local Demo - optional provider-neutral cloud LLM

This demo wiring is separate from P15, which remains NOT_STARTED. P5-P11 truth,
P12 contracts/grounding/approval authority and P14 frontend/runtime contracts are
unchanged. Only backend Local composition can opt into a provider. The existing
offline Local/AgentArts compatibility harnesses still use deterministic models.

### Offline Local Demo (default)

After installing the existing Agent/development dependencies, start from root:

```powershell
.\backend\.venv\Scripts\python -m competition_copilot.integrations.local_runtime
```

The existing `scripts/run_local_runtime.py` command is equivalent. With no mode
environment variable, startup is offline even if OPENAI_API_KEY exists. To return
from a cloud demo explicitly, set COMPETITION_COPILOT_LLM_MODE=offline. Offline
startup does not import/construct langchain-openai or require an API credential.
Both modes use the same loopback endpoint and port/origin flags.

### Cloud LLM Local Demo (explicit opt-in)

Install the optional provider overlay without upgrading frozen Agent dependencies:

```powershell
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-cloud-llm.lock
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[agent,cloud-llm,dev]"
.\backend\.venv\Scripts\python -m pip check
```

The overlay pins langchain-openai 1.7.2, whose published requirement accepts the
unchanged langchain-core 1.6.10; LangGraph remains 1.2.15. ChatOpenAI is the only
provider entry. No application code calls the bare OpenAI SDK. Its SDK is an
ordinary transitive provider dependency. Existing Agent/AgentArts locks are unchanged.

Backend process configuration (not frontend/public configuration):

| Variable | Meaning |
|---|---|
| COMPETITION_COPILOT_LLM_MODE | offline by default; cloud is explicit opt-in |
| COMPETITION_COPILOT_LLM_PROVIDER | openai (default), bigmodel or deepseek only |
| COMPETITION_COPILOT_LLM_MODEL | Required in cloud mode; an accessible model supporting the selected output method |
| COMPETITION_COPILOT_LLM_BASE_URL | Optional explicit HTTPS API base path on the selected provider's official origin; blank uses the default below |
| COMPETITION_COPILOT_LLM_STRUCTURED_METHOD | json_schema, function_calling or json_mode; blank uses the provider default below |
| COMPETITION_COPILOT_LLM_INTENT_STRUCTURED_METHOD | Intent-only override; blank selects BigModel json_mode, otherwise inherits the generic method |
| COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE | Intent-only temperature; finite number strictly between 0 and 1; blank selects BigModel 0.1, otherwise retains provider default |
| COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS | Per-model-call timeout, default 30; finite and greater than zero, at most 120 |
| COMPETITION_COPILOT_LLM_API_KEY | Selected provider's backend-only API credential; required in cloud mode |
| OPENAI_API_KEY | Backward compatible fallback for openai only if the unified key is unset (not blank); never used for BigModel/DeepSeek |

Provider defaults (model IDs remain operator configuration, never business code):

| Provider | Base URL | Intent method / temperature | Explanation and clarification method |
|---|---|---|---|
| openai | https://api.openai.com/v1 | Existing ChatOpenAI default / provider default | Existing ChatOpenAI default |
| bigmodel | https://open.bigmodel.cn/api/paas/v4/ | json_mode / 0.1 | function_calling |
| deepseek | https://api.deepseek.com | function_calling / provider default | function_calling |

OpenAI Example: select `openai`; leave base URL and structured method unset/blank
to retain the existing official configuration. BigModel Example: select `bigmodel`
and an accessible GLM model supporting JSON mode and Tool Calling. DeepSeek Example:
select `deepseek` and an accessible Tool Calling model. BigModel Intent uses JSON
mode with the existing IntentRoutingProposal schema instructions and Pydantic
validation, without depending on an optional tool call. Intent-only temperature
0.1 uses a separate ChatOpenAI client configuration; constructing two clients does
not invoke either model. Explanation/clarification keep their original temperature.
The generic STRUCTURED_METHOD continues to configure explanation/clarification.
For BigModel, only INTENT_STRUCTURED_METHOD overrides the intent default, so an
existing generic function_calling setting cannot accidentally restore the old intent
failure path. For OpenAI/DeepSeek, intent inherits generic settings unless explicitly
overridden; their existing defaults remain unchanged.

The intent prompt distinguishes a known requested task from missing business context:
participation-eligibility questions select CHECK_ELIGIBILITY / check_eligibility,
with missing profile/competition/edition fields handled by the existing validator.
No model decides eligibility truth. The frozen graph may still expose intent UNKNOWN
while clarification is pending; verify the proposal and requested business fields,
not that public intent field alone. Missing context must not request INTENT merely
because a competition/student/edition was not provided.
Hard admission/registration questions select CHECK_ELIGIBILITY. Personal suitability,
comparison, recommendation and preparation priority select GET_RECOMMENDATIONS.
When a request combines eligibility with recommendation/priority, recommendation
takes precedence: the existing Local workflow prepares real P5 eligibility through
the Facade before P6 scoring/ranking. Such a subsumed prerequisite does not make
the request ambiguous or MULTI_STEP. Truly independent operations retain the existing
ambiguity policy. This prompt policy does not change Domain scoring or validator rules.

BigModel explanation/clarification and DeepSeek still use Function/Tool Calling by
default, not OpenAI json_schema response format. BigModel documents auto-only tool choice;
DeepSeek thinking mode also rejects forced tool choice. Both therefore omit forced
tool choice and parallel-tool options. A missing/invalid tool response fails closed
(or uses the existing grounded explanation fallback), without a second model call.
Tool schemas describe untrusted proposals/drafts only; they execute no business tools.
An explicit json_mode adds the same public output schema as JSON instructions;
all three methods still apply the existing Pydantic model validation.

The CLI reads process environment; backend/.env.example is a reference, not an
automatically loaded secrets file. Enter a model ID available to your provider account.
The following PowerShell startup avoids printing the key or placing it in history:

```powershell
$env:COMPETITION_COPILOT_LLM_MODE = 'cloud'
$env:COMPETITION_COPILOT_LLM_PROVIDER = Read-Host 'Provider: openai, bigmodel or deepseek'
$env:COMPETITION_COPILOT_LLM_MODEL = Read-Host 'Accessible structured-output/Tool Calling model ID'
# Clear overrides when switching providers; the matching safe defaults apply.
Remove-Item Env:COMPETITION_COPILOT_LLM_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:COMPETITION_COPILOT_LLM_STRUCTURED_METHOD -ErrorAction SilentlyContinue
Remove-Item Env:COMPETITION_COPILOT_LLM_INTENT_STRUCTURED_METHOD -ErrorAction SilentlyContinue
Remove-Item Env:COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE -ErrorAction SilentlyContinue
$env:COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS = '30'
$demoSecret = Read-Host 'Selected provider API key (backend process only)' -AsSecureString
try {
    $env:COMPETITION_COPILOT_LLM_API_KEY = [System.Net.NetworkCredential]::new('', $demoSecret).Password
    .\backend\.venv\Scripts\python -m competition_copilot.integrations.local_runtime
} finally {
    Remove-Item Env:COMPETITION_COPILOT_LLM_API_KEY -ErrorAction SilentlyContinue
    $demoSecret.Dispose()
}
```

Start the frontend from a separate terminal using its existing LOCAL-mode setup:
`npm run dev --prefix frontend`. Browser code/config never receives the key.
Startup prints only the loopback URL, LLM mode and model name. Missing credentials,
invalid configuration or unavailable provider fail fast with sanitized codes.
ChatGPT subscription is not an OpenAI API credential; use an API project/key and
its separate API usage/billing. No live provider invocation is part of required tests.

### Model and authority boundaries

Cloud mode constructs ChatOpenAI with the selected provider's official endpoint,
configured model/timeout and max_retries=0. The app-owned BASE_URL option accepts
only the selected official HTTPS origin (no userinfo/query/fragment or alternate
port), so credentials cannot be redirected across providers. Generic OPENAI_BASE_URL
is ignored. Changing provider never changes request/Domain/approval contracts. Neither
transport nor model invocation automatically retries a failed/unknown execution.

Each initial request uses LangChainIntentModel once. The resulting typed untrusted
proposal is admitted through the existing P12 routing catalog/validator, used to
prepare arguments solely from explicit caller/server context, then reused by the
same graph. The final P12 validator still authorizes routing with the completed
payload. There is no second graph/model route, new business validator or inferred
target ID. A failed intent model produces the normal sanitized P12 failure.

Cloud model missing_context is advisory, never input-existence authority. The
prepared boundary validates the typed proposal, then normalizes missing_context
to an empty tuple before both preflight and graph validation. Intent, capability,
ambiguity and asserted targets remain unchanged. The existing validator derives
required missing fields from the published input schema and actual prepared
arguments/bindings. It still rejects asserted target conflicts and clarifies genuine
intent ambiguity. No P12 contract or validator changes are needed.

An existing local-unknown StudentProfile with unknown education attributes is
present input, so P5 decides its unknown eligibility result. An unresolvable profile
ID contributes no invented StudentProfile; existing local bindings leave the required
student input absent and request STUDENT_PROFILE. Complete local-graduate context
executes P5 even when the model claims STUDENT_PROFILE is missing.
The Local server loads Python modules at startup and does not auto-reload changes.
After updating demo wiring, stop it with Ctrl+C and restart the documented command
before re-smoke. Restarting discards ephemeral pending workflows; begin a new request
rather than replaying an old continuation. Check the launched environment/source path
if an older process still reports a profile missing with otherwise complete context.

Structured clarification continues through existing P12 resolution. The normalized
prepared proposal is reused without another intent LLM call; core validates the
accepted clarification fields and arguments. LangChainHumanResponseInterpreter handles language only
against caller-owned P4 competition read choices and P12's exact-label validation.
Unknown/ambiguous choices remain unresolved; other fields use structured input.
The current frozen frontend continues to show structured clarification controls;
this does not introduce a natural-language approval UI or a new continuation contract.

LangChainExplanationModel receives only the existing authoritative explanation
projection/evidence/source data. P12.6 validates the draft and retains its grounded
fallback on invalid output/model failure. Eligibility, scores, skill gaps, planning,
replanning and PlanDiff still come from P5-P11. Approval never invokes a language
interpreter: explicit typed APPROVE/REJECT and P12.5/P11 remain authoritative.

Required offline checks:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_model_context_authority.py backend/tests/integration/test_bigmodel_intent.py backend/tests/integration/test_local_llm_providers.py backend/tests/integration/test_local_cloud_llm.py backend/tests/integration/test_local_runtime.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

Cloud wiring tests use a fake BaseChatModel plus real core/Domain services and block
external sockets. Frontend regression subprocesses explicitly select offline even
when the calling demo shell has cloud mode set. Tests never need a real API key.
Manual cloud smoke is optional: use the secure startup above with the selected
provider, then submit discovery and eligibility requests through the normal LOCAL
frontend. Check the authoritative structured results, clarification and typed approval
controls. This intentionally makes billable external calls only after operator opt-in;
no required pytest or CI job runs it. Account/model access must be checked by the
demo operator; offline compatibility tests do not certify live account availability.
BigModel re-smoke should repeat both discovery and eligibility prompts, recording
structural failures separately from wrong-intent/INTENT-field clarifications. The
scripted offline responses verify prompt delivery, parsing and core behavior; they
do not measure a real model's semantic accuracy. Invalid JSON/proposals still fail
closed with sanitized INTENT_MODEL_FAILED, with no retry or OfflineIntentModel fallback.
Never place credentials in VITE_/NEXT_PUBLIC_ variables,
fixtures, logs, URLs, screenshots or checked-in files. Explicit cloud mode sends
the request/context and authoritative result projections to the selected provider for the requested
intent/clarification/explanation calls; use the supplied synthetic local demo data.

References: [OpenAI authentication](https://developers.openai.com/api/reference/overview),
[LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai),
[provider package metadata](https://pypi.org/project/langchain-openai/1.7.2/),
[BigModel OpenAI compatibility](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction),
[BigModel Tool Calling](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling),
[DeepSeek API](https://api-docs.deepseek.com/),
[DeepSeek Tool Calling](https://api-docs.deepseek.com/guides/tool_calls/).

## AgentArts invocation transport compatibility

The server-only bridge implements official ExecuteRuntime forwarding; it does not
start a second Agent or deploy cloud resources. It reuses the existing Local HTTP
parser/drain behavior and forwards unchanged P12 JSON to the configured Runtime.
Server environment names are documented in backend/.env.example (reference only;
the CLI reads the process environment and does not auto-load .env files).

Required server environment: COPILOT_AGENTARTS_GATEWAY_URL (HTTPS access-domain origin),
COPILOT_AGENTARTS_RUNTIME_NAME and COPILOT_AGENTARTS_AUTHORIZATION (Bearer credential,
from your server environment only). Optional COPILOT_AGENTARTS_ENDPOINT selects a
version and COPILOT_AGENTARTS_GATEWAY_USER_ID is transport correlation only. Do not
put any credential in frontend environment, checked-in files, command logs or responses.
This compatibility adapter supports API Key/OAuth Bearer transport. IAM signing and
production credential acquisition/rotation remain P16.

From repository root:

```powershell
.\backend\.venv\Scripts\python scripts/run_agentarts_bridge.py
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agentarts_transport.py
```

The local trusted endpoint is POST /runtime/agentarts/{configured_runtime_name}/invoke
on loopback port 8766. Browser-supplied URLs/credentials/gateway user headers are not
forwarded. Only validated session correlation is passed to X-Hw-Agentarts-Session-Id.
No session/user metadata becomes Domain identity, actor, consent or trusted continuation.
Local Runtime on port 8765 and its endpoint/404/403/415 behavior remain unchanged.

The optional `create_hosted_app(host)` factory reuses the P12.7 SDK app entrypoint and
accepts the existing private LocalInvocationHost. That host calls the existing pure
adapter/CompetitionCopilotAgent/LangGraph/Facade/authorities and returns only public
runtime/presentation data with opaque handles. This factory adds no default global
application, credentials, business logic or cloud startup. Existing Local development
composition remains the bounded synthetic offline-intent example; production runtime
composition is caller-owned. Never expose raw GraphInput to browsers.

Tests use backend/tests/agentarts_gateway_harness.py, an official-shape loopback gateway
with synthetic authorization, deterministic time/nonces and the real core. It contains
no decision/PlanDiff implementation. It is test-only and not packaged as a production
server. Default tests require no external network, cloud or real credentials. No real
cloud smoke is implemented. P13 MCP stays separate; production deployment/auth remain
P16. Official source audit and transport/security gates are in docs/ARCHITECTURE.md.

## P11 Adaptive Replanning - Phase Closure

Status: CLOSED. Final Review: PASS. Frozen: YES / FROZEN FOR DOWNSTREAM USE.
P12 Agent: CLOSED_FROZEN; Final Review: REVIEW_PASS. P13 is CLOSED_FROZEN; Final Review: REVIEW_PASS; production deployment remains deferred to P16.
Canonical phase-status source: `docs/DEVELOPMENT_PLAN.md`; this document must agree.

| Phase | Scope | Status |
|---|---|---|
| P11 | Adaptive Replanning | CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE |
| P11.1 | Adaptive Replanning Contract | CLOSED / FROZEN |
| P11.1.2 | Canonical Plan Reference Serialization Compatibility Fix | CLOSED / FROZEN |
| P11.2 | Deterministic Event Impact Analysis | CLOSED / FROZEN |
| P11.3 | Replanning Decision + Affected Scope | CLOSED / FROZEN |
| P11.3.5 | Structured Replanning Input | CLOSED / FROZEN |
| P11.4 | Deterministic Plan Revision + PlanDiff | CLOSED / FROZEN |
| P11.4.2 | Plan-Level Replanning Resolution | CLOSED / FROZEN |
| P11.5 | Real Adaptive Replanning Integration | CLOSED / FROZEN |
| P12 | Agent | CLOSED_FROZEN |
| P13 | MCP + AgentArts MCP compatibility | CLOSED_FROZEN; P13.0-P13.6 REVIEW_PASS |

### Frozen authority map

- P11.1: typed result Contract authority, including controlled mixed-scope/status Diff extensions.
- P11.1.2: canonical PlanReference compatibility, not a new business authority.
- P11.2: Event impact authority.
- P11.3: ReplanningDecision + AffectedPlanScope authority.
- P11.3.5: structured authorized WHAT-to-change authority, including explicit coverage resolution.
- P11.4 / P11.4.2: deterministic authorized revision execution authority.
- P11.5: real-component integration proof only; no new business authority.

### Frozen safety semantics

1. Impact is tri-state: NO_PLAN_IMPACT / UNDETERMINED / AFFECTS_PLAN.
2. Missing represented Plan dependency -> UNDETERMINED, never proven no-impact.
3. Decision precedence: any AFFECTS_PLAN -> REPLAN; else any UNDETERMINED ->
   UNDETERMINED; else -> KEEP_CURRENT_PLAN. No voting or severity score.
4. AffectedPlanScope describes WHERE; it is not a RevisionInstruction/operation.
5. Reason code is neither structured evidence nor approval authority.
6. Structural changes require typed explicit revision authority/evidence and exact
   Plan/version/before-state preconditions; no Event-to-Plan mutation guessing.
7. PARTIAL cannot masquerade as COMPLETE; partial structural execution rejects.
   COMPLETE requires explicit coverage authority AND semantic compatibility.
8. KEEP -> unchanged Plan, identity/version/metadata, and empty PlanDiff.
9. UNDETERMINED -> unresolved input and no speculative revision; distinct from KEEP.
10. Confirmed TARGET_TRACK_REMOVED + REPLAN + original whole-plan scope may be
    resolved operationally by explicitly approved draft/active -> cancelled.
11. Cancellation does not choose another track or erase the Event. Preserve target
    identity, needs, audit, horizon and historical milestones; no automatic deletion.
12. Revision is atomic, before Plan immutable, and PlanDiff derives from actual
    validated before/after. Status-only cancellation declares no milestone change.
13. Full Event -> Impact -> Decision -> original Scope -> authorized Resolution ->
    Input -> Authority -> before/after Plan -> PlanDiff lineage is required.
14. Legitimate sourced P8 Plans retain source_item/typed URLs and support deterministic
    PlanReference, stable audit JSON and legacy identity. Explicit AnyUrl serialization
    retains original UTC/key/sequence/enum rules; unknown types still reject.
15. P11 Domain services have no Repository access, persistence or network side effects.
16. No LLM/Agent owns P11 business authority; downstream orchestration must delegate
    impact, decisions, authority validation and execution to deterministic services.

### Integration proof and resolved evolution history

P11.5 validates all three offline production-component paths:
- Proven no-impact -> KEEP -> NO_REVISION_REQUIRED -> unchanged Plan + empty Diff.
- Missing dependency -> UNDETERMINED -> UNRESOLVED -> no speculative revision.
- Controlled TRACK_MEMBERSHIP_CHANGED / target removal -> AFFECTS_PLAN -> REPLAN ->
  explicit COMPLETE coverage -> HUMAN_APPROVED active -> cancelled -> actual status Diff.

Repository-backed target data is real local Seed; controlled changes/approval are
TEST-ONLY scenarios, not official historical events or a claim that Huawei removed
a track. Final Review PASS; exit criteria 16/16 PASS; validation: 1824 tests, 0 skipped,
Ruff PASS, Diff Check PASS. P11.5 commit: 5394316; sourced-reference fix: bf792fc.
Earlier reason/evidence, mixed-scope, revision-input and whole-plan capability
blockers are resolved by controlled evolution. The sourced HttpUrl Final Review
defect is resolved by P11.1.2. Detailed historical rationale below is retained;
none of these historical blockers is an open P11 issue.

### Deferred scope and P12 boundary

P11 does not implement automatic replacement-track selection, automatic Eligibility/
Recommendation/SkillGap reruns, new PlanningNeed derivation from Events, Plan save/
replacement, Event history persistence, cross-run dedup persistence, scheduler/polling,
notification, Agent, MCP or frontend. Severity/impact scoring remains deferred.
Target-added impact has no complete cancellation policy. No supersession/replacement
relation or arbitrary Plan status machine is implied by the existing status enum.

P12 is CLOSED_FROZEN. Injected model proposals and explicit human replies are validated; the isolated Runtime Adapter reuses the same core graph. The Agent may understand natural-language intent,
select tools/workflows, orchestrate, clarify, explain and collect explicit approval.
It must not own Eligibility, Recommendation scoring, SkillGap, Event impact,
ReplanningDecision or revision execution rules; must not turn PARTIAL into COMPLETE,
bypass Revision Authority or mutate Plans directly. Approval collection submits
structured inputs through an authorized boundary; Domain remains the business authority.


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
and P10 Final Review re-run PASS.** **P11 Adaptive Replanning: CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE.**
P11.1 through P11.5, including P11.1.2/P11.3.5/P11.4.2, are CLOSED / FROZEN.
P12 Agent is CLOSED_FROZEN; P13.0 is REVIEW_PASS; P13.1 is REVIEW_PASS.
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
P11 Impact Analysis / Adaptive Replanning is CLOSED / FROZEN below. `CompetitionEvent` is
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
in P9.5 below; P10 Event and P11 impact/Replanning are CLOSED / FROZEN below. P9 Final Review
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
  event mapping; P11 owns impact/affected scope/authorized revision, PlanDiff,
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
-> P10.2 Event Engine -> CompetitionEvent -> P11 Impact/Replanning
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
planning context. P11 owns student/plan impact, affected milestones
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
design. P11 produces Impact Analysis, Affected Plan scope, Replanning Decision
and Plan Diff from Events and planning context. P10 does not implement P11 logic; the CLOSED / FROZEN P11 implementation is documented below.

```text
Official Source -> P9.5 Monitor -> CompetitionSnapshot -> P9 SnapshotDiff
-> P10.2 Primitive Events -> P10.3 Canonical Events (CompetitionEvent)
-> P11 Impact / Replanning
```

Closure validation: 1536 passed, 0 skipped; Ruff/diff check PASS (closure-time record).

## P11.1 Adaptive Replanning Contract - CLOSED / FROZEN

`domain/replanning.py` defines immutable supplied-result Contracts only, not impact,
decision, revision or PlanDiff computation engines are added by that module.
P11 CLOSED / FINAL REVIEW PASS / FROZEN; P11.2 implementation is described below. P10 Events are upstream
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
-> P11 Event Impact Analysis -> Replanning Decision -> Affected Plan Scope
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

## P11.2 Deterministic Event Impact Analysis - CLOSED / FROZEN

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
P8/P9/P9.5 stay frozen. P11 is CLOSED / FINAL REVIEW PASS / FROZEN. Implemented P11.3: ImpactAnalysis[] +
existing Plan + explicit context -> ReplanningDecision + canonical AffectedPlanScope;
no need to reinterpret Event, revisit P10 or refetch sources.

### P11.1 Adaptive Replanning Contract - CLOSED / FROZEN (controlled evolution history; resolved)

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
P11.2/P8/P10/P9/P9.5 unchanged. P11.3 implementation is below; P11.4 implementation is documented below, Review PASS / committed / frozen.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_mixed_contract.py
```

## P11.3 Replanning Decision + Affected Scope - CLOSED / FROZEN

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
P11.4 is Review PASS / committed / frozen; P11 is CLOSED / FINAL REVIEW PASS / FROZEN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_decision_service.py
```

## P11.3.5 Structured Replanning Input - CLOSED / FROZEN

Historical P11.4 guard found no approved WHAT-to-change authority; resolved by P11.3.5 and P11.4.2. `domain/replanning_input.py`
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
ready for this narrow executable path. P11.4 is REVIEW PASS / COMMITTED / FROZEN below.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_input_contract.py
```

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_event_impact_analyzer.py
```

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_p10_real_event_integration.py
```

## P11.4 Deterministic Plan Revision + PlanDiff - CLOSED / FROZEN


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
and services remain unchanged. P11 is CLOSED / FINAL REVIEW PASS / FROZEN; P11.5: Real Adaptive
Replanning Integration (implemented, Review PASS / committed, below).

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_plan_revision_service.py
```


### P11.4.2 Plan-Level Replanning Resolution - CLOSED / FROZEN

Controlled reopen only: P11.1 PlanDiff, P11.3.5 inputs and P11.4 execution.
P11.2/P11.3/P8/P10 production semantics are unchanged. P8 PlanStatus already has
 draft/active/completed/cancelled/superseded, but had no transition policy.
This phase defines only explicit approved draft/active -> cancelled, for verified
TARGET_TRACK_REMOVED. completed/superseded cancellation and cancelled no-op reject.
Target changes and supersession/replacement semantics remain deferred.

Plan cancellation means this particular Plan is no longer executable. It does not
mean withdrawal from the Competition, restoration of the track, erasure of the
Event, or selection of a replacement track. Preserve target identity, needs, audit,
horizon, historical milestones and created_at. No recommendation/gap/eligibility
rerun, generated content, persistence, Network, LLM, Agent or MCP.

UpdatePlanStatusInstruction carries exact expected PlanReference/version/content,
expected-before status, desired cancelled status, source Decision fingerprint,
original AffectedPlanScope and reused HUMAN_APPROVED RevisionAuthority references.
ReplanningInput adds optional plan_status_instruction and scope_resolution.
Cancellation cannot be combined with milestone edits in this first policy.

AuthorizedScopeResolution is immutable, with COMPLETE/PARTIAL/UNRESOLVED states,
explicit typed coverage, original scope, canonical instruction/milestone refs,
Plan/Decision binding and authority. Impact scope describes WHERE; resolution
specifies authorized executable coverage; instruction specifies WHAT; Diff records
actual changes. COMPLETE cancellation requires one exact authorized status instruction,
whole-plan confirmed removal impacts only, and no unresolved impacts/remainder.
Normal EventImpactAnalysis validation verifies typed removal lineage; execution
consumes that validated evidence without reinterpreting Events or SnapshotDiff.
Human approval cannot override semantic incompatibility. Target-added impacts have
no complete cancellation policy and reject. Milestone-only target-invalidation
edits remain PARTIAL, including explicit partial coverage; fake COMPLETE rejects.
Original impact, scope and uncertainty lineage is retained, never replaced.

P11.4 revalidates all inputs, executes only EXECUTABLE batches atomically, constructs
normal CompetitionPlan, then computes Diff from actual states. PARTIAL/UNRESOLVED
REPLAN still reject. KEEP and UNDETERMINED safe no-op behavior is unchanged.
PlanDiff adds optional immutable PlanStatusChange(before_status, after_status).
Status-only cancellation has no milestone change declaration. Full collection
snapshots still provide unchanged context for actual milestone revision.
The schema can distinguish empty, milestone and status change; simultaneous
status/milestone revision is deliberately rejected by this initial cancellation policy.

Reuse revised-plan-v1 identity derivation with status included when it actually
changes, version + 1, preserved created_at and explicit aware UTC execution time
for updated_at. Existing milestone identity derivation and input IDs without new
options remain unchanged. Old payloads parse; serialization schema adds nullable
status_change / plan_status_instruction / scope_resolution fields. Receipt retains
full resolution/instruction/approval payload alongside Diff/Event/Impact/Decision.

Real offline production probes in test_plan_level_revision.py use Repository targets,
P8 Builder, controlled test-only Event Engine lineage, unchanged Analyzer/Decision,
explicit human-approved fixture cancellation, normal input/resolution constructors,
and real Revision Service. Draft and active paths produce cancelled after Plan plus
actual status Diff, without substituted milestone scope. Controlled events and
approvals are test fixtures, not official historical changes or automatic rules.
Tests cover preconditions, fake complete, partial rejection, wrong impact, terminal
states, original context preservation, immutable JSON and determinism.
P11.5 integration is implemented, Review PASS / committed, as described below. P11 remains
CLOSED / FROZEN; P12 is CLOSED_FROZEN; Final Review is REVIEW_PASS; Closure is CLOSED_FROZEN. No P12 work or git commit in this Closure.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_plan_level_revision.py
```


### P11.5 Real Adaptive Replanning Integration - CLOSED / FROZEN

`backend/tests/integration/test_real_adaptive_replanning.py` proves the frozen
production-component chain, offline by default. No business orchestration service
or new rule is introduced. Real JsonSeedCompetitionRepository supplies huawei-ict /
huawei-ict-2026 / huawei-ict-2026-innovation Domain context. A minimal synthetic
StudentProfile and explicitly supplied existing uncertainty Need/audit context feed
real P8 BaselineCompetitionPlanBuilder. Active status is prepared with a normal
CompetitionPlan constructor (P8 supplied metadata), retaining baseline identity,
needs and milestones. No Eligibility/Recommendation/SkillGap rerun or duplicate
Planner implementation. This is not a new requirement-data inference.

Controlled membership/window Events, Snapshot references and approval references
are TEST-ONLY deterministic scenarios. They do not claim official historical changes
or actual removal of the Seed track. Local Seed is read-only and byte-identical after
tests. Socket connection/DNS guards reject network access; no live official fetch.
Every Event is produced by real P10 Engine, impact by real P11.2 Analyzer, Decision
and scope by real P11.3 Service, input/authority/resolution by normal P11.3.5/P11.4.2
constructors, and after Plan/Diff by real P11.4 Revision Service. No validator bypass.

Validated paths:
1. Unrelated track membership change with target preserved -> NO_PLAN_IMPACT ->
   KEEP_CURRENT_PLAN -> known-empty scope / NO_REVISION_REQUIRED -> unchanged
   Plan, ID/version/metadata and empty Diff with complete trigger lineage.
2. Same-target registration window change, dependency not represented ->
   UNDETERMINED impact / decision -> unresolved scope/input -> unchanged Plan and
   empty Diff retaining uncertainty. This is machine-distinct from proven KEEP.
3. Typed target-track removal -> AFFECTS_PLAN / TARGET_TRACK_REMOVED -> REPLAN /
   original whole-plan scope -> explicitly approved COMPLETE cancellation coverage
   -> UPDATE_PLAN_STATUS active -> cancelled -> actual revised Plan / status Diff.
   Target/student, horizon, audit, needs and historical milestones remain unchanged.
   No replacement track, deadline guessing or automatic instruction generation.

COMPLETE is approved operational cancellation, not erasure of the impact or track
restoration. Human approval cannot bypass semantic compatibility. Milestone-only
whole-plan target-removal edits stay partial and execution rejects; target-added
cancellation and missing approval evidence reject. Approved fixture values are
explicit, not derived from Event summary or milestone text.

Each main path executes twice with identical Event/impact/decision/scope/input/after/
Diff JSON and identities; typed JSON roundtrips cover all outputs and COMPLETE
resolution. Multiple-impact input permutations preserve canonical complete lineage.
Before Plan and Student serialization stay unchanged. PlanDiff is the actual Service
result, never a manually substituted expected Diff. No persistence, active-Plan
replacement, Scheduler, Notification, Network, LLM, Agent or MCP.

P11 Adaptive Replanning functional chain is complete for the supported paths;
P11.5 is CLOSED / FROZEN; P11 is CLOSED / FINAL REVIEW PASS / FROZEN FOR DOWNSTREAM USE.
Exit criteria 16/16 are covered by this integration and frozen phase regressions.
P12 input is ready at the deterministic contract boundary; no autonomous or model-based workflow is implemented.
A future Agent may collect explicit approvals and submit typed inputs through an
authorized boundary; it cannot recompute impact/decisions, bypass resolution or
mutate Plans directly. Frozen production semantics remain unchanged.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_real_adaptive_replanning.py
```


### P11.1.2 Canonical Plan Reference Serialization Compatibility Fix - CLOSED / FROZEN

Historical P11 Final Review found this sourced P8 Plan defect, now resolved by P11.1.2:
PlanningNeed.source_item (SkillGapItem) retains nested HttpUrl source evidence;
Plan JSON serialization worked but PlanReference digest raised TypeError.
Controlled follow-up extends only the canonical serialization boundary for the
explicit Pydantic AnyUrl family (including HttpUrl/AnyHttpUrl), using its formal
JSON URL representation. No default=str, repr or arbitrary-object fallback.
Existing UTC datetime, enum, collection and sorted-key semantics are unchanged;
previously unsupported types still reject. Pre-fix URL-free digest/identity
constants are retained. No P8 schema, evidence deletion or P11 business-rule change.

Focused tests reuse the existing real P8 COMAP planning chain without copying it
or removing source_item. Both student fixtures cover reference equality, Plan JSON
roundtrip, Analyzer/Decision lineage and safe unresolved revision/Diff serialization.
Typed URL construction is offline, without URL accessibility checks or DNS/network.
P11.5 is IMPLEMENTED / REVIEW PASS / COMMITTED (5394316).
This compatibility defect is resolved by committed P11.1.2 (bf792fc).
P11 Final Review retry PASS; P11 is CLOSED / FROZEN. P12 is CLOSED_FROZEN; Final Review is REVIEW_PASS; Closure is CLOSED_FROZEN.
The original follow-up made no git commit; Closure is a documentation-only update.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_replanning_reference_serialization.py backend/tests/integration/test_replanning_reference_serialization.py
```

## P12.0 Framework & AgentArts Compatibility Baseline

Current canonical status: docs/DEVELOPMENT_PLAN.md. P12 CLOSED_FROZEN;
P12.0 REVIEW_PASS (baseline commit 73d3d71); P12.1 REVIEW_PASS; P12.2 REVIEW_PASS; P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN.
Agent framework: LangGraph; support: LangChain Core; Domain schema: Pydantic 2.
MVP: one platform-neutral orchestrator invoking Tool/Application deterministic
capabilities, not a supervisor or autonomous ReAct core. AgentArts is a thin
runtime/deployment integration target; Domain keeps all business authority.

Python requirement >=3.11; current local CPython 3.12.9 / Pydantic 2.13.5. Existing
PEP 621 core/dev dependencies, requirements.lock and explicit setuptools package
list remain unchanged. At P12.0 LangGraph/Core installation was DEFERRED to graph phase;
future optional agent extra/lock contains only required abstractions. AgentArts
SDK is DEFERRED / optional isolated runtime dependency, never a core import.
No model provider, graph, tool router, approval flow, OTel/probe or MCP is added.
No cloud/network invocation or SDK/package smoke is claimed in this phase.

Core development is supported on Windows. Per the official AgentArts deployment
baseline, final image validation uses Linux Ubuntu 22.04 ARM64 and project-compatible
Python >=3.11 (SDK minimum 3.10+ does not override backend). Runtime/ARM64 image
execution remains NOT_TESTED. Local/runtime semantic parity is mandatory at the
adapter boundary; initial adapter P12.7, compatibility integration P12.8,
P16 AgentArts Production Deployment & Hardening. No cloud resources are created.

See docs/ARCHITECTURE.md for stable rationale, boundary and official sources;
see docs/DEVELOPMENT_PLAN.md for subphases and Gates A-F. Existing backend install,
pytest and Ruff commands above are unchanged; the P12.3 Python graph entrypoint is documented below; P12.4 adds injected intent models; no interactive CLI or configured live provider exists.

## P12.1 Agent Contract & State

Status: REVIEW_PASS; P12 overall CLOSED_FROZEN. P12.0 is REVIEW_PASS
(baseline commit 73d3d71); P12.2 REVIEW_PASS; P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.
Package: competition_copilot.agents (the plural directory selected in P12.0).
contracts.py defines interaction/audit envelopes; state.py defines immutable snapshots.
AgentRequest, intent, clarification, explicit approval, capability invocation reference,
AgentResponse and AgentState are provider-neutral Pydantic 2 values. All IDs are
caller-owned; no random/clock IDs or implicit approval. Optional context never selects
a default competition. PlanReference and P4 ToolResult are reused, not replaced.
No Domain service is executed and no business decision, graph, router, reducer,
model, memory, SDK adapter, network or persistence is implemented. Reference existence,
approval provenance and P11 authority conversion remain later authorized-boundary work.
Gate A-E contract tests PASS; deployment Gate F is DEFERRED. LangGraph/Core/SDK
dependencies remain deferred as documented; only setuptools package enumeration changes.

Install using the existing editable backend/dev command above; focused validation:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/agents/test_agent_contracts.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

## P12.2 Agent Capability / Tool Facade

Status: REVIEW_PASS; P12 overall CLOSED_FROZEN; P12.1 REVIEW_PASS;
P12.3 REVIEW_PASS; P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS. Canonical status remains docs/DEVELOPMENT_PLAN.md.
competition_copilot.agents.capabilities adds a static approved capability facade,
typed argument/result envelopes and JSON-safe discovery metadata. It reuses P12.1
invocation refs, six P4 Tools, existing Applications and injected deterministic
authorities. Caller composition provides dependencies; no Repository adapter is
constructed by the facade. Formal Domain outputs/reasons/evidence/sources are retained.
Approved revision requires P11 ReplanningInput; Agent approval responses do not grant
authority. Source monitoring remains unexposed; P12.5/P12.6 now add internal human
continuation and Graph explanation, without new selectable facade capabilities.
The P12.2 baseline added no Graph/model/routing/approval flow/MCP/SDK/persistence or
dependencies. Full exposure inventory and gates are in DEVELOPMENT_PLAN.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_capability_facade.py
```

## P13.0 MCP Protocol & AgentArts Compatibility Baseline

P12 remains CLOSED_FROZEN. P13 is CLOSED_FROZEN; P13.0 is REVIEW_PASS.
P13.0-P13.3 are REVIEW_PASS; P13.4 is REVIEW_PASS; P13.5 REVIEW_PASS; P13.6 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN.
DEVELOPMENT_PLAN is the canonical lifecycle, capability inventory, compatibility
matrix and independent MCP gate source (A-H baseline, I/J in P13.4, K/L in P13.5, M/N in P13.6).

P13 designs Competition Copilot as a Tools-only MCP server: typed projection ->
existing Capability Facade -> existing authorities. This differs from P12.7
AgentArts Runtime, which runs the complete Agent/Graph. No MCP server, endpoint,
concrete tool names, registry implementation or handlers are added in P13.0.
No dependency/configuration changes or new installation/run commands are needed.

The baseline targets modern MCP 2026-07-28 plus AgentArts-compatible 2025-11-25
over Streamable HTTP; stdio is optional development/testing and legacy SSE is not
primary. P13.4 below records actual local HTTP verification of these targets. MCP dependencies
already installed transitively with optional AgentArts SDK do not implement MCP.
P13.2 selects the official SDK; P13.4 verifies both protocol paths over HTTP locally.

Every capability requires individual exposure review. READ/DECISION are candidates;
mutation (`revise_plan`) is not exposed by default. Authentication/session metadata
cannot establish human approval, P11 authority or business identity. No Sampling,
Elicitation, Resources, Prompts, external MCP consumption or extra web search is
planned. Inputs are structured and business execution is stateless. Official
protocol/Gateway sources and metadata/result restrictions are recorded in the plan.
Production auth/cloud/ARM64 deployment remains P16; no deployed MCP/Gateway support
or durable sessions are claimed.

## P13.1 MCP Tool Exposure Contract

Status: REVIEW_PASS. The SDK-free `integrations/mcp/` package
defines typed input/result envelopes and an immutable explicit exposure registry.
Eight names are admitted: `competition_list`, `competition_get`,
`competition_editions_list`, `competition_edition_get`, `competition_tracks_list`,
`competition_track_get`, `competition_snapshot_build`, `eligibility_check`.
They reuse existing payloads and canonical Capability Facade receipts. Other
decision capabilities await trusted artifact admission; mutation and Agent
internals are excluded. Full exposure matrix and gate dispositions are canonical
in DEVELOPMENT_PLAN. Business decisions remain Domain-owned.

No MCP SDK/runtime dependency, server, tools/list/tools/call RPC handler, HTTP
endpoint or Gateway connection is added. Existing backend installation commands
remain valid; no new application start command exists. Contract tests run offline:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_exposure_contract.py
```

## P13.2 MCP Server Core & Tool Catalog

Status: REVIEW_PASS. The optional official MCP SDK 2.3.0 powers
`competition_copilot.integrations.mcp.server.build_mcp_server(registry=None)`.
Its tools/list publishes only P13.1 registry metadata and generated schemas.
P13.3 extends the original disabled call boundary with guarded Facade execution,
as described below. Unknown/excluded names still fail closed. P13.4 adds the SDK
Streamable HTTP app; no Gateway connection exists. P16 retains production deployment.

MCP installs independently of AgentArts and LangGraph. From the repository root,
using the existing backend virtual environment:

```powershell
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-mcp.lock
.\backend\.venv\Scripts\python -m pip install --no-deps -e backend
.\backend\.venv\Scripts\python -c "from competition_copilot.integrations.mcp.server import build_mcp_server; print(type(build_mcp_server()).__name__)"
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_server_core.py backend/tests/integration/test_mcp_import_boundaries.py
```

The project declares an optional `mcp` extra; the lock commands above retain exact
development pins. AgentArts installs include this same MCP overlay. Existing core
and Agent-only installs remain SDK-independent. No package build procedure changes.
No process/server starts on import or construction; this phase uses public SDK
`Client(server)` in-process tests, without ports, stdio loops, network or credentials.
Tests assert registry/catalog fidelity, JSON safety, deterministic independent
connections, invalid-call rejection and SDK import isolation. There is no standalone
production transport startup configuration; P13.4 provides the ASGI app factory below.

## P13.3 Safe Tool Execution & Result Mapping

Status: REVIEW_PASS. MCP tools now execute the eight approved
capabilities through the existing P12.2 Facade, supplied explicitly by trusted
outer composition: `build_mcp_server(facade=configured_facade)`. This does not
create a Repository, guess data paths or construct an Agent. Calling without an
injected Facade fails closed; the existing construction smoke remains catalog-only.

Exact registry lookup, exposure/mutation checks and typed validation precede one
Facade execution. Canonical receipts pass unchanged as structured JSON plus
deterministic JSON text. INELIGIBLE/UNKNOWN remain successful execution, with
reason/evidence/source lineage preserved. Unknown names, invalid fields, mutation
attempts and unexpected errors fail safely; no retry, LLM, Graph or session context.
The frozen catalog names, schemas and ordering are unchanged. Other decision
capabilities remain withheld; human approval/revision is not exposed through MCP.

Using the existing optional MCP installation, run offline tests from repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_execution.py backend/tests/integration/test_mcp_call_integration.py
```

Tests compose real Repository/P4/P5/P9 authorities with explicit dependencies and
use public SDK in-process calls. Streamable HTTP and protocol-era verification
are described in P13.4 below; Gateway compatibility remains P13.5. No production server, Gateway
connection, mutation support or durable session is claimed. No dependencies added.

## P13.4 Streamable HTTP & Protocol Compatibility

Status: REVIEW_PASS. The official SDK ASGI transport is available
through `competition_copilot.integrations.mcp.http.build_streamable_http_app(server)`.
Pass the same `build_mcp_server(facade=configured_facade)` core assembled by trusted
outer composition. Registry, dispatcher, mapper and business authorities are shared
with the local path. No default business data paths, second HTTP API or server
startup side effect. Existing MCP installation/lock commands remain sufficient.

P13.0 targets are locally verified: 2025-11-25 initialize and 2026-07-28 discover,
tools/list and tools/call over Streamable HTTP. Both protocols and local invocation
preserve equal canonical receipts, including INELIGIBLE/UNKNOWN success, source
metadata, evidence refs, URLs and timezones. Unsupported versions fail closed.
MCP session/header/admin metadata cannot provide identity or approval. The SDK
uses stateless HTTP and ordinary JSON responses; there is no business streaming
or automatic business retry. Connection loss may leave caller outcome unknown.

From repository root, using the existing optional MCP environment:

```powershell
.\backend\.venv\Scripts\python -c "from competition_copilot.integrations.mcp.http import build_streamable_http_app; from competition_copilot.integrations.mcp.server import build_mcp_server; print(type(build_streamable_http_app(build_mcp_server())).__name__)"
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_http_compatibility.py backend/tests/integration/test_mcp_import_boundaries.py
```

The construction smoke creates an inert app; business calls require an injected
Facade. Tests use official SDK HTTP clients via in-process ASGI with sockets blocked;
`localhost:0` is only a logical URL, no port is opened. No real credentials/network
service are required. MCP Gates I/J cover protocol semantic parity and transport
isolation. Gateway-specific compatibility remains P13.5; no AgentArts connection,
MCP Target/cloud provisioning, production deployment, auth/IAM setup or durable
session is claimed. P16 owns production hosting and hardening.

## P13.5 AgentArts Gateway Compatibility

Status: REVIEW_PASS. The MCP Server is AgentArts-gateway-compatible
at the locally tested protocol/tool contract level (2025-11-25 / Streamable HTTP).
This is distinct from P12.7 Runtime, which hosts the complete Agent. The Gateway
path discovers approved tools and calls the same Registry/Dispatcher/Facade; no
separate tool list, Agent graph, LLM, business mapper or endpoint is introduced.

Test-only official SDK forwarding fixtures model restricted Gateway discovery,
schema ingestion without outputSchema/annotations/icons, and event-stream responses.
They verify full canonical parity with direct Facade/local MCP/modern HTTP, including
JSON text fallback, INELIGIBLE/UNKNOWN success, URLs/evidence/source refs/timezones,
mutation denial, safe errors, metadata isolation and one execution per valid call.
MCP Gates H/K/L pass at this local contract level. No real cloud acceptance is claimed.

From repository root with the existing optional MCP installation:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_gateway_compatibility.py
```

Default tests use in-process ASGI and deny sockets; no credentials or cloud resources
are required. Real Gateway smoke is NOT_RUN. No production Gateway/Target connection,
public deployment or IAM/SWR/Secrets configuration exists. P13.6 is REVIEW_PASS;
P16 owns production deployment/hardening. Dependency and installation commands are unchanged.

## P13.6 Real MCP Integration & Authority Preservation

Status: REVIEW_PASS. Competition Copilot exposes the same eight
approved deterministic capabilities through local/HTTP/AgentArts-compatible MCP.
Real integration injects the formal seed Agent composition's Capability Facade into
MCP; Agent/Runtime still use Graph -> same Facade. Complete canonical receipts remain
equal across entries, including reasons, evidence/source refs, IDs, URLs and dates.
MCP calls do not invoke routing/explanation models. Mutation remains MCP-isolated.

Tests exercise actual repository/policies and all admitted tools. Withheld P6/P7/P8
authorities run through the existing Agent path and remain inaccessible through MCP.
Negative/UNKNOWN outcomes remain successful tool calls. Official policy coverage is
not expanded to invent positive eligibility. Default tests block network and verify
official data unchanged, including attack, concurrency and exception cases.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_mcp_authority_parity.py backend/tests/integration/test_mcp_real_integration.py
```

MCP Gates M/N cover final authority lineage and cross-entry consistency. No production
code, dependency or install/run command changes. Real Gateway smoke NOT_RUN; no cloud
deployment, durable session, MCP mutation or frontend support is claimed. P13 Final
Review REVIEW_PASS; Closure CLOSED_FROZEN; P14 CLOSED_FROZEN.

## P14.0 Frontend & Runtime Invocation Compatibility Baseline

P12/P13/P14 remain CLOSED_FROZEN; P14.0-P14.7 REVIEW_PASS;
P14 Final Review REVIEW_PASS; P14 Closure CLOSED_FROZEN.
The following inventory records the historical P14.0 baseline; completed frontend
and runtime behavior is described above and in frontend/README.md.
At that baseline the frontend directory had documentation only; no app, runtime
client, new endpoint or Local/AgentArts frontend connection had been implemented.
Inventory, actual contract fields, security boundaries, roadmap and Frontend Gates
A-J were recorded in DEVELOPMENT_PLAN and the then-current frontend/README.md.

Frontend's planned primary path is RuntimeInvocationClient -> Local/AgentArts
transport -> existing P12 Runtime Adapter -> Agent/Graph -> Facade. MCP remains a
separate structured capability boundary. P12.7's actual typed request/resume envelope
is reused, not a query-only or second business API. Invocation is non-streaming first.
The current internal GraphInput continuation must be hidden by future trusted hosting;
safe artifact/ref presentation and generated public contracts are P14.1/P14.4/P14.5
work. No browser secrets, client business rules or browser-created approval authority.
The frontend shell consumes the fake client; real Local/AgentArts runtime invocation
remains P14.5/P14.6. P15/P16 boundaries are unchanged.

## P12.8 End-to-End Agent Integration

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1-P12.7 REVIEW_PASS.
P12 Final Review REVIEW_PASS; Closure CLOSED_FROZEN; P13 CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.

`competition_copilot.composition.build_seed_agent` is the explicit outer composition
root: seed repository, P4 tools, policy provider, P5-P11 authorities, Facade, injected
models and the existing graph. It returns `AgentComposition(agent, facade)`.
`competition_copilot.agents.agent.CompetitionCopilotAgent.invoke(AgentRequest)` returns
the existing `AgentResponse`; `start` returns `GraphTurn` for human continuation.
`run_turn/resume` implement the same core entry used by the P12.7 Runtime adapter.
Agent package imports remain SDK/framework independent; import the optional entry
module explicitly. The composition module is outside Agent because it constructs
concrete data adapters. No business logic or provider is selected by composition.

Callers explicitly supply `AgentInputPreparer`, paths, a P6 scoring engine and model
dependencies. The preparer resolves only caller-owned structured arguments/refs;
it must preserve AgentRequest and must not infer consent or fill missing business
truth. Runtime uses the same preparer plus the existing trusted continuation bindings.
No default profile, clock, repository path, implicit scorer or session cache is added.

```python
from competition_copilot.composition import build_seed_agent
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter
from competition_copilot.integrations.agentarts.app import create_app

# seed_dir/policy_dir, trusted_bindings, scoring, routing/explanation/interpreter
# are explicit caller/application dependencies, not values parsed by the adapter.
composition = build_seed_agent(
    seed_directory=seed_dir, policy_directory=policy_dir,
    inputs=trusted_bindings, scoring=scoring,
    intent_model=routing, explanation_model=explanation,
    human_interpreter=interpreter,
)
response = composition.agent.invoke(request)
app = create_app(AgentArtsRuntimeAdapter(composition.agent, trusted_bindings))
```

End-to-end tests use real seed/policy/COMAP requirement data and P4-P11 authorities,
with deterministic fake models. They cover NL discovery/eligibility/recommendation/
skill gap/planning, clarification, controlled P11 track-removal approval/reject,
stale/wrong/cross-request safety, grounded explanation/fallback and Runtime parity.
Real partial policies remain uncertain; the supplemental confirmed recommendation
case uses an explicitly controlled complete policy evaluated by real P5, without
altering official artifacts. P9/P10 exposed capabilities are exercised offline;
P9.5 monitor remains NOT_EXPOSED_BY_DESIGN. All data files are checked read-only.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_real_integration.py backend/tests/integration/test_agent_human_flow_integration.py backend/tests/integration/test_agent_e2e_architecture.py
```

Gate K covers complete local/runtime lifecycle parity; Gate L preserves Domain and
explicit human authority lineage. End-to-end integration and P12 Final
Review are complete. No MCP, frontend, persistence or production deployment
is added. P16 retains ARM64/SWR/IAM/Secrets/MaaS/scaling/load/hardening responsibilities.

## P12.7 AgentArts Runtime Adapter

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1-P12.6 REVIEW_PASS;
P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.

`competition_copilot.integrations.agentarts` contains the SDK-free typed transport
and `app.py` official SDK wiring. The adapter calls the existing graph exactly once
per invocation. Business decisions and grounded explanations remain core-owned.
No cloud deployment, durable sessions, production image or MCP capability is added.

From repository root, install the optional SDK overlay and run offline tests:

```powershell
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-agentarts.lock
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[dev,agent,agentarts]"
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agentarts_runtime.py
.\backend\.venv\Scripts\python -m pip check
```

Application composition supplies the existing graph and trusted `RuntimeBindings`:

```python
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter
from competition_copilot.integrations.agentarts.app import create_app

# core = build_competition_copilot_graph(facade, intent_model=..., explanation_model=...)
# bindings implements RuntimeBindings using authorized application context.
app = create_app(AgentArtsRuntimeAdapter(core, bindings))
```

The app factory constructs `AgentArtsRuntimeApp` and registers `@app.entrypoint`;
tests invoke the public `/invocations` endpoint in memory, without launching a server.
New payload: `{"request": <AgentRequest JSON>}`. Resume payload:
`{"continuation_ref": "authorized-ref", "approval": <ApprovalResponse JSON>}`
(or `clarification` / typed human `message`). The response envelope retains the full
`AgentResponse`, pending `GraphInput` continuation, or sanitized typed error.
`RuntimeBindings` prepares caller-owned arguments, authorizes continuation lookup,
and supplies actor/current Plan/explicit time; there is no default store or resolver.
Runtime/application callers must retain pending JSON behind an authorized reference.
Arbitrary submitted state is rejected; references are not authorization or signed tokens.
`RequestContext` is ignored for business identity, consent and evidence.

SDK 0.1.6 has mandatory transitive MCP/Docker/identity packages; installing those
does not implement project MCP or deployment. Core-only installations keep the
existing locks. The new overlay extends them and records Windows CPython 3.12
development resolution. Project minimum is Python 3.11 (SDK minimum 3.10).
Native dependencies and Linux ARM64 installation/build remain a P16 verification
gate; no ARM64 image or cloud readiness is claimed.

## P12.6 Evidence-grounded Explanation

Status: REVIEW_PASS. P12 remains CLOSED_FROZEN; P12.1-P12.5 REVIEW_PASS;
P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.

Agent now composes evidence-grounded Chinese explanations through an optional injected
ExplanationModel (`build_competition_copilot_graph(..., explanation_model=...)`).
Business decisions remain Domain-owned. The first version accepts only structured
sentence variants from an explicit minimal result/evidence projection; arbitrary
paraphrases, invented citations, altered statuses and missing uncertainty fail closed.
Timeout/schema/grounding failure returns deterministic explanation, preserving business
success and executing no additional Tool or mutation. Approval and clarification resume
retain P12.5 validation. An optional LangChain Core adapter uses structured output;
default tests use offline fake models. No concrete provider/dependency, Runtime Adapter,
MCP, persistence, memory or deployment is added. Gates A-E/G/H/I apply; F is deferred.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_explanation.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

## P12.5 Clarification + Human Approval

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1-P12.4 REVIEW_PASS;
P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.

Agent graph now supports typed clarification/approval replies and explicit trusted-state
continuation: run_turn(GraphInput) returns GraphTurn(response, continuation), and
resume(continuation, HumanResume) continues the pending interaction. invoke still
returns AgentResponse. Caller/runtime owns continuation trust, authenticated actor,
current Plan reference and aware times. This is not durable sessions, signed browser
tokens, cross-process replay storage or long-term conversation memory.

Clarification merges only requested missing fields. Natural clarification uses an injected
interpreter plus unique caller-read choices and deterministic label validation. Approval
uses typed APPROVE/REJECT or a bounded full-message consent rule; ambiguous/expanded
instructions never grant authority. The P11 bridge binds exact proposal/Plan/version/
scope and revalidates formal input, then executes only via Capability Facade. Existing
formal caller P11 proposal input is not current-user consent. No P5-P11 rules change.
AgentArts Gates A-E/G/H pass at the core boundary; deployment F remains DEFERRED.
P12.5 added no provider dependency, persistent saver, Runtime adapter or MCP. P12.6 now adds bounded final explanation.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_human_interactions.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

## P12.4 LLM Intent + Safe Tool Selection

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1-P12.3 REVIEW_PASS;
P12.5 REVIEW_PASS; P12.6 REVIEW_PASS; P12.7 REVIEW_PASS; P12.8 REVIEW_PASS; Final Review REVIEW_PASS; Closure CLOSED_FROZEN. DEVELOPMENT_PLAN is canonical.

agents/routing.py defines an untrusted structured proposal and deterministic validator.
The existing graph factory accepts optional intent_model injection. Explicit known
intent bypasses the model; UNKNOWN may receive a proposal through the injected interface.
agents/model.py offers an optional LangChain Core bridge around a caller-configured
chat model; agents/prompts.py holds the single routing prompt. No concrete provider,
API key, new dependency, cloud call or live model smoke is required for default tests.
Business truth stays in P5-P11; models never supply arguments, results or approval.
Caller supplies argument artifacts and invocation IDs; missing context clarifies,
invalid/hallucinated proposals fail closed, model-originated mutation is blocked.
Routing does not generate final explanations. P12.5 adds the human continuation;
P12.6 adds bounded LLM explanation; AgentArts adapter is implemented at P12.7; MCP/persistence/memory remain unimplemented.

Install the agent extra using the P12.3 instructions below, then run offline tests:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_intent_routing.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

AgentArts Gates A-E/G pass at the injected core boundary; Gate F remains DEFERRED.
No configured live provider or production runtime certification is claimed.

## P12.3 LangGraph Orchestration Graph

Status: REVIEW_PASS; P12 CLOSED_FROZEN; P12.1/P12.2 REVIEW_PASS;
P12.4 REVIEW_PASS; P12.5 REVIEW_PASS; P12.6 REVIEW_PASS. DEVELOPMENT_PLAN is canonical.
competition_copilot.agents.graph.build_competition_copilot_graph(facade) creates a
compiled deterministic LangGraph. Its invoke(GraphInput) returns existing AgentResponse;
stream exposes stable node updates. GraphInput wraps AgentState, caller-owned interaction/
result refs, optional structured arguments JSON and a caller-prepared approval proposal.
Intent/invocation are explicit; no user_message inference, keyword matching or LLM.
Missing context clarifies; pending proposal waits; only tool_execution calls the Facade.
No graph persistence, checkpointer/store, memory, AgentArts adapter or MCP. Approval
collection and resume remain P12.5; LLM selection P12.4 and explanation P12.6.

Optional graph stack: LangGraph 1.2.15 / LangChain Core 1.6.10, exact overlay lock
requirements-agent.lock (includes unchanged core lock). No concrete model provider is required. AgentArts SDK is isolated in the optional P12.7 overlay. From repository root, install/validate:

```powershell
.\backend\.venv\Scripts\python -m pip install -r backend/requirements-agent.lock
.\backend\.venv\Scripts\python -m pip install "setuptools>=68"
.\backend\.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e ".\backend[agent,dev]"
.\backend\.venv\Scripts\python -m pip check
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_agent_orchestration_graph.py
.\backend\.venv\Scripts\python -m pytest
.\backend\.venv\Scripts\python -m ruff check .
```

Setuptools is the existing build requirement, not a Domain/Agent runtime dependency;
the explicit build-tool step avoids this managed venv's isolated build_meta import issue.
Core-only development may retain the original install; graph tests require the optional
agent stack and skip as a module if LangGraph is absent. Full graph validation installs
the stack and has zero skips. Core contracts/root imports never require graph packages.
Gate A-E PASS at graph boundary; Gate F DEFERRED. Native ARM64/CPython 3.11 wheel
resolution passed, but no Linux/container/runtime deployment is claimed.

## Frontend runtime contract consumer

frontend/src/runtime contains the transport-neutral RuntimeInvocationClient and
Local/AgentArts interfaces with offline fake tests. P12 Pydantic contracts remain
authoritative. The frontend workspace consumes this client through fake presets;
no backend endpoint or live Runtime connection is added.

From the repository root, verify checked-in public schema/type/fixture parity:

```powershell
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
```

Omit --check to regenerate after an authorized contract change. Internal graph and
HumanResume authority state are never generated. The safe pending continuation_ref
projection requires trusted hosting/authorization in P14.5; it does not expose the
current internal P12 GraphInput output to browsers. AgentResponse refs remain refs;
no new business result/evidence bodies are fabricated. Frontend commands and error,
config, cancellation and continuation contracts are documented in frontend/README.md.


## Multi-candidate recommendation assembly

`application/recommendation.py` owns `RecommendationContextAssembler`, shared
Application orchestration over the abstract formal CompetitionRepository and a
P5 evaluator. It enumerates every formal edition (there is no current/latest
edition policy), uses edition-level alternatives, retains the exact optional
anchor including its explicit track, deduplicates and sorts by
`(competition_id, edition_id, track_id or "")`. No raw ingestion candidates or
model-generated competitions enter this collection.

Local Runtime calls this assembler through a thin Facade P5 bridge with distinct
invocation/argument/result references per candidate, then invokes P6 once with
all contexts. The AgentArts-compatible demo uses the same host composition.
P5 UNKNOWN is retained; a failed prerequisite aborts assembly, without partial
ranking or an invented UNKNOWN. A blocked anchor does not stop alternatives.
Profile-driven recommendation needs only the current student repository snapshot;
competition/edition/track selection is optional. All formal edition candidates
are enumerated by the existing backend assembler, not supplied by Frontend.
An explicitly selected complete target remains an optional additional anchor.
The P6 identity guard admits an optional caller target as batch membership only for
multi-candidate get_recommendations; student identity, internal target coherence,
and all plan/approval paths retain their guards. No public schema changes.

The demo wires one real presence-only component, verified-skill-overlap-v1,
with the sole component's default weight 1.0. Existing aggregation and bucket
policies remain unchanged. Original profiles without explicit skill records
still have unavailable soft scores; the separate recommendation fixture can
produce evidence-backed partial skill overlap. No other soft signals are scored.

Targeted verification from repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_recommendation_assembler.py backend/tests/integration/test_multi_candidate_recommendation.py
```


## Verified skill route: recommendation data foundation

The reviewed skill route combines exact-target requirement facts with explicit
StudentProfile.skills. Data artifacts themselves contain no score. The first
component built on this foundation is documented below; P5 truth and the existing
P6 aggregation/bucket/missing-signal semantics remain unchanged.

`data/local_runtime/recommendation_demo.json` supplies the additive, synthetic
`local-recommendation-demo` profile and a four-edition curated audit set (GCXL,
COMAP, C4 and China Graduate Mathematical Modeling). Runtime candidate expansion
continues to use the full formal repository, not this audit set. The original
three demo profiles retain their exact facts. Non-skill profile fields are not
scoring inputs. Requirement membership must come from independently reviewed
source-backed artifacts, with PARTIAL coverage and null thresholds where the
source does not define proficiency. Drafts in data/review are never loaded by
the formal requirement provider.

RecommendationContext.skill_requirements is optional and defaults to None.
Application prepares an immutable RecommendationSkillRequirements containing
requirement_version and the existing SkillRequirementSet (which already owns
target, coverage and evidence). Both Application and Context check exact target
binding; no edition-to-track inheritance occurs. The provider version and lookup
facts must agree. Domain performs no IO. P7 diagnosis is not converted to a score.

Data-foundation verification from repository root:

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_recommendation_data_foundation.py
```


The approved skill-route snapshot currently covers COMAP 2027, C4 2026 and
China Graduate Mathematical Modeling 2026: 3/4 curated editions, 3/12 formal
editions, all PARTIAL and with unspecified proficiency. GCXL remains unavailable.
The new stable Skill ID is machine-learning-modeling; mathematical-modeling is
reused unchanged. The review record and official source references live in
`data/review/p6-skill-route/README.md`. The demo has mathematical-modeling only,
so exact-ID presence overlaps two curated sets and is absent from the C4 set;
absence means unknown student capability, never zero proficiency or a score.
All four curated demo P5 results remain UNKNOWN. This data snapshot enables
future policy work but does not make confirmed eligibility or ranking claims.


## Verified skill overlap V1

`domain/verified_skill_overlap.py` implements the sole real component:
component_id and policy_version are `verified-skill-overlap-v1`. It returns 1.0
only when every currently verified official REQUIRED skill has an exact profile
record with a non-UNKNOWN level and all REQUIRED thresholds are unspecified.
BEGINNER counts as explicit presence; it never proves sufficient proficiency.
DESIRED requirements are not scored. Absent requirements, no verified REQUIRED
facts, absent/UNKNOWN profile skill or any non-null REQUIRED threshold produce
None, never zero. It does not compare levels or infer a missing skill's ability.

`unavailability_reason(context)` exposes stateless policy diagnostics, including
SKILL_LEVEL_POLICY_UNSUPPORTED for non-null thresholds. The unchanged scorer
protocol returns Component | None; the unchanged aggregation engine records its
existing SOFT_SIGNAL_UNAVAILABLE / NO_ACTIVE_SOFT_SIGNALS audit for None. No
exception, invented component or mutable diagnostic state is used for absence.

Positive component evidence retains policy and requirement versions, exact
candidate identity, coverage, each matched skill ID, original verified presence
evidence, and actual profile level/self_assessed/note facts. Self-assessment is
not external verification. Coverage currently is 3/12, all PARTIAL: 1.0 is only
recorded-ID overlap over current verified REQUIRED facts, not eligibility, overall
fit, complete requirements satisfaction, proficiency sufficiency or win probability.

For local-recommendation-demo, COMAP and China Graduate Mathematical Modeling
receive 1.0 in uncertain; C4 and GCXL receive None. The original eligibility and
eligibility_buckets_score_desc_target_id_v1 ranking policies remain authoritative.
Existing tie order places China Graduate Mathematical Modeling before COMAP,
followed by unavailable scores. No confirmed promotion, retry, fallback or second
component is introduced. Restart Local Runtime to load current composition.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/domain/test_verified_skill_overlap.py backend/tests/application/test_recommendation_skill_preparation.py backend/tests/integration/test_verified_skill_recommendation.py
```
## Local profile evidence preparation

`data/local_runtime/recommendation_demo.json` explicitly declares the demo
student's self-assessed skill evidence. Application's
`prepare_student_skill_evidence` validates its student/skill identity, actual
level and self-assessment before Local Runtime passes the existing `Evidence`
objects into P7 and P8's P7 prerequisite. Student facts have `source=None` and
retain `self_assessed=true`; they are simulated profile declarations, not
externally verified abilities. Missing declarations are never synthesized.
P7's known-skill evidence completeness protection and unknown-threshold/partial
coverage semantics remain unchanged. Restart Local Runtime to load fixture edits.

## Session plan registry and explicit selection

Application `PlanRegistry` defines full-plan registration, exact-reference
resolution, current-head lookup and atomic compare-and-swap replacement with
retained PlanDiff/history. The Local Runtime `InMemoryPlanRegistry` adapter
stores both the controlled fixture and successful P8 generated plans. No Domain
service performs persistence. Duplicate canonical registration is idempotent;
conflicting content/version under an existing ID rejects. Historical IDs remain
resolvable and point to their lineage's current head for stale checks.

The frontend offers generated plans only when validated CompetitionPlan artifacts
match server-supplied `plan_refs`. Select a plan explicitly in the context area;
no plan is selected automatically. The browser retains only references and display
metadata, never recalculates digest/version and never supplies plan bodies for
registration. Selection does not approve or create a revision proposal.

Generated COMAP plans have no target-consistent executable ReplanningInput yet.
A revision attempt with a valid selected reference returns existing runtime error
category `CORE_VALIDATION_ERROR` with the public message
`NO_TARGET_CONSISTENT_REPLANNING_INPUT`. No event, impact or instruction is fabricated.
The controlled fixture APPROVE/REJECT path continues through existing P12/P11
guards. Replacement retains the full before/after and authoritative PlanDiff.

Storage is per host and in memory: new requests share registered plans; server
restart discards generated plans/history and restores the controlled fixture.
Page reload loses frontend choices. Old browser references after server restart
fail closed; regenerate/reselect. Production persistence is outside this demo.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_plan_registry.py backend/tests/integration/test_local_runtime.py
```

## Instruction preparation policy V1

Application `TargetTrackRemovedCancellationPolicy` returns a typed authority-free
`PlanRevisionProposal` for `target-track-removed-cancel-v1`, or typed UNSUPPORTED
with `NO_SUPPORTED_INSTRUCTION_POLICY`. It proposes draft/active -> cancelled only
for exact target-track removal, a known whole-plan REPLAN and no unresolved impact.
The proposal retains original Plan/Decision/Event lineage and policy version.
An edition-level Event is not an exact track-level match for this policy.

`prepare_approval` and `build_approved_replanning_input` support this proposal in
addition to their existing compatibility path. The new path requires explicit
APPROVE, trusted server-supplied `approved_by_ref`, current exact PlanReference and
execution time. Before approval and on REJECT there is no executable instruction
or invented human authority. The unchanged P11 executor consumes the authorized
input after the bridge. Pure helpers do not replace runtime authentication,
single-use continuation, host lock or registry CAS.

The policy/bridge is independently testable. The generated Huawei composition
described below reuses it without changing preparation or authorization rules.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_instruction_preparation.py backend/tests/integration/test_prepared_instruction_approval.py
```

## Generated Huawei same-plan local demo

After independent acceptance of the policy, the same-plan path is now composed
through Application `ControlledPlanRevisionPreparer`. Generate a plan using:
student `local-recommendation-demo`, competition `huawei-ict`, edition
`huawei-ict-2026`, track `huawei-ict-2026-innovation`. Missing reviewed requirements
are explicitly prepared as MISSING; P7/P8 preserve uncertainty-resolution needs.
No Huawei skill requirement is invented.

Select that generated plan explicitly and request revision. The preparer reads
the separately declared `CONTROLLED DEMO OBSERVATION` in
`data/local_runtime/generated_huawei_observation.json`, checks its before-membership
against the Repository-backed `CompetitionSnapshotBuilder` baseline, and constructs
new exact-track manual before/after snapshots from the explicit observation.
This does not relabel an edition-level official Event or weaken the baseline
builder's edition-only guard. Unchanged windows retain their baseline provenance;
the changed membership carries only the manual demo source.
`SnapshotDiffEngine` and `CompetitionEventEngine` derive new lineage/identity,
then the real impact analyzer and Decision service feed the accepted
`target-track-removed-cancel-v1` policy. Local composition contains no cancellation rule.
Complete manual snapshot/Diff/Event/Impact/Decision preparation bundles are retained
in memory for the host lifetime; approved PlanDiff/history stays in PlanRegistry.

The graph holds the authority-free proposal in a private typed preparation channel,
with a strictly bound before-only argument artifact. No executable ReplanningInput
is constructed until explicit APPROVE via the existing authority bridge. REJECT
does not invoke P11; APPROVE executes P11 once and CAS-updates the generated plan's
lineage. Public P12/P14 envelopes and Domain execution rules are unchanged.

**This is not a real Huawei announcement or official track deletion.** The manual
source's `verified` status validates the synthetic scenario input for the existing
observation contract; it does not verify a real-world change. The original
`controlled_revision.json` remains a separate low-level regression scenario.
COMAP and other targets without matching executable preparation still fail closed.
Restart Local Runtime to load this composition; generated state is not durable.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_generated_huawei_replanning.py
cd frontend
npm run test:local
```

### Explicit local demo actions

`AgentRequest.intent` is an optional, additive operation selector using the existing
AgentIntent enum. Omit it for natural-language model routing. The five guided demo
operations prepare an untrusted deterministic routing proposal instead of invoking
the intent model. Both pre-routing argument preparation and graph routing reuse this
mapping and the existing routing validator, Facade and business services. An intent
cannot supply arguments, results, an approval decision or execution authority.
Unsupported explicit operations fail closed rather than falling back to inference.
Restart the runtime to load the updated request schema and composition.

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/integration/test_explicit_local_actions.py
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
```

### PX2.2 authoritative competition detail reads

The additive `get_competition_details` READ capability uses the existing invocation
transport and Facade. Explicit GET_COMPETITION_DETAILS prepares canonical IDs only;
its detail read and result rendering make no LLM calls. Existing P4 outputs and all
business decision/approval contracts retain their semantics. No HTTP API or MCP Tool
was added (the new capability is explicitly excluded from the MCP exposure catalog).

`application/competition_detail.py` owns the immutable query/projection and Reader.
It depends only on CompetitionRepository, EligibilityPolicyProvider,
SkillRequirementProvider and repositories/provenance.py's abstract reader.
JsonSeedCompetitionRepository retains reviewed source/temporal metadata in memory;
Application does no filesystem IO and never runs Eligibility/SkillGap or event services.
The outer build_seed_agent accepts an injected requirement_provider for detail reads;
Local composition supplies the existing JsonSkillRequirementProvider. Other adapters
can inject the same abstraction; no provider JSON is passed through Runtime input.

Competition-only queries enumerate editions without selecting one. Parent identity,
exact policy/artifact target, null windows/endpoints, requirement versions, skill catalog,
coverage and evidence are preserved. Missing sections remain partial reads; provider
execution failures/corrupt data/identity mismatches are errors, not ordinary UNKNOWN.
Nested snapshots/collections are immutable and stable-order JSON serializable.

Full event history remains EVENT_HISTORY_PERSISTENCE_GAP. The read returns unavailable
availability and never generates events or writes an Event Ledger. Current-session
PlanDiff/events are separate evidence; manual controlled-demo changes are not official
changes. No submission-window fact contract is added. P12/P13/P14 remain CLOSED_FROZEN;
P15 is NOT_STARTED; current PX3 closure is recorded below.

Release checkpoint: **PX2 Authoritative Competition Read Baseline** is suitable
as the shared GitHub team reference. PX1 / PX2 Core = CLOSED_VERIFIED;
PX2.1 = REVIEW_COMPLETE; PX2.2 = REVIEW_PASS. P12/P13/P14 remain CLOSED_FROZEN.
PX2 Product Detail Enrichment is DEFERRED non-blocking product work; future PX2
UX enrichment or separately authorized PX3 work starts from this baseline.
Complete history remains unavailable (EVENT_HISTORY_PERSISTENCE_GAP), and current
session evidence is not complete history. Submission window remains an unimplemented
DATA_CONTRACT_GAP. Enrichment must preserve unknown facts rather than infer them.
See the [release checkpoint](../docs/DEVELOPMENT_PLAN.md#px2-release-checkpoint--px2-authoritative-competition-read-baseline).

```powershell
.\backend\.venv\Scripts\python -m pytest backend/tests/application/test_competition_detail.py backend/tests/integration/test_competition_detail_runtime.py
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
.\backend\.venv\Scripts\python scripts/export_frontend_results.py --check
```
## PX2.4 Temporal evidence read projection

Status: CLOSED_VERIFIED; FINAL INDEPENDENT RE-REVIEW = REVIEW_PASS. `application/temporal_evidence.py` defines
immutable presentation candidates and the abstract TemporalEvidenceProvider;
`infrastructure/temporal_evidence_json.py` loads the explicit reviewed artifact at
host initialization, validating Raw digest, quote/locator, target, admission ID,
and source against reviewed edition provenance. Detail requests read the cache.

`CompetitionDetailReader` adds candidates and section availability to the existing
GET_COMPETITION_DETAILS projection. Source verification is separate from temporal
verification; pending candidates never overwrite Edition TimeWindow. Rejected or
verified-status candidates cannot masquerade as pending or auto-create a window.
See [candidate data notes](../data/temporal_evidence/README.md).

No parser, LLM extraction, new endpoint or MCP Tool is added. Candidate is excluded
from P8 deadlines, P9 Snapshot/Event, P10 Impact and P11 Replanning. Formal promotion
continues to require P2 Raw digest binding, approval, verification and seed validation.
PX2 Competition Experience is CLOSED_VERIFIED (PX2.1 COMPLETE; PX2.2–PX2.4 CLOSED_VERIFIED).
P12-P14 remain CLOSED_FROZEN; PX3 has started (see current PX3.2 status below);
P15 remains NOT_STARTED. Candidate coverage is limited to three reviewed quotes.
Event History persistence and submission-window contracts remain gaps; Local
PlanRegistry remains in-memory. No temporal crawler/parser/LLM extraction exists.

## PX3.2 Profile Read / Edit

Status: CLOSED_VERIFIED; PX3.1 COMPLETE. PX3 CLOSED_VERIFIED;
P12-P14 CLOSED_FROZEN; P15 NOT_STARTED. PX3.3/PX3.4 are CLOSED_VERIFIED below.

`repositories/student.py` defines deeply immutable profile snapshots, ProfileReference
and StudentProfileRepository. `infrastructure/repositories/student_memory.py`
bootstraps fixture profiles once per host. Every Local Runtime student lookup now
reads the same repository, including Eligibility, Recommendation and SkillGap.
References bind student ID, version, canonical content SHA-256 and repository
instance scope. updated_at is audit metadata, never the concurrency token.

`application/profiles.py` provides reader/editor use cases through explicit
GET_PROFILE / UPDATE_PROFILE via existing Runtime, Graph and CapabilityFacade.
GET is READ; UPDATE is MUTATING with server-bound operator/student scope and CAS,
not P11 approval. Model-originated profile updates cannot execute. No LLM needed.
No new HTTP endpoint or MCP tool. Seven base fields are writable; skills/ID/version/
owner are forbidden. Omitted fields stay; null clears optional fields; empty lists
clear preferences. Existing Domain validation applies, including finite hours 0-168.

Persistence is HOST_MEMORY: rereads retain edits; server restart restores fixture
seeds with a new scope. Refresh requires explicit student selection again. This
is not a production account system or persistent database. Mutation returns the
validated new snapshot, reference, changed fields and request correlation.

New Recommendation/SkillGap/Planning calls capture the profile at preparation.
Host profile_input_bindings retains immutable references by result artifact ID,
plus plan ID/version for plans. Old payloads and legacy results remain valid.
Full stale UI is deferred. Saves never run analysis, modify plans or produce PlanDiff.

## PX3.3 Skills Read / Edit — CLOSED_VERIFIED

`application/profile_skills.py` aggregates the authoritative requirement-artifact
catalog (stable ID order, identical definitions deduplicated, conflicts rejected).
GET_SKILL_CATALOG is READ; ADD_PROFILE_SKILL / UPDATE_PROFILE_SKILL /
REMOVE_PROFILE_SKILL are explicit MUTATING capabilities through the existing
Runtime/Facade. No model call, new endpoint or MCP tool is involved.

New skill IDs must be in the catalog. Historical unresolved records remain legal.
Add defaults to self-assessed; update accepts level/note only; remove deletes the
record rather than setting UNKNOWN. Notes and non-self-assessed flags are not
certification. Missing, UNKNOWN and formal SkillGap remain distinct.

Profile and existing P7 declaration evidence are stored in one immutable record.
Application validates matching evidence before a locked copy-on-write CAS commit;
known-level changes replace the corresponding fact, UNKNOWN/removal remove it.
Validation failure leaves both old states and ProfileReference intact. Base profile
edits preserve evidence. Every changed profile gets one version increment; unchanged
content is a no-op. Business preparation reads one profile/evidence snapshot and
retains its input_profile_ref. Skill saves never run P6/P7/P8/P11 or change plans.

Persistence remains host-scoped in-memory; restart restores fixture bootstrap.
PX3.4 is CLOSED_VERIFIED below; P12-P14 remain CLOSED_FROZEN; P15 remains NOT_STARTED.

## PX3.4 Derived Result Staleness — CLOSED_VERIFIED

`application/profile_freshness.py` provides immutable ProfileFreshness and a pure
reference resolver. Exact student/version/digest/host equality means CURRENT;
different references within the same student/host mean STALE. Missing references,
missing current profile or incomparable host scopes mean UNKNOWN. Cross-student
results are excluded, never displayed as stale. Timestamps and result age are not used.

GET_PROFILE_ANALYSES is an explicit READ via the existing Runtime/Facade, excluded
from MCP. It reads existing host input_profile_bindings and the current profile;
no Domain result contract, score, gap, plan status/version or PlanReference changes.
Bindings retain the preparation-time ProfileReference and canonical result target,
plus exact PlanReference for plans. Changed caller-prepared inputs without matching
repository lineage are not retroactively assigned the latest profile reference.

Freshness is mark-on-read metadata, not invalidation. It never deletes old results,
runs P6/P7/P8/P11, generates events, revises plans or creates PlanDiff. Explicit rerun
buttons use the existing P6/P7/P8 paths. Input bindings remain host-memory only;
legacy/previous-host results remain legal and UNKNOWN. No history database or LLM.
PX3.4_ELIGIBILITY_FRESHNESS_GAP: P5 depends on StudentProfile but is intentionally
outside this freshness scope; its existing output/authority are unchanged.

PX3 final status: PX3.1 COMPLETE; PX3.2/PX3.3/PX3.4 and PX3 overall CLOSED_VERIFIED.
Browser Smoke PASS; Final Independent Review REVIEW_PASS. Profile read/edit,
ProfileReference CAS, trusted self-edit, catalog/skills management and atomic evidence
mutation are verified; Recommendation/SkillGap/Plan freshness never automatically
reruns decisions or P11. PX1/PX2 CLOSED_VERIFIED; P12-P14 CLOSED_FROZEN; P15 NOT_STARTED.

Retained gaps: host-scoped in-memory profile/skill/evidence storage restores fixture
baseline on server restart; full account/identity system is not implemented.
SKILL_REQUIREMENT_DATA_ENRICHMENT_GAP retains incomplete required_level coverage.
PLANNING_ACTIONABILITY_GAP (PX4 high priority) records P8 over-concentration on
uncertainty-resolution tasks when constraints are incomplete; P8 truth is unchanged.
Complete Event History remains unavailable; Submission Window is DATA_CONTRACT_GAP.
PX4 My Competitions + Planning Workspace is READY_TO_START, with suggested PX4.1
Planning Readiness & Actionable Preparation; no implementation starts in this sync.
