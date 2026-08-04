# JobLens Agent Integration Note

This directory contains JobLens Collector v1.4.3, derived from the standalone `岗位筛选` Chrome extension.

## Boundary

`apps/collector-extension` only collects, normalizes and exports source evidence. It does not perform career matching, recommendation, ranking or application automation.

## Normal import

Upload the full report to:

```text
POST /api/v1/job-imports
boss-job-filter-report-v1.4.3-*.json
```

The backend remains compatible with Collector v1.3.1 through v1.4.3. Collector v1.4.3 preserves the v1.4.2 quality gate and adds accepted-job detail overfetch plus allocation diagnostics, while keeping the raw source payload in `JobSource.source_raw`.

## Requirement quality review

For Requirement Extraction acceptance, use:

```text
boss-job-filter-requirement-review-v1.4.3-*.json
```

The dataset contains only jobs where:

- the detail page was read successfully;
- a trusted JD selector produced the description, or a broad container was reduced to a bounded JD segment;
- `descriptionNoiseCount` is `0`;
- `descriptionQuality` is `full_jd`;
- `requirementReviewEligible` is `true`;
- recruiter profile fragments are absent;
- the description has a stable content hash and source URL.

`qualityGate.status` is `ready` only when 20 distinct eligible JD samples were selected. `eligibleCount` counts eligible postings; `distinctEligibleCount` removes near-duplicate JD bodies. Excluded duplicates are listed in `excludedNearDuplicates`. A dataset with fewer than 20 distinct jobs is diagnostic only and must not be presented as formal Requirement quality evidence.

In `matched` detail mode, v1.4.3 plans up to 30 accepted-job detail reads before remote candidates when `detailLimit=40`. Allocation is traceable through `detailTargetsPlannedAccepted`, `detailTargetsPlannedRemoteCandidates` and `detailTargetsDeferredAccepted`.

## Runtime guard

When a Collector v1.4.x job is imported from the full report, the backend checks the persisted quality evidence before invoking the Requirement Extractor. `card_only`, `partial_jd` and `unavailable` inputs return `job_description_not_extractable` before a model call or Trace run is created.

Future P1 integration may add optional API sync while preserving offline JSON export.
