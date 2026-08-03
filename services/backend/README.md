# JobLens Backend

JobLens Agent 的 Python Backend，采用 **模块化单体（Modular Monolith）**。

当前已完成：P0-1 Job Data Foundation + 最小 Web E2E、Phase 2A 版本化 Profile / Evidence / SearchIntent、Phase 2B Profile Proposal/Eval/Review、Phase 3A 版本化 JobRequirement 事实底座，以及 Phase 3B-1 Requirement Eval Run/Case 持久化、Trace 回查、Baseline 对比和只读 API。Profile/Requirement 的真实 Provider 质量仍需运行凭据和人工审查；尚未进入 Eligibility / Match。

## Prerequisites

- Python >= 3.12（推荐用 [uv](https://docs.astral.sh/uv/) 管理）
- [uv](https://docs.astral.sh/uv/)（包管理 / 虚拟环境 / lockfile）

## Install

```bash
cd services/backend
uv sync
```

`uv sync` 会创建虚拟环境、按 `pyproject.toml` 安装依赖，并生成 `uv.lock`。

## Run

```bash
uv run fastapi dev
```

启动后访问：

- Health：`http://127.0.0.1:8000/api/v1/health`
- 交互式文档：`http://127.0.0.1:8000/docs`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`

### Confirm Profile and SearchIntent

当前为本地单用户。首次保存使用 `expectedVersion=0`，之后使用当前版本；陈旧版本返回 409。

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/profile \
  -H 'Content-Type: application/json' \
  --data '{"expectedVersion":0,"headline":"Frontend to AI Application Engineer","yearsOfExperience":8,"evidence":[{"key":"joblens","type":"project","summary":"Built JobLens","source":"confirmed by user"}],"skills":[{"name":"Agent Application Engineering","level":"working","evidenceKeys":["joblens"]}]}'
```

查询当前版本：

```bash
curl http://127.0.0.1:8000/api/v1/profile
curl http://127.0.0.1:8000/api/v1/search-intent
```

每个 Skill 必须关联同一 Profile 请求中的 Evidence key；保存后 API 返回服务器生成的 Evidence IDs。

### Propose Profile from resume text

默认 Provider 为 `disabled`。测试/演示可以使用 `fixture`，真实调用使用 `openai` 并从环境变量读取模型和 Key。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/profile-proposals \
  -H 'Content-Type: application/json' \
  --data '{"resumeText":"8 年前端经验。负责 Electron 桌面端与 React、TypeScript 业务开发，并参与 Agent 功能落地。"}'
```

返回的是待确认 Proposal，不会写 confirmed Profile。每个 Evidence 都必须包含简历中的原文 `evidenceSpan`；每次成功/失败运行写入 `trace_spans`，Trace 只保存简历 SHA-256 与字符数，不保存完整简历文本。

文件上传复用同一 Workflow：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/profile-proposals/file \
  -F 'file=@./resume.docx'
```

支持 5 MiB 内的文本型 PDF 和 DOCX。PDF 最多 20 页；加密 PDF、扫描/图片 PDF、伪装文件会返回稳定 4xx。原始文件不落库、不进入 Trace；OCR 不在当前范围。

Eval：

```bash
# deterministic CI Gate，并持久化 Eval Run / Case Result
PROFILE_EXTRACTOR_PROVIDER=fixture uv run python -m scripts.run_profile_eval

# 与历史 baseline 比较
PROFILE_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_profile_eval --baseline-run-id eval_xxx

# live provider（需先配置模型和 API Key）
PROFILE_EXTRACTOR_PROVIDER=openai uv run python -m scripts.run_profile_eval

# 使用人工接受的正式 live baseline
PROFILE_EXTRACTOR_PROVIDER=openai \
uv run python -m scripts.run_profile_eval --accepted-baseline
```

查看不可变历史与逐案例失败：

```bash
curl http://127.0.0.1:8000/api/v1/profile-evals
curl http://127.0.0.1:8000/api/v1/profile-evals/eval_xxx
```

`profile-eval-gate-v1` 检查案例通过率、Workflow 成功率、技能召回、年限准确率和禁用事实率。Fixture 结果只证明 Pipeline/Eval/Trace 可重复；只有 `mode=live` 且 Gate 通过时 `releaseEligible` 才可能为 true。

人工审查与正式 baseline：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/profile-evals/eval_xxx/review \
  -H 'Content-Type: application/json' \
  --data '{"decision":"accepted","reviewer":"local-user","notes":"Reviewed every case and Trace; no unsupported career facts."}'

curl http://127.0.0.1:8000/api/v1/profile-evals/baseline/accepted
```

`releaseEligible=true` 只允许进入人工审查，不等于已批准。Fixture Run 不能正式审查；一个 Run 只能保存一条不可变 Review。

### Extract JobRequirements

默认 Requirement Provider 为 `disabled`。本地工程验证可使用 `fixture`；真实模型使用 `openai`：

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture uv run fastapi dev
```

对已保存 Job 创建一个不可变 Extraction Run：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_xxx/requirement-extractions
```

读取最新版本和历史版本：

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx/requirements
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx/requirement-extractions/reqrun_xxx
```

每条 Requirement 都必须有命中 JD 原文的 `evidenceSpan`；重新抽取会创建新 Run，不覆盖历史。Trace input 只保存 Job ID、JD SHA-256 与字符数。后续 Eligibility / Match / Gap 必须复用 JobRequirement，不应重新解释 raw JD。

Requirement Eval 会保存不可变 Run、逐 Case 结果和 Trace 关联：

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval

# 与历史 Run 比较
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval \
  --baseline-run-id reqeval_xxx
```

查询质量证据：

```bash
curl http://127.0.0.1:8000/api/v1/requirement-evals
curl http://127.0.0.1:8000/api/v1/requirement-evals/reqeval_xxx
```

Fixture 10/10 只证明 Dataset / Workflow / Validator / Trace / Gate / Persistence 可重复，`releaseEligible` 始终为 false，不代表真实模型质量。只有 Live Run 且 Gate 通过时才可能成为人工审查候选；当前尚未实现 Requirement 人工 Review 或正式 accepted baseline。

### Import Collector report

```bash
curl -i \
  -X POST http://127.0.0.1:8000/api/v1/job-imports \
  -H 'Content-Type: application/json' \
  --data @../../data/samples/collector-report-minimal.json
```

成功返回 `201 Created`：

```json
{
  "importId": "imp_...",
  "sourceVersion": "1.3.1",
  "received": 1,
  "created": 1,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
```

重复导入同一岗位时会创建新的 `JobImport` 审计记录，但不会重复创建 `Job`，响应通常为 `created=0 / updated=1`。

查询某次导入审计：

```bash
curl http://127.0.0.1:8000/api/v1/job-imports/imp_xxx
```

返回批次统计、快照、candidateSummary 和按 `inputIndex` 排序的逐条 outcome；数据库中保存的错误 raw 与 candidateRaw 都不进入普通 API。

### Query Job Pool

```bash
curl 'http://127.0.0.1:8000/api/v1/jobs?city=武汉&minSalaryK=20&remoteStatus=unknown&sort=latest&limit=20&offset=0'
```

详情：

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx
```

列表支持：`q / city / minSalaryK / remoteStatus / source / sort / limit / offset`。普通查询响应不会返回 `sourceRaw`、`canonicalKey` 或 `normalizedSourceUrl`。

## Test

```bash
uv run pytest
```

## Migration commands

Alembic 已指向 `Base.metadata`：

- `20260801_0001_create_job_data_foundation.py` 创建 `jobs / job_sources / job_imports / job_import_items`；
- `20260802_0002_create_job_import_candidates.py` 创建 `job_import_candidates`；
- `20260803_0003_create_career_context.py` 创建版本化 Profile / Evidence / Skill links / SearchIntent；
- `20260803_0004_create_trace_spans.py` 创建通用能力 Trace；
- `20260803_0005_create_profile_eval_runs.py` 创建不可变 Profile Eval Run 与逐案例结果；
- `20260803_0006_create_profile_eval_reviews.py` 创建不可变人工 Review 与正式 baseline 治理记录；
- `20260803_0007_create_job_requirements.py` 创建版本化 JobRequirement Extraction Run 与逐条 Requirement；
- `20260803_0008_create_requirement_eval_runs.py` 创建不可变 Requirement Eval Run 与逐 Case 结果。

```bash
# 查看当前迁移版本
uv run alembic current

# 查看迁移历史
uv run alembic history

# 应用全部迁移
uv run alembic upgrade head

# 回退一版
uv run alembic downgrade -1

# 检查 ORM metadata 与数据库迁移是否漂移
uv run alembic check
```

## Configuration

配置通过 `.env` + `pydantic-settings` 加载（参考 `.env.example`）：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `local` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./data/joblens.db` |
| `PROFILE_EXTRACTOR_PROVIDER` | `disabled / fixture / openai` | `disabled` |
| `PROFILE_EXTRACTOR_MODEL` | 运行时模型名，不在代码硬编码 | 空 |
| `PROFILE_EXTRACTOR_TIMEOUT_SECONDS` | Profile Provider 超时 | `60` |
| `REQUIREMENT_EXTRACTOR_PROVIDER` | `disabled / fixture / openai` | `disabled` |
| `REQUIREMENT_EXTRACTOR_MODEL` | Requirement 运行时模型名 | 空 |
| `REQUIREMENT_EXTRACTOR_TIMEOUT_SECONDS` | Requirement Provider 超时 | `60` |
| `OPENAI_API_KEY` | OpenAI API Key，仅服务端读取 | 空 |
| `OPENAI_BASE_URL` | OpenAI API Base URL | `https://api.openai.com/v1` |

生产 Secret 不要写死在代码里。

## Project structure

```text
services/backend/
├── pyproject.toml
├── uv.lock
├── .python-version
├── README.md
├── alembic.ini
├── alembic/            # 数据库迁移
├── app/
│   ├── main.py         # Composition Root（创建 App、注册 Router）
│   ├── core/config.py  # 配置（pydantic-settings）
│   ├── api/            # HTTP Router / DTO / DI / Error Mapping
│   ├── domain/
│   │   ├── jobs/       # RemoteStatus / RemoteConfidence / ImportOutcome
│   │   └── career_context/ # EvidenceType / SkillLevel / Seniority
│   ├── application/
│   │   ├── career_context/ # versioned Profile/SearchIntent commands and queries
│   │   ├── job_imports/ # Adapter / Normalizer / Canonical Key / ImportJobsUseCase
│   │   ├── job_queries/ # Job Read Models / ListJobs / GetJob
│   │   ├── job_import_queries/ # Import Audit Read Model / Get Detail
│   │   └── ports/       # Write Repository / Query Repository / Unit of Work
│   ├── llm/             # disabled / fixture / OpenAI Profile Extractor adapters
│   ├── workflows/       # Profile Extraction orchestration and deterministic gates
│   ├── evals/           # repeatable Profile Eval runner
│   ├── repositories/    # SQLAlchemy write/query/trace repositories + Unit of Work
│   └── db/
│       ├── session.py  # Engine / Session / SQLite FK enforcement
│       └── models/     # Job data + versioned career-context ORM
└── tests/              # health / ORM / migration / import / query / architecture / HTTP integration tests
```

分层调用方向：`API → Application → Domain → Repository → Database`。
