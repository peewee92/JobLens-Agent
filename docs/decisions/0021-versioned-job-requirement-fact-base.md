# ADR-0021｜Versioned JobRequirement Fact Base

- Status: Accepted
- Date: 2026-08-03

## Context

Eligibility, Match, Skill Gap, Resume and Interview preparation all need a stable interpretation of Job descriptions. Re-reading raw JD text independently in every Workflow would create inconsistent requirements, repeated model cost and conclusions that cannot be reproduced.

Requirement Extraction is also an LLM boundary. Strict JSON output guarantees shape, but cannot prove that a Requirement appears in the JD or that mandatory/bonus wording was interpreted correctly.

## Decision

### 1. JobRequirement is the shared derived fact base

Later capabilities must consume persisted `JobRequirement` IDs and `evidenceSpan` values. They must not silently re-interpret raw Job descriptions.

### 2. Every extraction creates an immutable Run

```text
Job
→ JobRequirementExtraction
→ N JobRequirement
```

A Run records Job ID, description hash/length, provider/model, extractor/prompt version, Trace ID and creation time. Re-extraction creates a new Run even when the input hash is unchanged. Old Runs remain queryable.

### 3. Structured Output is followed by deterministic grounding

Provider output is rejected unless:

- `originalText` and `evidenceSpan` occur verbatim in the persisted JD;
- skill Requirements include a normalized capability;
- confidence and enum values are valid;
- duplicate requirements are absent;
- at least one Requirement exists.

### 4. Trace and derived facts have separate transactions

Provider attempts write their Trace before the Extraction Run transaction. If Run persistence fails, the Trace remains for diagnosis while the Run and Requirements roll back atomically. We avoid holding a database transaction open across external model calls.

### 5. Requirement Eval starts with the first pipeline

A versioned 10-case anonymized dataset measures case pass rate, Workflow success, capability recall, importance accuracy and forbidden capability rate. Fixture results validate the pipeline only. Live model approval is separate future evidence.

### 6. Public Web shows latest facts and provenance

Job detail displays the latest Run, Requirement IDs, evidence spans, confidence and Trace ID. A user may trigger a new version explicitly. The browser does not call the Provider directly.

## Consequences

### Positive

- Match/Gap/Prepare can share one reproducible fact source;
- old recommendations can record the exact Requirement extraction version;
- hallucinated spans are blocked before persistence;
- model/prompt changes can be compared without overwriting history;
- failures remain traceable.

### Costs

- storage grows with every extraction;
- latest selection needs deterministic ordering;
- model quality still requires live Eval and human review;
- Job updates can make an older Run stale, so later Workflows must record extraction ID/input hash.

## Rejected alternatives

### Return free-form requirements without persistence

Rejected because later Workflows would have no stable IDs, provenance or reproducibility.

### Overwrite requirements on re-extraction

Rejected because old Match results could no longer be explained.

### Store requirements directly on Job as JSON

Rejected because version history, individual Requirement IDs, indexes and database integrity would be weak.

### Let Match re-read raw JD

Rejected because it creates competing fact interpretations and violates the project architecture boundary.

## Not decided here

- Requirement human acceptance/review;
- live model quality approval;
- stale-run invalidation policy when Job text changes;
- Eligibility, Match, Ranking or Agent orchestration;
- batch extraction scheduling and cost controls.
