# JobLens Web

Browser product loop for Job Data, confirmed career context, grounded Profile proposals, Profile Eval governance and Requirement Eval governance.

## Current routes

```text
/profile                    Generate/review Profile proposal, then confirm Profile/Evidence and SearchIntent
/evals/profile                  View Profile Eval history and accepted baseline
/evals/profile/{evalRunId}      Inspect Profile cases/Trace IDs and submit immutable Review
/evals/requirements             View Requirement Eval history and accepted baseline
/evals/requirements/{evalRunId} Inspect Requirement cases/Trace IDs and submit immutable Review
/import                     Upload Collector report JSON
/imports/{importId}         View import audit detail
/jobs                       Filtered and paginated Job Pool
/jobs/{jobId}               Job detail + latest JobRequirements + explicit re-extraction
```

The browser submits Profile/SearchIntent commands and imports to same-origin Next Route Handlers:

```text
Browser
→ POST /api/profile-proposals or /api/profile-proposals/file
→ review/apply in local form state
→ PUT /api/profile | PUT /api/search-intent | POST /api/job-imports
→ POST /api/profile-evals/{id}/review
→ POST /api/requirement-evals/{id}/review
→ POST /api/jobs/{id}/requirement-extractions
→ FastAPI Workflow / Application Use Cases
```

Server-rendered pages call FastAPI using the server-only `JOBLENS_BACKEND_URL` environment variable. The Backend URL is never exposed as a `NEXT_PUBLIC_*` value.

## Install

From the repository root:

```bash
pnpm --dir apps/web install --lockfile=false
```

Dependencies use exact versions in `package.json`. The repository currently does not commit a JS lockfile.

## Run locally

Terminal 1:

```bash
cd services/backend
uv run alembic upgrade head
uv run fastapi dev
```

Terminal 2:

```bash
cd apps/web
cp .env.example .env.local
pnpm dev
```

Open:

```text
http://127.0.0.1:3000/profile
http://127.0.0.1:3000/evals/profile
http://127.0.0.1:3000/evals/requirements
http://127.0.0.1:3000/import
http://127.0.0.1:3000/jobs
```

## Verification

```bash
cd apps/web
pnpm test
pnpm typecheck
pnpm build
pnpm smoke:e2e
pnpm smoke:eval-review
pnpm smoke:requirement-review
```

`smoke:e2e` creates a temporary SQLite database, migrates it, starts real FastAPI and production Next processes, then verifies:

```text
DOCX upload → extracted text → Profile Proposal
→ explicit Profile + Evidence v1 confirmation
→ SearchIntent v1
→ stale-version 409
→ same-origin import proxy
→ filtered Job Pool
→ Job detail
→ two immutable Requirement Extraction versions
→ latest evidence-grounded Requirements
→ Import audit detail
```

`smoke:eval-review` seeds deterministic test-only Profile Fixture/failed-live/eligible-live runs, then verifies history rendering, failed-case Trace display, Fixture 422, reject 201, accept 201, duplicate 409 and accepted baseline refresh.

`smoke:requirement-review` runs the equivalent Requirement governance path and additionally shows missing Requirement and wrong-importance evidence through real FastAPI and production Next processes.

All smoke scripts clean up processes and temporary data after completion.

## Boundary rules

- Client Components are limited to genuine browser interaction: resume/Collector file input, proposal review, Profile/SearchIntent editing, Eval Review commands and explicit Requirement extraction.
- Job Pool filters live in URL search params.
- Server Components fetch list/detail/audit/Eval governance/latest Requirement data.
- Public Web types do not include `sourceRaw`, `candidateRaw`, `canonicalKey`, `profileKey`, or `intentKey`.
- Profile Proposal never auto-calls the confirmed Profile API; the user must adopt, review and save explicitly.
- Profile Skills reference Evidence through request-local keys; the Backend returns opaque Evidence IDs.
- The Web does not run Requirement providers or reimplement idempotency, transaction, grounding or Eval acceptance policy; Backend responses remain authoritative.

## Out of scope

- OCR, image resumes, encrypted PDF passwords and legacy DOC;
- live-provider Profile or Requirement quality claims without credential-backed Eval runs and human review;
- Match / Ranking / Agent Chat;
- authentication;
- favorites and ignore state;
- candidate raw browser;
- design-system or client-cache libraries.
