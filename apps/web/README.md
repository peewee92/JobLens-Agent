# JobLens Web

Browser product loop for P0-1 Job Data Foundation, confirmed career context and Phase 2B Profile Extraction proposals from text, PDF and DOCX.

## Current routes

```text
/profile             Generate/review Profile proposal, then confirm Profile/Evidence and SearchIntent
/import              Upload Collector report JSON
/imports/{importId}  View import audit detail
/jobs                Filtered and paginated Job Pool
/jobs/{jobId}        Public Job detail
```

The browser submits Profile/SearchIntent commands and imports to same-origin Next Route Handlers:

```text
Browser
→ POST /api/profile-proposals or /api/profile-proposals/file
→ review/apply in local form state
→ PUT /api/profile | PUT /api/search-intent | POST /api/job-imports
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
→ Import audit detail
```

The script cleans up processes and temporary data after completion.

## Boundary rules

- Client Components are limited to genuine browser interaction: resume/Collector file input, proposal review and Profile/SearchIntent editing.
- Job Pool filters live in URL search params.
- Server Components fetch list/detail/audit data.
- Public Web types do not include `sourceRaw`, `candidateRaw`, `canonicalKey`, `profileKey`, or `intentKey`.
- Profile Proposal never auto-calls the confirmed Profile API; the user must adopt, review and save explicitly.
- Profile Skills reference Evidence through request-local keys; the Backend returns opaque Evidence IDs.
- The Web does not reimplement idempotency, transaction, or audit decisions.

## Out of scope

- OCR, image resumes, encrypted PDF passwords and legacy DOC;
- live-provider Profile quality claims without a credential-backed Eval run;
- Match / Ranking / Agent Chat;
- authentication;
- favorites and ignore state;
- candidate raw browser;
- design-system or client-cache libraries.
