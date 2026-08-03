# ADR-0015 · Versioned Profile Evidence and SearchIntent

- **Status:** Accepted
- **Date:** 2026-08-03
- **Related:** ADR-0004, ADR-0005, Phase 2 Profile + SearchIntent

## Context

JobLens now has a real Job Pool and browser loop, but recommendations cannot be evidence-based until the system has two independent facts:

1. what the user has actually done;
2. what the user currently wants to find.

The existing domain model requires every skill assertion to reference Evidence. The older `user-profile.schema.json` also embedded a preferences object, while the PRD and domain model define SearchIntent as a separate entity. Keeping both would create competing sources of truth.

Adding LLM resume extraction in the same slice would mix two risks:

- correctness of Profile/Evidence persistence and confirmation;
- correctness and hallucination rate of model extraction.

## Decision

### 1. Phase 2 is split

This slice implements manual confirmation and versioned persistence first:

```text
Profile + Evidence + Skill links
SearchIntent
API + Web confirmation
```

Resume parsing, LLM structured extraction and Profile Eval are deferred to the next slice.

### 2. Profile and SearchIntent are separate immutable version streams

A save creates a new row with `version = current + 1`; it never updates the previous row.

Requests carry `expectedVersion`:

```text
expectedVersion == current → create next version
expectedVersion != current → 409 conflict
```

This prevents stale browser tabs from silently overwriting newer confirmed context.

### 3. Evidence is relational, not an optional text decoration

A Profile version contains:

```text
UserProfile
├── ProfileEvidence
├── ProfileSkill
└── ProfileSkillEvidence links
```

Application invariants:

- Evidence keys are unique in one request/version;
- Skill names are unique case-insensitively;
- every Skill references at least one Evidence key;
- every referenced key exists in the same submitted Profile version.

The HTTP request uses request-local `evidenceKeys`; the server creates opaque Evidence IDs and returns `evidenceIds`.

### 4. SearchIntent is the only preference source of truth

The duplicate `preferences` object is removed from the public UserProfile Contract. SearchIntent independently stores:

- target roles;
- cities and remote acceptance;
- salary and seniority;
- employment types and exclusions;
- hard constraints for future Eligibility;
- soft preferences for future Ranking.

### 5. Local MVP is single-user

The database uses internal stream keys (`default`) but public APIs expose only current Profile/SearchIntent resources. Authentication and multi-user ownership are deferred.

### 6. Agent/Workflow boundary

Future Match or Agent code must consume a confirmed Profile version and Evidence IDs through Application Use Cases. Raw resume text or unconfirmed LLM extraction must not be treated as career facts.

## Consequences

### Positive

- old recommendations can later reference exact Profile/SearchIntent versions;
- every Skill has a traceable Evidence path;
- stale writes are visible rather than silently lost;
- SearchIntent has one authoritative representation;
- manual confirmation gives a safe target for the next LLM extraction Eval.

### Cost / limits

- each Profile version duplicates Evidence and Skill rows;
- the MVP has no authentication or user ownership column;
- direct SQL could theoretically create a cross-version Skill/Evidence link, although Application and Repository never do so;
- concurrent saves can still race between version check and unique insert; database uniqueness prevents duplicate version numbers, but automatic retry is not implemented;
- no Profile diff/history API is exposed yet.

## Verification

Completion must be demonstrated by:

- Alembic 0003 upgrade and stepwise downgrade;
- relational Skill→Evidence rows;
- invalid Evidence references creating zero rows;
- immutable v1/v2 history in SQLite;
- stale expectedVersion returning 409 with no new version;
- API 404/422/409 contracts;
- Web save and refresh behavior;
- real FastAPI + Next smoke E2E;
- architecture tests preventing Application/Router framework leakage.
