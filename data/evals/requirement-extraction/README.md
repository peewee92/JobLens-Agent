# Job Requirement Extraction Eval v1

This dataset validates the first Requirement Intelligence pipeline:

```text
Job description
→ Requirement Extractor
→ deterministic grounding
→ Trace
→ case-level assertions
```

## Cases

`requirement-extraction-v1.jsonl` contains 10 anonymized Job descriptions covering:

- Python / FastAPI;
- React alias normalization / TypeScript;
- Docker bonus wording;
- experience and education;
- responsibility, domain and constraint;
- Agent / RAG;
- Next.js / Electron bonus wording.

Each case freezes expected type, normalized capability and importance, plus capabilities that must not be invented.

## Gate v1

- case pass rate >= 90%;
- Workflow success rate = 100%;
- expected capability recall >= 95%;
- importance accuracy >= 90%;
- forbidden capability case rate = 0%.

Every case runs through the full Workflow and must produce a Trace for each Provider attempt.

## Run

```bash
cd services/backend
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval
```

Use `REQUIREMENT_EXTRACTOR_PROVIDER=openai` with runtime credentials for a live run.

A Fixture 10/10 result validates only Dataset / Workflow / Validator / Trace / Gate plumbing. It is not evidence that a live model is production-ready.
