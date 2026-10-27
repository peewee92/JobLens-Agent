# JobLens Backend

JobLens Agent 的 Python Backend，采用 **模块化单体（Modular Monolith）**。

当前已完成：P0-1 Job Data Foundation + 最小 Web E2E、Phase 2A 版本化 Profile / Evidence / SearchIntent、Phase 2B Profile Proposal/Eval/Review、Phase 3A 版本化 JobRequirement 事实底座、Phase 3B-1 Requirement Eval Run/Case 持久化、Phase 3B-2 不可变人工 Review / Accepted Baseline，以及 Phase 4 的 Eligibility Gate、Evidence Retrieval v1、guarded Semantic Match v1、transient MatchReport / Recommendation Policy 与 Match Eval v1。Semantic Match prompt 已迭代到 v3：v2 的首轮 blind holdout 为 9/10，v3 进一步约束“表面流程相似 ≠ shared core mechanism”，随后在一套全新的 10-case blind holdout v2 上达到 10/10，workflow/Trace coverage 均为 100%。该结果仍只是质量证据，不是自动 release approval。Requirement 的真实 Provider 20 岗位人工验收仍未完成，因此真实 Match 执行继续由 Match Input Readiness fail-closed；MatchReport 持久化 runtime 已实现但真实数据库 schema 尚未迁移。Phase 5 已具备纯只读 Batch Ranking application use case：组合每岗最新 MatchReport snapshot、当前 SearchIntent.softPreferences 与 Job title/area 元数据，复用确定性 Ranking Policy 返回稳定排序；它不生成新 Match、不调用 Provider/Trace，也不写数据库。

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

### Guarded Semantic Match + persisted MatchReport

Semantic Match 只消费已通过 Eligibility 与 Evidence Retrieval 的冻结事实：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_xxx/semantic-match
```

Provider 只允许逐条输出 `matched / partial / not_matched` 和真实 `evidenceIds`。它不能输出 Eligibility、recommendation、ranking、score 或 probability；related-only Evidence 不能被提升成 `matched`，并且 Semantic verdict 永远不能改写 deterministic Eligibility。prompt v3 允许模型使用一般技术知识判断**输入中已明确出现的能力之间**是否共享核心机制，但职业事实仍只能来自 Requirement + Candidate Evidence。`partial` 需要共享 protocol/runtime semantics、data model、API pattern 或实际 implementation concern；generic scheduling、generic CRUD、共享业务场景或同属一个大类都不足以构成 `partial`。真实 Provider 默认 `SEMANTIC_MATCH_PROVIDER=disabled`，只有人工明确配置并授权后才会调用。

用户级 persisted MatchReport 入口：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_xxx/match-report
```

MatchReport 在一次 guarded Semantic Match 后，由 Backend 的确定性 Recommendation Policy 生成 `strong / good / stretch / low / blocked`。v1 规则不使用百分制阈值：`Eligibility=blocked => blocked`；`Eligibility=conditional => stretch`；`eligible` 后再根据 `must_have + preferred` 的 semantic verdict 区分 `strong / good / low`。deterministic `missing` 在最终摘要拥有更高优先级，即使 Semantic 返回 `matched` 也不能进入“明确匹配/核心优势”；`partial + missing` 可以同时表达“存在相关证据”和“仍有硬条件缺口”。Bonus 未命中不会进入“主要风险”。

MatchReport 返回 `strengths / risks / requirementResults / matchedRequirementIds / partialRequirementIds / missingRequirementIds / evidenceLinks`，不产生独立 Trace；Provider/Trace 计数来自它内部的 Semantic Match。成功 runtime 会追加一个不可变 `match_reports` snapshot，并返回 `dbWrites=1`。Web 端只在用户明确点击“生成完整匹配建议”时 POST，不在 SSR/刷新页面时自动触发 Provider。

Phase 5 提供只读批量排序查询：

```bash
curl 'http://127.0.0.1:8000/api/v1/match-ranking?jobId=job_a&jobId=job_b&includeBlocked=false&topN=5'
```

该接口只读取每岗最新 MatchReport snapshot，复用 Backend Ranking Policy 与当前 `SearchIntent.softPreferences`，不会生成新 Match、调用 Provider、创建 Trace 或写数据库。`topN=1..50` 可在排序完成后稳定截取前 N 个结果；每个结果直接返回既有 MatchReport `summary` 作为推荐理由，并透传 `evidenceLinks`（Requirement → Profile Evidence）作为可追溯引用，不在 Ranking 层重新生成解释。为避免旧结论污染当前排序，返回前会校验 MatchReport 的 `profileId/profileVersion` 与当前 Profile 一致，并要求 `extractionId` 等于该岗位当前最新 Requirement Extraction；stale snapshot 会被过滤。正式 `match_reports` schema 尚未迁移时返回 `409 match_report_persistence_not_ready`。Web 仅通过 same-origin `/api/match-ranking` Route Handler 转发该查询，不在前端复制排序规则。

Phase 6 已提供 transient Target Cohort 的 Gap Detail Backend API：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/target-cohort/gaps \
  -H 'content-type: application/json' \
  -d '{"cohortId":"cohort_demo","name":"目标岗位","selectedFeedbackIds":["feedback_xxx"]}'
```

该接口不会持久化 TargetCohort，而是只消费用户显式选中的**当前** UserFeedback candidate，并复用既有确定性链路：Feedback → transient Cohort → Requirement release gate → capability normalization → confirmed Profile comparison → SkillGap metrics → P0/P1 → Action Plan → Gap Detail。响应可直接展示 `targetCoverage / mustHaveRatio / gapSeverity`、`supportingRequirementIds / supportingJobIds`、`profileSkillIds / evidenceIds`、当前缺口状态和 completion criteria。过期或不再是当前 candidate 的 Feedback 返回 `409 target_cohort_selection_invalid`；正式 `match_reports/user_feedback` schema 未准备时返回 `409 user_feedback_persistence_not_ready`。接口固定不调用 Provider、不创建 Trace、不写数据库。

Phase 5 还提供纯 application 层的 `PlanBatchMatchUseCase`，用于真正批量执行之前把请求岗位稳定去重并分类为 `ready / input_blocked / persistence_blocked`。它复用单岗 Match Input Readiness，输入事实未通过时保留原 blocker codes；输入已可信但 `match_reports` schema 未就绪时只标记 persistence blocker。Planner 不运行 Eligibility/Semantic Match，不调用 Provider/Trace，也不写数据库。

在 Planner 之上新增 `ExecuteBatchMatchUseCase` 作为首个受限批量执行编排器：只执行 Planner 标记为 `ready` 的岗位，复用现有单岗 `BuildJobMatchReportUseCase`，不复制 Eligibility/Semantic Match 规则。单次调用最多执行 10 个 ready job，超过部分标记为 `deferred_limit`；输入或 persistence blocker 原样保留。单岗失败会隔离为 `failed` 并继续后续岗位，但因为异常路径无法可靠知道 Provider/Trace 是否已发生，此时 `sideEffectCountsComplete=false`，不会猜测失败任务的副作用数量。`POST /api/v1/match-batch` 已作为受控 HTTP contract 暴露该编排器：`jobIds` 至少 1 个且最多 50 个，`maxReadyJobs` 被请求模型硬限制为 1–10。响应的 `resumeJobIds` 只包含本轮因执行上限而确定未运行的 `deferred_limit` 岗位，`executionComplete` 表示是否还存在这类安全续跑项；失败任务不会自动加入恢复集合，避免副作用状态不明时被无意重放。测试已验证 50 个全部 ready 的岗位可按 `resumeJobIds` 经过 5 轮显式续跑完成，且每轮最多只运行 10 个。真实未通过 Match Input Readiness 的岗位仍只返回 blocker，不触发 Match/Provider/Trace/DB 写入；真实业务 DB 仍未应用 `0016/0017` migration。

`match_reports` 持久化使用不可变 JSON snapshot，同时单独保存 Job/Profile/Extraction、Eligibility/Recommendation、Matcher/Prompt/Model 与 Trace 身份；写入走显式 Unit of Work，未 commit 会 rollback，同一岗位的多次报告会追加历史而不是覆盖。runtime 在任何 Semantic/Provider 工作前先检查 `match_reports` 表是否存在；schema 未准备好时稳定返回 `409 match_report_persistence_not_ready`，不会偷偷建表、写 Trace 或产生 Provider 成本。`20260810_0016` migration 已在临时 SQLite 完成 upgrade/downgrade 验证，但尚未应用到真实业务数据库。

20 岗位人工 Match 评审还有一个只读 readiness 入口：

```bash
curl http://127.0.0.1:8000/api/v1/match-review/readiness
```

它只扫描最多 20 个岗位并复用现有 Match Input Readiness，要求 20/20 岗位都已有可信 Profile + Requirement 输入，同时要求 `match_reports` schema 已就绪；否则 `readyForHumanReview=false` 并返回 blockers。该接口不会运行 Eligibility/Semantic Match，不调用 Provider、不创建 Trace、不写数据库。当前真实 DB 仍未应用 0016，且 Requirement 真实人工基线尚未完成，因此该门禁会 fail-closed。

### Semantic Match Eval

Match Eval v1 把“护栏是否正确”和“模型质量是否正确”分开验证。`semantic-match-v1.jsonl` 是最小 Contract/Safety Eval；`semantic-match-quality-v1.jsonl` 是 10 条人工标注的 synthetic quality cases。已消费的 `semantic-match-blind-holdout-v1.jsonl` 在 prompt v2 上真实运行 10 条，得到 verdict/evidence accuracy 90%、workflow/Trace 100%，唯一错误是 Kafka requirement + cron batch Evidence 被判 `partial`。v3 修复该假阳性边界后，冻结了一套全新的 `semantic-match-blind-holdout-v2.jsonl`，与 calibration、holdout v1 及 Prompt v3 完整示例保持不重复；该 v2 holdout 的 10 条真实 Provider 调用全部符合预先人工标签，verdict/evidence accuracy、workflow success、Trace coverage 均为 100%。两套 holdout 一经消费均不能再作为后续 prompt 的无偏验证集。当前质量指标只用于观测与人工审查，不存在自动 release threshold。

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

没有 `--confirm-live-cost` 会在 Provider 调用前拒绝执行；live 模式没有显式 `--max-cases` 也会拒绝执行。Blind holdout 通过 `--dataset` 显式选择，且每一套已运行的数据集都要视为已消费，不得在 prompt 调整后继续冒充无偏验证。`qualityGateApplied=false` 表示当前不会因为某个准确率自动发布或拒绝模型；live 结果仍需要人工查看错误案例、reason 和 Trace。synthetic / blind Match Eval 都不能替代 ROADMAP 要求的 20 个真实岗位人工 Match 评审与未来 UserFeedback 基准。

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
curl http://127.0.0.1:8000/api/v1/requirement-evals/mvp-quality-status
```

`mvp-quality-status` 在隔离 SQLite 中运行冻结的 Requirement replay 与 20-job offline Match/Ranking Top-5 验收，不读取 live Provider key，也不会发起 Provider 调用；它用于 Requirement Eval 首页的轻量 MVP 状态展示。Provider smoke 仍是独立、非阻塞诊断信号，不会因为打开页面而自动产生付费调用。

显式执行 `python -m scripts.check_requirement_provider_health --execute-health-probe --confirm-live-cost --json`（或 MVP gate 的显式 `--provider-smoke --confirm-live-cost`）后，会把最新 smoke 的非敏感摘要写入 Git 忽略的 `data/local/requirement-provider-smoke.json`。该 snapshot 只包含检查时间、provider/model、ready/blocker、plain/json_schema HTTP 状态与调用次数，不保存 API key、base URL、Trace ID、原始响应或错误正文。`mvp-quality-status` 只读取该 snapshot；不存在时返回 `providerSmokeState=never_run`，snapshot 损坏时 fail-soft，且无论 smoke 结果如何都不改变离线 MVP gate 的 pass/fail。

MVP 工程进度统一用 `python -m scripts.check_mvp_progress --json` 汇总：离线 gate、可演示 E2E slice、Top-N 与 evidence 完整性、v42.95 冻结状态、Provider smoke 是否阻塞，以及当前真实 Job Pool 的 current MatchReport / UserFeedback / Requirement Analysis 覆盖率。真实覆盖率通过现有只读 API policy 计算，读取失败时 fail-soft 为 unknown，不改变离线 MVP gate，也不发起 live Provider 调用。Requirement Extraction 在 MVP 期间默认冻结为 `0 bump/week`；只有用户可见且 deterministic replay 可复现的 P0 缺陷才允许显式解冻，其他语义调优进入 P1 backlog。

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

### 先检查就绪，再验证副本

`GET /api/v1/health` 仅检查进程存活。`GET /api/v1/readiness` 检查数据库连接、当前 Alembic 版本是否与程序一致、ORM 所需表是否齐全。全部通过返回 200，否则返回 503 和稳定原因码（`database_unavailable / migration_required / schema_incomplete / migration_metadata_unavailable`），不泄露连接串或异常栈，不创建数据库、不运行迁移、不调用模型。

首页、Agent 页及求职工作区入口会先检查就绪；失败时提供中文说明，不继续读取业务表。该检查不是权限控制，也不拦截全部现有 API；API 使用者和部署脚本应显式检查就绪。它不验证每个列、索引及约束完全一致，结构漂移仍需 `alembic check` 和迁移回归测试。

对真实 SQLite 数据，先验证一个**不存在的新副本路径**：

```bash
cd services/backend
.venv/bin/python -m scripts.verify_migration_copy \
  --source /absolute/path/to/source.db \
  --output /absolute/path/to/new-copy.db
```

脚本以只读方式备份来源，仅对新副本执行迁移，并比较所有原有业务表、原有列的逐行摘要及行数，检查完整性、外键和就绪。拒绝覆盖任何已有输出。失败副本保留用于检查；**不会切换配置或升级来源数据库**。验证成功不等于已授权升级真实库；升级前仍需备份并确认目标连接。

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


### 读取已保存的匹配结果

`GET /api/v1/jobs/{job_id}/match-reports` 只读返回历史，不调用模型，也不自动启动分析。
每项包含 `reportId`、`createdAt`、`isCurrent`、`staleReasons` 和完整原始 `report`。
即使当前资料已删除或变化，也能读取原报告；旧策略结果明确标记过期，不重新解释。
网页 `/jobs/{job_id}?reportId={report_id}` 可以重新打开指定结果；指定标识不存在或不属于该岗位时，不回退冒充其他结果。
当前性是读取时的派生检查，不是跨请求锁；运行事实版本的原子校验与保存属于后续阶段 3。


### 目标建议边界

排序保留可读的 `low` 报告，但图只把 `strong / good / stretch` 选作默认目标。
默认三个、人工最多五个、分析范围最多五十个。没有可靠建议时返回 `target_evidence_insufficient`，而不是凑齐 Top 3。
`targetSuggestionMode=challenge_only` 表示本次建议只有挑战／待核实目标。该字段只是运行时展示提示，不替代原匹配报告和事实版本。

### 主业务阶段 3A：同库运行状态

正式运行存储使用既有 SQLAlchemy `SessionLocal`，由迁移 `20261025_0023` 创建 `career_agent_runs` 和 `career_agent_run_events`。运行与追加事件同事务写入；迁移需匹配修订、预期状态、步骤和运行身份，并检查合法状态迁移。竞争失败返回 409 `career_agent_state_conflict`，缺运行存储返回 503 `career_agent_storage_not_ready`；请求不会自动创建数据库或表。

`CAREER_AGENT_CHECKPOINT_PATH` 在正式依赖中仅用于读取旧文件，不双写。旧完成运行显示没有原始结果快照；旧未完成运行显示需要重新分析，不允许继续旧流程。旧事件未导入，旧文件保留。历史测试适配器仍存在，不是正式权威存储。

本阶段解决状态覆盖和部分提交，**不等同于**命令内容幂等、执行租约或完整结果持久化已经完成；这些属于 3B/3C。迁移仅在新副本验证，没有升级真实求职数据库。实现与重启证据见 [阶段 3A 交付记录](../../docs/implementation/P1-main-loop-runtime-store.md)。

### 主业务阶段 3B-1：重复命令内容校验

新开始命令保存规范化岗位范围、顺序及 `topN` 的摘要；新人工确认保存等待点、决定及所选岗位的摘要。标识与内容均相同，返回已有状态；标识相同但内容不同，返回 409，原状态不变。摘要随状态保存，已接受决定不能被后续迁移改写。重复岗位去重后视为同内容，但不同岗位顺序保留为不同请求。

无摘要的旧已接受命令不能证明内容一致，拒绝重放并提示新分析，仍允许只读查看。此切片不替代执行租约，也不解决所有并发重复计算；网页发送前保存标识、显式继续及完整原始结果仍待交付。见 [阶段 3B-1 记录](../../docs/implementation/P1-main-loop-command-integrity.md)。

### 主业务阶段 3B-2：执行领取与显式继续

迁移 `20261025_0024` 为主运行表增加租约令牌及到期时间。正式开始先保存 `created` 和原始请求范围，再领取默认 120 秒的运行租约。领取和释放是短事务，工作流在事务外执行；运行提交同时检查令牌、有效期和状态修订。释放必须仍持有原令牌，过期执行者不能覆盖或释放新执行者的状态。

`POST /api/v1/career-agent/runs/{thread_id}/continue` 无请求体，只推进已经接受的请求：`created` 从已保存输入排序，已保存排序直接建立等待点，`resuming` 继续已确认分析；等待确认和终态不推进。缺失运行返回 404，只读旧运行返回 409。`GET` 不领取租约、不调用工作流。网页对应“继续分析”和“重新查看状态”两个独立操作。

本地首版没有后台调度和自动续租。执行超过租约会拒绝保存，并由用户显式继续；只读计算可能重算，不保证恰好一次。保存约束失败返回 503 `career_agent_save_failed`，不把所有保存失败误报为并发冲突；唯一键或修订竞争仍返回 409。网页发送前保存完整命令、最近运行查询以及原始结果快照仍待后续交付。见 [执行恢复记录](../../docs/implementation/P1-main-loop-execution-recovery.md)。

### 主业务阶段 3B-3：请求重试与最近运行

`GET /api/v1/career-agent/runs?limit=10` 直接投影主运行表，限制 1–20，按更新时间和 threadId 倒序；不领取租约、不调用模型、不写事件，不扫描旧独立检查点。公开状态增加 `decisionActionId`，网页可识别自己的决定已接受或被其他页面决定取代。

网页在网络请求前保存完整开始／确认命令，失败后提供“查看请求状态”和“重试原请求”。重试不生成新标识，也不能覆盖未确认的不同请求。本地保存失败则不发送。首次响应丢失后先 GET；若没有服务端记录但仍有原开始命令，不丢弃，允许原样重试。页面地址保存 threadId，最近列表可在本地引用丢失后重开；打开和刷新不自动继续。岗位列表暂时不可用也不隐藏运行找回入口。

本地存储不是并发锁，真正的决定竞争和执行保护仍在数据库。完整分析快照、工作台和反馈闭环仍待后续阶段。见 [请求恢复交付记录](../../docs/implementation/P1-main-loop-request-recovery.md)。
完整报告引用与指纹仍保留，恢复验证没有因只显示三个建议而缩小范围。

### 主闭环 3C：固定事实与保存分析

迁移 `20261025_0025` 在主运行表保存版本化结果，包含本次事实绑定、共同差距和最多 5 个确认目标的确定性准备材料。计算不持有写事务；最终短事务复核事实、租约和修订，一起保存结果、完成状态与事件。事实已变化则保留原材料并标记过期。无需增加模型调用。

- `GET /api/v1/career-agent/runs/{thread_id}/result`：只读原结果，另行返回 `isCurrent/staleReasons`，不自动重算。
- 新结果页面 `/agent/results/[threadId]` 从原运行进入；旧指纹没有完整快照时明确缺失。
- 原库不自动迁移，先用 `scripts/verify_migration_copy.py` 验证新副本。
- 设计、失败复现及未完成范围：[3C 需求卡](../../docs/implementation/P1-main-loop-analysis-snapshot.md)。一键建立工作区与反馈更新尚未纳入此切片。

### 从保存的分析开始执行（4A）

迁移到 `20261025_0026` 后，可用 `POST /api/v1/career-agent/runs/{threadId}/execution`，提交 `commandId/resultId/jobIds`（最多 5 个原确认目标）。工作区、保存的简历事实草稿、来源行动、创建事件与命令回执在同一事务提交；失败整批回滚。相同命令同内容返回原结果，异内容 409；事实过期阻止首次创建，已保存回执仍可找回。

`GET` 同一路径只查询已有结果；`GET /api/v1/application-workspaces/{workspaceId}/preparation` 返回引用的保存材料及当前性。工作区保留初始事实来源，当前分析与行动来源分别可追溯；打开历史材料不重算，也不调用模型。本地单用户范围，不宣称多租户部署。见 `docs/implementation/P1-main-loop-start-execution.md`。

`GET /api/v1/workbench` 是现有事实的只读投影，包含资料/意向版本、具体输入问题、最近运行和原始结果引用、最多 5 个本地用户工作区、最多 10 条实际变化及一个下一步。不生成排序或模型输出，也不维护独立进度。共享契约 `workbench.schema.json`，实现及验证见 `P1-main-loop-workbench.md`。

### 反馈事务（5A）

提案创建/确认、行动状态和投递状态的生产写接口现在共用调用方 Session。确认提案使用既有 Profile 归一化规则在同一事务写入新版本、确认状态和事件，无内层提交。SQLite 短写锁与条件更新保护并发。失败返回 `workspace_transaction_save_failed`（503，含重试与修复信息）；重试前查询原记录，未知提交结果不伪报成功。此片未扩展其他旧写入口，也不自动合并过期提案。见 `P1-main-loop-feedback-transactions.md`。


### 真实成果核对（5B）

迁移至 `20261025_0027`。`GET /api/v1/application-workspaces/{id}/evidence-context` 只读返回当前资料版本、已完成行动的原始技能要求选项及不可核对的行动标识。行动有分析引用时从该分析读取来源，不使用工作区最初资料或当前实时材料代替。

普通准备行动提交提案时须传 `requirementId/expectedProfileId/expectedProfileVersion/reviewedCurrentProfile`，保留用户输入的摘要、来源和技能程度；“暂不判断”保留已有技能程度。提案创建不写职业资料，确认才写新版。旧学习行动接口保持兼容，但确认仍检查版本。

`POST /api/v1/application-workspaces/{id}/evidence-proposals/{proposalId}/reconsider` 要求显式核对当前版本和新的幂等标识，另存提案并关联原始提案；旧记录不改。替代链最多一次确认，已被替代或同源已确认的历史提案不再计入待处理数。原请求同内容返回回执，异内容冲突。沿用 5A 的同库短事务，不引入模型或第二套状态机。

网页仅对提案创建、确认及重新核对保存本地待确认请求；成功清除，未知失败保留，刷新不发送。明确拒绝可由用户丢弃后修正。此存储含用户刚填的成果描述，界面明确告知，不作为服务端权威状态。投递/行动状态的浏览器命令恢复不在此片范围。

旧单岗位重新匹配仍保留，执行前检查是否需要语义模型；需要则阻断，不自动付费，不代表 5C 的范围更新已实现。详细证据与失败复现见 [5B 记录](../../docs/implementation/P1-main-loop-evidence-review.md)。

### 限定范围更新：只读预检（5C-1a）

`GET /api/v1/career-agent/runs/{threadId}/update-plan?scope=targets|batch` 从原运行读取确认目标或原请求批次（最多 50），结合当前已确认资料、意向、岗位要求和最近报告，区分可复用、可规则重算、下一小批、需模型和输入阻断。首批新增分析候选最多 5 个；原结果不修改，GET 不运行 Match、不写 Trace 或业务数据。缺少原结果返回 404，数据库结构不可用返回安全的 503，不把空结果当成功。

此接口 `advisoryOnly=true`：是输入预检，不是执行回执、预留、授权或强一致执行保证。事实在执行前仍须再次校验。语义模型需求判断与真实语义工作流、旧单岗位重新匹配共用 `needs_semantic_model`；它只判断是否需要模型，不代替授权、预算或实际调用计数。

结果页 `/agent/results/{threadId}` 可进入 `/update` 选择范围。已接入显式有界规则更新、继续与独立新结果保存；新旧比较和完整反馈闭环验收仍待完成，不能把页面预检当成执行回执。设计与证据见 [5C 交付记录](../../docs/implementation/P1-main-loop-analysis-update.md)。

#### 有界规则更新分析

`POST /api/v1/career-agent/runs/{sourceThreadId}/updates` 消费更新预检的 `sourceResultId/scope/inputDigest`，加上新的 `threadId/runId/requestId/topN`。固定当前事实版本，复用兼容报告，每次最多尝试 5 个纯规则匹配。报告、步骤完成和追加事件在同一事务保存，沿用主运行存储与租约。分批 Continue 必须带 `actionId/expectedRevision/useCompletedOnly`，相同命令重放不会继续下一批。需要模型的岗位明确等待；用户可明确仅分析已完成岗位，运行与保存结果会标注部分范围。新结果不覆盖原分析，不调用模型、不在 GET 自动继续。

### 保存结果比较

`GET /api/v1/career-agent/runs/{threadId}/comparison` 只读新运行明确来源及两次绑定的归档报告，不重新匹配或查询最新事实补齐。岗位要求/策略变更、部分范围与报告缺失有稳定原因码；身份冲突返回 409，数据库不可读返回安全 503。无新表或模型调用。复现：`.venv/bin/python -m pytest tests/test_analysis_comparison.py -q`，须按测试说明配置隔离 SQLite、禁用模型。详见根目录 `docs/implementation/P1-main-loop-analysis-comparison.md`。
