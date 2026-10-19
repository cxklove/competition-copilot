# Frontend baseline

P14.0 audits and plans this directory; it does not initialize an application.
Canonical phase status and subphase boundaries: `docs/DEVELOPMENT_PLAN.md`.

## Existing inventory

The directory had no files before this baseline. There is no package.json, lockfile,
src/public, framework, app entry, API client or test configuration. Existing dev,
build, lint and test commands are NOT_AVAILABLE; no commands should be guessed.

Planned empty-directory stack: React + TypeScript + Vite, npm/package-lock.
P14.2 selects/pins versions and defines actual install/dev/build/lint/test scripts.
No packages are installed by P14.0. P14.1 first defines the Runtime client contract.

## Invocation direction

Frontend -> RuntimeInvocationClient -> Local/AgentArts transport -> existing P12
Runtime Adapter -> CompetitionCopilotAgent -> Graph -> Capability Facade.
Frontend does not use MCP as its primary Agent path or implement business rules.
Backend Pydantic public contracts remain authoritative; no Domain model duplication.

P12 pending runtime output currently contains internal GraphInput. Future trusted
hosting must hide it behind an authorized opaque continuation reference; browser
submissions never become trusted state. AgentResponse supplies refs rather than all
result/evidence/diff bodies, so safe canonical artifact presentation remains future
P14.1/P14.4/P14.5 work. No endpoint/resolver is implemented here.

Clarification/approval UI follows structured outcomes and explicit P12 replies.
No browser credentials, approval authority, session-derived business identity or
durable resume. Primary invocation is non-streaming. Production auth/deployment is
P16; systematic evaluation is P15. No UI or Local/AgentArts connection exists yet.
