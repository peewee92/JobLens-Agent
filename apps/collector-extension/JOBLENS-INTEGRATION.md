# JobLens Agent Integration Note

This directory contains JobLens Collector v1.4.0, derived from the standalone `岗位筛选` Chrome extension.

## Boundary

`apps/collector-extension` only collects, normalizes and exports source evidence. It does not perform career matching, recommendation, ranking or application automation.

## Normal import

Upload the full report to:

```text
POST /api/v1/job-imports
boss-job-filter-report-v1.4.0-*.json
```

The backend remains compatible with Collector v1.3.1. Collector v1.4.0 adds JD quality evidence to every job while preserving the raw source payload in `JobSource.source_raw`.

## Requirement quality review

For Requirement Extraction acceptance, use:

```text
boss-job-filter-requirement-review-v1.4.0-*.json
```

The dataset contains only jobs where:

- the detail page was read successfully;
- a trusted JD selector produced the description;
- `descriptionQuality` is `full_jd`;
- `requirementReviewEligible` is `true`;
- the description has a stable content hash and source URL.

`qualityGate.status` is `ready` only when exactly 20 eligible jobs were selected. A dataset with fewer than 20 jobs is still useful for diagnostics, but it is `blocked` and must not be presented as formal Requirement quality evidence.

## Runtime guard

When a Collector v1.4.0 job is imported from the full report, the backend checks the persisted quality evidence before invoking the Requirement Extractor. `card_only`, `partial_jd` and `unavailable` inputs return `job_description_not_extractable` before a model call or Trace run is created.

Future P1 integration may add optional API sync while preserving offline JSON export.
