# ADR-0027｜Requirement Canary Review Workbench Boundary

- Status: Accepted
- Date: 2026-08-04
- Related: ADR-0024, ADR-0025, ADR-0026

## Context

JobLens already has:

- persistent Requirement Acceptance Runs;
- 20 operational Case records;
- explicit live-call limits;
- an immutable human Canary Continue/Stop command;
- a read endpoint for one known Run ID.

The missing product capability is a usable human review surface. Without it, the reviewer must copy IDs from CLI output and manually navigate separate Job, Extraction and database views. That friction encourages shallow approval and makes failed Canary calls easy to overlook.

The workbench must improve inspection without weakening governance:

- it must not start paid Provider work;
- it must not duplicate Backend gate policy;
- it must not substitute an Agent judgment for a human judgment;
- it must show exact frozen evidence, not mutable latest data.

## Decision

### 1. Add a paginated read-only Run list

Backend exposes:

```http
GET /api/v1/requirement-acceptance-runs
```

The list returns Backend-derived status, attempts, completed/failed/deferred counts, Canary decision and Batch reference.

### 2. Keep Provider execution out of Web

Web contains no command to create or resume an Acceptance Run. Long-running paid work remains CLI-owned until queue, lease, authorization, cancellation and cost-ownership semantics are defined.

The only Web write is:

```http
POST /api/v1/requirement-acceptance-runs/{runId}/canary-review
```

This is a short immutable human decision transaction.

### 3. Freeze the exact normalized JD input

A new Acceptance Run Case stores the stripped, normalized persisted `Job.description` after Import. This is the text used by Requirement Extraction, so it is the correct historical review input.

The snapshot must not be taken directly from raw Collector JSON because the import adapter/normalizer may alter whitespace or structure before persistence.

Run detail also returns the current Job description hash and `descriptionIsCurrent`. Later Job updates are shown as stale context; they never overwrite the frozen Canary snapshot.

The new snapshot column is nullable for backward compatibility. An old Run without a snapshot may fall back to current Job text only when the current SHA-256 still equals the Run hash. Otherwise the UI must state that exact historical JD evidence is unavailable.

### 4. Render exact Extraction evidence

For each attempted Case, Web fetches:

```text
Current Job Detail by jobId (navigation/current-state comparison)
Exact Requirement Extraction by jobId + extractionId
Frozen Run Case descriptionSnapshot (historical model input)
```

It must not use the latest Requirements endpoint or silently substitute current Job text for the historical review artifact.

### 5. Keep Canary evidence identity stable across continuation

Before a human decision exists, current Canary evidence candidates are Cases with `attemptCount > 0`.

After the immutable decision exists, Canary evidence is defined only by the Review’s frozen `reviewedCaseIds`. Later continuation may attempt the remaining 17–19 Cases, but those results must not be relabeled as evidence the human inspected before Continue/Stop.

- failed reviewed Cases remain visible;
- deferred, merely reused, or later post-approval Cases are not presented as original Canary evidence;
- source order is preserved.

### 6. Backend owns decision eligibility

Run detail exposes:

```text
canaryContinueAllowed
canaryStopAllowed
canaryReviewBlockReason
```

React consumes these facts. It does not reimplement provider, attempt, Trace or Extraction policy.

### 7. Expose bounded Trace summary, not a new raw Trace API

Each attempted Case may expose:

- Trace ID;
- capability;
- model;
- prompt version;
- latency;
- input/output tokens;
- error;
- creation time.

The full structured Requirement output is already displayed through the exact Extraction API. A general raw Trace endpoint is outside this slice.

### 8. Isolate Case-level read failures

If one Job or Extraction read fails, the page renders an error for that Case and keeps the remaining evidence visible. The reviewer can still choose Stop based on incomplete or broken evidence.

### 9. Use Server Components for reads and a Client Component for the command

- Run list/detail and evidence retrieval occur server-side.
- The review form is client-side because it manages user input and submits a command.
- The browser sends the command to a same-origin Route Handler.
- The Route Handler only proxies Backend response/status.

### 10. Add a learning forcing function without treating it as audit proof

Before enabling a decision button, the Client asks the learner to confirm they personally inspected:

- full JD;
- Requirements/importance/evidenceSpan;
- Trace metrics/errors.

These checkboxes improve deliberate practice but are not persisted and are not considered proof that the review was correct. The persisted notes and server-frozen evidence IDs remain the audit record.

## Consequences

### Positive

- the Reviewer can inspect a complete Canary evidence bundle in one place;
- frozen persisted-JD input and exact Extraction IDs prevent both JD drift and “latest data” drift;
- failed cases cannot disappear behind success-only filtering, and later calls cannot expand the historical Review evidence set;
- React remains a presentation layer rather than a policy engine;
- Provider credentials and paid commands stay outside the browser;
- decision evidence remains immutable and server-derived.

### Negative

- Run Cases now duplicate up to 20 normalized JD texts as immutable operational evidence;
- detail rendering makes multiple Backend reads per attempted Case;
- no full raw Trace payload is shown;
- no authentication or CSRF protection exists beyond the current local MVP boundary;
- first-page pagination has no interactive next/previous controls yet;
- checkboxes cannot prove genuine human understanding.

## Alternatives rejected

### Put a “Run next 17” button in the workbench

Rejected because queue, concurrency, cancellation, cost ownership and authentication are not defined.

### Display only successful Extractions

Rejected because it creates selection bias and hides precisely the failures Canary exists to catch.

### Fetch latest Requirements or current Job text

Rejected because the page could display evidence different from the Run’s frozen Extraction ID or model-input JD. Current Job text is navigation/current-state context, not a historical substitute.

### Let the Client submit reviewed evidence IDs

Rejected because the browser could omit failed Cases or forge the claimed evidence set.

### Build a general Trace explorer now

Rejected as scope expansion. The workbench needs a bounded operational summary, not an observability product.

## Verification

- Backend repository/API tests cover list, frozen JD snapshot, current-hash stale detection, Trace fields and policy booleans.
- Alembic tests cover nullable snapshot upgrade/downgrade compatibility.
- Web helper tests cover waiting-first ordering and Backend-marked Canary evidence.
- Backend API tests prove post-Continue calls do not expand the frozen reviewed Case set.
- architecture tests prove same-origin command proxy and absence of Provider commands.
- typecheck/build prove route and contract integration.
- existing immutable Review tests remain the authority for duplicate decision rejection.

## Revisit when

- Provider execution moves to a queued Web command;
- multiple reviewers or RBAC are introduced;
- a full Trace explorer becomes necessary;
- pagination/search becomes operationally important;
- production security requires authenticated commands and CSRF protection.
