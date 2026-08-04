# ADR 0035: Requirement Review Batch Final Quality Decision

Status: Accepted

Date: 2026-08-05

## Context

JobLens already freezes exact Requirement Extraction versions into a Manual Review Batch and records one immutable accepted/rejected judgment per Case.

The existing read model derives `formalEvidenceEligible` when a Batch has:

- exactly 20 Cases;
- all 20 Cases reviewed;
- no stale Extraction or changed JD input;
- a non-Fixture Provider cohort.

That condition proves that formal human evidence is structurally complete. It does not prove that the model quality is acceptable for Match. A Batch with 20 rejected Cases can still satisfy the evidence-completeness condition.

The project has not approved an automatic acceptance-rate or issue-count threshold for promoting a Requirement model. Hard-coding a percentage would manufacture a quality policy that has not been calibrated on real Provider evidence.

## Decision

### 1. Separate evidence completeness from quality approval

The read model exposes three different facts:

```text
formalEvidenceEligible
finalDecision
matchReleaseEligible
```

Their meanings are:

- `formalEvidenceEligible`: the current Batch is valid formal evidence;
- `finalDecision`: one immutable human conclusion exists for the Batch;
- `matchReleaseEligible`: the current Batch is still formal evidence and its immutable conclusion is `accept_for_match`.

`formalEvidenceEligible=true` never automatically sets `matchReleaseEligible=true`.

### 2. Use one immutable Batch-level decision

A formal Batch may receive exactly one decision:

```text
accept_for_match
reject_for_match
```

The decision is stored in a separate table with a unique constraint on `batch_id`. Application pre-checks improve the error message; the database constraint is the final concurrency guard.

Only the Batch owner may submit the decision. The command requires at least 20 characters of human notes.

### 3. Freeze the reviewed evidence snapshot

The final decision stores:

- sample, reviewed, accepted, rejected and stale counts;
- structured issue-code distribution;
- reviewer, notes and decision timestamp;
- a SHA-256 evidence fingerprint.

The fingerprint canonicalizes:

- Provider, Model, Extractor and Prompt cohort;
- ordered Batch Case IDs;
- Job, Extraction and Trace IDs;
- JD text hash;
- current-version state at decision time;
- Case Review IDs, decisions and issue codes;
- Review notes hash and timestamp.

The Batch remains the source of full human-readable evidence. The fingerprint proves which exact evidence graph the decision referenced without duplicating raw JD or Review notes into another record.

### 4. Recompute release eligibility on every read

`matchReleaseEligible` is not persisted. It is derived from current facts:

```text
formalEvidenceEligible
AND finalDecision == accept_for_match
```

If a newer Extraction appears or the Job description changes:

- the historical Final Decision remains immutable;
- the Batch becomes stale;
- `matchReleaseEligible` becomes false;
- the accepted-baseline query no longer returns that Batch.

This resolves the race between a human decision and later Extraction work without pretending the entire quality system is globally locked. A decision can remain historically true while no longer authorizing current Match work.

### 5. Expose Command and Query separately

Command:

```http
POST /api/v1/requirement-review-batches/{batchId}/final-decision
```

Query:

```http
GET /api/v1/requirement-review-batches/accepted-baseline
```

The accepted-baseline query returns only a current human-accepted Batch. It returns 404 when no such baseline exists.

The Web Client submits the command only through a same-origin Route Handler. The page consumes Backend facts and does not calculate a release threshold.

## Rejected alternatives

### Treat `formalEvidenceEligible` as approval

Rejected because evidence completeness is not model quality.

### Automatically accept above a percentage threshold

Rejected because no production threshold has been approved or calibrated.

### Store a mutable `approved` flag on the Batch

Rejected because it loses decision provenance, encourages silent overwrite and cannot preserve historical approval after staleness.

### Delete acceptance when evidence becomes stale

Rejected because deleting governance history would hide what was approved and when.

### Lock all Extraction work while the human decides

Rejected for this local MVP. Dynamic stale invalidation gives the required safety property without a cross-workflow distributed lock.

## Consequences

Positive:

- Match cannot consume evidence merely because 20 Reviews are complete;
- human governance is explicit and auditable;
- no unapproved numeric threshold is invented;
- stale evidence automatically loses release eligibility;
- historical decisions remain inspectable;
- later Match work has one stable accepted-baseline query.

Trade-offs:

- reviewer identity remains free text in the local single-user MVP;
- an accepted Batch can become stale immediately after decision;
- a later accepted baseline may supersede an earlier one;
- the fingerprint detects identity but no signing key or external audit log exists;
- the decision does not prove the 20-job sample is statistically representative.

## Verification

Required evidence:

1. incomplete, Fixture or stale Batch returns 422 and writes no decision;
2. one Batch has one decision under both Application and DB race protection;
3. all-rejected formal evidence does not release Match without human acceptance;
4. accepted decision creates a current accepted baseline;
5. later JD or Extraction change revokes release eligibility while retaining history;
6. API/OpenAPI expose stable 201/404/409/422 behavior;
7. Web uses same-origin command proxy and contains no hidden acceptance threshold;
8. production FastAPI + Next smoke proves accept → baseline → stale → revoked lifecycle.
