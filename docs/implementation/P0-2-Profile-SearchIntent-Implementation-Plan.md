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

This is Phase 2A. Phase 2B will add resume text/PDF ingestion, LLM structured extraction and Profile Eval against this confirmed Contract.

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
| 8 | Resume input + LLM extraction + Profile Eval | Next |

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
- resume PDF upload or parsing;
- LLM extraction;
- model/provider selection;
- Profile Eval dataset;
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

## Next slice

```text
resume text input
→ Profile Extraction structured output
→ proposed facts separated from confirmed facts
→ user confirmation/edit
→ Profile Eval dataset and assertions
→ save confirmed Profile version
```

The first LLM pipeline must not ship without Eval and evidence-span checks.
