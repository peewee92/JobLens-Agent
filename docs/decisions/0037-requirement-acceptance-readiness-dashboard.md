# ADR 0037: Requirement Acceptance Read-only Readiness Dashboard

- Status: Accepted
- Date: 2026-08-05
- Scope: Requirement Acceptance operational visibility

## Context

Requirement Acceptance already had a zero-call CLI readiness gate. It combined the formal 20-JD dataset, Provider configuration, API-key presence, Alembic state, persisted Acceptance Run and immutable human decisions to produce one `nextAction`.

The CLI remained the correct boundary for operational work, but it created two usability problems:

1. a user had to repeatedly run commands to learn whether the workflow was blocked, waiting for Provider execution, or waiting for human review;
2. the existing Canary Web Workbench showed evidence only after a Run existed, so it could not explain pre-Run blockers such as a missing canonical dataset or an outdated database.

Adding a browser button that starts Provider work would solve the visibility problem by weakening the safety model. It would bypass the existing explicit cost acknowledgement, execution budget and controlled operator contracts.

## Decision

### 1. Add one read-only readiness endpoint and page

Expose:

```http
GET /api/v1/requirement-acceptance-runs/readiness
```

and:

```text
/evals/requirements/canary/readiness
```

They derive current status on every read. They do not persist a `ready` flag.

### 2. Keep dataset discovery server-side

The browser cannot provide a filesystem path. The Backend scans only the configured canonical private root:

```text
<private-root>/datasets/formal-*.json
```

Dataset discovery has four explicit states:

- `missing`: no canonical candidate exists;
- `selection_required`: more than one candidate exists;
- `invalid`: one candidate exists but JSON, formal preflight or fingerprint-derived filename validation fails;
- `ready`: exactly one valid fingerprint-addressed formal dataset exists.

The API returns only the canonical file name and Dataset Fingerprint. It does not return an absolute path or JD contents.

### 3. Reuse the existing readiness policy

`evaluate_requirement_acceptance_readiness` remains the source of truth for:

- workflow blockers;
- Provider-execution blockers;
- `workflowReady`;
- `providerExecutionAllowed`;
- `readyForNextAction`;
- the unique `nextAction`;
- Workbench and Manual Review handoff URLs.

The policy now accepts an absent formal preflight and fails closed with a dataset blocker rather than requiring a caller to invent dataset facts.

### 4. Share read-only runtime facts between CLI and Web

Alembic head and database revision reads are implemented once and reused by both the existing CLI and the Web Dashboard.

For SQLite, revision inspection uses URI read-only mode. It must not create a missing database or change database bytes.

The Dashboard does not query Acceptance Run tables until:

```text
formal dataset valid
AND database reachable
AND database revision == Alembic head
AND Provider == openai
AND model/reviewer/title are present
```

This prevents an outdated schema from causing a Run-table query before the migration blocker is reported.

### 5. Preserve the operational boundary

The Dashboard is GET-only. It does not expose:

- `execute-canary`;
- Controlled Resume execution;
- Alembic upgrade;
- database backup or restore;
- API-key values;
- command previews;
- arbitrary private paths;
- full JDs or raw Trace payloads.

When `nextAction` is `run_canary` or `resume_run`, the page explains that an explicit CLI Operator remains required. When the next action is human review, the page may link to the existing read-only evidence workbench or manual-review page.

### 6. Expose zero-side-effect evidence

The response includes:

```json
{
  "dbWrites": 0,
  "providerCalls": 0
}
```

These fields describe the readiness request itself. They do not claim that the overall Acceptance Run has never called a Provider; cumulative real attempts remain represented by `attemptedCalls` and persisted Run/Trace facts.

## Consequences

### Positive

- Human gates are visible without repeated CLI inspection.
- Missing dataset, configuration and migration blockers are distinguishable.
- Web visibility does not become Web execution authority.
- CLI and Web cannot silently diverge on database revision logic.
- The user can see whether the next action belongs to automation or requires human review.
- No new domain table or migration is required because readiness is derived state.

### Trade-offs

- If multiple canonical datasets are staged, the Dashboard blocks rather than selecting one automatically.
- Operational commands still require a terminal.
- The page reflects configuration at request time and is not a push-based monitor.
- The default private root is local-project specific; deployments may override it only through server configuration.

## Rejected alternatives

### Persist `acceptance_ready=true`

Rejected because dataset files, environment variables, database revision and human decisions can change independently. A stored boolean would become stale.

### Let the browser pass a dataset path

Rejected because it would expose local filesystem authority and make path traversal/privacy mistakes possible.

### Add a “Run Canary” browser button

Rejected because it would bypass the explicit CLI cost confirmation and operational execution lease contract.

### Treat the newest formal file as active

Rejected because file modification time is not a domain identity and would make Run selection nondeterministic.

## Verification

The decision is enforced by:

- dataset discovery and policy truth-table tests;
- SQLite missing-file and byte-preservation tests;
- API serialization and query-validation tests;
- Backend and Web architecture guards;
- TypeScript type checking and production build;
- FastAPI + production Next + isolated SQLite Smoke proving blockers render with zero Extraction, Trace and Acceptance Run writes.

## Non-goals

This ADR does not:

- stage a real 20-JD dataset;
- migrate the real local database;
- configure OpenAI;
- call a Provider;
- submit Continue/Stop;
- complete a Manual Review Batch;
- approve Requirement quality;
- implement Eligibility or Match.
