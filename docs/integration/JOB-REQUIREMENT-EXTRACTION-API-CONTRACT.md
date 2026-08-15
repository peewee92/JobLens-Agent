# Job Requirement Extraction API Contract

Status: Phase 3A frozen slice

## Goal

Convert one persisted Job description into an immutable, evidence-grounded JobRequirement Extraction Run. The result becomes the only JD fact source for later Eligibility / Match / Gap / Prepare workflows.

## Endpoints

### Create a new extraction

```http
POST /api/v1/jobs/{jobId}/requirement-extractions
```

The request body is empty. Backend reads the persisted Job description, invokes the configured Requirement Extractor, validates every evidence span, writes a Trace, then persists one immutable Extraction Run and its Requirements.

Successful response:

```http
201 Created
```

Body follows `packages/contracts/schemas/job-requirement-extraction.schema.json`.

### Read the latest extraction

```http
GET /api/v1/jobs/{jobId}/requirements
```

Returns the latest successfully persisted Extraction Run for the Job.

### Read a historical extraction

```http
GET /api/v1/jobs/{jobId}/requirement-extractions/{extractionId}
```

Returns one immutable historical Extraction Run. `extractionId` must belong to `jobId`.

## Stable errors

| HTTP | code | Meaning |
|---|---|---|
| 404 | `job_not_found` | Job does not exist |
| 404 | `job_requirement_extraction_not_found` | No latest extraction, or historical extraction not found for the Job |
| 422 | `job_description_not_extractable` | Job description missing/outside boundaries, or Collector v1.4.x marked it `card_only / partial_jd / unavailable` |
| 502 | `requirement_extractor_failed` | Provider invocation or response parsing failed |
| 502 | `invalid_requirement_extractor_output` | Structured output violated deterministic grounding/business rules |
| 503 | `requirement_extractor_unavailable` | Provider is disabled/not configured, or a transient upstream outage returned 429/503/504 |

## Deterministic validation

A provider result is rejected unless:

- at least one Requirement exists;
- each `originalText` and `evidenceSpan` is non-blank;
- Collector v1.4.x inputs must have `descriptionQuality=full_jd` and `requirementReviewEligible=true` before any model call or Trace is created;
- each `evidenceSpan` occurs as one contiguous substring of the persisted Job description;
- `originalText` also occurs in the description;
- confidence is in `[0, 1]`;
- skill requirements include a non-blank `normalizedCapability`;
- duplicate `(type, normalizedCapability, evidenceSpan)` entries are rejected;
- all public enum values match the frozen Contract.

Structured Output guarantees shape only. It does not replace these checks.

## Versioning and persistence

Every successful extraction creates a new immutable Run, even when the Job and input hash are unchanged. This preserves model/prompt/extractor history. A Run records:

- Job ID;
- SHA-256 of the description;
- provider and model;
- extractor and prompt versions;
- Trace run ID;
- Requirement count;
- creation time.

Old Runs remain queryable. `GET /jobs/{jobId}/requirements` selects the latest Run by `createdAt DESC, extractionId ASC`.

## Trace and privacy

Trace capability: `requirement_extraction`.

Trace input refs contain:

```json
{
  "jobId": "job_xxx",
  "descriptionSha256": "...",
  "characterCount": 1234
}
```

Trace does not duplicate the full JD. Trace output may contain the structured Requirement proposal and therefore remains sensitive product data.

For deterministic quote recovery, Trace output also records audit-only grounding metadata:

```json
{
  "groundingPolicyVersion": "grounding-v1",
  "groundingRepairs": [
    {
      "requirementIndex": 0,
      "field": "originalText",
      "strategy": "punctuation_width"
    }
  ]
}
```

`grounding-v1` is deliberately narrow. Exact JD substrings remain preferred. Recovery may only ignore Unicode whitespace and normalize the width of ASCII punctuation, and only when the normalized quote maps to exactly one location in the JD. The value written to Trace and persistence is always the corresponding raw JD slice. Ambiguous matches, case changes, number/word rewrites, fuzzy matching and semantic rewrites remain invalid. `groundingRepairs` is diagnostic metadata only and does not relax the final verbatim validation gate.

## Scope exclusions

This slice does not implement:

- Eligibility;
- Profile-to-Requirement Match;
- batch Ranking;
- Requirement human review/acceptance;
- OCR or job-page fetching;
- Agent orchestration;
- live model quality approval without credentials.
