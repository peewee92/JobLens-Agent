# JobLens Agent 路线图

## 总目标

用最小工程成本打通：

```text
Profile → SearchIntent → JobRequirement → Eligibility → Match → Ranking → UserFeedback
```

路线图强调先形成可验证闭环，再增加能力广度与平台规模。**Eval 从 Phase 1 就介入，不是最后一个 Phase。**

领域模型、阶段边界与关键决策见：
- [领域模型](architecture/DOMAIN-MODEL.md)
- [系统架构](architecture/SYSTEM-ARCHITECTURE.md)
- [评估与追踪](architecture/EVAL-AND-TRACE.md)
- [MVP 范围决策](decisions/0001-mvp-scope.md)
- [后端技术栈](decisions/0002-backend-stack.md)
- [数据库策略](decisions/0003-database-strategy.md)
- [LLM / Workflow / Agent 边界](decisions/0004-llm-workflow-agent-boundary.md)
- [Eval 从第一天开始](decisions/0005-eval-from-day-one.md)

---

# Phase 0.5｜产品与领域模型冻结（P0，概念基线）

目标：在写第一行业务逻辑前，先把**产品定义、领域模型、阶段边界、架构边界**冻结。

### 为什么有这个 Phase

早期最容易失控的是“文档无限扩张但无工程证据”。Phase 0.5 只做三件事：

1. 收缩 Primary Persona（有 3–10 年经验、有简历、有 1–3 个目标方向、主动求职/转型）；
2. 冻结领域模型（`UserProfile` / `SearchIntent` / `Job` / `JobRequirement` / `MatchReport` / `UserFeedback` / `TargetCohort` / `SkillGap`）；
3. 冻结阶段边界与后端边界（单 FastAPI 进程 + 分层，不拆微服务；LLM Capability → Domain Workflow → Career Agent）。

### 交付

- [x] MVP PRD v2.0（单 Persona、两阶段 MVP、JobRequirement、UserFeedback、Eligibility+Fit）
- [x] 领域模型 `DOMAIN-MODEL.md`
- [x] 系统架构 `SYSTEM-ARCHITECTURE.md`（单后端应用 + 新执行链）
- [x] Collector 导入契约
- [x] 核心领域 Schema（含 3 个新增：`search-intent` / `job-requirement` / `user-feedback`）
- [x] ADR-0001..0005

### 完成标准

开发者进入仓库后，可以直接回答：

- 系统解决什么问题、不解决什么；
- 第一阶段只做哪 8 步（v0.1）；
- Collector 与 Agent 如何分工；
- 第一批 API 和数据模型是什么；
- 不需要理解整个 JobLens 长期愿景就能开工。

---

# Phase 1｜Job Data Foundation（P0）

对应需求文档：`P0-1-job-data-foundation.md`

建议周期：2–3 天

目标：不依赖手工 CSV 分析，把已有 Collector 的 JSON 正式导入系统，形成可靠的 `Job Pool`。

### 任务

1. 单个 FastAPI 进程（非微服务，见 ADR-0002 / 0003）；
2. SQLite 数据库；
3. `POST /api/v1/job-imports`；
4. 解析 Collector report：`jobs` / `candidates` / `statistics` / `config`；
5. Job 标准化与去重（canonical key）；
6. Job Pool 查询接口；
7. 保存 `sourceRaw`，避免数据不可追溯；
8. 导入批次记录：`Import Batch` / `Source Snapshot` / `Collector Version` / `Collected At` / `SearchIntent Snapshot`（见 COLLECTOR-CONTRACT）。

### 验收

- 同一 JSON 重复导入两次，Job 数量基本不增加；
- 可以按城市、薪资、关键词查看岗位；
- 可以打开原始 BOSS URL；
- 能回答“这批岗位里 Python 比例为什么这么高”（需保存搜索关键词 / 城市 / 时间 / Collector 版本）。

> 这一阶段**只做数据地基**，不碰 Match / Profile LLM。做完即可作为第一个可独立验收的节点。

---

# Phase 2｜Profile + SearchIntent（P0）

建议周期：3–5 天

目标：建立个人事实底座与“我想找什么”的明确约束。

### 任务

1. 简历文本输入；
2. LLM Structured Output → `UserProfile`（带 `Evidence`）；
3. Evidence 抽取与用户确认；
4. Profile Version；
5. `SearchIntent` 定义（目标角色 / 城市 / 远程 / 薪资下限 / 级别 / 硬约束 / 软偏好）；
6. `Profile Eval` 数据集与断言（从第一个 LLM Pipeline 开始，见 ADR-0005）。

### 当前进度（2026-08-05）

- 手工确认的 Profile + Evidence + Skill 链接已完成；
- Profile/SearchIntent 不可变版本、`expectedVersion` 冲突保护、API 与 Web 编辑闭环已完成；
- Confirmed Career Context Release Gate 已完成：只读验证最新用户确认 Profile/SearchIntent、Profile Evidence/Skill 引用和目标岗位完整性，返回精确 IDs/versions 与结构化 blockers；不读取 Profile Eval baseline、不调用 Provider、不产生 Trace，Profile 页面展示未来 Match 的个人侧输入状态；
- Resume Text → Profile Proposal、strict Structured Output、evidenceSpan/reference 门禁、Trace 0004 和 10-case Profile Eval 已完成；
- PDF/DOCX 文本摄取、文件隐私边界与 Web 上传已完成；`profile-extractor-v2` 保持 evidence fail-closed，并仅对空白或 Markdown `*` / 反引号造成的展示差异做唯一、确定性的原文连续片段对齐，改写/幻觉/多义匹配仍拒绝；Eval Run/Case Result、`profile-eval-gate-v1`、baseline 对比、人工 accept/reject Review、正式 accepted baseline 与 Eval Review Web 已完成；下一步是带真实凭据的 Provider Eval 和人工质量结论。Fixture 通过仍不代表生产模型质量。

### 验收

Profile 页面可以明确区分：

- 我真的做过；
- 我了解但缺少项目证据；
- 我完全没有。

`SearchIntent` 可保存为快照并与导入批次关联。

---

# Phase 3｜Requirement Intelligence（P0，核心新增）

目标：`JobRequirement` 成为 `Match` / `Gap` / `Prepare` 的**统一事实基础**。

### 为什么单独成 Phase

过去 Requirement Extraction 只是 Match 内部一步。现在它被提升为独立能力，因为：

- `Match` 需要它对每条 JD 要求结构化；
- v0.2 的 `Skill Gap` 直接复用它做需求聚合，不必回读 JD；
- `Resume` / `Interview` 的准备也基于它定位差距。

### 任务

1. JD → `JobRequirement`（LLM Structured Output）；
2. `type` 分类：`skill` / `experience` / `education` / `responsibility` / `domain` / `constraint`；
3. `normalizedCapability` 归一化；
4. `importance`：`must_have` / `preferred` / `bonus`；
5. `evidenceSpan` 命中 JD 原文；
6. `confidence` / `extractorVersion`；
7. `Requirement Eval` 数据集与断言。

### 当前进度（2026-08-05）

- `JobRequirementExtraction` 与逐条 `JobRequirement` 已按不可变版本持久化；
- strict Structured Output Adapter、exact `originalText/evidenceSpan` 门禁与 Requirement Trace 已完成；
- POST 抽取、GET 最新版本、GET 历史版本 API 已完成；
- 10-case 脱敏 Requirement Eval、Fixture Gate、失败案例解释和独立 CLI 已完成；
- Requirement Eval Run / Case Result 已不可变持久化，支持 Trace 回查、Fixture/Live 发布资格隔离和历史 baseline 对比；
- 不可变 Requirement 人工 Review、Accepted Baseline、CLI baseline 选择、质量历史页与逐 Case Web 审查已完成；
- 版本冻结的 1–20 Case Manual Review Batch、stale 检测和 formal/practice 证据区分已完成；
- Manual Review Batch Final Quality Decision 已完成：`formalEvidenceEligible` 只表示 20 Case 正式证据完整，不自动代表模型通过；Batch Owner 可提交唯一不可变 `accept_for_match/reject_for_match`，结论冻结计数、issue 分布与完整 evidence fingerprint；只有当前未 stale 的人工 accepted Batch 才由 accepted-baseline Query 暴露给后续 Match，证据变旧会自动撤销门禁但保留历史结论；
- Job Requirement Fact Release Gate 已完成：以当前 Job JD hash、latest Extraction、逐条 Requirement、Trace 和 human-accepted baseline 构造只读信任链；只有输入当前、cohort 精确一致、Trace 成功且输入/逐字段输出与数据库完全一致时 `releaseEligible=true`，Job 详情页展示结构化 blockers；该 Gate 不运行 Match，也不产生 Provider/DB 写入；
- 从 Collector 正式 20-JD 数据集到 Import → resumable Extraction → exact Review Batch 的 CLI 编排已完成；同输入同 cohort 会复用，部分失败不会创建不完整 Batch；
- Requirement Acceptance Run / 20 Case 运行控制、零调用 Preflight、显式 live canary 上限和失败 Trace 保留已完成；
- 累计第 4 次 live 调用前的不可变人工 Canary `continue/stop` 门禁已完成，Review 冻结 Case/Extraction/Trace IDs；
- Canary Review Web Workbench 已完成：可浏览 Run、完整 JD、精确 Extraction、Requirements/evidenceSpan 与 Trace 摘要，并通过同源短命令提交不可变判断；浏览器仍不能启动长 Provider 任务；
- Live Acceptance Readiness Gate 已完成：在零写入、零 Provider 调用下检查 formal dataset、live config、API Key 是否存在、动态 Alembic head、Existing Run 与请求预算，并输出唯一 nextAction、结构化 blockers、Workbench/Manual Review URL 和无密钥 command preview；
- Read-only Requirement Acceptance Readiness Dashboard 已完成：Backend 只扫描服务端 canonical private dataset 目录，区分 missing/multiple/invalid/ready，复用 CLI 同一 DB/Alembic 只读事实和 Readiness Policy；Web 只展示 blockers、唯一 nextAction、Run/Batch handoff 与零副作用证据，不接收任意路径、不返回密钥/命令/JD，也不能启动 Provider、迁移或 Resume；
- Live Canary Session Manifest 已完成：用 Dataset Fingerprint + Reviewer/Title + Provider/Model/Extractor/Prompt 生成稳定 Session ID，并原子导出 Readiness、Run/Case/Trace/Review/Batch 引用、隐私边界和完成清单；不复制 API Key、完整 JD、Raw Trace 或人工 Notes 正文；
- Guarded Local Live Bootstrap 已完成：默认 Plan 零 operational mutation，显式 Apply 后将 formal dataset 以 Hash 校验方式写入 `data/private`，对 SQLite 执行 online backup、integrity/revision 验证和 Alembic upgrade，并在 post-check 后重新运行 Readiness；backup/migration failure 均 fail-closed，不调用 Provider、不自动 restore；
- Resumable Database Preparation Checkpoint 已完成：以数据库绝对路径 + Alembic Head 生成稳定操作 ID，按 `planned → backup_verified → migration_attempted → applied` 持久化私有 Receipt；只有未尝试的 verified backup 可自动续跑，inconclusive attempt 禁止重试，到 Head 但 Receipt 未完成时可基于 DB facts 恢复；本地真实 DB 已从 `20260803_0010` 升级到 `20260804_0013`，旧 Revision Backup、Hash、Integrity、新 Schema 与幂等重跑均已验证；
- Explicit Live Canary Operator 已完成：只接受 fingerprint-addressed canonical private dataset，将 read-only Readiness 与 Provider 副作用分离，要求 `--execute-canary` 和成本/人工审核双确认；执行前后原子更新 Session Manifest，以 Run Case `attemptCount` 增量、Extraction ID 和 Trace ID证明本次证据；第三次累计 Attempt 后只返回 Workbench，不能自动 Continue/Stop，也不提供 Fixture 路径；
- Controlled Resume Operator 已完成：只允许 `nextAction=resume_run`，显式绑定 canonical Dataset、Run ID、不可变 Continue Review ID 和剩余 Case 预算；执行前验证冻结 Case/Extraction/Trace 证据，复用数据库 Execution Lease，部分完成时生成下一次专用 Resume 计划命令，20 Case 完成时只交接 frozen Manual Review Batch；
- 2026-08-07：OpenAI-compatible Provider 兼容层已支持 `responses/chat_completions` 双协议、可选 thinking 开关、completion 上限和 HTTP `traceId` 保留；基元律动 `deepseek-v4-flash` 的首个 v3 Live Canary 已真实成功，1 次调用生成 1 个 Extraction、18 条 Requirement 和成功 Trace，19 Case 保持 deferred，未超预算；该结果只证明接口与结构化链路可运行，不代表模型质量通过；
- Fixture 不能正式 Review，失败 Live 只能 rejected，合格 Live accepted 后才能成为正式 baseline；
- Job 详情页可显式触发新版本并展示 Requirement ID、importance、evidenceSpan、confidence 与 Trace；
- 尚未完成剩余 19-job Provider Extraction、逐条人工决策和真实 Batch Final Decision；当前虽已有首个真实成功 Case，仍不能视为生产模型质量结论，也不进入 Match。

### 验收

抽样 20 个岗位，人工检查：

- `must_have` 与 `bonus` 区分合理；
- `evidenceSpan` 能精确指向 JD 原文；
- 同义能力已归一（如 “React.js” / “ReactJS” → “React”）。

---

# Phase 4｜Single Job Match（P0，核心）

建议周期：5–7 天

目标：让单个岗位判断“是否值得投、为什么”可信、可解释。

### 当前进度（2026-08-09）

- 已完成只读 `Match Input Readiness` 预检，统一组合 Confirmed Career Context 与 Job Requirement Fact Release Gate；它只暴露 blockers 和冻结事实身份，不运行 LLM、Trace 或数据库写入。
- 已完成 Phase 4 首个确定性 `Eligibility Gate` 切片：只读组合当前已确认 Profile 与当前 JobRequirement，逐条输出 `matched / conditional / missing`、`evidenceIds / profileFactRefs` 与原因，整体输出 `eligible / conditional / blocked`；`must_have + missing => blocked`，专项年限不使用总工作年限冒充，不做模糊百分制评分。
- Eligibility 执行仍严格受 Match Input Readiness 约束；真实 Requirement 20 岗位人工验收未完成时返回 `eligibility_inputs_not_ready`，不得绕过门禁执行真实判断。
- 已完成 Phase 4 第二个 `Evidence Retrieval v1` 切片：只读返回每条 Requirement 的真实 Profile Evidence 候选，区分 `direct / related` 与 `exact_skill_link / explicit_text_overlap / related_capability_hint`；Retrieval 不输出 Match verdict，不调用 Provider、不创建 Trace、不写数据库，并在 Readiness 后复核冻结 Profile/Extraction 身份防止 stale 输入。
- 当前 related hint 仅覆盖已明确批准的 MCP → Function Calling / Tool Calling / 工具调用 / 工具集成 / 工具接入候选关系；向量/Embedding 语义检索尚未引入。
- 已完成 guarded `Semantic Match v1`：模型只判断真实 Candidate Evidence 与 JobRequirement 的 `matched / partial / not_matched`，不能输出或改写 Eligibility / recommendation / ranking / score；related-only Evidence 不得升级为 matched，真实调用创建 Trace，Provider 默认 disabled。
- 已完成 transient `MatchReport v1 + Recommendation Policy + Web 摘要卡片`：`blocked` 不可升级、`conditional => stretch`，`eligible` 再按 must-have/preferred 的 semantic verdict 确定 `strong / good / low`；无百分制匹配概率，用户必须明确点击才会触发完整 Semantic Match。
- 已完成 MatchReport 持久化 runtime wiring：`match_reports` snapshot ORM、Repository/Query Repository、显式 Unit of Work 与 `20260810_0016` migration 定义已接入 `POST /match-report`；成功 runtime 追加一个不可变 snapshot 并返回 `dbWrites=1`。在任何 Semantic/Provider 工作前先检查 `match_reports` 表，缺表时稳定返回 `409 match_report_persistence_not_ready`，不会偷偷建表、写 Trace 或产生 Provider 成本。临时 SQLite 已验证 upgrade/downgrade、历史追加不覆盖、未 commit rollback；真实业务 DB 仍停在 `20260805_0015`，**尚未应用 0016 migration**。
- 已完成 `Match Eval v1` 基础设施：保留 3 条 Contract/Safety cases，并新增 10 条人工标注 synthetic quality cases；报告 verdict/evidence accuracy、workflow success、Trace coverage、混淆矩阵与逐案例 reason/Trace。fixture 全量验证 10/10 通过仅证明 harness 可重复，不代表真实模型质量。
- live Match Eval operator 默认不写正式业务 DB，真实 Provider 必须显式 `--confirm-live-cost` 且设置 `--max-cases`；当前没有自动质量放行阈值，真实结果必须人工复核。
- 已完成首轮 3-case `deepseek-v4-flash` live Semantic Match Canary：3 条 workflow 全部成功、2 条需要 Provider 且 Trace coverage=100%；Java direct 正确为 `matched`，无候选场景正确为 deterministic `not_matched`，MCP related 人工期望 `partial` 但模型返回 `not_matched`，首轮 verdict/evidence accuracy 均为 66.7%。该结果显示模型在 related-but-not-explicit 边界偏保守，不构成 release 通过证据，也未触发自动阈值或继续扩跑。
- 已完成 `Semantic Match prompt v2` 小型校准：加入 MCP/Function Calling 与 FastAPI/Python API 两个 `partial` 正例、MCP/React AI UI 的 `not_matched` 反例以及 Java direct 的 `matched` 锚点；同时明确 related 候选只是检索信号、不能自动 `partial`，related-only 仍绝不能 `matched`。synthetic quality Eval 10/10 与全量回归通过。
- 已完成 5-case `deepseek-v4-flash` Prompt v2 live Calibration Canary：3 个 related/transferable 正例全部为 `partial`，MCP/React AI UI 负例保持 `not_matched`，Java direct 保持 `matched`；verdict/evidence accuracy、workflow success、Trace coverage 均为 100%，且 `partial -> matched=0`、`not_matched -> partial=0`。首轮 v1 中 MCP `partial -> not_matched` 的过度保守错误在 v2 中被修复。该 5-case 校准集仍只是小样本边界证据，不构成 release 通过；v2 五次调用共 3002 input tokens，较 v1 Prompt 明显增加输入成本，后续扩大样本时需继续观察质量/成本权衡。
- 已完成 `semantic-match-blind-holdout-v1` 的 10-case `deepseek-v4-flash` live Eval：9/10 通过，verdict/evidence accuracy=90%，workflow success/Trace coverage=100%。3 个 `matched`、4 个 `partial` 全部正确；3 个 `not_matched` 中有 1 条 Kafka requirement + cron batch Evidence 被模型判为 `partial`，暴露“表面流程相似被误当可迁移核心能力”的假阳性边界。该 holdout 已消费，后续 Prompt 调整不得再把它当无偏验证集；正式业务 DB 未写入。
- 已完成 `Semantic Match prompt v3` 假阳性边界校准：`partial` 现在要求 Evidence 与 Requirement 共享 core mechanism / protocol-runtime semantics / data model / API pattern / implementation concern；generic scheduling、generic CRUD、共享业务场景或同属大类不再足以构成 `partial`。同时明确一般技术知识只能判断输入中已出现能力的关系，不能补造用户职业事实。synthetic quality harness 与全量回归通过。
- 已完成 `semantic-match-blind-holdout-v2` 的 10-case `deepseek-v4-flash` live Eval：3 `matched` / 4 `partial` / 3 `not_matched` 全部正确，verdict/evidence accuracy、workflow success、Trace coverage 均为 100%；10 条全部真实进入 Provider，使用 `semantic-match-v3`。该 holdout 与 calibration、已消费 holdout v1、Prompt v3 完整示例均保持不重复，正式业务 DB 未写入。该结果提供新的泛化证据，但仍不构成自动 release approval，也不能替代 ROADMAP 的 20 个真实岗位人工评审。
- 已完成 20 岗位人工 Match 评审的只读 readiness gate：`GET /api/v1/match-review/readiness` 复用每个岗位的 Match Input Readiness，并额外要求 `match_reports` persistence schema 已就绪；只有 20/20 岗位输入可信且持久化准备完成时才 `readyForHumanReview=true`。当前真实 DB 实测为 20 个 Job、0 个 input-ready、`match_reports` 表缺失，因此稳定 fail-closed，且 `dbWrites/providerCalls/traceRunsCreated` 均为 0。
- 尚未完成 MatchReport 正式 DB migration、20 岗位人工 Match 评审本身与基于 UserFeedback 的人工基准；Requirement 真实人工基线未通过前仍不能执行正式 Match。

### 任务

1. `Eligibility Gate`（确定性 / 半确定性硬条件判定）— v1 已完成；
2. `Evidence Retrieval`（从 UserProfile 拉相关 Evidence）— v1 deterministic candidate retrieval 已完成；
3. `Semantic Match`（LLM，基于 Evidence 与 JobRequirement）— guarded v1 已完成，真实 Provider 质量待验；
4. `MatchReport` Structured Output（`eligibility` / `recommendation` / `matchedRequirementIds` / `missingRequirementIds` / `evidenceLinks`）— immutable persistence + runtime fail-closed wiring 已完成；正式 DB migration 待授权；
5. 推荐等级：`strong` / `good` / `stretch` / `low` / `blocked` — deterministic policy v1 已完成；
6. `Match Eval` 数据集与断言 — v1 synthetic quality harness、Prompt v2 calibration canary、两轮 10-case blind holdout live Eval 与 prompt v3 假阳性边界校准已完成；20 岗位人工评审与 UserFeedback 人工基准待完成。

### 验收

至少选 20 个真实岗位人工评审：

- Top 推荐是否大体合理；
- 推荐理由是否能引用真实经历；
- 不匹配原因是否能引用 JD / JobRequirement；
- 数字 `score` 未被当作概率展示。

---

# Phase 5｜Batch Ranking + UserFeedback（P0）

建议周期：3–4 天

目标：从“单个岗位判断”到“一批岗位排序 + 人类反馈闭环”。

### 当前进度（2026-08-10）

- 已完成 Phase 5 首个纯确定性 Ranking Policy 切片：消费已存在的 `StoredMatchReport` snapshot，按 `strong > good > stretch > low > blocked` 稳定排序；`blocked` 默认隐藏，显式包含时始终沉底；同推荐等级保持输入顺序且不修改输入集合。
- 已完成 `SearchIntent.softPreferences` 的最小确定性次级排序：只在同一 recommendation 等级内，根据偏好词是否明确出现在岗位 `title / area` 中进行稳定排序；不得跨 recommendation 等级逆转，也不做语义猜测、LLM 调用或隐藏分数。
- 已完成批量 Ranking 的只读 MatchReport 查询基础：`AbstractMatchReportQueryRepository.list_latest_for_jobs(...)` / SQLAlchemy 实现可一次读取多个岗位，每个岗位只返回最新 immutable snapshot，去重重复 jobId、跳过缺失岗位并保持调用方请求顺序；不在 SQL 层复制 Ranking 策略、不生成新 Match、不调用 Provider/Trace，也不写正式数据库。
- 已完成纯只读 `BatchRankMatchReportsUseCase`：输入一批 jobId 后组合每岗最新 MatchReport、当前 `SearchIntent.softPreferences` 与对应 Job `title / area`，复用现有 Ranking Policy 输出稳定排序；无 report 时提前停止，缺 SearchIntent/Job 元数据时 fail-soft 保持基础排序，只读取实际有 report 的 Job 元数据。该 use case 不生成新 Match、不调用 Provider/Trace、不写数据库。
- 已完成 Batch Ranking 只读 API/Web query wiring：Backend `GET /api/v1/match-ranking` 接受重复 `jobId` 与 `includeBlocked`，Web `/api/match-ranking` 仅做 same-origin 参数/响应代理，不复制 Ranking 策略。Application 层在排序前过滤与当前 Profile `id/version` 或岗位最新 Requirement Extraction 不一致的 stale MatchReport；真实 `match_reports` schema 未准备时在 SQL 查询前 fail-closed 返回 `409 match_report_persistence_not_ready`。
- 已完成批量 Match 队列的首个只读 Planning 切片：`PlanBatchMatchUseCase` 对输入 jobId 稳定去重，复用单岗 Match Input Readiness 分类 `ready / input_blocked / persistence_blocked`；输入事实 blocker 优先保留，只有输入已可信但 `match_reports` schema 未就绪时才标记 persistence blocker。Planner 明确 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`，不运行 Eligibility/Semantic Match。
- 已完成首个受限批量 Match 执行编排切片：`ExecuteBatchMatchUseCase` 只消费 Planner 的 `ready` 项并复用现有单岗 MatchReport workflow；每次最多执行 10 个 ready job，超出部分稳定标记 `deferred_limit`，input/persistence blockers 原样保留，单岗失败隔离后继续后续岗位。成功任务聚合其真实 `dbWrites/providerCalls/traceRunsCreated`；如果任一任务抛异常，由于异常路径无法可靠证明已发生的 Provider/Trace 副作用，结果将 `sideEffectCountsComplete=false` 而不是猜测。
- 已完成受控 Batch Match HTTP contract：`POST /api/v1/match-batch` 复用上述 application orchestrator，`jobIds` 至少 1 个且 `maxReadyJobs` 在请求层硬限制为 1–10，不在 API 层复制 Match 策略；真实 DB smoke 使用现有岗位验证，在 Requirement 人工基线未通过时只返回 `input_blocked` 与结构化 blocker，`dbWrites/providerCalls/traceRunsCreated` 均为 0。正式业务 DB 未迁移，未真实执行 Match。
- 已完成 50-job 显式安全恢复契约：单次 Batch 请求最多声明 50 个岗位，但每轮仍只执行最多 10 个 `ready` 岗位；响应新增 `resumeJobIds`，只包含因本轮执行上限而**确定尚未运行**的 `deferred_limit` 岗位，并通过 `executionComplete` 表示是否仍有安全可继续的工作。失败任务不会自动加入恢复集合，因为异常路径不能可靠证明 Provider/Trace/DB 副作用是否已经发生。测试已验证 50 个全部 ready 的岗位可通过 5 轮显式续跑完成，同时每轮调用上限保持 10；该能力不等于正式业务已完成 50 岗位 Match，真实 Requirement 基线与 `0016` migration 门禁仍未满足。
- 已完成 UserFeedback 领域契约与确定性校验首切片：decision 固定为 `interested / maybe / rejected`，反馈必须绑定具体 immutable `matchReportId + jobId`；reasons 使用稳定枚举并去重，`rejected` 至少一个结构化 reason，`other` 必须附 note。同步收紧跨组件 JSON Schema 与 example；本切片不落库、不新增 API、不触发 migration。
- 已完成 UserFeedback persistence foundation：新增 immutable `user_feedback` ORM、Repository/Query Repository、显式 Unit of Work 与 `20260810_0017` migration 定义；Feedback 以外键绑定 `match_reports.id + jobs.id`，支持按 Feedback ID、MatchReport、Job 回查历史，追加写不覆盖旧反馈，未 commit 自动 rollback。新增只读 persistence readiness gate 与 SQLAlchemy schema inspector，同时要求 `match_reports` 和 `user_feedback` 表存在，缺失时返回结构化 blocker 且 `dbWrites/providerCalls/traceRunsCreated` 均为 0。migration 仅在临时 SQLite 验证 upgrade/downgrade，真实业务 DB 仍停在 `20260805_0015`，未执行 0016/0017 migration。
- 已完成 guarded UserFeedback 写入 use case 与 `POST /api/v1/user-feedback`：写入前先检查两张 persistence 表，再读取 immutable MatchReport 并校验请求 `jobId` 与报告绑定 Job 一致，最后才通过显式 Unit of Work 追加一条反馈；成功返回 `dbWrites=1 / providerCalls=0 / traceRunsCreated=0`。真实 DB 未迁移时稳定返回 `409 user_feedback_persistence_not_ready`，不会读取不存在的 MatchReport 表、更不会自动迁移或写入。
- 已完成 UserFeedback 只读历史回查：`GET /api/v1/user-feedback` 要求且只允许 `matchReportId` / `jobId` 二选一，复用 Query Repository 按 immutable MatchReport 或 Job 返回反馈历史，并显式返回 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`；schema 未准备时在任何反馈查询前继续 fail-closed `409 user_feedback_persistence_not_ready`，不触发 migration、Provider 或 Trace。
- 已完成 UserFeedback → Match Eval 的首个确定性统计基线：按 immutable `matchReportId` 精确关联 MatchReport，同一报告存在多次反馈时只取最新一次作为当前观察，同时保留完整反馈记录数；输出 decision 分布、recommendation × decision 矩阵、rejected reason 计数、缺失 MatchReport IDs 与覆盖数。该统计明确把反馈视为用户偏好观察而非客观 Match ground truth，`qualityGateApplied=false`，不生成准确率/概率或自动 release 结论；缺失报告不按 Job 猜测回填。
- 已完成按 Job 构建 UserFeedback Match Eval 观察的只读 application query：`UserFeedbackMatchEvalQueryUseCase` 在 persistence readiness 通过后读取该 Job 的 immutable Feedback 与 MatchReport 历史并复用同一确定性统计器；schema 未就绪时在任何 repository read 前 fail-closed。结果显式 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`，不把反馈升级为质量放行证据。
- 已完成 UserFeedback Match Eval 只读 HTTP query：`GET /api/v1/user-feedback/eval?jobId=...` 仅暴露按 Job 聚合的真实反馈观察、MatchReport 覆盖、rejection reason 与 recommendation × decision 分布，并固定 `qualityGateApplied=false`；空 jobId 在 HTTP contract 层返回 422，真实 `match_reports/user_feedback` schema 未准备时继续在 repository read 前返回 `409 user_feedback_persistence_not_ready`。该 API 不产生 DB 写入、Provider 调用或 Trace，也不输出准确率、概率或自动 release 结论。
- 已完成 v0.2 Target Cohort 的 UserFeedback 只读来源切片：跨 Job 读取 immutable Feedback 历史，每个 Job 只采用 `(createdAt, feedbackId)` 最新一条真实决策；`interested` / `maybe` 输出为带 `feedbackId + matchReportId + jobId` provenance 的候选，`rejected` 默认排除并单独记录。该切片只提供未来 TargetCohort 的可追溯输入，不创建 Cohort、不推断用户意图、不运行 Match/Provider/Trace；persistence schema 未准备时在任何 feedback read 前继续 fail-closed。

### 任务

1. 批量 Match 队列；
2. Ranking（Eligibility + Fit + SearchIntent.softPreferences）；
3. Blocked 沉底 / 默认隐藏；
4. `UserFeedback` 采集（interested / maybe / rejected + reasons）；
5. 反馈回查到 MatchReport；
6. 反馈作为 `Match Eval` 基准与 v0.2 `Target Cohort` 来源。

### 验收

- 可批量匹配至少 50 个岗位；
- 可按推荐等级排序；
- 用户反馈可回查；
- 反馈数据落库，可进入 Eval 统计。

> 到 Phase 5 结束，MVP v0.1 闭环完成。此时即可独立演示与评测，不必等 v0.2。

---

# Phase 6｜Target Cohort + Skill Gap（v0.2）

建议周期：4–6 天

目标：把岗位池变成用户自己的学习路线，而不是通用课程。

### 当前进度（2026-08-10）

- 已完成 TargetCohort 最小领域契约：`job-target.schema.json` 正式演进为 `TargetCohort`，新增 `selectionSource / sampleSize / createdFromFeedback`；Backend 提供 immutable `TargetCohortSnapshot`，稳定去重 `jobIds` 并冻结 `sampleSize`。`user_feedback` 来源必须对 cohort 内每个 Job 提供且只提供一条 `feedbackId + matchReportId + jobId` provenance；manual 来源不得伪造 Feedback provenance。该切片仅冻结领域/跨组件契约，不创建正式 DB 表、不新增 API、不运行 Provider/Trace，也不自动把 `maybe` 推断为正式 Target Cohort 成员。
- 已完成显式 Feedback selection → transient TargetCohort application use case：只接受当前 UserFeedback source 暴露的 immutable `feedbackId`，稳定去重并按用户选择顺序构建 `jobIds + feedbackId + matchReportId` provenance；过期/被拒绝/非当前候选的 Feedback 均 fail-closed，不按 Job 猜测回填。`maybe` 只有在用户显式选中时才可进入 Cohort，不会自动加入；结果固定 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`，本切片不持久化 Cohort、不新增 API。
- 已完成 TargetCohort → JobRequirement 的首个只读聚合切片：对 Cohort 内每个 Job 先复用现有 Job Requirement Fact Release Gate，只有全部岗位均 `releaseEligible=true` 才读取对应 latest immutable Extraction 并按 Cohort 顺序展开 Requirement facts；任一岗位未通过 release gate 时整个 Cohort `factsUsable=false` 且不读取 Requirement Repository，避免用部分岗位静默生成 Skill Gap。Release 检查后若 latest Extraction ID 发生变化也 fail-closed 为 `release_identity_changed`，不消费 stale facts；结果显式 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`，不回读 raw JD、不运行 Provider/Trace、不生成 Skill Gap。
- 已完成 TargetCohort capability 显式同义归一切片：只消费已 release 的 `skill` Requirement facts，将 `React.js / ReactJS / React`、`Node.js / NodeJS`、`Next.js / NextJS`、`Vue.js / VueJS` 等明确 alias 归并为稳定 canonical capability，同时保留原始 capability 标签、Requirement IDs、Job IDs 和 must-have/preferred/bonus 计数；未知能力保持原样，不做 fuzzy/LLM 语义合并。上游 facts 不可用时继续 fail-closed，结果固定 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`。
- 已完成 TargetCohort 市场能力 vs Profile 的首个确定性事实比较层：复用同一显式 capability alias 规则，把已归一的市场 skill 与 Profile 明确 Skill 做 exact canonical 对齐，并区分 `evidenced / unevidenced / missing`；每项结果同时保留 Requirement IDs、Job IDs、Profile Skill IDs 与 Evidence IDs，供后续 SkillGap 指标使用。该层不做 fuzzy/LLM 语义推断，不把“Profile 中有技能名但无 Evidence”升级为已覆盖；上游市场 facts 不可用时 fail-closed，结果固定 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`。当前切片本身不负责建立 Profile release eligibility，调用方仍必须只传入已确认的 Profile facts。
- 已完成 SkillGap 四指标的确定性计算基础：对每个 capability 计算 `targetCoverage = 要求该能力的岗位数 / Cohort 岗位数`、`mustHaveRatio = must-have Requirement 数 / 该能力 Requirement 总数`，`evidenceCoverage` 仅在存在明确 Profile Evidence 时为 1，否则为 0，绝不把“技能名存在但无证据”伪装成部分 Evidence；`gapSeverity` 再组合市场覆盖、must-have 权重与显式 `evidenced / unevidenced / missing` 缺口状态，其中 unevidenced 使用中间缺口权重、missing 使用完整缺口权重。每项继续保留 `supportingRequirementIds / supportingJobIds / profileSkillIds / evidenceIds`；数值仅作为后续排序信号，不解释为求职成功概率或模型质量分数。上游 facts 不可用或 Cohort 为空时 fail-closed，且不写 DB、不调用 Provider、不创建 Trace。
- 已完成 SkillGap 的 P0/P1 确定性优先级契约：只消费上述透明 `gapSeverity`，完整 Evidence 覆盖的 capability 不进入 Gap backlog；`gapSeverity >= 0.5` 标为 P0，其余真实 Gap 标为 P1，并按 severity、targetCoverage、capability 稳定排序。因为 severity 已同时包含目标岗位覆盖、must-have 权重和显式 Evidence 缺口，优先级不会退化成“出现频率高就是 P0”；每项继续透传 `supportingRequirementIds / supportingJobIds / profileSkillIds / evidenceIds`。该切片不生成 Action Plan、不写 DB、不调用 Provider、不创建 Trace。
- 已完成 P0/P1 Action Plan 的最小确定性契约：只消费已排序 SkillGap，`missing` 明确为“能力与证据均缺失”，完成条件要求存在已确认 Profile Skill 且至少一条已确认 Evidence 与该 Skill 关联；`unevidenced` 明确为“已有 Skill、缺已确认 Evidence”，完成条件只要求补齐已确认 Evidence。每项继续透传 priority、市场覆盖、must-have 比例、gapSeverity 与 `supportingRequirementIds / supportingJobIds / profileSkillIds / evidenceIds`，因此可以回答“为什么重要 / 当前缺什么 / 什么算补齐”；本切片不生成课程、项目、预计工时等学习内容，不写 DB、不调用 Provider、不创建 Trace。
- 已完成 Phase 6 Gap Detail 只读验收投影：把既有 Action Plan 事实重新组织为单项可展示契约，直接暴露 `targetCoverage / mustHaveRatio / gapSeverity`、`supportingRequirementIds / supportingJobIds`、`profileSkillIds / evidenceIds`、当前缺口状态与 completion criteria，对应“为什么重要 / 哪些岗位要求 / 当前证据 / 具体缺什么 / 做到什么算补齐”五个验收维度；该层不补造解释、课程或经历，不读取 raw JD，不写 DB、不调用 Provider、不创建 Trace，上游 facts 不可用时继续 fail-closed。
- 已完成 transient Target Cohort Gap Detail Backend HTTP contract：`POST /api/v1/target-cohort/gaps` 只接受用户显式选择的当前 `selectedFeedbackIds`，依次复用 Feedback candidate → transient Cohort → Requirement release gate → capability normalization → confirmed Profile comparison → SkillGap metrics → P0/P1 → Action Plan → Gap Detail 的既有确定性链路。过期/已拒绝/非当前反馈选择返回结构化 `409 target_cohort_selection_invalid`；真实 `match_reports/user_feedback` schema 未准备时在 Feedback repository read 前继续 `409 user_feedback_persistence_not_ready`。接口固定 `dbWrites=0 / providerCalls=0 / traceRunsCreated=0`，真实 DB smoke 已确认 revision、Job/Extraction/Trace 计数前后不变。
- 已完成 Phase 6 最小 Web 展示链路：新增 same-origin `POST /api/target-cohort/gaps` proxy 与 `/gaps` 页面，用户可显式提交已选择的 Feedback IDs，并逐项展开 Gap，直接查看“为什么重要 / 哪些岗位要求 / 当前证据 / 具体缺什么 / 做到什么算补齐”。Web 只展示 Backend 已计算事实，不复制 gapSeverity/coverage 策略、不调用 Provider、不创建 Trace，也不执行 migration；主导航已加入“能力差距”。真实业务 DB 仍停在 `20260805_0015`，因此在正式 0016/0017 migration 和真实 Feedback 数据完成前，该页面会继续通过 Backend readiness gate fail-closed。

### 任务

1. 创建 `Target Cohort`（收藏岗位 / UserFeedback 聚合，概念从 `JobTarget` 演进）；
2. 复用 `JobRequirement` 聚合需求；
3. 归一化同义技能；
4. 市场要求 vs Profile；
5. 生成 `SkillGap`：优先级不单看频率，引入 `targetCoverage` / `mustHaveRatio` / `evidenceCoverage` / `gapSeverity`；
6. 生成 P0/P1 Action Plan；
7. 每项建议关联 `supportingRequirementIds`。

### 验收

用户点击任一 Gap，可以看到：

```text
为什么重要
哪些岗位要求（JobRequirement）
我当前有什么证据
具体缺什么
做到什么算补齐
```

---

# Phase 7｜Job Preparation（v0.2）

建议周期：3–5 天

目标：让分析直接服务于投递和面试。

### 当前进度（2026-08-11）

- 已完成 Phase 7 首个只读 Job Preparation Readiness Gate：复用既有 Match Input Readiness，只在当前已确认 Profile/SearchIntent 与当前 JobRequirement Fact Release Gate 同时通过时冻结 `profileId/profileVersion/extractionId/requirementCount` 作为后续 Resume / Interview 准备输入身份；任一事实门禁未通过时保持 blockers 并 fail-closed。该切片不生成 Resume Delta、面试题或学习建议，不读取 raw JD、不写数据库、不调用 Provider、不创建 Trace。
- 已完成 Resume Delta 的最小确定性事实契约：只消费上述 frozen readiness、当前 confirmed Profile 与同一 immutable Requirement Extraction；仅对 `skill` Requirement 使用显式 capability alias 做 exact canonical 对齐。只有已匹配 Profile Skill 且链接 confirmed Evidence 的 Requirement 才进入 `highlights`；Skill 名存在但无 Evidence 明确标记 `unevidenced`，Profile 不存在该 Skill 则标记 `missing`。Profile/Extraction 身份变化或 readiness 未通过时 fail-closed；本切片不生成简历文案、不把缺失能力改写成用户经历，也不写 DB、不调用 Provider、不创建 Trace。
- 已完成项目/经历排序的最小确定性事实层：只对 Profile 中 `project/work` 类型的 confirmed Evidence 建议前置顺序，并且只有当 Evidence 通过显式 Profile Skill 链接命中当前 released `skill` Requirement 时才进入候选；不读取 Evidence summary 做关键词或语义猜测。排序先看覆盖的 `must_have` Requirement 数，再看总 Requirement 覆盖数，同分时保持 Profile Evidence 原始顺序；每项保留 `evidenceId/evidenceType/supportingRequirementIds/matchedCapabilities` provenance。Readiness、Profile version 或 Extraction identity 变化时 fail-closed；本切片不生成项目文案、不调用 Provider、不创建 Trace、不写 DB。
- 已完成 STAR / 项目讲述重点的最小事实选择契约：只消费上述已排序 Project/Work Evidence，并逐项回接同一 frozen Profile 的原始 confirmed Evidence summary 与同一 released Extraction 中的 supporting Requirement 原文；输出继续保留 Evidence/Requirement IDs、matched capabilities 与 must-have/coverage 计数。该契约刻意不定义或生成 `situation/task/action/result`、指标、职责或成绩，避免把后续表达层需要的结构化讲述误写成用户真实经历；Priority/Profile/Extraction identity 或 provenance 不一致时 fail-closed。本切片不读取 raw JD、不调用 Provider、不创建 Trace、不写 DB。
- 已完成预计面试问题的最小确定性事实候选契约：对同一 released Requirement 按 `must_have > preferred > bonus` 生成稳定准备优先级，同级保持 Extraction 原始顺序；`skill` Requirement 只复用 Resume Delta 已确认的 `supported / unevidenced / missing` Evidence 状态，并回接真实 Profile Evidence summary，非 skill Requirement 明确标记 `not_assessed`，不做文本或语义猜测。该契约只回答“哪些 Requirement 值得重点准备、哪些已有事实可支撑、哪些存在缺证据风险”，刻意不定义或生成 `question / answer / sample_answer / metric`；Readiness/Profile/Extraction/Resume Delta identity 或 provenance 不一致时 fail-closed。本切片不读取 raw JD、不调用 Provider、不创建 Trace、不写 DB。

### MVP 交付

- Resume Delta（简历调整建议，非整份重写）；
- 项目排序建议；
- STAR / 项目讲述重点；
- 预计面试问题；
- 面试前补习清单。

### 验收

所有建议只能使用 UserProfile 中已存在的事实，不得虚构项目和成绩。

---

# Phase 8｜Career Agent（P1）

目标：让 `Career Agent` 成为面向用户的统一入口，去**编排**已经成熟的 Workflow（Profile / SearchIntent / Requirement / Match / Ranking / Gap / Prepare）。

### 关键边界（ADR-0004）

- Agent 不直接实现业务能力；
- Agent 组合稳定 Workflow；
- 所有业务事实仍来自 `JobRequirement` 等统一模型；
- 多 Agent 不进入本期。

### 任务

- 统一对话入口；
- Tool Registry（复用 Workflow 能力，不是把业务全写成 Agent Tool）；
- Context Builder（P0 用户确认事实 / 当前 Job，P1 相关 Evidence）；
- `Agent Eval`。

---

# Phase 9｜Growth Loop / Collector Sync（P1）

目标：形成真正的 `Gap → Action → Evidence → Re-match`，并从“下载 JSON → 上传”升级为一键同步。

### 任务

- ActionItem 状态；
- 学习 / 项目 Evidence 录入；
- Profile 更新与重新匹配；
- Collector API 同步（插件 POST Agent API，增量导入，保留 JSON 兜底）；
- “补完这个能力后影响了哪些岗位”对比；
- 新岗位提醒 / 定时更新（价值验证后再做）。

---

# 当前最推荐的开发顺序

```text
Phase 0.5  产品与领域基线（本文档 + PRD v2.0 + DOMAIN-MODEL + ADR）
Phase 1    Job Data Foundation（POST /api/v1/job-imports）
Phase 2    Profile + SearchIntent
Phase 3    Requirement Intelligence（JobRequirement）
Phase 4    Single Job Match（Eligibility + Fit）
Phase 5    Batch Ranking + UserFeedback
--- v0.1 闭环完成，可独立演示与评测 ---
Phase 6    Target Cohort + Skill Gap
Phase 7    Job Preparation
Phase 8    Career Agent
Phase 9    Growth Loop / Collector Sync
```

不要先做漂亮 Dashboard，也不要先做 Multi-Agent。先把 Phase 1–5 跑通，且每个 LLM Pipeline 从第一天接 Eval。
