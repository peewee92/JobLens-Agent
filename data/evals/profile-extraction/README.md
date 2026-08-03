# Profile Extraction Eval v1

Dataset: `profile-extraction-v1.jsonl`

Contains 10 desensitized, representative resume snippets used to verify:

- structured output can be parsed;
- every proposed Evidence has an exact `evidenceSpan` in source text;
- Skills reference Evidence;
- expected explicit skills are not dropped;
- years of experience stays within a 0.5-year tolerance;
- selected unsupported facts do not appear.

## CI Gate

```bash
cd services/backend
uv run pytest -q tests/test_profile_extraction_eval.py
```

The CI test uses `FixtureProfileExtractor` so it is deterministic and verifies the pipeline, validator, Trace and Eval infrastructure. It does **not** claim live model quality. Each execution persists one immutable `profile_eval_runs` row and one `profile_eval_case_results` row per case.

## Fixture Eval command

```bash
cd services/backend
APP_ENV=test \
DATABASE_URL=sqlite:///./data/test_joblens.db \
PROFILE_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_profile_eval
```

The command prints the Eval Run ID. A later run can compare against it:

```bash
PROFILE_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_profile_eval --baseline-run-id eval_xxx
```

Fixture can pass `profile-eval-gate-v1`, but `releaseEligible` remains false.

## Live OpenAI Eval

```bash
cd services/backend
uv run alembic upgrade head
PROFILE_EXTRACTOR_PROVIDER=openai \
PROFILE_EXTRACTOR_MODEL='<configured model>' \
OPENAI_API_KEY='<secret>' \
uv run python -m scripts.run_profile_eval
```

A live run writes one `trace_spans` row per case plus an immutable Eval Run and Case Results. Only a live, gate-passing run can be marked `releaseEligible=true`; human review of failed cases and Trace remains required. Do not commit API keys, private resumes or live Trace databases.

The current implementation has not executed a live-provider Eval in the repository verification environment because no API credential was supplied.
