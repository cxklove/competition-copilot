# Competition Copilot frontend and runtime invocation contract

The React + TypeScript + Vite product shell opens on Dashboard and keeps Copilot
as an independent page. The retained workspace presents current-page conversation,
structured workflow states, clarification forms and explicit approval controls.
The same RuntimeInvocationClient supports offline fake presets or the real local
Agent invocation path or AgentArts-compatible trusted bridge, selected at the composition root.
The result panel presents supplied result artifacts, evidence, sources and PlanDiff.
Trusted hosting retains scoped public continuation/artifact data. AgentArts transport
compatibility is covered offline; real-cloud smoke and production deployment are not claimed.
P14 Frontend + Runtime Invocation Compatibility is completed and CLOSED_FROZEN.
Canonical lifecycle status: `docs/DEVELOPMENT_PLAN.md`. P15 evaluation and P16
production deployment/hardening remain deferred.

## Toolchain and commands

Use Node >=24.12 (verified with 24.14.1), npm (verified with 11.11.0).
From the repository root:

```powershell
npm ci --prefix frontend --registry=https://registry.npmjs.org --ignore-scripts
npm run dev --prefix frontend
npm test --prefix frontend
npm run test:hitl --prefix frontend
npm run test:results --prefix frontend
npm run test:local --prefix frontend
npm run test:agentarts --prefix frontend
npm run test:e2e --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
npm run format --prefix frontend
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
.\backend\.venv\Scripts\python scripts/export_frontend_results.py --check
```

`dev` serves Vite on 127.0.0.1:5173, failing visibly if the port is busy.
`preview` previews the built frontend on 127.0.0.1; neither command hosts a Runtime.
`test` retains the Node test runner, using tsx to load TS/JSX; jsdom and Testing
Library exercise the DOM offline. `lint` runs TypeScript and Prettier over existing
runtime code/tests and the new workspace. `build` now type checks and produces a
real Vite bundle in ignored dist/. No React framework/plugin or state library is
needed beyond React's built-in reducer/hooks. Versions are pinned in package/lock;
jsdom 26.1.0 supports the existing Node version. Installation needs npm registry
access; default tests/build require no external network or credentials.

## Real Local Runtime development

Install the existing backend `agent`/development dependencies per backend README;
AgentArts SDK, cloud credentials and an external LLM are not required.
From the repository root, start the backend in one terminal:

```powershell
.\backend\.venv\Scripts\python scripts/run_local_runtime.py
```

In another terminal, copy `frontend/.env.example` to ignored `frontend/.env.local`
and run `npm run dev --prefix frontend`. The only public config is
`VITE_RUNTIME_MODE=LOCAL` and optional `VITE_LOCAL_RUNTIME_BASE_URL`; empty base URL
uses the same-origin Vite proxy. `LOCAL_RUNTIME_PROXY_TARGET` is Vite server config,
defaulting to http://127.0.0.1:8765. No secret belongs in any public variable. Removing
VITE_RUNTIME_MODE retains fake mode. AGENTARTS mode selects the trusted bridge described below.

Try these bounded offline intent-model phrases (business results are real):

- `discovery` / `有哪些比赛？`: real repository discovery.
- `detail` / `赛事详情`: real clarification asks for competition ID; enter `huawei-ict`.
- `eligibility` / `检查资格`: explicit student `local-graduate`, competition
  `gcxl-engineering-practice-innovation`, edition
  `gcxl-engineering-practice-innovation-2027` returns real INELIGIBLE; `local-unknown`
  preserves UNKNOWN. The local profiles are synthetic server-owned input facts.
- `skill` / `plan`: student `local-graduate`, competition `comap-mcm`, edition
  `comap-mcm-2027` runs real P7/P8 with formal requirement data and uncertainty.
- `recommend`: explicit student/target context runs P5 per formal candidate and P6 once.
  The wired `verified-skill-overlap-v1` signal uses reviewed requirements and explicit
  profile skill records; missing signals remain unknown, and scores never promote P5 UNKNOWN.
- `controlled revision`: clear unrelated student/target fields, explicitly select
  the local controlled PlanRef checkbox. Review the real ApprovalRequest, then
  APPROVE or REJECT. Only P12.5 creates new bound authority; P11 returns the actual
  immutable cancelled Plan/PlanDiff on approval. The synthetic event is not an
  official competition change. Restart the backend to reset this controlled case.

POST `/runtime/invoke` receives the unchanged P12 new-request or continuation
envelope. HTTP delivery is `{runtime: <safe P12-compatible public result>,
presentation: <readonly current request/ref artifact snapshot>}`. LocalRuntimeTransport
only sends JSON, forwards AbortSignal, unwraps this delivery and passes unknown
presentation data to composition. The unchanged RuntimeInvocationClient validates
the runtime portion; P14.4 validates attachment structure/ref binding. No UI fetch,
MCP shortcut, second Agent contract, direct mutation, business interpretation or retry
exists in transport. UI correlation uses the existing P12 canonical input projection
before dispatch, including whitespace request IDs.

Server artifacts are selected from actual Facade receipts, revalidated by their
original Pydantic models and resolved only at retained audit JSON pointers. Real P12
root result refs are TOOL_RESULT; the consumer accepts that kind for explicitly
selected model types instead of inventing new response refs. Discovery/Plan/ranking
schemas are generated from existing P4/P6/P8 models. No receipt authority/GraphInput
or secret is delivered. Full validation/authorization remains server-side.

The loopback host represents one explicitly authorized local development operator,
not multi-user production auth. Cookies, sessions, request headers and roles never
supply student/Plan/approval identity or consent. Opaque handles expire, are bounded,
and are consumed once; server execution is serialized to preserve current-Plan checks.
State is ephemeral, fixtures/repository files are never modified, and restart loses
pending handles. HTTP cancellation cannot prove server non-execution. No automatic
retry exists, especially for uncertain continuation outcomes. Vite uses a same-origin
development proxy; the backend restricts browser Origin to configured exact local
origins (`--origin` can be repeated). Production IAM/auth/CORS/persistence are P16.

`test:local` starts a temporary real Python HTTP server on a random loopback port,
uses the real TypeScript client/transport and DOM UI, then terminates the server.
The backend Windows virtualenv path is the repository convention (tests use Node
>=24.12); no external network/cloud/LLM is used. `test` includes these tests plus
P14.1-P14.4 regressions. Gates R/S cover the actual local chain and delivery/UI parity;
Gate E is LOCAL_RUNTIME_PASS_AGENTARTS_DEFERRED at this boundary.

## AgentArts-compatible transport

Use VITE_RUNTIME_MODE=AGENTARTS and VITE_AGENTARTS_RUNTIME_NAME matching the trusted
server configuration. VITE_AGENTARTS_BRIDGE_BASE_URL is only the bridge address;
empty selects the same-origin Vite proxy. AGENTARTS_BRIDGE_PROXY_TARGET defaults
to http://127.0.0.1:8766. No cloud URL, Authorization or credential is public config.
The UI and HITL/result components are identical across modes.

Start the trusted bridge from root after setting its server environment per
backend/.env.example (see backend README):

```powershell
.\backend\.venv\Scripts\python scripts/run_agentarts_bridge.py
npm run dev --prefix frontend
```

The bridge forwards to an already configured Runtime's official ExecuteRuntime path;
it does not deploy a Runtime. The hosted entrypoint must use the safe public hosting
projection factory in integrations/agentarts_transport/hosting.py, around the existing
P12.7 adapter/private host. Raw internal GraphInput responses are rejected. Both paths
still use the same P14.1 response validator and P14.4 artifact guard.

Session UUID remains transport metadata and never supplies business identity or consent.
Only explicit P14.3 typed continuation controls send clarification/approval decisions.
Auth/resource/server/network/timeout failures remain transport errors, business negative
responses remain normal results, invalid/private responses are contract errors. No
automatic retry or redirect. AbortSignal does not imply rejection or non-execution.

`npm run test:agentarts --prefix frontend` launches only the loopback official-shape
harness and trusted bridge with synthetic test authorization. Actual Agent/Graph/Facade
and Domain services execute. Time/nonces are fixed only in that test harness so complete
responses/artifacts and rendering can be compared exactly with Local. All tests remain
offline. No real cloud smoke is implemented or required. Gate E is
LOCAL_AGENTARTS_RUNTIME_PARITY_PASS at this compatibility boundary; Gates T/U/V/W cover
transport compatibility, semantic parity, credential isolation and session authority
isolation. Production auth/deployment is P16; broad acceptance is P14.7.

## Real frontend E2E and cross-runtime matrix

`npm run test:e2e --prefix frontend` uses the actual Workspace/useConversation,
RuntimeInvocationClient and both real HTTP transports. The test-only Python host
starts real Local and AgentArts-compatible Agent/LangGraph/Facade/Domain chains;
no client stub, cloud credential, external network or LLM is required. Existing
backend agent dependencies must be installed. Default `npm test` includes this suite.

Both modes run discovery, eligibility negative/unknown, undetermined diagnosis,
recommendation/planning, structured clarification/resume, approval wait and explicit
APPROVE/REJECT. The actual P11 status PlanDiff appears only after approval returns;
reject/no-change creates none. Tests cover one invocation per action, backend replay,
stale callbacks and identity tampering, reversed delivery order, independent frontend
roots, unmount/abort, evidence/source grounding and safe unknown-reason fallback.
The test-only comparator retains public business identities, full artifacts and UI
workflow/conversation/HITL semantics, excluding only transport metadata.

HTTP fault controls in `backend/tests/agentarts_gateway_harness.py` can reset serial
test scenarios or supply malformed/error/security payloads. Those controls exist
only in the test harness, never in Local/AgentArts product servers. Injected hostile
text or invalid payloads test presentation/validation, not Domain business truth.
Normal scenarios continue through real authorities. Runtime reference failures,
unavailable sockets, auth, timeout and contract errors stay distinct from negatives;
neither transport retries automatically.

For actual layout verification using an installed Chrome (no new browser framework),
leave port 5173 free and run from the repository root:

```powershell
# Optional: set COPILOT_CHROME to an installed Chrome executable outside Windows default.
npm run test:responsive --prefix frontend
```

The script uses native CDP and actual Vite composition/proxies in both modes, checks
desktop/390px rendering, HITL control bounds, POST counts and browser exceptions,
and saves screenshots/results under ignored `tmp/p14-7-e2e/`. It requires Chrome
process permission; a startup/layout failure fails visibly. This is separate from
the default React semantic suite; jsdom does not assert browser layout.
Gates X/Y/Z cover real frontend E2E, cross-runtime workflow parity and authority
preservation. Production deployment/IAM, cloud certification and load testing remain P16.

## Workspace behavior and boundaries

- src/workspace/: presentation-only ConversationEntry, pure reducer, invocation hook
  and accessible Workspace. UI IDLE/SUBMITTING/READY/ERROR is separate from the
  unchanged AgentResponse.outcome. Loading is never claimed as an Agent status.
- src/main.tsx and src/demo/: composition root and fixed P12-shaped presets. Only
  this boundary knows FakeRuntimeTransport. UI consumes the generic client exchange
  of RuntimeInvocationClient, never transport APIs or MCP.
- Request IDs are created by the UI caller (crypto.randomUUID, injectable in tests).
  Message rendering IDs are separate. Explicit retry preserves the original full
  AgentRequest/ID; no silent retry or inferred transport/session identity.
- Optional student ID is explicit structured input, not a profile editor or a session
  inference. Missing context stays missing. Example prompts only fill the textarea.
- A synchronous pending lock prevents duplicate invocation before React's disabled
  state commits. Reducer attempt/request correlation and unmount abort/generation
  guards keep late responses out of a fresh workspace.
- Completed and business-negative replies are normal Agent entries. Core FAILED,
  runtime envelope error, contract mismatch, transport failure and abort remain
  distinct. Invalid raw payloads and exception details are never displayed as replies.
- NEEDS_CLARIFICATION renders only requested public fields, with no default choice.
  Nested profile/Plan/invocation values use a labeled JSON input only when requested;
  P14.1 validates their real public shape. APPROVAL_CONTEXT has no writable public
  clarification value and stays disabled for trusted-server handling.
- WAITING_FOR_APPROVAL shows readonly action, Plan version/target and lineage refs.
  Separate APPROVE/REJECT buttons send the actual ApprovalResponse, never authority.
  Ordinary text, Enter elsewhere, dismiss and new-request actions do not approve.
  No optimistic Plan update or success is displayed. Results render only after a
  completed authoritative response; waiting HITL states never display final diffs.
- A public interaction snapshot and private detached copy bind the current request,
  proposal and opaque handle. Tokens are consumed synchronously before invocation;
  stale callbacks, changed proposal context and repeated clicks cannot replay them.
  This is a UI guard, never a replacement for server identity/scope/version validation.
- Continuation failure leaves execution unconfirmed, without automatic or button retry.
  Starting a new request invalidates the old UI controls but does not cancel/reject
  the old server workflow. Initial ordinary requests retain explicit retry.
- State is memory-only and clears on reload; no localStorage, durable resume, trusted
  browser state, new business rules, secrets, client LLM or MCP integration.

Manual fake demos: in dev only, expand the small 'development demo scenario' control
at the bottom right to choose completed, business negative, clarification, approval,
transport/runtime/contract error. Switching remounts/clears the demo workspace.
Production builds omit that developer control; unset runtime mode uses fake completed presets, while LOCAL selects the local client;
a Vite production build is not a production AgentArts deployment. Presets are
synthetic examples based on the existing contract fixtures, never decisions computed
from the user's text/profile. The UI explicitly labels this fake environment.

## Contract source and synchronization

Backend P12 Pydantic contracts remain authoritative. Regenerate the checked-in
selected public JSON schemas, TypeScript projections and canonical fixtures using:

```powershell
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py
```

Export/check uses the backend environment with its existing optional `agent` extra
installed, because the P12 runtime envelope imports the graph contracts. No new
Python dependency is introduced; base-only backend tests skip this parity module.

Do not edit `src/runtime/generated/` or `tests/fixtures/runtime.json` by hand.
The backend drift test regenerates in memory and compares both schema/types and
fixtures. No AgentState, GraphInput or trusted HumanResume is exported.

## Invocation boundary

Frontend -> RuntimeInvocationClient -> RuntimeTransport (Local / AgentArts)
-> P12 Runtime Adapter -> Agent -> Graph -> Capability Facade.
No MCP dependency or capability-specific business clients are introduced.

`invoke(AgentRequest)` returns a validated AgentResponse. `resume` submits the
existing typed continuation envelope. `exchange` returns the safe transport wrapper
including an opaque continuation_ref, retained explicitly by the HITL UI.
AgentArtsRuntimeTransport and LocalRuntimeTransport implement
the same interface via isolated HTTP adapters; FakeRuntimeTransport remains preset-only.

Request validation preserves caller request IDs, explicit context and typed replies;
it adds no defaults or authority. Response validation is strict, including enum,
identity, nested HITL and audit reference consistency. Unknown/extra shapes fail
closed. Data is detached through a JSON boundary; aware timestamps and URL/ref
strings retain their public P12 semantics; generated normalization hints and
behavioral fixtures cover constraints not expressible in JSON Schema. No automatic retry or stored last-request/session context.

Errors are TRANSPORT_ERROR, CONTRACT_ERROR, RUNTIME_ERROR or ABORTED, with safe
messages. Core AgentResponse FAILED remains a valid structured response. Business
negative outcomes, clarification, approval wait and valid rejection do not become
client errors. Actual AgentResponse contains audit/result refs rather than embedded
business result/evidence/PlanDiff bodies; fixtures preserve that real shape instead
of inventing business status fields. The readonly artifact presentation boundary below
supports those referenced bodies without altering P12 or P14.1 wire contracts.

## Grounded result presentation

`src/results/` contains pure result/status, reason, evidence, source and PlanDiff
components. Conversation displays the returned explanation verbatim; structured
panels never parse it, call an LLM, calculate scores or invoke Runtime. UNKNOWN and
UNDETERMINED have explicit uncertainty text. Missing reasons/bodies/source metadata
stay missing; an unknown reason retains its raw code. Runtime errors stay separate.

Actual AgentResponse contains `audit.results/reasons` and `plan_refs`, not embedded
business decisions, Evidence or PlanDiff. An optional synchronous `ArtifactReader`
at composition supplies a readonly `{request_id, artifacts:[{ref, model, value}]}`
presentation snapshot. It is not another Agent API, a Runtime wire field, an artifact
fetcher or authorization. Request ID, exact referenced kind/ID, model, duplicate keys
and selected generated schema are checked before display. Invalid attachments show
ARTIFACT_CONTRACT_ERROR and no body; a new response replaces the old presentation.
Without a matching attachment, the UI shows the references and unavailable-body text.

Fake composition supplies fixed Pydantic-validated attachments; Local composition
supplies revalidated actual receipt data through scoped local hosting.
JSON Schema guards structure only; they do not establish factual truth or duplicate
Domain behavioral rules. P12/P13/P14.1 contracts are unchanged. No browser object is
trusted authority. Generated schemas/types for selected existing EligibilityDecision,
RecommendationEvaluation, SkillGapDecision, Evidence, SourceMetadata and PlanDiff
come from `scripts/export_frontend_results.py`; regenerate by running it without
`--check`. It reuses the existing export's type formatting and existing backend test
factories only for offline synthetic fixtures. Backend drift tests revalidate every
fixture with the unchanged Domain models. Do not hand-edit generated files or
`src/demo/result-fixtures.json`. This is consumer data, not a new source of truth.

PlanDiff's real contract provides complete milestone before/after collections and
optional status_change, not per-item ADD/REMOVE/UPDATE operations. The UI preserves
both supplied collections, including removed/new/changed content, exact Plan IDs and
versions, decision, trigger events, reason codes, evidence refs and provided sources.
It does not compare Plans, derive a per-item change classification, create a diff
from plan_refs, or synthesize one after approval. Empty supplied diffs remain empty.

Evidence is React-escaped text, never raw HTML/Markdown execution. Source links allow
only HTTP(S), reject embedded credentials, use noopener/noreferrer with new tabs,
and preserve the supplied URL string. Type, aware observation time (UTC display with
original ISO in title/dateTime) and verification state remain distinct. Long refs/URLs
wrap; semantic lists/headings/links and labeled before/after sections support keyboard
and narrow-screen use. Frontend Gates O/P/Q cover grounded claims, supplied-diff
authority and safe untrusted source presentation. Gate E remains
CONTRACT_PASS_REAL_RUNTIME_DEFERRED; no real Runtime or production deployment claim.

## Continuation and security

PublicRuntimeResult reuses unchanged P12 AgentResponse/RuntimeError and adds a safe
continuation_ref transport projection. Pending raw P12 GraphInput output is rejected.
Local trusted hosting retains internal continuations, returns scoped opaque handles
and resolves them through the existing P12 continuation_ref input under its local
operator policy. Production multi-user authorization is not implemented. Completed wire continuation:null
is accepted. All browser handles/replies remain client-controlled and require server
validation of identity, actor, scope and Plan version. No browser HUMAN_APPROVED.
Clarification sends existing clarification_id/source_request_id plus only requested
values; approval sends existing approval_request_id/source_request_id, decision and
submitted_at. P12 does not require echoing Plan/scope fields in ApprovalResponse;
those readonly references remain bound by the server's proposal and handle. No full
AgentState is stored. Local interaction acceptance only means an attempt was sent,
not that approval or mutation succeeded. Fake demos use fixed response sequences,
not decision-dependent Plan calculations or a real authorized continuation store.

Frontend Gate M (HITL Authority Preservation): controls collect expressions only;
P12.5/core still creates authority. Gate N (Continuation Identity Integrity): current
request/proposal/handle binding, stale replacement and consumed-action guards are
covered by offline tests. Local hosting now retains private continuations and validates core authority; AgentArts remains P14.6 and production authorization remains P16.

Public config selects LOCAL/AGENTARTS and supplies baseUrl/runtimeName. Unknown config
keys, missing/non-string required values, credential-bearing URLs and
query/fragment tokens are rejected. Config baseUrl/runtimeName must be strings;
surrounding whitespace is rejected rather than coerced or normalized. No secret/header
provider, production auth or cloud SDK is implemented. Do not put secrets in public
config, bundles or storage. Future trusted backend/BFF routing is allowed; production
security remains P16. Transport metadata is discarded by the generic client and
never becomes Agent context or approval. Config chooses transport, not business logic.

Cancellation is an AbortSignal transport concern, never ApprovalResponse(REJECT),
and cannot guarantee server execution was canceled. AUTO_RETRY=OFF.
NON_STREAMING_PRIMARY: one complete AgentResponse, no simulated token streaming.
Local and AgentArts invocation compatibility are implemented; P15 owns systematic evaluation.

## Public validator behavioral parity

Generated normalization hints come from P12 public Pydantic field annotations,
not from matching field names or assuming every string should be trimmed. Before
transport serialization and identity correlation, the client constructs a detached
canonical input. Existing caller IDs are normalized, never replaced/generated.
StableId strings use Pydantic Unicode whitespace stripping and reject blanks;
response message follows the same constraint. Public AgentContract timestamps use
UTC with microsecond precision; PlanReference.updated_at retains its existing offset.

Public validators that JSON Schema alone cannot express are centralized in runtime
validation: milestone IDs reject duplicates after normalization and sort (never
silently deduplicate), clarification fields reject duplicates and sort, audit refs
remain unique/bound/canonically ordered, approval artifact types/reasons/evidence
stay checked, response payload/interaction identity stays bound, and nested public
clarification profile/invocation contracts preserve their structural normalization.
Profile interest/goal normalization follows the existing public model; no decision,
scoring, planning or approval authority is implemented by these consumer guards.

`tests/fixtures/runtime.json` includes Pydantic-generated behavioral cases with raw
input and canonical output or rejection. Frontend tests exercise these through the
client; backend tests and --check recompute expectations from unchanged P12 models.
This extends the existing generation strategy, not a new source of truth. Consumer
JSON schema remains strict: no general Pydantic scalar coercion is enabled.
## Explicit generated plan selection

In Local/AgentArts-compatible runtime sessions, successful CompetitionPlan
artifacts with matching `plan_refs` appear under “当前计划 / 选择计划”. Choose a
plan explicitly before a later request. The browser passes the exact returned
reference; it does not recalculate digest/version, register plans or grant approval.
The existing controlled-fixture checkbox remains available and is mutually
exclusive with generated-plan selection. No plan is selected automatically.

Choices last only for the current mounted page. Local server restart clears
generated registry state and restores the controlled fixture; reload/regenerate
before selecting a generated plan again. Registration alone does not provide
replanning events, impact or instructions. Generated COMAP revision is currently
rejected without entering WAITING_FOR_APPROVAL because no matching executable
ReplanningInput exists. This is an in-memory local demo, not durable persistence.

For the generated Huawei same-plan demo, explicitly enter student
`local-recommendation-demo`, competition `huawei-ict`, edition `huawei-ict-2026`
and track `huawei-ict-2026-innovation`, then generate a plan. Select that returned
plan and request revision. REJECT preserves it; a new workflow's APPROVE displays
the backend PlanDiff (draft -> cancelled, version +1). This uses a manual controlled
observation, **not a real official Huawei track deletion**. The frontend creates no
Event/Impact/instruction/authority and computes no diff. Restart Local Runtime
after upgrading; previously generated references are not durable.

## Demo Polish 1: semantic results and error presentation

The verified artifacts now render as recommendation cards, a skill comparison table
and a plan timeline. Backend ordering, buckets, scores and decisions are unchanged.
`verified-skill-overlap-v1=1` means explicit recorded overlap, never “100% suitable”.
Missing skill facts and unspecified requirement levels remain unknown. Missing
deadlines stay unset. Competition names are display labels from verified seed data,
with an identity fallback for unknown names; labels never select or score candidates.

Evidence, sources, original replies and raw audit snapshots remain available through
keyboard-accessible disclosure controls. Manual controlled-demo sources are labelled
as simulated changes. No frontend diff, authority or version is computed.

The presentation composition retains validated public runtime error code/message
without changing RuntimeInvocationClient, transport errors or workflow state.
`NO_TARGET_CONSISTENT_REPLANNING_INPUT` explains the current plan limitation instead
of suggesting a later retry. Explicit stale/consumed error identifiers have dedicated
wording; an opaque `CORE_VALIDATION_ERROR` stays generic because the UI cannot infer
whether it means stale state, replay or another validation failure. Advanced details
preserve the supplied public code/message. No error triggers an automatic invocation.

Run `npx tsx --test tests/results.test.tsx tests/local.test.tsx` from `frontend/`
for presentation and real Local HTTP coverage; `npm test`, `npm run lint` and
`npm run build` remain the full frontend validation commands. This polish is
Post-P14 demo work; P15 implementation remains NOT_STARTED.

### Demo Polish 1.1: recommendation presentation cleanup

Recommendation deliveries show one bucket-count summary, the first five candidates
in existing backend bucket/entry order, and an expandable remainder. Each card has
one explanation and one source-grouped disclosure. Source cards group by URL and
show the latest observation plus history count; profile facts are grouped by explicit
skill ID. No candidate, bucket, rank or score is changed. Missing scores mean
insufficient scoring information, never zero or a negative skill judgment.

All validated recommendation, Evidence and Source artifacts, references and scoring
configuration remain in a single advanced audit disclosure. Only their redundant
visual blocks are removed. The original authoritative reply is folded at the bottom
of the recommendation result; earlier conversation records remain available.

### Demo Polish 1.2: skill gap and plan presentation

Skill gap summaries translate the supplied decision, requirement coverage and item
statuses. Known self-assessed ability with an unspecified required level stays
undetermined; missing profile records never become a skill deficit. Ability and
requirement provenance are grouped behind disclosures; full artifacts and references
remain in one advanced audit section, with the original reply separately folded.

Plan timelines use exactly the supplied milestones and their order. Existing
uncertainty-resolution needs receive readable requirement/skill labels, draft plans
display as drafts, and missing deadlines remain unset. Follow-up explanatory text
is explicitly outside the authoritative milestone list. Complete IDs, original
titles/descriptions, planning needs and dates remain accessible in audit.

Recommendation source cards now consolidate observations of the same URL. The card
shows metadata from the newest supplied observation and the number of distinct
historical records. No source/evidence history is removed or written back. P7/P8,
Runtime, registry and approval behavior are unchanged; this is frontend polish only.

### Demo Polish 1.3: clarification and PlanDiff evidence aggregation

Clarification fields remain backend-requested and use the existing typed continuation
builder. Known target IDs use normal inputs; requested student profiles allow an
explicit ID and optional user-supplied education, with no inferred facts. Plan inputs
select only exact references already returned by the server. No field is treated as
resolved until a runtime response says so. Original questions/enums remain in audit.

The browser has no trusted SkillGap/capability argument assembler. Arbitrary capability
arguments/invocations and unavailable plan structures therefore use an explicitly
opened advanced JSON fallback, never a guessed payload assembled from context IDs.
JSON textareas are mounted only after opening advanced input. Public client/Core
validation, continuation identity, stale/replay guards and approval controls remain.

PlanDiff keeps the supplied before/after, version and declared changes. Duplicate
Source/Evidence attachments are consolidated into one source section and one audit
snapshot containing all original artifacts and references. The decision chain only
labels returned Event/Impact/Decision facts. Human approval wording additionally
requires a completed revision with backend approval-request, approval-response and
authority audit refs; explanation text or a status change alone is insufficient.
No Impact, REPLAN, mutation, authorization or diff is computed in presentation code.

### Demo Polish 2.1: explicit guided actions

The composer retains natural-language chat and adds five explicit operations:
eligibility, recommendations, skill gap, planning and plan revision. Buttons submit
the existing AgentIntent with the page's explicit context through the same runtime
client. They never provide capability arguments, results or authorization. Chat
requests omit intent and continue to use configured intent routing.

This requires the additive optional `AgentRequest.intent` transport field (the old
public request only exposed text/context; explicit intent was internal graph state).
Backend preparation and graph routing use the same deterministic proposal mapping
and existing routing validator; explicit operations make zero intent model calls.
Old requests remain valid. Generated schemas/types are exported from Python.

Skill gap/planning buttons require an explicitly entered competition and edition;
revision requires an explicitly selected exact PlanReference. These are UI hints,
not business validation. Missing facts still use server clarification; planning
still runs P7 first, and revision still requires event/impact/policy preparation
and human approval. Buttons are locked during pending/clarification/approval states.
No default entity, implicit plan selection, retry or business result is synthesized.

## Post-P14 Product Experience Upgrade (PX): design handoff

Product direction: Competition Copilot is a university competition lifecycle
decision and growth platform. Dashboard becomes the default entry; Copilot remains
a dedicated workspace and a contextual entry across business pages. The current
workspace and semantic result components are the reusable implementation baseline;
PX1 implementation is described below; later business pages remain planned.

- **PX0 / Design: DOCUMENTED. PX1 / PX2 / PX3: CLOSED_VERIFIED. PX2.1: COMPLETE. PX2.2: CLOSED_VERIFIED. PX4: IN_PROGRESS; PX4.1 CLOSED_VERIFIED; PX4.2 CLOSED_VERIFIED_LOCAL. PX5/PX6: PLANNED.**
  P12/P13/P14 remain CLOSED_FROZEN; P15 remains NOT_STARTED.
- Planned navigation: 首页、赛事中心、我的赛事、我的能力、备赛计划、赛事动态、Copilot.
  Approval Center placement remains a later navigation decision. Deliver incrementally.
- PX1 establishes shell/navigation, Dashboard, Current Context Panel and basic
  Empty/Loading states. Populate only from validated state and explicit selection;
  show Empty/unavailable when a safe read path does not exist. No fabricated counts,
  progress, profile-completeness percentages or inferred server history.
- Existing explicit actions use the same Agent Runtime and Facade; context selection
  carries exact authoritative references, not editable technical identities or authority.
  Evidence stays accessible through Conclusion → Explanation → Evidence → Advanced Audit.
- Task/Action Item, follow-state storage, completeness policy, notifications and
  new persistence/API work require separate design/review; none is implied here.
  Controlled Huawei observations remain demo-only, cloud smoke is not production,
  and generated plans do not survive an in-memory runtime restart.

Canonical page/interaction design: [PRODUCT_SPEC](../docs/PRODUCT_SPEC.md#post-p14-product-experience-design).
PX1–PX6 scope, dependencies and acceptance gates:
[DEVELOPMENT_PLAN](../docs/DEVELOPMENT_PLAN.md#post-p14-product-experience-upgrade-px).
Authority/data-flow boundaries:
[ARCHITECTURE](../docs/ARCHITECTURE.md#post-p14-product-experience-boundary).

### PX1 — product shell, Dashboard and current context

Status: CLOSED_VERIFIED. The design handoff above describes the PX0
baseline; PX1 is implemented; PX2.2's authoritative reads and history boundary are documented below. PX3 is CLOSED_VERIFIED, PX4 IN_PROGRESS (PX4.1 CLOSED_VERIFIED; PX4.2 CLOSED_VERIFIED_LOCAL) and PX5/PX6 PLANNED. PX1 did not change backend; PX2.2 adds the approved readonly projection.

The default `#/home` presents current explicit context, the selected plan's known
version/status, the most recent validated reply, a pending approval only when the
live workflow supplies it, and links back to Copilot. Missing information uses
empty states; there are no invented metrics, default targets, completeness scores
or auto-selected plans. Context labels reuse existing presentation names; unknown
names are not guessed from identifiers. Raw identities are folded in technical details.

`#/copilot` retains the existing Workspace as one mounted instance. Minimal hash
navigation supports browser back/forward and deep links without a router dependency.
Changing pages hides/shows the workspace; it does not submit, reset conversation,
clear drafts, choose a plan, reread server state or resume approval. Dashboard reads
a UI snapshot, not a second workflow or a server current-plan registry. Selected
versions may be stale; the server still owns validation, CAS and all approval authority.

PX1 delivered five honest coming-soon pages. PX2 now activates 赛事中心;
我的赛事、我的能力、备赛计划、赛事动态 remain coming-soon pages.
The existing recommendation, skill-gap, planning, evidence and PlanDiff renderers,
semantic clarification, explicit actions and approval controls remain in Copilot.
Session/restart boundaries are unchanged. No Task, Event Feed, Notification Backend,
Demo Mode or new business capability is implemented by PX1.

Validation: frontend targeted 52 / full 247 tests passed; lint/build passed.
`npm run test:responsive` passed for Local/AgentArts with 24 captured layouts,
including Dashboard at 1440 and 1920 widths, with no horizontal overflow.
Screenshots remain ignored local artifacts in `tmp/p14-7-e2e/`.

### PX2.2 - Authoritative Competition Detail

Status: CLOSED_VERIFIED, with Final Independent Review REVIEW_PASS; PX2 Core is CLOSED_VERIFIED.
P12/P13/P14 remain CLOSED_FROZEN; P15 remains NOT_STARTED; current PX3 closure is recorded below.

The center preserves existing Runtime discovery, search and canonical catalog
records. A direct `#/competitions/<encoded canonical id>` opens a fresh readonly
query without requiring Discovery. Detail reads use explicit GET_COMPETITION_DETAILS,
zero intent/explanation LLM calls and the existing Runtime/Agent/Facade path.
They never read seed files, invoke providers or execute P5/P7 in the frontend.

Generated schemas validate CompetitionDetailProjection before use. Competition-only
queries return editions without selecting one. Edition/track selectors send exact
canonical identities and update current context; no default edition/track is guessed.
Browsing and scope selection do not trigger analysis. Since PX2.3, clicking an
analysis action opens Copilot and submits the existing explicit intent through
the shared Workspace submit path; missing context still requires Core clarification.

Seven accessible tabs display authoritative entity snapshots, reviewed policy facts,
full skill requirement artifacts/version/catalog, registration/competition windows,
tracks and provenance. Unspecified proficiency remains unspecified; partial coverage
is retained. Source URL grouping is visual only; complete projection, source metadata,
evidence and result references remain in folded audit. Null time endpoints are unknown;
submission windows are not invented. Personal decisions attach only for exact student
and competition/edition/track matches, without running new eligibility or skill analysis.

Full event history remains EVENT_HISTORY_PERSISTENCE_GAP. The history tab explicitly
states that complete history is unavailable; exact-target current-session evidence is
separate and never presented as a complete ledger. Controlled-demo sources remain
manual demo evidence, not claims of real official changes. No persistence was added.

#### Shared release checkpoint

**PX2 Authoritative Competition Read Baseline** is ready as a shared GitHub team
reference. PX1 / PX2 Core are CLOSED_VERIFIED; PX2.1 is REVIEW_COMPLETE and PX2.2
is REVIEW_PASS. Later PX2 Detail UX Enrichment or separately authorized PX3 work
continues from this stable checkpoint; this status sync does not commit or publish.

**At this release checkpoint, PX2 Product Detail Enrichment was DEFERRED.** Scope:
center information density, richer detail organization, edition/track selection UX,
visual/information structure polish, and more authoritative facts when data coverage
increases. Unknown facts must never be inferred to enrich the page. Complete event
history remains unavailable; current-session evidence is not complete history.
Submission window remains DATA_CONTRACT_GAP and is not implemented.

### PX2.3 — Detail enrichment / information architecture

Status: **CLOSED_VERIFIED**, following Final Independent Review = REVIEW_PASS.
PX1 / PX2 Core / PX2.2 remain CLOSED_VERIFIED; PX2.1 is REVIEW_COMPLETE;
P12/P13/P14 remain CLOSED_FROZEN. PX3 and P15 have not started.

- Center cards group available sections instead of repeating missing-field notices.
  Counts and availability filters use already validated, cached detail projections;
  unvisited cards show basic entity information without automatic per-card reads.
  A cached summary labels its actual target scope and never selects that scope.
- Detail uses a scope hierarchy, explicit edition/track selectors, grouped overview,
  partial-policy notice, requirement catalog labels, and a two-stage time line.
  Null endpoints remain unknown; no submission stage is invented.
- The evidence center groups URLs visually while retaining section/scope associations,
  each association's verification and observation, and complete raw projection/ref audit.
  A competition or edition source never verifies an unreferenced track.
- Personal eligibility/gap results remain exact student/target session attachments.
  Suggested actions reuse existing intents; no analysis runs on browsing/selection.
  Complete event history remains unavailable; current-session evidence is separate.

Projection boundaries: unqueried tracks do not expose exact policy/requirement
availability (`PX2.3_PROJECTION_GAP`); cards use an exact cached projection or say
that scope has not been read. Student display names and full selected-plan metadata
are not in the detail projection; the scope panel shows session selection/version,
not an invented profile or server-current status. No Backend extension was made.

Validation: 15 new presentation tests; full frontend suite 276 passed; lint/build
passed. `npm run test:responsive` exercises offline Local/AgentArts-compatible
Chrome flows, including Huawei competition → edition → track, COMAP requirements,
unknown times, and 1080/1440 layouts (42 layout checks / 28 explicit requests passed).
Only the browser harness uses a 5-second test gateway timeout to tolerate rendering
load; transport fault tests retain their 0.5-second default, with no production
timeout or retry changes. A no-edition/no-track entity is tested as a
synthetic UI fixture; no fake competition was inserted into the formal catalog.
Independent review passed; this closure does not claim production Cloud deployment.

**PX2.4 Temporal Information Enrichment — CLOSED_VERIFIED**, FINAL INDEPENDENT RE-REVIEW = REVIEW_PASS.
PX2 Competition Experience overall is CLOSED_VERIFIED: PX2.1 COMPLETE,
PX2.2/PX2.3/PX2.4 CLOSED_VERIFIED. PX3 is CLOSED_VERIFIED; PX4 IN_PROGRESS; PX4.1 CLOSED_VERIFIED; PX4.2 CLOSED_VERIFIED_LOCAL;
P15 remains NOT_STARTED and P12/P13/P14 remain CLOSED_FROZEN.
`PX2.4 TEMPORAL_INFORMATION_PROJECTION_GAP` was the design baseline: the previous timeline
could not express official date text awaiting structured verification. PX2.4 adds
that reviewed evidence projection, now verified by independent review. It was non-blocking for PX2.3; a source
link or year never establishes an announced date. The projection gaps above, full
event-history persistence gap and submission-window contract gap remain unresolved.

PX2.4 adds reviewed temporal candidates to the same generated detail projection.
Timeline distinguishes verified full, verified partial, official pending quote,
unknown within current records, and edition not requested. Candidates preserve
raw text, precision and source; no dates/timezones are inferred. Complete verified
windows take priority, with pending evidence folded below; partial windows keep
unknown endpoints even when a candidate quote is available. Edition evidence stays
labelled as edition-level on track pages. Evidence source grouping remains visual,
with Raw/review references and digests available in the existing projection audit.
This does not feed planning, snapshots, events, impact or replanning. There is no
runtime extraction, new intent, endpoint, MCP Tool or automatic promotion.

The partial endpoint blocker is fixed: only explicit candidates for missing
endpoints appear in the main timeline. Same-endpoint candidates for verified
values and stage-level candidates in partial windows remain in folded audit.
Classification uses field identity, never quote text. Verified endpoint > Candidate.
No year, timezone, midnight or month-range bounds are inferred. Targeted tests:
41 passed; full frontend: 302 passed; lint/build/diff check passed.
Coverage remains three admitted quotes, not all Raw temporal text; complete event
history and submission windows remain gaps. Local PlanRegistry remains in-memory.

Validation commands (from frontend):

```powershell
npm run test:results
npm run test:local
npm test
npm run lint
npm run build
```

Backend schema exports/checks (from repository root):

```powershell
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
.\backend\.venv\Scripts\python scripts/export_frontend_results.py --check
```

## PX3.2 Profile Read / Edit

Status: CLOSED_VERIFIED. Existing #/profile navigation hosts profile
read/edit through Runtime GET_PROFILE / UPDATE_PROFILE. Current student must be
explicit; no first-profile fallback or hardcoded demo identity.

Seven base fields support view/edit/cancel/save. Skills were read-only in PX3.2;
PX3.3 management is described below. Decimal
and zero weekly hours are supported. Form completion counts N/7 fields; zero
counts as supplied and skills are outside the denominator. This is not a score.
Missing skills differ from UNKNOWN; non-self-assessed does not mean certified.
Unresolved skill names fall back to IDs without a duplicate frontend catalog.

Save uses the returned ProfileReference and backend snapshot. Conflicts preserve
the draft and require reload; no automatic overwrite or business analysis.
The page explicitly states that Demo edits live only within the running server
and disappear after restart. Refresh can reread after selecting the student again.
IDs/digest/host scope stay in folded technical details. Full stale-result UI is
CLOSED_VERIFIED in PX3.4; skill mutation is CLOSED_VERIFIED in PX3.3 below.

P12-P14 CLOSED_FROZEN; P15 NOT_STARTED.

## PX3.3 Skills Read / Edit — CLOSED_VERIFIED

The existing “我的能力” / `#/profile` page now manages skills through explicit
GET_SKILL_CATALOG / ADD_PROFILE_SKILL / UPDATE_PROFILE_SKILL / REMOVE_PROFILE_SKILL.
The catalog selector uses backend names, excludes recorded IDs and disallows free
ID entry. Historical unresolved names fall back to their original ID.

Add/edit supports UNKNOWN (尚未评定), beginner/intermediate/advanced and optional
user notes. Skill identity and source flags are read-only. Non-self-assessed never
means certified. Delete requires confirmation and makes the record missing, not
UNKNOWN. Empty state is “尚未记录技能”; N/7 base completion still excludes skills.

Each write uses the current ProfileReference and adopts only the returned validated
snapshot. Conflicts keep the draft; reload is required, with no automatic merge.
No recommendation, gap analysis or plan change runs on save. Full stale-result UX
is CLOSED_VERIFIED in PX3.4. Profile/skill changes remain host-memory only and disappear after
server restart, as visibly explained on the page.

## PX3.4 Derived Result Staleness — CLOSED_VERIFIED

Copilot result panels, Dashboard and My Profile related analyses consume the
Backend ProfileAnalysesProjection. They display 基于当前画像 / 基于较早画像 /
画像版本未记录，无法确认. A failed read stays neutral: 无法确认画像版本状态.
Frontend never compares profile references to decide freshness or uses timestamps.
Refs remain in folded audit details. Stale is informational, not a failed result.

The session keeps old validated recommendation/gap/plan bodies. Profile/skill saves
and new results trigger only GET_PROFILE_ANALYSES reads; opening/rendering a page
does not rerun business analysis. Existing student/competition/edition/track matching
still applies. Current plan summaries use the exact selected PlanReference. In the
product shell, explicit successful plan generation selects its returned exact
reference and immediately reads Planning Workspace; other plan choices stay manual.

相关分析 now supports viewing existing results and explicit recommendation rerun,
skill-gap rerun and P8 plan generation. Saving does not change an old score, gap or
plan, and does not invoke P11. No implicit latest student/plan selection. Unknown
lineage and cross-host scopes remain UNKNOWN. Persistence remains host-memory.

Profile-driven recommendation can start from 我的能力 → 根据当前画像推荐赛事
with only the current student selected. No competition/edition/track is required;
Runtime prepares the formal multi-candidate pool. Copilot natural-language and
explicit recommendation use that same path. Existing exact-target requirements
for eligibility, skill-gap and planning remain unchanged. A requested explicit
action waits for a concurrent catalog read instead of being silently discarded.

Copilot also renders the latest successful recommendation, skill-gap analysis and
plan for the current student/target from the existing validated session cache when
the active workflow has been cleared or replaced. Profile/skill edits retain those
bodies and refresh only Backend freshness. Explicit successful reruns replace the
latest displayed analysis; no history database or persistent result store is added.
The selected plan remains bound to its canonical PlanReference. Session retention
still ends on browser refresh.

Recommendation names use the shared authoritative CompetitionCatalog resolver.
When a recommendation references a competition not yet read in this session,
the product reads GET_COMPETITION_DETAILS at competition scope to fill its name.
Initial, stale and rerun presentations reuse that directory; no translation or
manual ID/name table is used, and unknown names safely fall back to canonical IDs.
These reads never select an edition/track or change recommendation results.

PX3 final acceptance: PX3.1 COMPLETE; PX3.2/PX3.3/PX3.4 and PX3 overall CLOSED_VERIFIED.
Browser Smoke PASS; Final Independent Review REVIEW_PASS. Profile/skill read and edit,
trusted authorization, optimistic concurrency and atomic skill evidence mutation are
verified. Missing record != UNKNOWN != SkillGap. Explicit rerun/re-analysis/P8
regeneration uses the current snapshot; saves do not automatically recompute or replan.

Known gaps remain: host-memory persistence (server restart restores fixture baseline),
no full account/identity system, incomplete required_level coverage
(SKILL_REQUIREMENT_DATA_ENRICHMENT_GAP), P8's concentration on uncertainty-resolution
tasks under incomplete constraints (PLANNING_ACTIONABILITY_GAP, PX4 high priority),
unavailable complete Competition Event History and Submission Window DATA_CONTRACT_GAP.
At the PX3 sync, PX4 was READY_TO_START. Current status: PX4 IN_PROGRESS;
PX4.1 CLOSED_VERIFIED; PX4.2 My Competitions Workspace CLOSED_VERIFIED_LOCAL.
PX1/PX2 CLOSED_VERIFIED; P12-P14 CLOSED_FROZEN; P15 NOT_STARTED.

## PX4.1 Planning Workspace — CLOSED_VERIFIED

Existing 备赛计划 navigation opens the read Workspace: 备赛概览 / 已确认约束 /
推荐准备任务 / 待确认事项 / 时间参考 / 计划原文与审计 / 显式操作.
Opening/refreshing calls only GET_PLANNING_WORKSPACE. No target selects no default;
edition/track remain explicit choices. Plan references come from a manual choice
or the validated result of explicit generation, never a latest-plan lookup. Counts come from
projection entries, with no readiness score. Full original milestones/dependencies/
needs and references remain in folded audit, with technical IDs hidden by default.

Stale Plan and current-profile suggestions are explicitly separate. Advice is not
old Plan text. Verified endpoints take precedence over pending candidates; quotes,
precision, scope and sources remain available, including overlapping audit evidence.
Weekly hours preserve None/0/decimals; no goals inference or time allocation.

Generate/regenerate and skill-gap re-analysis use existing explicit P8/P7 actions.
Viewing, refreshing or saving a profile never executes them automatically.
Detail/profile CTAs preserve canonical context. PLANNING_ACTIONABILITY_GAP is
mitigated without changing P8 truth or P11 authority. Browser Smoke PASS;
Final Independent Review REVIEW_PASS. PX4 IN_PROGRESS; PX4.1 CLOSED_VERIFIED;
PX4.2 CLOSED_VERIFIED_LOCAL; PX4.3/P15 NOT_STARTED.

Targeted frontend verification (from frontend):

```powershell
node --import tsx --test tests/planning-workspace.test.tsx tests/local.test.tsx
```

Planning clarification renders backend-resolved missing fields only. An existing
repository profile plus a missing Edition shows the Edition input without a second
profile form. MISSING_STUDENT_PROFILE directs users to 我的能力; no temporary
profile JSON or education selector is offered for that unavailable-profile state.
The UI does not infer profile availability from student_id.

BUILD_PLAN completion now surfaces this same Workspace in Copilot's right result
panel through GET_PLANNING_WORKSPACE, using the full returned exact PlanReference.
The left chat stays concise. No refresh, route change or second plan-selection
click is required. The original Plan renderer remains folded under 计划原文 / 审计;
advisory tasks are independent and never inserted into the original milestones.


## PX4.2 My Competitions - CLOSED_VERIFIED_LOCAL

The existing `#/my-competitions` navigation is now a workspace with ALL / SAVED /
PREPARING filters, authoritative target names, result/freshness summaries, time
references and deterministic next-action CTAs. `MyCompetitions.tsx` contains the
read projection consumer and explicit relationship controls shared by Competition
Detail, Recommendation and Planning Workspace. It never calculates business truth.

Joining requires an explicitly selected Edition; Track remains optional and exact.
Add/update/remove use Runtime typed actions and backend snapshots; there is no
authoritative browser bookmark state. Set-current is a separate existing workspace
selection, carries the full target and clears incompatible selected Plan context.
Removing a relationship leaves Current Context and previous analyses/plans intact.

Relationships are local Demo host memory and are lost on service restart. Provider
failures, not-analyzed results, invalid references and profile freshness are distinct.
Candidate times remain labelled official/pending references, never deadlines.

Targeted: `node --import tsx --test tests/my-competitions.test.tsx tests/workspace.test.tsx`.
### PX4.2 exact target completion

Add controls with a competition-only target lazily read authoritative Editions
through the existing Runtime detail READ and display an unselected Edition chooser.
Only explicit confirmation sends ADD. Exact recommendation/workspace targets keep
their direct Add path. Runtime clarification options render as label/id selects;
the reply sends `edition_id`, not supplemental text. P7 completion can restore the
workspace Edition only from its validated result matching the submitted choice.
No latest/first selection, automatic analysis or inferred Track is introduced.

### PX4.2 local closure and regression alignment (2026-10-30)

Current status: CLOSED_VERIFIED_LOCAL. Local Browser Smoke and Final Independent
Review PASS after the exact-target and Recommendation/Plan-context blocker fixes.
PX4 remains IN_PROGRESS; PX4.1 CLOSED_VERIFIED; PX4.3/P15 NOT_STARTED.
CI_PIPELINE_STABILITY_GAP remains OPEN: local closure does not mean GitHub Actions
is green. Durable relationships/result history and other documented gaps remain.

Frontend full: **383 passed / 0 failed / 0 skipped**. PX4.2 frontend targeted:
82 passed; backend targeted: 61 passed. Lint, build and diff check PASS. Regression
alignment changed only test infrastructure/assertions, with no production change
and no new production blocker.

The former response-correlation failure was TEST_HARNESS_BUG: use request_id to
match each response to its request. `tests/runtimeTrace.ts` waits for the matching
identity and reports observed requests/responses on timeout; completion order,
array positions and the last response are not valid correlation mechanisms.
The former 5-vs-2 and 8-vs-4 count failures were OUTDATED_ASSERTION. Extra projection
READs are legitimate; the latter trace contains exactly one P7 invocation.

No-auto-analysis tests classify READ / BUSINESS / MUTATION and assert business
intent counts (P5/P7/P8/P11), never total Runtime request counts. READs remain in
the trace. Rendering, relationship mutations and Set Current must not start
business analysis. The full trace is retained for diagnostics.

Multiple Editions: automated coverage PASS; browser coverage NOT_VERIFIED due to
FORMAL_TEST_DATA_COVERAGE_GAP (no second formal Edition for the same Competition).
This is neither browser PASS nor an implementation failure. Detailed verification
and all open gaps are in [Development Plan](../docs/DEVELOPMENT_PLAN.md).
