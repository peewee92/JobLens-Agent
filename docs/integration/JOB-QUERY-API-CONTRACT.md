# Job Query API Contract

- **Status:** Frozen for P0-1 MVP
- **Date:** 2026-08-02
- **Endpoints:** `GET /api/v1/jobs`, `GET /api/v1/jobs/{jobId}`

## 1. User value

After importing Collector data, users can view a stable Job Pool, narrow it by practical constraints, and open one normalized job without exposing internal identity or raw-source fields.

## 2. List endpoint

```http
GET /api/v1/jobs?q=AI&city=武汉&minSalaryK=20&remoteStatus=unknown&source=boss&sort=latest&limit=20&offset=0
```

### Query semantics

| Parameter | Semantics |
| --- | --- |
| `q` | Case-insensitive literal substring in title, company, or description |
| `city` | Case-insensitive literal substring in `area` |
| `minSalaryK` | Keep jobs whose `salaryMaxK >= minSalaryK`; unknown maximum salary is excluded |
| `remoteStatus` | Exact `confirmed / rejected / unknown` match |
| `source` | Exact source match; returned primary source must match this filter |
| `sort` | `latest` (default), `salaryDesc`, `salaryAsc` |
| `limit` | Default 20, range 1–100 |
| `offset` | Default 0, minimum 0 |

### Stable ordering

- `latest`: primary source `lastSeenAt DESC`, then `job.id ASC`;
- `salaryDesc`: null salary last, `salaryMaxK DESC`, `salaryMinK DESC`, then `job.id ASC`;
- `salaryAsc`: null salary last, `salaryMinK ASC`, `salaryMaxK ASC`, then `job.id ASC`.

### Primary source

A Job may have multiple JobSource rows. The public item selects exactly one primary source:

```text
latest last_seen_at
→ source_id ASC as deterministic tie-breaker
```

When `source` is supplied, primary-source selection is restricted to that source.

### Response

```json
{
  "total": 1,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "id": "job_...",
      "title": "AI 应用开发工程师",
      "company": "示例公司",
      "area": "武汉",
      "salaryMinK": 15,
      "salaryMaxK": 30,
      "remoteStatus": "unknown",
      "remoteConfidence": "low",
      "source": "boss",
      "sourceUrl": "https://www.zhipin.com/job_detail/example.html",
      "sourceVersion": "1.3.1",
      "collectedAt": "2026-07-21T00:00:00Z"
    }
  ]
}
```

## 3. Detail endpoint

```http
GET /api/v1/jobs/job_xxx
```

The detail response adds `experience`, `education`, `description`, `skills`, `descriptionQuality`, `requirementReviewEligible`, and `requirementReviewIneligibilityReasons` to the list item fields. Raw Collector payload remains private.

Missing jobs return:

```http
HTTP 404
```

```json
{
  "error": {
    "code": "job_not_found",
    "message": "Job not found: job_xxx"
  }
}
```

## 4. Public-field boundary

Neither list nor detail may expose:

```text
canonicalKey
canonicalKeyVersion
sourceRaw
normalizedSourceUrl
```

## 5. Scope exclusions

This contract does not add import-batch queries, favorites, ignored state, full-text search, Agent tools, authentication, caching, or cursor pagination.
