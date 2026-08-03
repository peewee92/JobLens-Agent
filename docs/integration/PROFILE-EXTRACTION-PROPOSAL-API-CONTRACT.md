# Profile Extraction Proposal API Contract

## Goal

Convert resume text into a **reviewable proposal**, never directly into a confirmed `UserProfile`.

```text
resume text
→ Profile Extractor
→ deterministic evidence validation
→ trace
→ proposal response
→ user review/edit
→ existing PUT /api/v1/profile
```

## Endpoint

```http
POST /api/v1/profile-proposals
Content-Type: application/json
```

Request:

```json
{
  "resumeText": "8 年前端经验……"
}
```

Rules:

- `resumeText` is required;
- leading/trailing whitespace is removed;
- minimum 50 characters;
- maximum 30,000 characters;
- the full resume text is sent only to the configured extractor;
- JobLens does not persist the full resume text in Trace; Trace stores only an input hash and character count.

## Success · 200

```json
{
  "runId": "run_...",
  "extractorVersion": "profile-extractor-v1",
  "model": "configured-model",
  "promptVersion": "profile-proposal-v1",
  "headline": "8 年前端工程师，具备 AI 应用项目经验",
  "yearsOfExperience": 8,
  "evidence": [
    {
      "key": "spinach-desktop",
      "type": "work",
      "summary": "负责 Electron 桌面端办公 Agent 产品开发",
      "source": "resume",
      "evidenceSpan": "负责 Electron 桌面端办公 Agent 产品开发"
    }
  ],
  "skills": [
    {
      "name": "React",
      "level": "strong",
      "evidenceKeys": ["spinach-desktop"]
    }
  ],
  "warnings": [
    "薪资偏好未从简历中推断，请在 SearchIntent 中单独确认。"
  ]
}
```

## Proposal invariants

A proposal is accepted only when all conditions hold:

1. headline is non-empty;
2. years of experience is null or non-negative;
3. evidence keys are non-empty and unique;
4. every `evidenceSpan` is a non-empty, exact contiguous substring of `resumeText`;
5. skill names are non-empty and unique case-insensitively;
6. every skill references at least one evidence key;
7. every referenced evidence key exists in the same proposal;
8. only public Profile fields are proposed; SearchIntent is not inferred from resume text.

A structurally valid model response can still fail these deterministic business gates.

## Confirmation boundary

This endpoint never writes:

- `user_profiles`;
- `profile_evidence`;
- `profile_skills`;
- `profile_skill_evidence`;
- `search_intents`.

The user must review/edit the proposal and explicitly call the existing:

```http
PUT /api/v1/profile
```

## Trace boundary

Every attempt writes one `trace_spans` row containing:

```text
runId
capability = profile_extraction
version = profile-extractor-v1
model
promptVersion
inputRefs.resumeSha256
inputRefs.characterCount
output proposal or null
latencyMs
inputTokens / outputTokens when available
error or null
createdAt
```

The full resume text is not persisted in Trace.

External provider requests must disable provider-side response storage when supported.

## Errors

```text
invalid/too short/too long resume text → 422 invalid_resume_text
extractor disabled or missing credentials → 503 profile_extractor_unavailable
provider/network failure → 502 profile_extractor_failed
provider output breaks proposal invariants → 502 invalid_profile_extractor_output
unexpected server error → 500 internal_server_error
```

A failed extraction still writes an error Trace whenever the database is available.

## Scope exclusions

This slice does not implement:

- PDF or DOCX parsing;
- automatic confirmed Profile writes;
- SearchIntent inference;
- resume file storage;
- OCR;
- profile history/diff UI;
- Match, Ranking or Agent orchestration;
- multi-user authentication;
- production model-quality claims without a live-provider Eval run.
