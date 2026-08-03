# ADR-0020: Profile Eval Review Web Boundary

- Status: Accepted
- Date: 2026-08-03

## Context

Profile Eval Runs, Case Results, human Reviews and the current accepted baseline already exist in the Backend. Without a browser surface, governance still requires curl or direct API use and is easy to misread as a simple pass/fail workflow.

The main risk is moving Backend review policy into React or presenting `releaseEligible=true` as if a model had already been approved.

## Decision

### Server-rendered read path

- `/evals/profile` and `/evals/profile/{id}` are Server Components.
- They read immutable Run, Case, Review and baseline facts using the server-only Backend client.
- Failed Cases are displayed before passed Cases.

### Client-only command boundary

- Only the Review form is a Client Component.
- It sends commands to a same-origin Next Route Handler.
- It never receives or exposes the FastAPI base URL.
- After a successful command, it calls `router.refresh()` and re-reads server facts.

### UI guidance is not policy

The UI may disable impossible or misleading actions:

- Fixture: no formal Review controls;
- failed live Run: reject only;
- eligible live Run: accept or reject;
- reviewed Run: read-only.

The Backend still performs all final validation and returns 201/404/409/422.

### No generic dashboard

This slice implements only the Profile Eval governance workflow. It does not introduce a reusable analytics framework, charting package, live model execution button or deployment approval.

## Consequences

### Positive

- Product owners can inspect failed cases and Trace IDs without curl.
- Human review remains visibly distinct from technical Gate status.
- Browser commands preserve same-origin and server-only configuration boundaries.
- Review decisions remain immutable Backend facts.

### Trade-offs

- No Trace detail page exists; the UI displays only Trace IDs.
- Reviewer identity remains local/self-declared.
- The current smoke E2E seeds deterministic test-only runs rather than calling a real provider.
- Real browser click automation is not included; Server HTML and same-origin HTTP flows are verified with production processes.

## Verification

- state-mapping and sorting unit tests;
- Web architecture tests;
- TypeScript and production build;
- test-only deterministic run seeding guarded by `APP_ENV=test`;
- real FastAPI + production Next smoke covering fixture 422, reject 201, accept 201, duplicate 409 and accepted baseline refresh.
