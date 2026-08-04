# P0-3B-3E｜Requirement Canary Review Web Workbench

Status: implemented and verified on 2026-08-04

## 1. Current real project feature

Provide one Web workbench where the learner/reviewer can inspect the exact evidence behind a controlled Requirement Extraction Canary Run and submit one immutable `continue` or `stop` decision.

```text
CLI creates a persistent Run and attempts 1–3 live Canary calls
→ Web lists recent Runs
→ reviewer opens one exact Run
→ before decision, Web loads the currently attempted Canary candidates
→ after decision, Web loads only the Case IDs frozen in that immutable Review
→ each Case displays current full JD + frozen Extraction + Requirement evidence + Trace summary
→ reviewer confirms personal inspection
→ reviewer writes their own notes
→ Web submits one immutable continue/stop command
→ Backend remains the authority for eligibility and evidence snapshot
```

This slice does not start Provider work. Provider execution remains CLI-owned.

## 2. Learning goal

Master the minimum Web/backend mechanisms needed for a trustworthy human-in-the-loop approval surface:

- Server Component read model versus Client Component command boundary;
- Backend-owned policy flags instead of duplicating gate rules in React;
- exact-version evidence retrieval rather than “latest” data;
- same-origin command proxy;
- partial read failure handling;
- immutable review command and frozen evidence references;
- why a UI checklist helps learning but is not itself proof of review quality;
- why an approval UI must not be confused with Provider execution or model acceptance.

## 3. Risk assessment

### Business risk: high

A broken workbench could:

- show the latest Extraction instead of the reviewed Extraction ID;
- show a different JD than the Run description hash represents;
- hide a failed Canary and show only successful Cases;
- recompute `continueAllowed` in React and drift from Backend policy;
- expose a button that directly starts paid Provider work;
- let the client choose reviewed Case/Trace IDs;
- make `continue` look like final model approval;
- lose the whole page when one Case evidence read fails.

### Learning risk: high

The learner may skip the core skill by:

- asking the Agent to recommend Continue/Stop;
- reading only normalized capabilities instead of the full JD;
- ignoring failed calls because they have no Requirements;
- treating checkbox clicks as proof of understanding;
- accepting all Cases without explaining evidence and trade-offs.

## 4. Core mechanisms reserved for the learner

The learner must personally:

1. predict the page’s data and command boundaries before reading the implementation;
2. inspect every displayed Canary JD, Requirement, importance and evidenceSpan;
3. inspect Trace model, prompt, latency, token counts and errors;
4. write at least 20 characters of their own decision rationale;
5. decide Continue or Stop without Agent-generated judgment;
6. explain why Continue is not a model-quality acceptance result;
7. demonstrate the page and explain one failed/read-error path.

## 5. Peripheral work completed by the development Agent

- paginated Run list read API;
- Trace summary fields in the Run Case read model;
- Backend policy flags for Continue/Stop eligibility;
- Web contracts and server-side data access;
- list/detail pages;
- same-origin Canary Review proxy;
- review form and evidence checklist;
- per-Case read-error containment;
- tests, documentation, Diff review and regression execution.

## 6. Facts, inference, assumptions and unknowns

### Confirmed facts

- persistent Acceptance Runs and 20 Case records already exist;
- each attempted Case records attempt count, Trace ID and optional Extraction ID;
- Backend already accepts one immutable Continue/Stop decision;
- exact Requirement Extraction versions can be read by Job ID + Extraction ID;
- Job detail API exposes the current persisted JD, but a current JD is not necessarily the text used by an older Canary Extraction;
- before this slice, Acceptance Run Cases stored only a JD hash and could not render the exact historical model input after a Job update;
- no public Trace read endpoint exists;
- Provider execution remains a CLI capability;
- no live OpenAI Run is available in the current environment.

### Inference

- a practical human gate needs a navigable Run list, not only a known Run ID;
- the workbench should show Trace metadata but avoid introducing a separate raw Trace API in this slice;
- exact Extraction retrieval is mandatory because “latest” may change after review;
- each new Run Case must freeze the normalized persisted `Job.description` actually used as model input, not merely the raw Collector description;
- current Job hash comparison should warn about later JD changes without replacing the frozen snapshot;
- server-side per-Case reads are acceptable because Canary size is at most three attempted Cases;
- policy booleans belong in Backend responses.

### Assumptions

- local single-user MVP;
- at most 20 recent Runs are needed on the first list page;
- before Review, Canary evidence candidates are the one to three attempted Cases;
- after Review, Canary evidence is the immutable `reviewedCaseIds` snapshot even if later calls run;
- the Reviewer identity stored on the Run remains the command identity;
- Trace metadata is sufficient for this review surface because the structured Requirements are already displayed separately.

### Unknowns

- usability with real model outputs and real latency/token values;
- whether reviewers need the full raw Trace output later;
- authentication, CSRF and RBAC requirements;
- pagination/search needs after many Runs;
- accessibility quality under keyboard and screen-reader use;
- whether a future queue will expose start/resume commands in Web.

## 7. User value hypothesis

A reviewer should be able to open one page and make a defensible Canary decision without copying Run IDs between CLI output, Job pages, Requirement pages and database tooling.

Observable value:

- waiting Runs are visible and prioritized;
- before decision, only actually attempted Cases appear; after decision, only frozen reviewed Case IDs remain Canary evidence;
- exact JD, Extraction, Requirements and Trace summary appear together;
- failed calls remain visible;
- one Case read failure does not hide other evidence;
- decision is submitted once through the existing Backend gate;
- no paid model call can be triggered from the page.

## 8. Completion standards

### 8.1 Engineering completion

| Standard | Required evidence |
|---|---|
| recent Runs can be listed | `GET /requirement-acceptance-runs`; repository/API test |
| list status is Backend-derived | API summary fields; Web source test |
| Canary evidence does not expand after Continue | API derives frozen Review Case IDs; post-resume test |
| exact Extraction version is displayed | server fetch by Job ID + Extraction ID |
| exact Canary-time JD is displayed | Run Case frozen snapshot created from normalized persisted Job.description |
| later JD changes are visible without rewriting history | Run/current SHA-256 fields + stale UI + persistence test |
| Trace summary is visible | Run Case API fields for model/prompt/latency/tokens/error/time |
| failed Canary remains visible | Case status/error rendering and tests |
| one evidence read failure is isolated | `loadCanaryEvidence` catches per Case |
| Continue/Stop eligibility is Backend-owned | API booleans; no React gate reimplementation |
| review command uses same-origin proxy | Web architecture test |
| client cannot choose evidence snapshot IDs | review payload contains reviewer/decision/notes only |
| UI cannot start Provider work | source/OpenAPI architecture tests |
| immutable decision is shown after refresh | API response + server page behavior |
| no regression | Backend/Web/Collector tests, typecheck, build, migration check |

### 8.2 Learning completion

The learner can explain without reading code:

- why exact Extraction ID is used instead of latest Requirements;
- why failed Cases with zero Requirements still matter;
- why `canaryContinueAllowed` is returned by Backend;
- why the form is a Client Component but the evidence page is a Server Component;
- why same-origin proxy exists;
- why checkbox confirmation is a forcing function, not audit proof;
- why Continue does not mean the model is accepted;
- why Provider execution is absent from Web.

### 8.3 Portfolio completion

Repository contains:

- a navigable Run list and detailed evidence workbench;
- exact-version evidence retrieval;
- Trace operational summary;
- immutable human command UI;
- backend and frontend tests;
- ADR and learning record;
- failure-path Demo;
- explicit unverified live-provider and security boundaries.

### 8.4 User-value completion

```text
open /evals/requirements/canary
→ choose a waiting Run
→ read each full JD
→ inspect exact Requirements/evidenceSpan
→ inspect Trace metrics/errors
→ write personal rationale
→ submit Continue or Stop once
→ see immutable decision after refresh
```

## 9. Minimal knowledge for this slice

### Server read versus client command

```text
Server Component:
Backend GET → render evidence

Client Component:
user writes judgment → same-origin POST → Backend validates and freezes decision
```

The browser never receives Provider credentials and never owns the gate rule.

### Exact-version evidence

```text
Run Case.extractionId
→ GET /jobs/{jobId}/requirement-extractions/{extractionId}
```

Using `/jobs/{jobId}/requirements` would read the latest Extraction and could silently display evidence different from what the Canary Run produced.

The JD has the same versioning problem. New Run Cases freeze the normalized persisted `Job.description` that is actually passed into Extraction. The current Job description is hashed separately only to signal whether the historical snapshot is still current. Raw Collector text is not used as the model-input snapshot because import normalization may change it.

### Backend-owned eligibility

The UI consumes:

```text
canaryContinueAllowed
canaryStopAllowed
canaryReviewBlockReason
```

It does not reproduce cumulative-attempt, provider, Trace or Extraction rules.

### Partial read failure

One failed Job/Extraction GET produces a Case-level error block. Other Canary Cases remain visible so the reviewer can still inspect the available evidence and choose Stop.

## 10. Prediction questions

Before reading the Diff, predict:

1. Should the page call latest Requirements or the exact Extraction endpoint?
2. Should React calculate whether Continue is allowed?
3. Should the Client submit reviewed Trace IDs?
4. What should happen when Case 2 evidence cannot be read?
5. Should a failed Provider Case with no Requirements be hidden?
6. Why is the review form client-side while the evidence page is server-side?
7. Which HTTP command may exist in this page, and which must not?
8. Does Continue mean the model passed the 20-case acceptance threshold?

## 11. Common wrong implementation

```tsx
const successful = run.cases.filter((item) => item.extractionId);
const canContinue = successful.length > 0 && run.attemptedCalls <= 3;

return successful.map((item) => <LatestRequirements jobId={item.jobId} />);
```

Why it fails:

- hides attempted failures;
- duplicates Backend policy;
- uses latest Requirements instead of the frozen Extraction;
- gives no Trace evidence;
- policy may drift after a Backend change;
- reviewers see a biased sample.

### Failure case

Case 1 succeeds, Case 2 fails with malformed structured output, Case 3 succeeds. A success-only UI shows two excellent results and hides the failure. The reviewer selects Continue based on incomplete evidence. The current workbench shows all three attempted Cases and the failed Trace/error.

## 12. Tickets (1–3 hours each)

### T0 — Contract and prediction sheet

- freeze Web boundary, evidence fields and completion proof;
- define no-Provider-command scope guard.

### T1 — Backend Run list, JD snapshot and Trace read model

- add summary/page application models;
- freeze normalized persisted JD input on each new Run Case;
- add migration and stale hash comparison;
- add repository list query;
- expose bounded Trace metadata and policy flags.

### T2 — Web contracts and server data functions

- add Run/Case/Review types;
- add list/detail/exact-extraction fetch functions.

### T3 — Run list page

- prioritize waiting Runs;
- show attempts, completed, failed, deferred and decision.

### T4 — Evidence detail page

- fetch attempted Cases before decision and frozen reviewed Case IDs after decision;
- render full JD, exact Requirements and Trace summary;
- isolate per-Case read failures.

### T5 — Human command UI

- require personal evidence checklist and notes;
- submit reviewer/decision/notes through same-origin proxy;
- show immutable result after refresh.

### T6 — Tests and independent Diff review

- Backend list/Trace/policy assertions;
- Web helper, architecture, typecheck and build;
- inspect misleading language and scope leaks.

### T7 — Portfolio artifacts

- ADR;
- learning record;
- interview questions;
- 3–5 minute Demo script;
- explicit unverified items.

## 13. Scope guard

Do not add:

- browser-triggered Provider execution or resume;
- automatic Continue/Stop recommendation;
- raw API key or provider request exposure;
- automatic 20-case judgments;
- model acceptance or Match promotion;
- queue, Redis, Celery or distributed locking;
- authentication/RBAC in this local MVP slice;
- a general-purpose raw Trace API;
- multi-agent architecture.
