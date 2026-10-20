# Frontend workspace and runtime invocation contract

The single React + TypeScript + Vite workspace presents current-page conversation,
structured workflow states, clarification forms and explicit approval controls.
The same RuntimeInvocationClient supports offline fake presets or the real local
Agent invocation path, selected at the composition root.
The result panel presents supplied result artifacts, evidence, sources and PlanDiff.
Local hosting retains scoped public continuation/artifact data. Real AgentArts
invocation and production authentication/deployment remain deferred.
Canonical lifecycle status: `docs/DEVELOPMENT_PLAN.md`.

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
VITE_RUNTIME_MODE retains fake mode. AGENTARTS mode is explicitly deferred to P14.6.

Try these bounded offline intent-model phrases (business results are real):

- `discovery` / `有哪些比赛？`: real repository discovery.
- `detail` / `赛事详情`: real clarification asks for competition ID; enter `huawei-ict`.
- `eligibility` / `检查资格`: explicit student `local-graduate`, competition
  `gcxl-engineering-practice-innovation`, edition
  `gcxl-engineering-practice-innovation-2027` returns real INELIGIBLE; `local-unknown`
  preserves UNKNOWN. The local profiles are synthetic server-owned input facts.
- `skill` / `plan`: student `local-graduate`, competition `comap-mcm`, edition
  `comap-mcm-2027` runs real P7/P8 with formal requirement data and uncertainty.
- `recommend`: the same explicit target context runs P5 then P6; no suitability
  signal is configured, so the existing P6 authority preserves missing-score semantics.
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
AgentArtsRuntimeTransport remains an interface only. LocalRuntimeTransport implements
the existing interface via HTTP; FakeRuntimeTransport remains preset-only.

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
Local invocation is implemented; P14.6 owns AgentArts integration and P15 owns systematic evaluation.

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
