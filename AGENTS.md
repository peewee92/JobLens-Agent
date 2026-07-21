# AGENTS.md

## Project Goal

Build a minimal, evidence-based job-search agent that connects a user's real career profile with real job postings collected by the JobLens browser extension.

## Product Principle

Never let the model invent career evidence.

Every important recommendation should be traceable to at least one of:

- user profile evidence;
- explicit user preference;
- concrete job-description requirement;
- aggregated market statistics from collected jobs.

## MVP Workflow

```text
Import resume/context
→ Build UserProfile
→ Import collected jobs
→ Select JobTarget
→ Match jobs
→ Analyze skill gaps
→ Produce action plan
→ Tailor resume/interview preparation
```

## Architecture Boundaries

- `apps/collector-extension`: collection only. No career recommendation logic.
- `services/api`: persistence and deterministic application APIs.
- `services/agent`: reasoning/orchestration. It may not bypass API/domain permission rules.
- `packages/contracts`: source of truth for cross-service data structures.

## Development Rules

1. Prefer structured outputs over free-form strings for Agent artifacts.
2. Matching scores must include evidence and reasons, not only a number.
3. Preserve raw job data. Derived fields must be reproducible.
4. Do not add multi-agent architecture during MVP.
5. Do not add automated job applications or recruiter messaging during MVP.
6. Every Agent feature should have at least one deterministic assertion or eval case.
7. Keep the MVP runnable locally with SQLite before adding cloud infrastructure.

## Definition of Done

A feature is not done until it has:

- a defined input/output contract;
- a runnable path;
- basic tests or eval cases;
- failure handling;
- documentation updated when the contract changes.
