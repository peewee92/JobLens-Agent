# Confirmed Career Context Release Gate

Status: Phase 2 → Phase 4 read-only contract

## 1. Purpose

Expose whether the latest explicitly confirmed `UserProfile` and `SearchIntent`
can be consumed by a future Match workflow.

This contract is not a Profile Proposal endpoint, Profile Eval result, Match
operation or Provider command.

## 2. Endpoint

```http
GET /api/v1/career-context/release-readiness
```

Existing-but-blocked context returns `200` with structured blockers. The query
itself has no request body and accepts no version override, model, local file
path or execution parameter.

## 3. Response

```json
{
  "releaseEligible": false,
  "confirmationBoundary": "explicit_versioned_user_confirmation",
  "profileId": null,
  "profileVersion": null,
  "profileCreatedAt": null,
  "profileEvidenceCount": 0,
  "profileSkillCount": 0,
  "searchIntentId": null,
  "searchIntentVersion": null,
  "searchIntentCreatedAt": null,
  "searchIntentTargetRoleCount": 0,
  "blockers": [
    {
      "code": "profile_missing",
      "message": "Confirm a UserProfile version before Match consumes career facts."
    },
    {
      "code": "search_intent_missing",
      "message": "Confirm a SearchIntent version before Match evaluates job fit."
    }
  ],
  "dbWrites": 0,
  "providerCalls": 0,
  "traceRunsCreated": 0
}
```

When released:

```json
{
  "releaseEligible": true,
  "confirmationBoundary": "explicit_versioned_user_confirmation",
  "profileId": "prof_...",
  "profileVersion": 3,
  "profileEvidenceCount": 6,
  "profileSkillCount": 9,
  "searchIntentId": "intent_...",
  "searchIntentVersion": 2,
  "searchIntentTargetRoleCount": 2,
  "blockers": [],
  "dbWrites": 0,
  "providerCalls": 0,
  "traceRunsCreated": 0
}
```

## 4. Blocker codes

### Profile

| Code | Meaning |
|---|---|
| `profile_missing` | No confirmed Profile version exists |
| `profile_headline_missing` | Confirmed headline is blank |
| `profile_years_invalid` | Years of experience is negative |
| `profile_evidence_missing` | No Evidence exists |
| `profile_evidence_invalid` | Evidence key, summary or source is blank |
| `profile_evidence_keys_duplicated` | Evidence keys collide after case-folding |
| `profile_skills_missing` | No confirmed Skill exists |
| `profile_skill_names_duplicated` | Skill names collide after normalization |
| `profile_skill_evidence_missing` | A Skill has no Evidence link |
| `profile_skill_evidence_reference_invalid` | A Skill points outside the current Profile Evidence set |

### SearchIntent

| Code | Meaning |
|---|---|
| `search_intent_missing` | No confirmed SearchIntent version exists |
| `search_intent_target_roles_missing` | No non-blank target role exists |
| `search_intent_target_roles_duplicated` | Roles collide after trim/case-fold normalization |
| `search_intent_minimum_salary_invalid` | Minimum salary is negative |

Multiple independent blockers are returned together. Consumers must not use the
first blocker as a substitute for the full diagnostic set.

## 5. Trust semantics

### Confirmed versions

A successful `PUT /api/v1/profile` or `PUT /api/v1/search-intent` creates a new
immutable version after optimistic `expectedVersion` checking and validation.
The release Gate selects the current Profile ID and SearchIntent ID in one SQL statement, then loads those exact immutable versions. This produces one reproducible version pair even if another confirmation is saved immediately afterward.

### Profile Proposal and Eval

```text
Resume/Text/PDF/DOCX
→ Profile Proposal + Trace
→ user review/edit
→ explicit PUT /profile
→ confirmed UserProfile version
```

Profile Eval baseline applies to the Proposal workflow. It is intentionally not
part of this Gate, because manually confirmed Profile facts may exist without an
LLM proposal.

### Future Match

Before calculating any Eligibility or semantic fit, Match must require:

```text
CareerContext.releaseEligible == true
AND JobRequirement.releaseEligible == true
```

It must then persist at least:

```text
profileId
profileVersion
searchIntentId
searchIntentVersion
jobRequirementExtractionId
```

A future confirmed version changes readiness identity but does not mutate an old
MatchReport.

## 6. Web behavior

`/profile` displays:

- release/not-released status;
- Profile and SearchIntent IDs/versions;
- Evidence, Skill and target-role counts;
- all blockers;
- explicit zero-side-effect counters.

The page does not perform the policy itself. Profile/SearchIntent editing remains
usable when the release query fails.

## 7. Privacy and non-goals

The response does not expose:

- resume text or Evidence summaries;
- Profile internal key or SearchIntent internal key;
- API keys;
- Profile Eval notes;
- raw Trace output;
- LLM command previews.

This slice does not implement:

- user authentication or confirmation identity proof;
- Profile truth verification beyond explicit confirmation and structural
  integrity;
- Eligibility;
- Evidence Retrieval;
- semantic Match;
- recommendation or score;
- Match persistence.

## 8. Verification matrix

| Scenario | Expected evidence |
|---|---|
| no Profile/Intent | `200`, two missing blockers |
| Profile only | `search_intent_missing` |
| complete confirmed versions | `releaseEligible=true`, IDs/versions returned |
| deleted Skill→Evidence links | `profile_skill_evidence_missing` |
| duplicate/corrupt read model | deterministic blocker |
| repeated readiness query | Profile/Intent/Trace counts unchanged |
| Web render before confirmation | both missing blockers visible |
| Web render after confirmation | released status and versions visible |
| production Smoke | FastAPI + Next + migrated temporary SQLite |
