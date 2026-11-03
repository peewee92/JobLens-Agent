# JobLens Web

JobLens 的求职任务工作台。先确认事实和岗位，再比较依据、确认目标、保存材料与执行行动。质量检查页是高级入口，不是普通用户的必经步骤。

首次体验推荐从仓库根目录执行 `python3 scripts/demo.py`，详见[项目入口](../../README.md)。以下是独立启动前后端的开发说明，不会替你迁移真实数据库或授权模型。

## Current routes

```text
/                           工作台与明确下一步
/profile                    确认职业事实和求职意向；简历草稿为可选入口
/import                     粘贴岗位或导入采集报告
/jobs                       岗位列表与筛选
/jobs/{jobId}               原文、要求核对、匹配依据与逐次模型授权
/agent                      选择岗位、比较已有报告、确认目标和恢复运行
/agent/analyze              原范围预检；显式启动缺失或过期报告的规则分析
/agent/results/{threadId}   重开当次保存材料，不以实时计算冒充历史
/applications               已有求职工作区
/applications/{id}          行动、人工状态、事实提案与面试准备
/quality                    高级质量检查入口
```

The browser submits Profile/SearchIntent commands and imports to same-origin Next Route Handlers:

```text
Browser
→ POST /api/profile-proposals or /api/profile-proposals/file
→ review/apply in local form state
→ PUT /api/profile | PUT /api/search-intent | POST /api/job-imports
→ POST /api/profile-evals/{id}/review
→ POST /api/requirement-evals/{id}/review
→ POST /api/jobs/{id}/requirement-extractions
→ FastAPI Workflow / Application Use Cases
```

Server-rendered pages call FastAPI using the server-only `JOBLENS_BACKEND_URL` environment variable. The Backend URL is never exposed as a `NEXT_PUBLIC_*` value.

## Install

From the repository root:

```bash
pnpm --dir apps/web install --frozen-lockfile
```

使用工作区根目录的 `pnpm-lock.yaml`；普通启动不应重新生成依赖锁文件。

## Run locally

Terminal 1:

```bash
cd services/backend
# 先按后端说明确认目标数据库并验证迁移，不对已有真实库自动升级
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
cd apps/web
JOBLENS_BACKEND_URL=http://127.0.0.1:8000 pnpm dev
```

Open:

```text
http://127.0.0.1:3000/
http://127.0.0.1:3000/evals/profile
http://127.0.0.1:3000/evals/requirements
http://127.0.0.1:3000/import
http://127.0.0.1:3000/jobs
```

## Verification

```bash
cd apps/web
pnpm test
pnpm typecheck
pnpm build
pnpm smoke:e2e
pnpm smoke:eval-review
pnpm smoke:requirement-review
```

`smoke:e2e` creates a temporary SQLite database, migrates it, starts real FastAPI and production Next processes, then verifies:

```text
DOCX upload → extracted text → Profile Proposal
→ explicit Profile + Evidence v1 confirmation
→ SearchIntent v1
→ stale-version 409
→ same-origin import proxy
→ filtered Job Pool
→ Job detail
→ two immutable Requirement Extraction versions
→ latest evidence-grounded Requirements
→ Import audit detail
```

`smoke:eval-review` seeds deterministic test-only Profile Fixture/failed-live/eligible-live runs, then verifies history rendering, failed-case Trace display, Fixture 422, reject 201, accept 201, duplicate 409 and accepted baseline refresh.

`smoke:requirement-review` runs the equivalent Requirement governance path and additionally shows missing Requirement and wrong-importance evidence through real FastAPI and production Next processes.

All smoke scripts clean up processes and temporary data after completion.

## Boundary rules

- Client Components are limited to genuine browser interaction: resume/Collector file input, proposal review, Profile/SearchIntent editing, Eval Review commands and explicit Requirement extraction.
- Job Pool filters live in URL search params.
- Server Components fetch list/detail/audit/Eval governance/latest Requirement data.
- Public Web types do not include `sourceRaw`, `candidateRaw`, `canonicalKey`, `profileKey`, or `intentKey`.
- Profile Proposal never auto-calls the confirmed Profile API; the user must adopt, review and save explicitly.
- Profile Skills reference Evidence through request-local keys; the Backend returns opaque Evidence IDs.
- The Web does not run Requirement providers or reimplement idempotency, transaction, grounding or Eval acceptance policy; Backend responses remain authoritative.

## Out of scope

- OCR, image resumes, encrypted PDF passwords and legacy DOC;
- live-provider Profile or Requirement quality claims without credential-backed Eval runs and human review;
- 自动投递、招聘消息和多 Agent 产品编排；
- authentication;
- favorites and ignore state;
- candidate raw browser;
- design-system or client-cache libraries.
