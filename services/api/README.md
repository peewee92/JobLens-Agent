# Application API

Planned stack: FastAPI + Pydantic + SQLite for MVP.

First endpoints:

```text
GET  /health
POST /api/v1/job-imports
GET  /api/v1/jobs
GET  /api/v1/jobs/{id}
POST /api/v1/profiles/extract
GET  /api/v1/profiles/current
POST /api/v1/jobs/{id}/match
POST /api/v1/targets
POST /api/v1/targets/{id}/gap-analysis
POST /api/v1/jobs/{id}/preparation-pack
```
