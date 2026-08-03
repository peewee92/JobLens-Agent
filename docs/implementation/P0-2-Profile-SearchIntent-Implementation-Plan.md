# P0-2 Profile + SearchIntent Implementation Plan

## Goal

Build the first confirmed user-context foundation for evidence-based matching:

```text
manual Profile confirmation
→ Evidence-linked Skills
→ versioned Profile
→ versioned SearchIntent
→ Web edit/read loop
```

Phase 2A established confirmed facts. Phase 2B now supports grounded proposals from pasted text and bounded PDF/DOCX documents, while preserving explicit human confirmation.

## Current status · 2026-08-03

| Slice | Content | Status |
| --- | --- | --- |
| 1 | Public Contract and invariants | Completed |
| 2 | ORM + Alembic 0003 | Completed |
| 3 | Command/Query Ports + UoW | Completed |
| 4 | Application validation/versioning | Completed |
| 5 | GET/PUT Profile + SearchIntent API | Completed |
| 6 | Web `/profile` confirmation loop | Completed |
| 7 | Backend/Web integration verification | Completed |
| 8 | Resume text → Profile Proposal + Eval + Trace | Completed |
| 9 | PDF/DOCX text ingestion + Web upload | Completed |
| 10 | Eval Run persistence, Gate v1 and baseline comparison | Completed |
| 11 | Credential-backed live-provider quality run and review | Next |

## Frozen scope

### Included

- local single-user current Profile;
- Evidence types: work/project/education/achievement/self_report;
- Skill levels: strong/working/basic/unknown;
- relational Skill→Evidence links;
- immutable Profile versions;
- immutable SearchIntent versions;
- optimistic `expectedVersion` conflict detection;
- API and Web confirmation;
- hardConstraints vs softPreferences separation.

### Excluded

- authentication and multiple users;
- OCR, image resumes and encrypted PDF passwords;
- automatic confirmed writes from extractor output;
- production model hard-coding;
- Match/Ranking/Agent;
- Profile history/diff API;
- deletion or rollback to a previous version.

## Engineering completion standards

| Standard | Evidence |
| --- | --- |
| Skill must reference Evidence | Application + API 422 tests |
| Unknown Evidence reference writes nothing | SQLite row-count tests |
| New saves create immutable versions | v1/v2 DB assertions |
| Stale browser state cannot overwrite | 409 + unchanged row count |
| Profile aggregate is atomic | forced-exception rollback test |
| SearchIntent normalizes list input | use-case/API response assertions |
| Public Profile has no duplicate preferences | JSON Schema + API negative assertion |
| Router/Application preserve boundaries | AST architecture tests |
| Web saves via same-origin proxy | Web architecture test |
| Full browser loop is runnable | production Next + FastAPI smoke E2E |

## Learning completion standards

The learner can explain and sketch:

1. why Profile and SearchIntent are separate aggregates;
2. why a Skill without Evidence is not a confirmed fact;
3. why request-local Evidence keys differ from persisted Evidence IDs;
4. why immutable versions are useful for future Match reproducibility;
5. what `expectedVersion` prevents and what concurrency race it does not fully solve;
6. why cross-field validation belongs in Application;
7. why the Agent must consume confirmed versions instead of raw resume/model output.

## Portfolio completion standards

Demo sequence:

```text
open empty /profile
→ add two Evidence records
→ link React and Agent skills
→ save Profile v1
→ save SearchIntent v1
→ refresh and show persistence
→ create Profile v2
→ demonstrate stale v0/v1 request returns 409
→ show DB retains previous version
→ run backend/web/smoke tests
```

Resume statement:

> Implemented a versioned, evidence-backed career context for JobLens: relational Skill→Evidence traceability, immutable Profile/SearchIntent versions, optimistic conflict handling, FastAPI contracts and a Next.js confirmation UI; verified through rollback, stale-write, API boundary and real dual-process E2E tests.

## User-value hypothesis

Before this slice, JobLens knew only jobs. After this slice, a user can explicitly confirm:

- what they have actually done;
- which Evidence supports each claimed capability;
- what roles and constraints they want.

This gives future matching a trustworthy input instead of a chat-memory guess.

## Slice 8 result · Profile Extraction Proposal

```text
resume text
→ configured Profile Extractor
→ strict structured output
→ deterministic evidenceSpan/reference gates
→ trace_spans
→ 10-case Profile Eval
→ Web review/apply
→ explicit existing Profile confirmation
```

The repository includes disabled, fixture and OpenAI adapters. Fixture is limited to deterministic CI/demo. The OpenAI network path is implemented and request-contract tested, but a live-provider Eval was not run because no API credential was supplied.

## Slice 9 result · Resume Document Input

```text
PDF / DOCX upload
→ byte/type/structure limits
→ deterministic text extraction
→ existing grounded Proposal Workflow
→ Trace
→ Web review/apply
→ explicit Profile confirmation
```

The original document is request-scoped and never persisted. Text-only PDF and DOCX are supported; scanned PDFs return a stable OCR-not-supported error. Parser, API, privacy and architecture tests plus a real production Next + FastAPI DOCX smoke flow are included.

## Slice 10 result · Eval Governance

```text
Profile Eval dataset
→ full Proposal Workflow per case
→ one Trace per provider attempt
→ immutable ProfileEvalRun + Case Results
→ profile-eval-gate-v1
→ optional baseline metric deltas
→ read-only history/detail API
```

Fixture runs can pass the engineering Gate but always keep `releaseEligible=false`. The environment did not provide a live API credential, so no live quality conclusion was created.

## Slice 11 result · Human Review and Accepted Baseline

```text
live Eval Run
→ immutable accept/reject Review
→ reviewer + notes + reviewedAt
→ latest accepted Review selects official baseline
→ live CLI can resolve baseline before Provider execution
```

Technical Gate results and human governance decisions are stored separately. Fixture runs cannot receive formal Reviews. A live Run can be accepted only when it is gate-passed and release-eligible; rejected Runs remain auditable. One Run can have only one immutable Review.

## Slice 12 result · Eval Review Web

```text
Profile Eval history + accepted baseline
→ failed Case Results shown first
→ Trace IDs and metric deltas
→ same-origin accept/reject Review command
→ Server Component refresh from Backend facts
```

The Web guides actions but does not implement final policy. Fixture review is rejected, failed live Runs can be rejected, eligible live Runs can be accepted, and immutable duplicate Reviews return 409. A real FastAPI + production Next smoke verifies history → cases → reject/accept → baseline.

## Next slice

```text
configure credential-backed live Provider/model
→ run Profile Eval against accepted baseline when available
→ review every failed Case and Trace in the Web
→ accept or reject the live Run
→ decide whether Profile Extraction quality is sufficient for Phase 3
```

Do not proceed to Requirement Intelligence until a real provider run is reviewed and Profile proposal quality is acceptable.
