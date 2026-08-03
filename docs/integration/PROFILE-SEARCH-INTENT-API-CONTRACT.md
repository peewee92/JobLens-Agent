# Profile + SearchIntent API Contract

## Scope

Phase 2A establishes a manually confirmed career fact base before any LLM extraction is added.

This slice implements:

```text
manual Profile + Evidence confirmation
→ immutable Profile version
→ manual SearchIntent confirmation
→ immutable SearchIntent version
→ Web read/edit loop
```

It does not implement resume parsing, PDF upload, LLM extraction, Profile Eval, Match, Ranking, authentication, or multiple users.

## Local-user assumption

The MVP is local and single-user. The server stores one logical profile stream and one logical SearchIntent stream under internal keys. Public APIs expose only the current version.

## Profile API

### GET `/api/v1/profile`

Returns the current confirmed Profile version.

```json
{
  "id": "prof_...",
  "version": 2,
  "headline": "Frontend Engineer moving into AI application engineering",
  "yearsOfExperience": 8,
  "skills": [
    {
      "id": "skill_...",
      "name": "React",
      "level": "strong",
      "evidenceIds": ["ev_..."]
    }
  ],
  "evidence": [
    {
      "id": "ev_...",
      "key": "spinach-desktop",
      "type": "work",
      "summary": "Built Electron desktop collaboration and Agent features.",
      "source": "confirmed by user"
    }
  ],
  "createdAt": "2026-08-03T00:00:00Z"
}
```

No current Profile returns `404 profile_not_found`.

### PUT `/api/v1/profile`

Creates a new immutable Profile version.

Request uses request-local Evidence keys because server IDs do not exist before persistence:

```json
{
  "expectedVersion": 1,
  "headline": "Frontend Engineer moving into AI application engineering",
  "yearsOfExperience": 8,
  "evidence": [
    {
      "key": "spinach-desktop",
      "type": "work",
      "summary": "Built Electron desktop collaboration and Agent features.",
      "source": "confirmed by user"
    }
  ],
  "skills": [
    {
      "name": "React",
      "level": "strong",
      "evidenceKeys": ["spinach-desktop"]
    }
  ]
}
```

Rules:

- first save uses `expectedVersion = 0`;
- update uses the current version;
- stale expected version returns `409 context_version_conflict`;
- Evidence keys are unique within one request;
- skill names are unique case-insensitively;
- every skill has at least one Evidence key;
- every referenced key exists in the same request/version;
- failed validation or version conflict creates no rows;
- successful save returns the new public Profile response.

## SearchIntent API

### GET `/api/v1/search-intent`

Returns the current confirmed SearchIntent.

No current SearchIntent returns `404 search_intent_not_found`.

### PUT `/api/v1/search-intent`

```json
{
  "expectedVersion": 0,
  "targetRoles": ["AI Application Engineer", "Agent Engineer"],
  "cities": ["武汉"],
  "remoteAccepted": true,
  "minimumSalaryK": 20,
  "seniority": "senior",
  "employmentTypes": ["full_time"],
  "excludeKeywords": ["博彩"],
  "hardConstraints": ["不接受长期驻场"],
  "softPreferences": ["AI 产品有真实用户"]
}
```

Rules:

- targetRoles contains at least one non-empty value;
- list values are trimmed and de-duplicated while preserving order;
- minimumSalaryK is null or non-negative;
- hardConstraints are future Eligibility inputs;
- softPreferences are future Ranking inputs and must not be treated as hard rejection rules;
- successful save creates a new immutable version.

## Public boundary

Public Profile/SearchIntent APIs do not expose:

- database stream keys;
- ORM relationship state;
- resume raw text;
- LLM prompts or model output;
- unconfirmed extracted facts;
- internal transaction/session details.

## Why Profile preferences are removed

The older `user-profile.schema.json` embedded a `preferences` object. The domain model and PRD now define SearchIntent as an independent versioned entity. This slice removes the duplicate preferences field to prevent two competing sources of truth.

## Error mapping

```text
not found                         → 404
stale expectedVersion             → 409
cross-field evidence violation    → 422
request shape violation           → 422
unexpected server error           → 500
```
