# P0-3A｜JobRequirement Foundation Implementation Plan

Status: implemented and verified on 2026-08-03

## Product slice

```text
Persisted Job description
→ Requirement Extractor
→ strict structured proposal
→ deterministic JD grounding
→ Trace
→ immutable Extraction Run + Requirements
→ latest/historical API
→ Job detail Web
```

This slice establishes the shared requirement fact base. It intentionally stops before Eligibility, Profile Match, Ranking or Agent orchestration.

## User value hypothesis

A single, versioned Requirement interpretation lets Match, Skill Gap, Resume and Interview workflows share the same facts instead of independently re-reading raw JD text. Requirement IDs and evidence spans make later recommendations explainable.

## Business risks

- unsupported requirements become persisted facts;
- optional wording is upgraded to must-have;
- capability aliases are normalized incorrectly;
- re-extraction overwrites old facts;
- downstream workflows silently read raw JD;
- Fixture quality is presented as live model quality.

## Architecture

```text
FastAPI Router
→ ExtractJobRequirementsUseCase
→ persisted Job read model
→ ExtractJobRequirementsWorkflow
→ AbstractJobRequirementExtractor
→ Disabled / Fixture / OpenAI adapter
→ deterministic validation
→ Trace UoW
→ JobRequirement UoW
→ immutable query read model
```

Trace and Requirement persistence use separate short transactions. Provider execution is never held inside the Requirement database transaction.

## Completed tickets

### T0 Contract

- strict JobRequirement JSON Schema;
- JobRequirementExtraction Run Schema and example;
- stable API/error/privacy contract.

### T1 Schema and migration

- `job_requirement_extractions`;
- `job_requirements`;
- composite extraction/job foreign key;
- unique requirement index and enum/confidence constraints;
- Alembic 0007 upgrade/downgrade.

### T2 Extractor and Workflow

- Disabled, Fixture and OpenAI adapters;
- strict Responses JSON Schema with `store=false`;
- exact original/evidence substring validation;
- success/failure Trace;
- input length and duplicate rules.

### T3 Application and API

- explicit extraction command;
- latest and historical queries;
- immutable re-extraction;
- stable 404/422/502/503 mappings.

### T4 Eval

- 10 anonymized JD cases;
- case pass, Workflow success, capability recall, importance accuracy and forbidden capability metrics;
- degraded extractor regression evidence;
- independent CLI and one Trace per case.

### T5 Web

- latest Requirements embedded in Job detail;
- must/preferred/bonus visual semantics;
- Requirement ID, evidenceSpan, confidence and Trace ID;
- explicit same-origin re-extraction command;
- Fixture warning.

### T6 Evidence

- ORM/Migration tests;
- Workflow/Adapter/API/transaction/architecture tests;
- production Next build;
- real FastAPI + Next E2E with two extraction versions;
- full regression suites.

## Completion evidence

| Standard | Evidence |
|---|---|
| exact grounding | hallucinated Rust output rejected with failed Trace |
| immutable versions | repeated extraction creates different Run/Trace IDs; old Run query remains valid |
| transaction safety | forced persistence failure leaves zero Run/Requirement rows and one diagnostic Trace |
| public Contract | API integration and Pydantic example validation |
| stable errors | API tests for 404/422/502/503 |
| Eval from day one | 10-case Fixture Gate + degraded extractor failure |
| Web product path | production Next/FastAPI smoke, import → two Requirement Runs → latest detail |
| no architecture leakage | AST guards for Application, Workflow, Router and Repository |

## Explicitly unverified

- live OpenAI Requirement quality;
- 20 real-job manual acceptance;
- cost/latency and retry policy;
- human Requirement review;
- stale extraction policy when Job description changes;
- batch extraction scheduling;
- Eligibility, Match, Ranking or Agent.

## Next recommended slice

```text
credential-backed Requirement Eval
→ inspect failures and Trace
→ manually review 20 real jobs
→ accept or revise model/prompt/normalization
→ only then begin deterministic Eligibility
```
