# ADR-0016 · Profile Extraction Proposal, Eval and Trace

- **Status:** Accepted
- **Date:** 2026-08-03
- **Related:** ADR-0004, ADR-0005, ADR-0015, Phase 2B

## Context

JobLens now has manually confirmed, versioned Profile/Evidence and SearchIntent. The next capability is resume extraction, but a model response must not become confirmed career truth automatically.

Risks:

- hallucinated company/project/achievement becomes a Profile fact;
- JSON shape succeeds while Evidence is not grounded in resume text;
- a model/provider call cannot be reproduced or compared;
- private resume text is retained unnecessarily;
- deterministic fixture results are mistaken for live model quality.

## Decision

### 1. Proposal before confirmation

```text
resume text
→ Profile Extractor
→ ProfileExtractionProposal
→ deterministic validation
→ user review/edit
→ existing SaveProfileUseCase
```

The extraction workflow never imports or calls `SaveProfileUseCase` and never writes confirmed Profile tables.

### 2. Capability and provider boundary

Application owns `AbstractProfileExtractor`.

Infrastructure adapters:

- `DisabledProfileExtractor` — safe default;
- `FixtureProfileExtractor` — deterministic tests/demo only;
- `OpenAIProfileExtractor` — Responses API with strict JSON Schema.

Model and credentials are runtime configuration. No production model name is hard-coded.

### 3. Structured Output is necessary but insufficient

After provider parsing, deterministic code requires:

- unique non-empty Evidence keys;
- every `evidenceSpan` is an exact contiguous source substring;
- unique Skill names;
- every Skill references existing Evidence;
- no SearchIntent inference inside Profile extraction.

A structurally valid provider output that violates these rules fails with `invalid_profile_extractor_output`.

### 4. Trace every provider attempt

Migration 0004 introduces `trace_spans`.

Each extraction attempt records:

```text
run id / capability / extractor version / model / prompt version
resume SHA-256 + character count
structured output or null
latency / token counts when available
error or null
```

The full resume text is not persisted in Trace.

### 5. Provider privacy

The OpenAI adapter sends `store=false` and keeps the API key server-side. Browser code calls only the same-origin Next Route Handler.

### 6. Eval from the first LLM pipeline

`data/evals/profile-extraction/profile-extraction-v1.jsonl` contains 10 desensitized representative cases.

Two results must not be confused:

- deterministic CI Gate verifies pipeline, validation, Trace and Eval mechanics;
- live-provider Eval measures configured model behavior and must be run separately with credentials.

A live-provider Eval has not been executed in the current verification environment.

## Consequences

### Positive

- model output cannot silently become confirmed fact;
- Evidence grounding is independently verifiable;
- Provider can change without changing Workflow/API;
- every attempt is traceable;
- Eval exists before Match/Agent work begins;
- resume text is not duplicated into Trace storage.

### Costs and limits

- proposal state is currently held in the Web page until adopted;
- Trace output stores the structured proposal, which may still contain career information;
- no proposal history/query API;
- no PDF/DOCX parser;
- no live-provider quality claim without an API-key-backed Eval run;
- concurrent live Eval cost/rate limiting is not implemented.

## Verification

Required evidence:

- OpenAI adapter sends strict JSON Schema and `store=false`;
- invalid evidenceSpan returns 502 and confirmed Profile row count remains unchanged;
- success and provider failure both create Trace rows;
- Trace input refs contain hash/length, not resume text;
- 10-case CI Eval creates 10 Trace rows;
- Web Client calls only `/api/profile-proposals` and never auto-calls `/api/profile`;
- production Next + FastAPI smoke completes proposal → confirmation → existing product loop;
- Application/Workflow/Router architecture tests remain green.
