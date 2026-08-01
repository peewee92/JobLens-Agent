# AGENTS.md

## Project Goal

Build a minimal, evidence-based job-search agent that connects a user's real career profile with real job postings collected by the JobLens browser extension.

MVP v0.1 delivers one hard loop:

> Based on my real experience and a batch of real target jobs, tell me which jobs are most worth applying to first, and why.

v0.2 adds Skill Gap / Action Plan / Resume / Interview. P1 adds a Career Agent that orchestrates the mature workflows.

## Product Principle

Never let the model invent career evidence.

Every important recommendation should be traceable to at least one of:

- user profile evidence;
- explicit user preference (SearchIntent);
- concrete job-description requirement (JobRequirement);
- aggregated market statistics from collected jobs.

## MVP Workflow (v0.1)

```text
Import profile
→ Confirm evidence
→ Define SearchIntent
→ Import jobs
→ Extract JobRequirements
→ Run Eligibility
→ Match evidence
→ Rank jobs
→ Collect UserFeedback
```

v0.2 extends with: Target Cohort → Skill Gap → Action Plan → Resume / Interview.

## Architecture Boundaries

- `apps/collector-extension`: collection only. No career recommendation logic.
- `services/backend` (one FastAPI process, built in Step 1): layered as `api / domain / application / repositories / llm / workflows / agent / evals / tracing`. MVP is a monolith — not microservices (ADR-0006).
- `packages/contracts`: source of truth for cross-service data structures (JSON Schema + examples).
- Repo is a **Polyglot Monorepo**: `apps` (user entry) / `services` (backend) / `packages` (shared assets). Agent stays inside Backend until it needs an independent lifecycle (ADR-0006).
- `JobRequirement` is the single fact base for Match / Gap / Prepare.
- Job identity and provenance follow ADR-0007: `Job.id` is JobLens-owned; external IDs belong to `JobSource`; `canonical_key` is internal and versioned; remote state is `confirmed / rejected / unknown`; import-item history is separate from JobSource.

## Development Rules

1. Eval starts with the first LLM pipeline (Profile / Requirement / Match Eval from day one — ADR-0005).
2. `JobRequirement` is the unified fact source for Match / Gap / Prepare. Do not re-read raw JD in those stages.
3. The Agent does not implement business capabilities; it composes stable Workflows (ADR-0004).
4. A numeric Match Score must not be interpreted as a probability. It is for internal ranking only.
5. Every recommendation must be traceable to a Profile Evidence or a Job Requirement (`evidenceLinks`).

Additional constraints:

6. Prefer structured outputs over free-form strings for Agent artifacts.
7. Matching scores must include evidence and reasons, not only a number.
8. Preserve raw job data. Derived fields must be reproducible and version-tagged.
9. Do not add multi-agent architecture during MVP.
10. Do not add automated job applications or recruiter messaging during MVP.
11. Keep the MVP runnable locally with SQLite before adding cloud infrastructure.

## Definition of Done

A feature is not done until it has:

- a defined input/output contract;
- a runnable path;
- basic tests or eval cases (rule 1);
- failure handling;
- documentation updated when the contract changes.
