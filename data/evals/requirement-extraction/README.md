# Job Requirement Extraction Eval

This dataset validates the first Requirement Intelligence pipeline:

```text
Job description
→ Requirement Extractor
→ deterministic grounding
→ Trace
→ case-level assertions
```

## Cases

`requirement-extraction-v1.jsonl` is the immutable historical 10-case baseline. `requirement-extraction-v2.jsonl` keeps the same source JDs but updates the two standalone `者优先` cases to the current business vocabulary: explicit preferred wording maps to `preferred`, while `bonus` is reserved for explicit bonus/additional-credit semantics.

The current v2 dataset contains 10 anonymized Job descriptions covering:

- Python / FastAPI;
- React alias normalization / TypeScript;
- Docker preferred wording;
- experience and education;
- responsibility, domain and constraint;
- Agent / RAG;
- Next.js / Electron preferred wording.

Each version freezes expected type, normalized capability and importance, plus capabilities that must not be invented. Do not rewrite v1 expectations in place; vocabulary corrections require a new dataset version.

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
