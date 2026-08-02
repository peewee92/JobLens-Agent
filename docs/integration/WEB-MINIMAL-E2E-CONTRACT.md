# Minimal Web E2E Contract

## Goal

Provide the first browser-usable JobLens loop without adding Profile, Match, Agent Chat, authentication, or design-system scope.

```text
Upload Collector JSON
→ See import result and audit link
→ Browse Job Pool
→ Filter using URL search params
→ Open Job detail and original source
```

## Routes

| Route | Responsibility |
| --- | --- |
| `/import` | Select one Collector report JSON file and submit it |
| `/imports/{importId}` | Render public import audit detail |
| `/jobs` | Render filtered, sorted, paginated Job Pool |
| `/jobs/{jobId}` | Render one public Job detail |
| `/api/job-imports` | Same-origin write proxy to FastAPI `POST /api/v1/job-imports` |

`/` redirects to `/jobs`.

## Architecture boundary

```text
Browser Client Component
→ Next Route Handler (write proxy)
→ FastAPI Import Use Case

Next Server Component
→ typed Backend API client
→ FastAPI Query Use Case
```

The browser must not know the internal FastAPI base URL. Next pages and route handlers read `JOBLENS_BACKEND_URL` on the server.

## Import state machine

```text
idle
→ reading
→ submitting
→ success | error
```

The client validates only that the file is valid JSON and the root value is an object. Collector item validation remains in the Backend Adapter so one malformed job does not reject all valid jobs.

## Job Pool URL state

Supported query parameters mirror the Backend contract:

```text
q
city
minSalaryK
remoteStatus
source
sort
limit
offset
```

Filters are submitted as URL search params so refresh, browser history, copied links, and reproducible demos preserve the same query.

## Public data boundary

The Web UI consumes only public API fields. It must not reference or render:

```text
sourceRaw
candidateRaw
canonicalKey
normalizedSourceUrl
errors.raw
```

## Error behavior

- Network/backend unavailable: render a clear retryable service error.
- Import 409/422: show the Backend public error message without stack traces.
- Job or Import detail 404: render the Next not-found page.
- Invalid local JSON: do not send a request.

## Scope exclusions

This slice does not add:

- login or user accounts;
- Profile or SearchIntent editing;
- Match/Ranking/LLM/Agent Chat;
- favorites or ignore state;
- candidate raw browser;
- file drag-and-drop library;
- component framework or Tailwind;
- client cache library;
- CORS changes in FastAPI.

## Completion evidence

- Next production build succeeds.
- TypeScript typecheck succeeds.
- Pure query/format tests succeed.
- Real FastAPI + real Next processes complete import → audit → list → detail.
- Rendered HTML and proxy JSON are asserted.
- Backend tests remain green.
