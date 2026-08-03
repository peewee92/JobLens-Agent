# Profile Eval Review Web Contract

## Goal

Expose the existing Profile Eval governance facts as a minimal browser workflow without moving review policy into the Web layer.

```text
GET Eval history / accepted baseline
→ inspect Run metrics and Case Results
→ inspect failure reasons and Trace IDs
→ POST one accept/reject Review through same-origin proxy
→ refresh from Backend facts
```

## Routes

```text
GET /evals/profile
GET /evals/profile/{evalRunId}
POST /api/profile-evals/{evalRunId}/review
```

## History page

The page displays:

- current human-accepted live baseline, if one exists;
- immutable Eval Run history;
- mode (`fixture` / `live`);
- Gate result;
- case pass count;
- skill recall;
- forbidden fact rate;
- release eligibility.

The page must not describe `gatePassed` or `releaseEligible` as human approval.

## Detail page

The page displays:

- Run/provider/model/prompt/gate versions;
- all quality metrics;
- baseline metric deltas;
- failed Cases before successful Cases;
- stable failure reasons/codes;
- expected, actual and missing skills;
- Trace run ID;
- immutable Review, when present.

The Web does not fetch or display resume text, resume hashes, Trace output, API keys or raw files.

## Review actions

Client guidance:

| Run state | Accept | Reject |
| --- | --- | --- |
| Fixture | hidden/disabled | hidden/disabled |
| Live, Gate failed | disabled | enabled |
| Live, release eligible | enabled | enabled |
| Already reviewed | disabled | disabled |

These controls are guidance only. The Backend remains the source of truth and may return:

- `201` review created;
- `404` run not found;
- `409` immutable Review already exists;
- `422` governance rule violation.

After `201`, the Client refreshes Server Components and reads Review/baseline facts again.

## Same-origin command proxy

```text
Browser
→ POST /api/profile-evals/{id}/review
→ Next Route Handler
→ POST /api/v1/profile-evals/{id}/review
→ ReviewProfileEvalRunUseCase
```

The browser never receives `JOBLENS_BACKEND_URL`.

## Completion evidence

- pure state-mapping tests;
- architecture tests for same-origin command routing;
- TypeScript and production Next build;
- real FastAPI + production Next smoke;
- fixture review rejected with 422;
- failed live review rejected with 201;
- eligible live review accepted with 201;
- duplicate review rejected with 409;
- accepted baseline visible after refresh.

## Out of scope

- running a live Provider from the browser;
- Trace detail API/page;
- authenticated reviewer identity;
- multi-person approval;
- Review revocation;
- automatic deployment;
- generic Eval dashboard;
- Requirement/Match Eval.
