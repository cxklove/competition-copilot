# Frontend runtime invocation contract

This directory currently contains TypeScript runtime contracts and fake transport
tests only. There is no UI, application entry, HTTP adapter or live Runtime connection.
React + Vite app initialization remains P14.2; npm/package-lock is retained.
Canonical lifecycle status: `docs/DEVELOPMENT_PLAN.md`.

## Toolchain and commands

Use Node >=24.12 (verified with 24.14.1), npm (verified with 11.11.0).
From the repository root:

```powershell
npm ci --prefix frontend --registry=https://registry.npmjs.org --ignore-scripts
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
npm run format --prefix frontend
.\backend\.venv\Scripts\python scripts/export_frontend_contracts.py --check
```

`test` uses the Node test runner with native TypeScript stripping. `lint` runs
TypeScript and Prettier; `build` currently means strict type checking only, with
no emitted UI bundle. There is no dev/server command yet. Runtime dependencies
are Ajv and ajv-formats; TypeScript, Node types and Prettier are development tools.
Versions are pinned in package.json/package-lock.json. Tests require no network.

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
including an opaque continuation_ref, for a future UI to retain explicitly.
LocalRuntimeTransport/AgentArtsRuntimeTransport are interfaces only; the deterministic
FakeRuntimeTransport returns preset payloads and records calls without business logic.

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
of inventing business status fields. Artifact presentation remains P14.4/P14.5.

## Continuation and security

PublicRuntimeResult reuses unchanged P12 AgentResponse/RuntimeError and adds a safe
continuation_ref transport projection. Pending raw P12 GraphInput output is rejected.
P14.5 trusted hosting must retain/authorize internal continuations, return scoped
opaque handles and resolve them through the existing P12 continuation_ref input.
That hosting/authorization is not implemented here. Completed wire continuation:null
is accepted. All browser handles/replies remain client-controlled and require server
validation of identity, actor, scope and Plan version. No browser HUMAN_APPROVED.

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
P14.5/P14.6 own real Local/AgentArts integration; P15 owns systematic evaluation.

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
