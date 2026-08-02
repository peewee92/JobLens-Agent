# Job Import Candidate Persistence Contract

## 1. Goal

Persist every entry from a Collector report's `candidates` array as immutable evidence of one import batch.

```text
Collector report.candidates
→ JobImportCandidate rows
→ future diagnostics / re-filtering / audit summary
```

Candidates are not Job Pool entities. A candidate may have been rejected by Collector rules, may still require detail enrichment, or may duplicate another candidate.

## 2. Ownership

```text
JobImport 1 ───── N JobImportCandidate
```

A candidate belongs to exactly one import batch. It does not own or mutate `Job`, `JobSource`, or `JobImportItem`.

Deleting a `JobImport` cascades to its candidates.

## 3. Persistence shape

Table: `job_import_candidates`

| Field | Meaning |
| --- | --- |
| `id` | JobLens opaque candidate row ID |
| `import_id` | FK to the owning `JobImport` |
| `candidate_index` | Original zero-based position in `report.candidates` |
| `keep` | Collector decision when it is a boolean; otherwise null |
| `decision` | Collector decision/reason when it is a string |
| `pending_detail` | Whether detail collection was pending when boolean |
| `source_job_id` | External source ID when explicitly present |
| `source_url` | Original source URL when present |
| `title` | Diagnostic title projection when present |
| `company` | Diagnostic company projection when present |
| `candidate_raw` | Complete original JSON value, including unknown fields |
| `created_at` | Persistence timestamp |

`(import_id, candidate_index)` is unique.

## 4. Import semantics

- Every candidate is persisted, including malformed JSON values such as strings or null.
- Structured columns are best-effort projections. Failure to project a field does not discard the raw candidate.
- Candidate writes share the same Unit of Work as Job, JobSource, JobImport and JobImportItem.
- A fatal import failure rolls back all candidate rows from that batch.
- Re-importing the same report creates a new candidate snapshot under the new JobImport; candidates are audit history, not globally deduplicated entities.

## 5. Public audit API

`GET /api/v1/job-imports/{importId}` exposes only a summary:

```json
{
  "candidateSummary": {
    "total": 3,
    "kept": 1,
    "rejected": 1,
    "unknown": 1
  }
}
```

It does not expose `candidateRaw` or a candidate list by default.

Definitions:

- `kept`: `keep == true`
- `rejected`: `keep == false`
- `unknown`: `keep` is null or not a boolean in the original candidate

## 6. Non-goals

This slice does not add:

- a public raw-candidate endpoint;
- candidate pagination;
- candidate-to-Job reconciliation;
- candidate re-filtering logic;
- compression or object storage;
- Web UI.
