# JobLens Backend

JobLens Agent 的 Python Backend，采用 **模块化单体（Modular Monolith）**。

当前已完成：P0-1 Job Data Foundation + 最小 Web E2E、Phase 2A 版本化 Profile / Evidence / SearchIntent、Phase 2B Profile Proposal/Eval/Review、Phase 3A 版本化 JobRequirement 事实底座、Phase 3B-1 Requirement Eval Run/Case 持久化、Phase 3B-2 不可变人工 Review / Accepted Baseline，以及 Phase 4 的 Eligibility Gate、Evidence Retrieval v1、guarded Semantic Match v1、transient MatchReport / Recommendation Policy 与 Match Eval v1。Semantic Match prompt 已迭代到 v3：v2 修复 related-but-transferable 过度保守，10-case blind holdout 达到 9/10；v3 进一步约束“表面流程相似 ≠ shared core mechanism”，用于降低 `not_matched -> partial` 假阳性。Requirement 的真实 Provider 20 岗位人工验收仍未完成，因此真实 Match 执行继续由 Match Input Readiness fail-closed；MatchReport 尚未持久化，Ranking 尚未实现。

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

返回的是待确认 Proposal，不会写 confirmed Profile。每个 Evidence 最终都必须包含简历中的原文 `evidenceSpan`；`profile-extractor-v2` 仅允许把模型因空白或 Markdown `*` / 反引号展示符造成的差异，在**唯一命中**时确定性对齐回真实连续原文，任何改写、幻觉或多义匹配仍 fail-closed。每次成功/失败运行写入 `trace_spans`，Trace 只保存简历 SHA-256 与字符数，不保存完整简历文本。

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

每条 Requirement 都必须有命中 JD 原文的 `evidenceSpan`；`skill` 类型在 Provider Structured Output 阶段就必须返回非空 `normalizedCapability`，Domain Gate 会再次校验，避免出现 Schema 接受但业务层拒绝的漂移。重新抽取会创建新 Run，不覆盖历史。Trace input 只保存 Job ID、JD SHA-256 与字符数。后续 Eligibility / Match / Gap 必须复用 JobRequirement，不应重新解释 raw JD。

### Deterministic Eligibility Gate

Phase 4 的首个切片提供只读接口：

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx/eligibility
```

Eligibility 只使用用户已确认的当前 Profile 与当前 JobRequirement，不调用 LLM、不创建 Trace、不写数据库，也不展示百分制“匹配概率”。每条 Requirement 返回 `matched / conditional / missing`、可追溯的 `evidenceIds` / `profileFactRefs` 和解释原因；整体结果为 `eligible / conditional / blocked`。明确 `must_have + missing` 会将岗位判为 `blocked`，而无法可靠判断的硬条件保持 `conditional`，不做语义猜测。专项年限不会使用总工作年限冒充。

该接口首先执行现有 Match Input Readiness。只要 Profile/SearchIntent 或 Requirement Fact 尚未通过可信输入门禁，就返回 `409 eligibility_inputs_not_ready`，不会绕过 Requirement 人工质量基线执行真实 Match 判断。Readiness 通过后还会再次核对冻结的 Profile ID/version 与 Extraction ID，防止检查完成后输入切换造成 stale Match。

### Deterministic Evidence Retrieval

Phase 4 第二个切片提供只读候选证据接口：

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx/evidence-candidates
```

Retrieval 的职责只是回答“哪些已确认的真实经历值得拿来继续判断”，不输出 `matched / missing` verdict。v1 只使用三类确定性依据：已确认 Skill → Evidence 的直接链接、Requirement capability 在 Evidence 原文中的显式出现，以及少量保守的 related capability hint。当前仅对已经明确批准的 MCP 场景提供 `Function Calling / Tool Calling / 工具调用 / 工具集成 / 工具接入` 相关候选；这类结果标记为 `related`，不得因此认定 MCP 已满足。

每个 Candidate 都返回真实 `evidenceId / evidenceKey / evidenceType / summary / source`、`direct / related` 层级、retrieval basis、matched terms 和原因。英文短能力词使用词边界匹配，避免 `AI` 之类短词误命中英文单词内部。接口不调用 Provider、不创建 Trace、不写数据库；可信输入未准备好时返回 `409 evidence_retrieval_inputs_not_ready`，并同样复核 Readiness 后的冻结输入身份。

### Guarded Semantic Match + transient MatchReport

Semantic Match 只消费已通过 Eligibility 与 Evidence Retrieval 的冻结事实：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_xxx/semantic-match
```

Provider 只允许逐条输出 `matched / partial / not_matched` 和真实 `evidenceIds`。它不能输出 Eligibility、recommendation、ranking、score 或 probability；related-only Evidence 不能被提升成 `matched`，并且 Semantic verdict 永远不能改写 deterministic Eligibility。prompt v3 允许模型使用一般技术知识判断**输入中已明确出现的能力之间**是否共享核心机制，但职业事实仍只能来自 Requirement + Candidate Evidence。`partial` 需要共享 protocol/runtime semantics、data model、API pattern 或实际 implementation concern；generic scheduling、generic CRUD、共享业务场景或同属一个大类都不足以构成 `partial`。真实 Provider 默认 `SEMANTIC_MATCH_PROVIDER=disabled`，只有人工明确配置并授权后才会调用。

用户级 transient MatchReport 入口：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_xxx/match-report
```

MatchReport 在一次 guarded Semantic Match 后，由 Backend 的确定性 Recommendation Policy 生成 `strong / good / stretch / low / blocked`。v1 规则不使用百分制阈值：`Eligibility=blocked => blocked`；`Eligibility=conditional => stretch`；`eligible` 后再根据 `must_have + preferred` 的 semantic verdict 区分 `strong / good / low`。deterministic `missing` 在最终摘要拥有更高优先级，即使 Semantic 返回 `matched` 也不能进入“明确匹配/核心优势”；`partial + missing` 可以同时表达“存在相关证据”和“仍有硬条件缺口”。Bonus 未命中不会进入“主要风险”。

MatchReport 返回 `strengths / risks / requirementResults / matchedRequirementIds / partialRequirementIds / missingRequirementIds / evidenceLinks`，不持久化、不产生独立 Trace；Provider/Trace 计数来自它内部的 Semantic Match。Web 端只在用户明确点击“生成完整匹配建议”时 POST，不在 SSR/刷新页面时自动触发 Provider。

### Semantic Match Eval

Match Eval v1 把“护栏是否正确”和“模型质量是否正确”分开验证。`semantic-match-v1.jsonl` 是最小 Contract/Safety Eval；`semantic-match-quality-v1.jsonl` 是 10 条人工标注的 synthetic quality cases。已消费的 `semantic-match-blind-holdout-v1.jsonl` 在 prompt v2 上真实运行 10 条，得到 verdict/evidence accuracy 90%、workflow/Trace 100%，唯一错误是 Kafka requirement + cron batch Evidence 被判 `partial`。该 holdout 已用于诊断 v3，不能再次作为 v3 的无偏验证集；后续需要冻结新的 blind holdout。当前质量指标只用于观测与人工审查，不存在自动 release threshold。

本地 fixture 验证：

```bash
SEMANTIC_MATCH_PROVIDER=fixture \
uv run python -m scripts.run_semantic_match_eval --json
```

报告包含 `verdictAccuracy / evidenceAccuracy / workflowSuccessRate / traceCoverage`、混淆矩阵、逐案例 actual reason / Evidence IDs / Trace ID。Eval Trace 只写临时 SQLite，随后汇总进 JSON 报告，不写正式 `data/joblens.db`。

真实 Provider Eval 必须同时显式确认成本并限制案例数，例如：

```bash
SEMANTIC_MATCH_PROVIDER=openai \
uv run python -m scripts.run_semantic_match_eval \
  --max-cases 3 \
  --confirm-live-cost \
  --json
```

没有 `--confirm-live-cost` 会在 Provider 调用前拒绝执行；live 模式没有显式 `--max-cases` 也会拒绝执行。Blind holdout 可通过 `--dataset ../../data/evals/semantic-match/semantic-match-blind-holdout-v1.jsonl` 显式选择，但真实运行仍必须经过 HUMAN_GATE 授权。`qualityGateApplied=false` 表示当前不会因为某个准确率自动发布或拒绝模型；live 结果仍需要人工查看错误案例、reason 和 Trace。synthetic Match Eval 也不能替代 ROADMAP 要求的 20 个真实岗位人工 Match 评审与未来 UserFeedback 基准。

Requirement Eval 会保存不可变 Run、逐 Case 结果和 Trace 关联：

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval

# 与历史 Run 比较
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval \
  --baseline-run-id reqeval_xxx

# Live Provider 使用最近一次人工接受的正式 baseline
REQUIREMENT_EXTRACTOR_PROVIDER=openai \
uv run python -m scripts.run_requirement_eval --accepted-baseline
```

查询质量证据和正式 baseline：

```bash
curl http://127.0.0.1:8000/api/v1/requirement-evals
curl http://127.0.0.1:8000/api/v1/requirement-evals/reqeval_xxx
curl http://127.0.0.1:8000/api/v1/requirement-evals/baseline/accepted
```

提交一次不可变人工 Review：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/requirement-evals/reqeval_xxx/review \
  -H 'Content-Type: application/json' \
  --data '{"decision":"accepted","reviewer":"local-reviewer","notes":"Reviewed every Requirement case and linked Trace before accepting."}'
```

Fixture 10/10 只证明 Dataset / Workflow / Validator / Trace / Gate / Persistence 可重复，`releaseEligible` 始终为 false，也不能接受或拒绝正式 Review。Gate 失败的 Live Run 只能记录 rejected；只有 Gate 通过且 `releaseEligible=true` 的 Live Run 才能 accepted。Accepted Baseline 是最近一次有效的不可变人工接受记录，不代表本仓库已经完成真实 OpenAI 质量验收。

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
- `20260803_0008_create_requirement_eval_runs.py` 创建不可变 Requirement Eval Run 与逐 Case 结果；
- `20260803_0009_create_requirement_eval_reviews.py` 创建不可变 Requirement Eval 人工 Review 与正式 baseline 治理记录。

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
| `PROFILE_EXTRACTOR_API_STYLE` | OpenAI-compatible 协议：`responses / chat_completions` | `responses` |
| `PROFILE_EXTRACTOR_ENABLE_THINKING` | 可选网关参数；`false` 可关闭支持该字段的推理模型 thinking | 空 |
| `PROFILE_EXTRACTOR_MAX_COMPLETION_TOKENS` | 可选网关参数；限制 Chat Completions 总 completion 预算 | 空 |
| `PROFILE_EXTRACTOR_TIMEOUT_SECONDS` | Profile Provider 超时 | `60` |
| `REQUIREMENT_EXTRACTOR_PROVIDER` | `disabled / fixture / openai` | `disabled` |
| `REQUIREMENT_EXTRACTOR_MODEL` | Requirement 运行时模型名 | 空 |
| `REQUIREMENT_EXTRACTOR_API_STYLE` | OpenAI-compatible 协议：`responses / chat_completions` | `responses` |
| `REQUIREMENT_EXTRACTOR_ENABLE_THINKING` | 可选网关参数；`false` 可关闭支持该字段的推理模型 thinking | 空 |
| `REQUIREMENT_EXTRACTOR_MAX_COMPLETION_TOKENS` | 可选网关参数；限制 Chat Completions 总 completion 预算 | 空 |
| `REQUIREMENT_EXTRACTOR_TIMEOUT_SECONDS` | Requirement Provider 超时 | `60` |
| `OPENAI_API_KEY` | OpenAI API Key，仅服务端读取 | 空 |
| `OPENAI_BASE_URL` | OpenAI API Base URL | `https://api.openai.com/v1` |

生产 Secret 不要写死在代码里。第三方 OpenAI-compatible 网关若只支持 `/chat/completions`，应为对应能力显式配置 `PROFILE_EXTRACTOR_API_STYLE=chat_completions` 或 `REQUIREMENT_EXTRACTOR_API_STYLE=chat_completions`；`OPENAI_BASE_URL` 只填写到版本根路径，不附加具体接口路径。部分 reasoning 模型会在结构化抽取时把 completion 预算全部消耗在思考过程；只有网关明确支持时才为对应能力配置 `*_ENABLE_THINKING=false`，并配合 `*_MAX_COMPLETION_TOKENS` 设置成本上限。HTTP 状态错误会保留网关返回的 `traceId`，但不会记录响应正文或密钥。

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
