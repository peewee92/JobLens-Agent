# JobLens Agent Integration Note

This directory contains JobLens Collector v1.6.0, derived from the standalone `岗位筛选` Chrome extension.

## Boundary

`apps/collector-extension` only collects, normalizes and exports source evidence. It does not perform career matching, recommendation, ranking or application automation.

## Bulk import

The popup now supports **同步到 JobLens** for the latest full report. It POSTs the same report payload directly to the local Backend endpoint:

```text
POST http://127.0.0.1:8000/api/v1/job-imports
```

The Backend remains the source of truth for import identity and deduplication: repeated syncs create a new import audit batch but existing jobs are updated/skipped instead of duplicated. On success the popup stores only the returned immutable `importId` and exposes **查看本次导入**, which opens the existing JobLens Web audit page at `http://127.0.0.1:3000/imports/{importId}`. Reopening the popup restores the most recent successful import link; a later failed sync does not erase that link. If the local Backend is unavailable or rejects the payload, the extension keeps the existing **完整报告** JSON download as the offline fallback:

```text
boss-job-filter-report-v1.6.0-*.json
```

The backend still accepts older supported Collector reports. Since v1.5.0, the collector preserves jobs whose recruiter activity cannot be read and marks them as `recruiterActivityStatus: unknown`. Only jobs whose activity is confirmed to be outside the requested window are filtered.

## Current job quick save

See the [Collector contract](../../docs/integration/COLLECTOR-CONTRACT.md) for the single-job report, the separate loopback targets, and the source evidence this path preserves.

## Requirement quality review

For Requirement Extraction acceptance, use:

```text
boss-job-filter-requirement-review-v1.6.0-*.json
```

The dataset contains only jobs where:

- the detail page was read successfully;
- a trusted JD selector produced the description, or a broad container was reduced to a bounded JD segment;
- `descriptionNoiseCount` is `0`;
- `descriptionHasRoleEvidenceSignal` is `true`, backed by an explicit duty/requirement section or sufficient responsibility and qualification evidence;
- company introduction, business marketing, team history and honor lists alone are not accepted;
- `descriptionQuality` is `full_jd`;
- `requirementReviewEligible` is `true`;
- recruiter profile fragments are absent;
- the description has a stable content hash and source URL.

`qualityGate.status` is `ready` only when 20 distinct eligible JD samples were selected. `eligibleCount` counts eligible postings; `distinctEligibleCount` removes near-duplicate JD bodies. Excluded duplicates are listed in `excludedNearDuplicates`. A dataset with fewer than 20 distinct jobs is diagnostic only and must not be presented as formal Requirement quality evidence.

In `matched` detail mode, v1.5.0 reserves the Requirement-review quota for already-accepted jobs first, then serves the recruiter-activity queue and other pending candidates, so a large unknown-activity queue cannot starve accepted jobs of JD enrichment. Remote-scope jobs whose card area names a concrete city are excluded as `卡片地点为线下城市（全国远程未命中）` before any detail budget is spent. Allocation is traceable through `detailTargetsPlannedRecruiterActivityCandidates`, `detailTargetsPlannedAccepted`, `detailTargetsPlannedRemoteCandidates` and `detailTargetsDeferredAccepted`; kept jobs with unreadable activity are counted by `recruiterActivityUnknown` / `recruiterActivityUnverifiedKept`.

## Runtime guard

For Collector v1.4.x through v1.6.x, the backend checks persisted quality evidence before invoking the Requirement Extractor. Ineligible or missing quality evidence returns `job_description_not_extractable` before a model call or Trace run is created.

API sync is intentionally local-only in this first P1 slice (`127.0.0.1` / `localhost`). It does not carry API keys, does not invoke Requirement extraction, and does not replace offline JSON export.
