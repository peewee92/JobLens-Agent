# P0-3B-3B｜Requirement Acceptance Preparation Learning Record

Date: 2026-08-04

## 1. What was built

A resumable application orchestration and CLI now turns one formally accepted Collector Requirement dataset into one exact manual Review Batch:

```text
formal 20-JD dataset
→ validate before persistence
→ atomic Job Import
→ resolve 20 unique Job IDs
→ reuse same-input/same-cohort latest Extractions
→ extract only missing or changed cases
→ keep partial progress and failed Trace evidence
→ create/reuse one exact 20-case Review Batch
```

Command:

```bash
cd services/backend
REQUIREMENT_EXTRACTOR_PROVIDER=openai \
OPENAI_API_KEY=... \
REQUIREMENT_EXTRACTOR_MODEL=... \
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /absolute/path/to/boss-job-filter-requirement-review-v1.4.5-*.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance"
```

Fixture engineering smoke requires explicit opt-in:

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /absolute/path/to/dataset.json \
  --reviewer will \
  --title "fixture orchestration smoke" \
  --allow-fixture
```

A fixture Batch remains practice evidence and can never establish model quality.

## 2. Learner predictions — complete before reading section 3

Write your answers in your own words:

1. Why is source URL insufficient for Extraction reuse?

   Your answer:

2. Which exact fields form the reuse key?

   Your answer:

3. Job 12 fails after Jobs 1–11 succeed. What persists and why?

   Your answer:

4. Why does the workflow continue with Jobs 13–20 but still refuse to create a Batch?

   Your answer:

5. What changes when the JD text changes but the URL stays the same?

   Your answer:

6. Why is a long-running provider workflow implemented as a CLI rather than a browser POST?

   Your answer:

7. Why is `fixture + 20 manually reviewed cases` still not production model evidence?

   Your answer:

8. Which decisions must remain human work?

   Your answer:

---

## 3. Minimal explanations

### 3.1 Application orchestration is not a new business capability

The new use case does not reimplement Import, Extraction, Trace or Review policy. It composes existing stable capabilities and decides their order and failure boundary.

```text
Capability: import one Collector report
Capability: extract one Job
Capability: create one coherent Review Batch
Orchestration: prepare 20 real cases safely
```

This keeps policy in the existing use cases instead of duplicating it in a script.

### 3.2 Reuse means evidence identity, not object identity

The safe reuse key is:

```text
SHA-256(persisted JD description)
provider
model
extractorVersion
promptVersion
latest Extraction for the Job
```

Why every part matters:

- Job ID or URL can stay the same while the JD changes;
- provider/model changes alter model behavior;
- extractorVersion changes deterministic validation or workflow behavior;
- promptVersion changes the instruction contract;
- an old matching Extraction is not reusable when a newer version exists, because new Batches must freeze current evidence.

### 3.3 Formal input is independently rechecked

Preparation does not trust the `ready` label alone. It verifies the 20 selected rows, source version, role evidence, UTF-16 length, FNV hash and pairwise NFKC alphanumeric 5-gram similarity before Import. It also stops if two source rows resolve to the same internal Job ID.

This prevents a modified or internally inconsistent export from entering expensive model work.

### 3.4 Partial progress and atomic Batch are different boundaries

External provider calls should not live inside one giant database transaction.

For each Job:

```text
provider call
→ Trace commit
→ Extraction commit
```

For the Batch:

```text
all 20 successful and current
→ one Batch transaction
```

This means Job 12 can fail without erasing valid paid work for Jobs 1–11. The failed call also keeps a Trace. However, no 19-case Batch is created because formal sample identity must remain exactly 20.

### 3.5 Resume is deterministic, not a blind retry

A rerun first imports the latest source data, then compares each Job with the latest Extraction. Only missing, changed or different-cohort cases call the provider.

Observed failure test:

```text
run 1: 19 Extractions + 20 Traces + 0 Batches
run 2: 19 reused + 1 new Extraction/Trace + 1 Batch
run 3: 20 reused + 0 new Extraction/Trace/Batch
```

A case-specific failure may be followed by later cases so the run gathers maximum useful evidence. A provider-wide unavailable error is different: after one traced failure, remaining cases are marked not attempted and no more calls are made. Missing OpenAI key/model configuration is rejected even earlier, before Import.

### 3.6 Immutable history produces stale evidence intentionally

When one JD changes:

- the old Extraction remains queryable;
- the old Batch and human decisions remain audit history;
- the old Batch becomes stale immediately because its `inputHash` no longer matches the current persisted JD, even before a replacement Extraction succeeds;
- the outdated Extraction disappears from new-Batch candidates;
- a successful new Extraction and new Batch restore current evidence.

Deleting or rewriting the old review would hide what was actually judged.

### 3.7 CLI versus HTTP boundary

A provider run across 20 JDs can take minutes, fail partially and consume cost. A browser request is the wrong lifecycle boundary for the current local MVP.

The CLI owns long-running orchestration. Existing HTTP/UI routes remain short:

- list candidates/batches;
- read Batch detail;
- submit one immutable human judgment.

A future queue may replace the CLI execution mechanism, but it should preserve the same application semantics.

## 4. Common wrong implementation

```python
extraction_ids = []
for job_id in job_ids:
    try:
        extraction_ids.append(extract(job_id).id)
    except Exception:
        pass
create_batch(extraction_ids)
```

Why it fails:

- it swallows failed cases;
- it can create a biased 19-case Batch;
- it repeats every provider call on rerun;
- it has no input/cohort reuse key;
- it hides failed Trace IDs;
- it may catch programming bugs as if they were expected provider failures;
- it creates duplicate Batches every time.

The implemented orchestration catches only expected extraction-domain failures. Unexpected programming or persistence errors fail loudly.

## 5. Evidence map

| Completion claim | Concrete evidence |
|---|---|
| invalid dataset rejected before persistence | blocked and selected-near-duplicate tests; zero Import/Job/Trace rows |
| source identity collision stops model work | one Import audit row; zero Trace/Extraction/Batch rows |
| first run prepares 20 cases | 20 Job rows, 20 Trace rows, 20 Extraction rows, one Batch row |
| exact rerun avoids model work | second-run test; Trace and Extraction counts unchanged |
| provider failure remains auditable | failed case contains Trace ID; Trace count includes failure |
| provider-wide unavailable fails fast | one failed Trace; 19 cases marked not attempted |
| incomplete evidence does not create Batch | failure test; Batch count remains zero |
| resume only fills missing work | 19 reused, one extracted, one Batch |
| duplicate Batch prevented | third run returns same Batch ID; Batch count unchanged |
| changed JD invalidates old evidence | input-hash repository test marks old Batch stale and removes candidate before re-extraction; successful rerun creates one new Extraction |
| fixture cannot claim formal evidence | provider guard + Batch `formalEvidenceEligible=false` |
| Review remains human | no Agent/LLM review-decision code exists in preparation path |

## 6. Diff reading guide

Read files in this order:

1. `docs/decisions/0024-resumable-requirement-acceptance-preparation.md`
2. `app/application/requirement_acceptance/models.py`
3. `app/application/requirement_acceptance/use_case.py`
4. `tests/test_requirement_acceptance_preparation.py`
5. `scripts/prepare_requirement_acceptance.py`

While reading, locate:

- validation before Import;
- SHA-256 and cohort comparison;
- the limited exception tuple;
- per-case result status;
- exact Batch reuse comparison;
- fixture opt-in guard.

## 7. Work the learner must still complete

Do not delegate these to the Agent:

1. Run the live Provider after credentials/model are deliberately selected.
2. Open the 20-case Batch in `/evals/requirements/manual`.
3. Compare each JD with every extracted Requirement and evidence span.
4. Decide accepted or rejected.
5. For rejected cases, select issue codes and write your own notes.
6. Summarize failure patterns and decide whether the model is acceptable.
7. Explain why the result is or is not enough to begin Match.

## 8. Interview questions to retain

1. How do you make a batch LLM workflow resumable without a task queue?
2. Why did you commit each Extraction separately but create the Review Batch atomically?
3. What is the idempotency/reuse key for an LLM Extraction?
4. How do you prevent a partial provider failure from biasing evaluation data?
5. Why do immutable versions create stale evidence instead of updating old reviews?
6. How do you distinguish Trace evidence, deterministic Eval evidence and human acceptance?
7. Why is a fixture provider valuable, and why can it never prove model quality?
8. What would change if this CLI became a distributed queue worker?
9. How do you prevent duplicate human-review batches on rerun?
10. Why should unexpected exceptions not be converted into per-case provider failures?

## 9. Demo content (3–5 minutes)

### Scene 1 — Input contract

Show the accepted Collector dataset:

```text
20 selected
status=ready
no blockers
role-evidence-backed full_jd
```

Explain that Collector readiness proves input quality, not model quality.

### Scene 2 — First preparation run

Run fixture or live CLI and show:

```text
createdJobs
createdExtractions
reusedExtractions
failedExtractions
batchId
```

Open one Job, its Extraction and Trace.

### Scene 3 — Failure and resume

Use the failure-injection test output:

```text
19 persisted
1 failed Trace
0 Batch
```

Then show the resumed result:

```text
19 reused
1 extracted
1 Batch
```

### Scene 4 — Human review boundary

Open the manual Review UI. Explain why the Agent does not click accept/reject or generate the reviewer judgment.

### Scene 5 — Stale evidence

Show the changed-JD test: the old Batch becomes stale and a new current Batch is created without deleting history.

## 10. Verification result

```text
Collector contract/syntax/tests = passed
Backend pytest = 284 passed
Requirement acceptance/review targeted tests = 22 passed
Web tests = 38 passed
TypeScript typecheck = passed
Next.js production build = passed
Python compileall = passed
Alembic check = no new upgrade operations detected
```

The exact uploaded v1.4.5 Review dataset was independently replayed in the attachment runtime:

```text
jobs = 20
UTF-16 lengths = all consistent
FNV-1a hashes = all consistent
excludedNearDuplicates = 3
maximum similarity among selected Jobs = 0.0453 (< 0.82)
```

## 11. Unverified items

- no credential-backed OpenAI 20-job run was executed in this implementation session;
- no live latency, cost, rate-limit or retry policy was measured;
- no real 20-case human decision set has been completed;
- no model has been approved for Match;
- no background queue, cancellation or distributed locking was implemented;
- reviewer identity remains local free text;
- the uploaded `/mnt/data` attachment is available to the analysis runtime but not mounted into the DevSpace host process, so the host CLI smoke used generated integration fixtures rather than the attachment path itself.
