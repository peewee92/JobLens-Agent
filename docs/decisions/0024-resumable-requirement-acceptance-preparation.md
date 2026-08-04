# ADR-0024｜Resumable Requirement Acceptance Preparation

- Status: Accepted
- Date: 2026-08-04
- Scope: Real Requirement Extraction acceptance preparation

## Context

JobLens already has independent capabilities for:

- importing Collector Jobs;
- extracting immutable JobRequirements with Trace evidence;
- creating version-frozen manual Review Batches;
- reviewing each case in the Web UI.

The missing boundary was orchestration. Preparing 20 real cases manually would require copying Job IDs, triggering 20 provider calls, checking cohort consistency and then selecting the exact Extractions for a Batch.

A naive loop creates two serious failure modes:

1. one provider timeout after several successful calls causes a rerun to repeat paid work;
2. swallowed failures or mixed versions create a biased/incoherent Review Batch.

## Decision

### 1. Formal input is one Collector manual-review dataset

Preparation accepts only a dataset that deterministically proves:

```text
purpose = requirement_manual_quality_review
qualityGate.status = ready
requiredSampleSize = 20
selectedCount = 20
distinctEligibleCount >= 20
blockers = []
```

Every selected Job must be a noise-free, role-evidence-backed `full_jd`, have a matching source version, and have self-consistent UTF-16 length and FNV-1a content hash. Preparation also recomputes pairwise NFKC alphanumeric 5-gram Jaccard similarity so a tampered file cannot claim 20 independent samples while containing a selected near-duplicate.

Validation runs before opening the Job Import transaction.

### 2. Import is one atomic boundary

The exact selected 20 Jobs are imported through the existing idempotent Job Import use case.

Preparation stops if:

- any selected Job is skipped;
- import items do not preserve dataset order;
- an item lacks a persisted Job ID;
- two selected rows collapse to one internal Job ID.

### 3. Extraction progress commits per Job

Each Job Requirement Extraction and Trace remains its own transaction.

If a case-specific provider failure occurs on Job 12:

- Extractions 1–11 remain persisted;
- the failed provider attempt remains visible as a Trace;
- Jobs 13–20 may continue;
- no Review Batch is created;
- a later run can reuse the 19 successful cases and retry only the missing case.

A provider-wide `unavailable` error is different: it records the first failed Trace, marks the remaining Jobs as not attempted, and stops further calls. The CLI also rejects missing OpenAI key/model configuration before Import.

This is deliberate partial progress, not an accidental half-written Batch.

### 4. Reuse requires full evidence identity

A latest Extraction is reusable and eligible for a new Review Batch only when all fields match:

```text
persisted JD SHA-256
provider
model
extractorVersion
promptVersion
```

URL, Job ID or title alone are insufficient because the JD or model configuration may have changed. Manual-review candidate and Batch `isCurrent` calculations compare the Extraction input hash with the current persisted JD, so importing changed text immediately makes old evidence stale even if replacement extraction later fails.

### 5. Review Batch creation is all-or-nothing

A Batch is created only after exactly 20 successful, latest, same-cohort Extractions are available.

The existing Batch use case remains authoritative for stale and cohort checks.

### 6. Exact existing Batches are reused

Before creating a Batch, preparation searches existing batches with the same:

- title and reviewer;
- provider/model/extractor/prompt cohort;
- ordered extraction IDs.

An exact match is returned instead of creating duplicate evidence.

### 7. Provider execution stays out of browser requests

This long-running workflow is exposed as a local CLI/application orchestration, not a synchronous browser-triggered endpoint.

The existing Web UI only reads prepared candidates/batches and records human judgments through short same-origin commands.

### 8. Fixture requires explicit opt-in

The CLI refuses fixture execution unless `--allow-fixture` is present. A fixture Batch is always practice evidence because existing Review policy sets `formalEvidenceEligible=false` for provider `fixture`.

## Consequences

### Positive

- real acceptance preparation becomes one repeatable command;
- failed cases cannot be silently omitted;
- reruns avoid unnecessary provider calls and cost;
- every case keeps Job, Extraction and Trace provenance;
- exact duplicate Batches are prevented;
- browser requests remain short and predictable;
- human judgment remains separate from Agent orchestration.

### Costs

- orchestration spans several existing application capabilities;
- successful partial work remains in the database after a failed run;
- local synchronous CLI has no queue, cancellation or distributed lease;
- an operator still must inspect failures and manually judge all 20 cases.

## Rejected alternatives

### One database transaction for import, all provider calls and Batch creation

Rejected because external model calls are slow and failure-prone. Rolling back successful Trace/Extraction evidence would waste cost and prevent resume.

### Always call the model on rerun

Rejected because immutable history does not imply duplicate work is desirable. Same-input same-cohort latest evidence is safe to reuse.

### Create a 19-case Batch after one failure

Rejected because it silently changes the formal sample and biases quality evidence.

### Reuse by Job ID or source URL

Rejected because neither proves that the JD content and extraction configuration are unchanged.

### Add Celery/Redis now

Rejected as premature. The local MVP needs deterministic orchestration and evidence first; queue infrastructure can be added when runtime constraints are observed.

## Verification

- malformed/non-ready/selected-near-duplicate datasets create zero JobImport rows;
- two selected source rows that resolve to one internal Job stop before any Extraction;
- missing OpenAI configuration stops before Import; runtime provider unavailability fails fast after one traced attempt;
- first fixture run creates 20 Jobs, 20 Traces, 20 Extractions and one practice Batch;
- identical second run creates a new Import audit row but zero new Trace/Extraction/Batch rows;
- injected provider failure yields 20 Traces, 19 Extractions and zero Batches;
- resumed run reuses 19 and creates exactly one new Trace/Extraction and one Batch;
- changed JD immediately removes the old Extraction from candidates and marks the old Batch stale by input hash, before replacement extraction;
- successful changed-JD rerun creates one new Extraction and a current Batch;
- CLI fixture provider requires explicit opt-in;
- full Backend/Web/Collector regression, typecheck, build and Alembic drift check.

## Explicitly not proven

- credential-backed OpenAI completion of all 20 Jobs;
- live latency, cost, rate-limit and retry policy;
- model quality or release approval;
- representative sampling across the whole market;
- authenticated reviewer identity;
- distributed execution safety;
- readiness to start Match.
