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

## MVP 破局五阶段（2026-08-25）

以“先解除外部 Provider 阻塞，再打通用户价值主循环”为当前最高优先级。Requirement Extractor 冻结在 `requirement-extractor-v42.95 / requirement-semantics-v42.95`，除非出现用户可见且 deterministic replay 可复现的 P0 缺陷，不再继续语义版本微调。

- [ ] 阶段 1：切断 Provider 人质状态
  - [x] OpenAI-compatible Requirement adapter 支持显式 opt-in 的 bounded retry + exponential backoff；仅重试 `429/503/504` 与 timeout，非重试型 HTTP/structured-output 错误保持立即失败；默认单次调用，避免绕过现有 Provider 成本预算。
  - [ ] 可测试 circuit breaker + 可配置 fallback provider/model，并与真实调用预算对齐。
  - [ ] Offline replay acceptance 可在无 Provider 情况下作为 MVP gate；live Provider 降为非阻塞 smoke。
  - [ ] Provider outage 聚合记录，不再为每次 503/504 单独生成 blocker commit。
- [ ] 阶段 2：冻结抽取器 v42.95，并增加版本 guard / P1 调优声明。
- [ ] 阶段 3：100% 离线 `JobRequirements → MatchReport → Ranking → Top N + evidenceLinks` 可演示切片。
- [ ] 阶段 4：默认 MVP quality gate 降配为 offline replay + match/ranking tests + lightweight eval；live canary 保留为诊断/周期 smoke。
- [ ] 阶段 5：落地抽取版本时间盒与 E2E slice / Top-N 可用性进度指标。

每项只有在有自动测试、可运行命令/API 或工程文档证据后才勾选；Provider outage 本身不再触发语义版本 bump。

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
- 2026-08-11：完成 canonical 20-JD provenance audit。Git 忽略的 `data/private/requirement-acceptance/datasets/formal-ef5f1f0c1287ff1b.json` 仍存在且是唯一 canonical dataset；formal preflight 重新验证 fingerprint `ef5f1f0c1287ff1b1784f8cac79197635ce34ae070db996dae0889145c5fc988`、sourceVersion `1.4.6`、20/20 Jobs，历史 Session Manifest 也指向同一 fingerprint。真实 SQLite 已有 verified 0015 backup 后升级到 Alembic `20260810_0017`，迁移时旧 `20 Jobs / 4 Requirement Extractions / 93 Traces` 计数保持不变，`match_reports/user_feedback` 新表为空，integrity/foreign-key check 通过。当前 `requirement-extractor-v4` readiness 为 `workflowReady=true / providerExecutionAllowed=true / nextAction=run_canary`；历史 v1/v2/v3 Run 不作为 v4 当前质量证据复用。
- 2026-08-11：Requirement Extraction 长请求增加显式英文 processing 状态、spinner 与 `aria-live` 提示；Readiness Web 从工程控制台式布局改为“当前能否继续 / 为什么 / 下一步”主流程，普通用户 blocker 使用产品文案，必须填写的审核信息在主流程可直接处理，Provider/DB revision/fingerprint/raw blocker 等字段默认收进折叠的技术详情。页面仍保持 read-only，不能启动 Provider、迁移或提交人工质量结论。
- 2026-08-11：完成 `requirement-extractor-v4` 正式 Live Canary 首轮 3 次受控 Provider 调用，均使用 canonical 20-JD fingerprint `ef5f1f0c1287ff1b1784f8cac79197635ce34ae070db996dae0889145c5fc988`、`deepseek-v4-flash` 与 `requirement-extraction-v1`。三次新调用均成功生成 Extraction + Trace，分别产生 10 / 29 / 25 条 Requirement，Trace error 均为空；累计 input/output token 为 1446 / 4947。Operator 在累计 3 次后自动切到 `nextAction=review_canary / providerExecutionAllowed=false`，未自动提交 Continue/Stop，也未继续运行剩余 Job。该证据只证明 v4 真实链路与结构化输出可运行，不代表人工质量通过。
- 2026-08-11：用户显式提交 Canary `Continue`，系统不可变记录 review `reqacceptcanary_e59d1588065147babc626c92e16c1902`，只冻结首轮 3 个实际 attempted Case / Extraction / Trace，不附加任何未声明的质量结论。随后按受控 Resume Operator 执行单轮最多 10 次真实 Provider 调用：8 次成功生成 Extraction + Trace，2 次被严格输出校验拒绝（1 条 `originalText` 不存在于原 JD、1 条 `evidenceSpan` 不存在于原 JD），失败 Case 均保留 Trace 且没有写入无效 Extraction；预算未超限、dataset hash 未变化、未自动提交新的人工决定。Run 当前累计 `attemptedCalls=13`，`completedCaseCount=14`，状态为 `partial`，还有 2 个失败 Case 与 4 个 deferred Case 待后续受控处理。
- Fixture 不能正式 Review，失败 Live 只能 rejected，合格 Live accepted 后才能成为正式 baseline；
- Job 详情页可显式触发新版本并展示 Requirement ID、importance、evidenceSpan、confidence 与 Trace；
- 2026-08-12：继续执行单轮最多 6 次正式 Requirement Acceptance Resume，dataset hash 保持不变且无 blocker；实际 6 次 Provider 调用中 4 次成功生成 Extraction + Trace，2 次再次被严格输出校验拒绝（1 条 `originalText` 不存在于原 JD、1 条重复 Requirement），无缺失 Trace、未超预算、未自动提交人工结论。Run 当前累计 `attemptedCalls=19`，20 个 Case 中已有 18 个具备可用 Extraction，仍有 2 个失败 Case 待后续受控重试，尚未生成 Manual Review Batch。
- 2026-08-12：收尾重试最后 2 个失败 Case。首轮 2 次调用中 `前沿部署工程师(FDE)` 成功生成 Extraction + Trace，`高级开发工程师（AI 平台 / 模型融合方向）` 仍因模型生成的 `originalText` 不存在于原 JD 被严格拒绝；随后仅对该最后 1 个 Case 再做 1 次受控重试，仍以同类 `originalText` 校验失败。该 Case 的失败已连续复现，所有失败均保留 Trace、未写入无效 Extraction、dataset hash 未变化、无缺失 Trace、未超单轮调用上限，也未放宽事实校验来凑齐证据。当前 20 个 Case 中 19 个具备可用 Extraction，1 个稳定失败；下一工程切片应修复或增强 extractor 对 verbatim `originalText` 的可靠输出，再继续正式 Acceptance，而不是继续无上限 Provider 重试。
- 2026-08-12：针对 v4 最后稳定复现的 verbatim grounding 失败完成 `requirement-extractor-v5` 最小修复：当 `originalText/evidenceSpan` 中恰好一项已被确定性验证为 JD 连续原文时，只允许用该真实原文回填另一项；两项都不在 JD 时仍 fail-closed，不做 fuzzy matching、改写或猜测。由于行为语义发生变化，Extractor Version 明确升级为 v5，旧 v4 Acceptance 不能冒充 v5 正式质量证据。v5 首轮 3-case Live Canary 使用同一 canonical 20-JD dataset 与 `deepseek-v4-flash`：1 Case 成功生成 Extraction + Trace，1 Case 因两侧 verbatim grounding 仍不满足被严格拒绝，1 Case 遇到 Provider HTTP 429 并保留失败 Trace；dataset hash 未变化、attempt budget 未超限、无缺失 Trace、未自动提交人工 Continue/Stop。当前 v5 Run 已停在 `review_canary` 人工门禁。
- 2026-08-12：用户显式提交 v5 Canary `Continue`，系统不可变记录 review `reqacceptcanary_00e2bc74a4b44b4fb1537006bcdd8626`，仅冻结首轮 3 个 attempted Case / 1 个成功 Extraction / 3 个 Trace，不附加额外质量结论。随后按受控 Resume Operator 执行单轮最多 10 次真实 Provider 调用；10/10 均因上游 Provider HTTP `503/504` 失败并保留 Trace，未创建任何无效 Extraction、dataset hash 未变化、无缺失 Trace、未超预算、未自动提交新的人工决定。v5 Run 当前累计 `attemptedCalls=13`，状态仍为 `partial`：1 个 Case 已成功、10 个 Case 处于失败状态、9 个 Case deferred。由于本轮失败集中为外部 Provider 可用性问题，停止继续自动重试以避免无意义成本，待 Provider 恢复后再从同一 immutable Continue review 受控 Resume。
- 2026-08-14：按 outage 恢复策略仅执行 1 次有界 Provider probe；同一 immutable v5 Run / Continue review 成功生成新的 Extraction `reqrun_8fab6ae1161547a785d4b6950192f04c` 与 Trace `run_77d41b81dd7843aaa081d31e8abef46e`，无 429/503/504、无缺失 Trace、未超预算，dataset hash 保持不变。该 probe 只证明 Provider 已恢复可用，不构成 Requirement 质量放行；本轮不继续扩跑，后续轮次可恢复 Controlled Resume，每轮仍最多 10 次调用。
- 2026-08-14：对一次 CLI 超时的 v5 Controlled Resume 做副作用对账。超时前 readiness 为 `attemptedCalls=14`，恢复连接后的同一 immutable Run 只读 readiness 明确为 `attemptedCalls=20 / status=partial / nextAction=resume_run / blockers=[]`，因此确认该超时进程实际已发生 6 次 Provider attempt；不能把 CLI 超时误判为“零调用”。为避免重复成本，本轮不再追加 Provider 调用，并把后续恢复起点冻结在 attempt 20；该对账不声称 6 次调用的质量结果，也不改变 Continue review、dataset fingerprint 或 v5 证据边界。
- 2026-08-14：继续同一 immutable v5 Run / Continue review 的 Controlled Resume。零调用复核发现先前超时进程已进一步推进到 `attemptedCalls=27`，11/20 Case 已具备 Extraction；最近成功 Trace 证明 Provider 已恢复，因此本轮按剩余 Case 数将预算从 10 收紧为 9 后执行。实际 9 次 Provider attempt 中 4 次成功生成 Extraction + Trace，5 次失败且全部保留 Trace：2 次为 Provider HTTP `503/502`，3 次为严格 verbatim grounding 校验失败（`originalText` 不在 JD）；无缺失 Trace、未超预算、dataset hash 未变化、未自动提交人工质量结论。Run 当前累计 `attemptedCalls=36`，15/20 Case 已具备可用 Extraction，仍有 5 个失败 Case 待后续受控处理；下一轮不得直接假设 outage，需先只读检查最近失败分布与 Provider 可用性，再决定 1-call probe 或最多 5 次 Resume。
- 2026-08-14：用户在本机交互式执行剩余 5 Case 的 Controlled Resume，同一 immutable v5 Run 从 `attemptedCalls=36` 推进到 `41`；5 次调用中 3 Case 成功，最终达到 18/20 Extraction，2 Case 仍因 `originalText does not occur in Job description` 被严格拒绝。只读 Trace/JD 对账确认两条失败均为 whitespace-only 漂移：模型内容与 JD 非空白字符一致，但原 JD 含异常字符间空格/换行，导致 exact substring 校验失败。已完成 deterministic grounding 修复：只有在去除空白后能唯一映射到 JD 时，才回写该唯一匹配的真实 raw JD slice；重复匹配继续 fail-closed，不引入 fuzzy matching、同义改写或语义猜测。针对性 7 tests、Backend 637 tests、Web 74 tests、TypeScript、production build、E2E Smoke 与 `git diff --check` 均通过；真实 DB 保持 integrity ok，本切片未新增 Provider 调用或正式 DB 写入。
- 2026-08-14：在 whitespace grounding 修复后，对同一 immutable v5 Run / Continue review 执行剩余 2 Case 的受控 Resume，预算严格限制为 2；其中 `高级开发工程师（AI 平台 / 模型融合方向）` 成功生成 Extraction + Trace，Run 达到 19/20，另一个 `高级ai工程师` 仍因 `originalText` 未命中 JD 被严格拒绝。新 Trace/JD 对账显示失败来自半角/全角 ASCII 标点宽度漂移（例如 JD `(LLM)` 被模型输出为 `（LLM）`），不是 Provider outage。已补 deterministic punctuation-width recovery：仅对 fullwidth ASCII punctuation 做宽度归一，且只有 normalized quote 在 JD 中唯一命中时才回写真实 raw JD slice；不归一字母/数字、不做 fuzzy/语义匹配。针对性 tests、Backend 638 tests、Web 74 tests、TypeScript、production build、E2E Smoke、compileall 与 `git diff --check` 均通过。本轮不再追加 Provider 调用，下一轮只需从 attempt 43 对最后 1 Case 做最多 1 次受控 Resume。
- 2026-08-14：完成 `grounding-v1` hardening 与 Trace repair audit；新增 mixed format、semantic/case/number rewrite、duplicate-after-repair、raw JD persistence 回归，仍只允许唯一 whitespace / ASCII punctuation-width 恢复并回写 raw JD。Backend 644、Web 74、build/smoke/compileall 均通过，本切片无 Provider、真实 DB 写入或 migration。
- 2026-08-15：`requirement-extractor-v5` 正式 20-case Acceptance 已完成并冻结 Manual Review 证据；人工审核更正后的 Batch `reqreviewbatch_b49be6930fd241afa888930b74311023` 为 16 accepted / 4 rejected / stale=0，4 个 Reject 均为 `wrong_importance`，对应「至少 N 项被拆成每项 must-have」「任职要求无软化措辞却系统性降为 preferred」「优先只修饰相邻专业条件却连带降级学历门槛」等真实语义错误。用户已提交不可变最终 `reject_for_match`（`reqbatchdecision_8fb929125fcb489ba7b5f6cac87f4eff`）；accepted baseline 保持不存在，v5 不得进入 Match。
- 2026-08-15：完成下一最小修复切片 `requirement-extractor-v6 / requirement-extraction-v2`。根因是 v5 Prompt 将「未出现显式强制措辞」默认分类为 preferred，与正式人工审核对任职要求的语义不一致。v2 Prompt 改为：显式任职/资格区默认 must-have，只有该具体条件被软化时才降级；`优先/加分/preferred/optional` 只作用于其修饰子句，硬/软条件混合时要求拆分；`至少 N 项/任一项/任意一种` 保留 mandatory group constraint，但不得把每个备选子项独立标为 must-have。新增 Prompt contract 回归测试，Backend 全量 645 passed；本切片未调用 Provider、未写真实 DB、未迁移。下一步必须用新的 v6/v2 证据链重新执行正式 Acceptance，旧 v5 rejected 证据只能作为历史回归。
- 2026-08-15：启动全新的 v6/v2 正式 Live Canary，仍绑定 canonical 20-JD fingerprint `ef5f1f0c1287ff1b1784f8cac79197635ce34ae070db996dae0889145c5fc988`，预算严格限制为 3 次。三次真实 Provider attempt 均返回 HTTP 503，0 个有效 Extraction、3 个失败 Trace、17 个 Case deferred；dataset 文件 hash/字节数执行前后保持一致，attempt budget 未超限。新 Run 为 `reqacceptrun_87d26bcae7e248cb8fbd62cd783a1f38`，当前 `attemptedCalls=3 / nextAction=review_canary / runStatus=awaiting_canary_review`。该结果只证明当前 Provider outage，不构成 v6 质量判断；必须由人工明确 Continue/Stop，且若 Continue，后续恢复前按 outage 策略每轮最多 1 次恢复 probe。
- 2026-08-16：修复 Requirement Provider outage 分类与 Canary 展示。OpenAI-compatible 429/503/504 现在映射为 `RequirementExtractorUnavailableError`，Acceptance 在首个有 Trace 的 unavailable attempt 后立即停止后续 Provider 调用并将剩余 Case deferred；普通 500 仍保持 case-specific failure。Canary UI 同时兼容历史 Run，将旧 `RequirementExtractorFailedError + HTTPStatusError(status=429/503/504)` 识别为 Provider outage，保留 Trace/Case 原始证据但不再误导为 v6 质量失败。Backend 648、Web 76、typecheck/build 均通过；localhost 已验证旧 v6 Run 显示 outage 语义，真实 DB 仍为 3 attempts / 3 failed / 17 deferred / 3 traces，无 Provider 调用、无真实 DB 写入、无 migration。
- 2026-08-16：Provider 恢复后新建独立 v6/v2 Canary Run `reqacceptrun_5e1ba4a4f086440fa4ae5cd68717b3ed`，3/3 调用均成功生成 Extraction + Trace；人工前置只读审查仍发现两类真实语义缺陷，因此不得 Continue：其一，`N 年经验，优秀者可放宽/豁免` 被拆为独立 must-have 阈值与 preferred 豁免，导致可豁免候选仍被硬门槛拒绝；其二，`如/例如/such as/e.g.` 示例项被拆成多个独立 must-have。完成下一最小修复 `requirement-extractor-v7 / requirement-extraction-v3`：豁免只软化其修饰阈值，不再保留独立硬门槛或把豁免本身当加分项；示例列表只说明 umbrella requirement，不得自动生成独立 must-have child。新增 Prompt contract 回归并升级 cohort，Backend 648、Web 77、typecheck/build/E2E Smoke 均通过；v7 零调用 readiness 为 `workflowReady=true / providerExecutionAllowed=true / nextAction=run_canary / attemptedCalls=0 / blockers=[]`；修复切片无 Provider 调用、无真实 DB 写入、无 migration，旧 v6 证据不得作为 v7 正式验收证据。
- 2026-08-16：v6 recovery Run 已冻结 `stop` 结论后执行全新 v7/v3 Canary Run `reqacceptrun_2992858221a94b1aaa02fce298a52b81`；3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。只读审查确认“如/例如”示例项已不再拆成独立 must-have，但仍存在两类阻断性语义错误：`2 年以上经验，优秀者可放宽` 仍保留独立 must-have 年限且丢失豁免；`至少一个方向` 虽保留总约束，却把四个方向列表分别输出为 must-have。故 v7 不得 Continue。完成 `requirement-extractor-v8 / requirement-extraction-v3`：在 grounded LLM 输出后新增 `requirement-semantics-v1` 确定性护栏，仅基于 exact JD span 与显式 waiver/cardinality 标记修复；同 clause 的可豁免阈值合并真实证据并降为 non-blocking preferred，冗余 waiver item 删除；`at least N / one of / 任意一个` 的 mandatory group 保持 must-have，受该列表 scope 控制的 child option 从独立 must-have 降为 preferred。Trace 新增 `semanticPolicyVersion/semanticRepairs` 审计字段。新增泛化与反例回归，Backend 653、Web 77、typecheck/build/E2E Smoke 均通过；本 v8 工程切片未新增 Provider 调用、未修改历史 v7 证据、无 migration。
- 2026-08-16：执行全新的 v8/v3 正式 Live Canary Run `reqacceptrun_f63694a9418c4236890208ebfb15d91d`，仍绑定 canonical 20-JD fingerprint `ef5f1f0c1287ff1b1784f8cac79197635ce34ae070db996dae0889145c5fc988`，预算严格限制为 3 次；3/3 Provider 调用成功、0 failure、17 deferred、Trace 3/3 完整、dataset 文件 SHA-256 前后均为 `851909dfa62c65f6b0d5c33fe0b114c4a3da64d1ec28e4b5a9a490cc53253106`，未超预算。只读质量审查确认 alternative/cardinality child 已修正：Harness 的四个方向均为 preferred，总约束仍为 must-have；但 v8 仍存在 blocking importance scope defects：模型若直接输出包含 `可放宽` 的整句 must-have，`requirement-semantics-v1` 不会触发修复（Harness 的 `2 年以上软件开发经验,特别优秀者可放宽(不限年限)` 仍为 must-have，Trace `semanticRepairs=[]`）；另有尾部 `优先` 污染前置硬条件的整句合并错误，例如 `熟悉智能体技术栈...,有落地项目经验者优先` 与 `有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先` 均被整体降为 preferred。故 v8 不得 Continue 或扩跑，Run 停在 `review_canary` 等待真实人工 Stop/Continue；下一工程切片应先以这两类真实输出形态写泛化失败测试，再扩展确定性 scope repair，而不是继续 Provider 调用。真实 DB 当前 integrity ok / Requirement Extractions 57 / Traces 180 / MatchReports 0 / UserFeedback 0；Backend 653、Web 77、typecheck/build/E2E Smoke 均通过。
- 2026-08-16：基于 v8 正式 Canary 的冻结输出完成下一最小修复 `requirement-extractor-v9 / requirement-extraction-v3 / requirement-semantics-v2`。v8 已修正 `至少一个方向` 的 child scope，但真实审查仍发现：Harness 的完整 waiver 句 `N 年以上...,优秀者可放宽(不限年限)` 在模型已经合并成单个 must-have 时未被 v1 护栏降级；另有 `硬要求,软条件者优先` 被整句标为 preferred，导致前置硬条件被错误降级。v9 新增确定性规则：对 exact-grounded 的 experience threshold，只有显式本地年限/优秀候选 waiver 才从 blocking must-have 降为 preferred，并排除 `学历/专业/年龄等其他目标可放宽` 的反例；对 narrow trailing `有…经验者优先` / `熟悉…者优先` 混合句，拆成 must-have 硬前缀与 preferred 软后缀，同时保留 `A，或 B 者优先` 整组软条件不拆。使用真实 v8 Case 0/1 做离线重放后，`熟悉智能体技术栈` 与 `主导千万级 AI 项目经验` 恢复为 must-have，两个尾部优先项保持 preferred，Harness waiver 整句变为 preferred，四个 alternative 方向仍保持 preferred。新增泛化/反例回归，Backend 657、Web 77、typecheck/build/E2E Smoke 均通过；v9 零调用 readiness 为 `workflowReady=true / providerExecutionAllowed=true / nextAction=run_canary / attemptedCalls=0 / blockers=[] / providerCalls=0 / dbWrites=0`。v8 Run `reqacceptrun_f63694a9418c4236890208ebfb15d91d` 仍停在人工 `review_canary`，不得绕过人工 Stop 直接启动 v9。
- 2026-08-16：真实状态已继续推进：v8 Run 已由用户提交不可变 `stop` 后启动 v9 Canary Run `reqacceptrun_5e5c29c59ff2401daeef64c8ba5b81fa`。首轮 Case 0 成功、Harness Case 因 Provider HTTP 504 失败后按 fail-fast 停止扩跑；本轮严格按 outage 策略仅执行 1 次 recovery probe。Provider 已恢复响应，但 Harness 再次未生成可用 Extraction，失败从网络问题收敛为严格 grounding 拒绝：模型把 JD 原文 `但至少要能独立 owner 一个核心方向` 改写为 `至少能独立 owner 一个核心方向`，丢失“要”，属于内容改写而非 whitespace / punctuation-width 格式漂移，因此 `grounding-v1` fail-closed 是正确行为，不应放宽为 fuzzy matching。该 probe 有完整 Trace `run_68a432d866ff4f3781f5e2a848c2dbc3`，dataset SHA-256 前后保持 `851909dfa62c65f6b0d5c33fe0b114c4a3da64d1ec28e4b5a9a490cc53253106`，预算未超限；v9 Run 现累计 `attemptedCalls=3`，状态 `awaiting_canary_review / nextAction=review_canary`，不得再追加 Provider 调用或自动代签 Continue/Stop。当前代码未修改，Backend 657、Web 77、typecheck/build/E2E Smoke/compileall 均通过；下一步只允许真实人工审查 v9 Canary 证据并明确 Continue/Stop。
- 2026-08-16：用户随后已对同一 v9 Run 提交不可变 `Continue`（`reqacceptcanary_5af0d0f68d3e4a2ba5a4b93ee5472c5e`），受控恢复后前 4 个 Case 均获得正式 Extraction。期间一次 5-call 小批次在 Case 4（`高级开发工程师（AI 平台 / 模型融合方向）`）遇到 HTTP 504 后正确 fail-fast；本轮按 outage 策略仅对该 Case 执行 1 次 recovery probe，成功生成 Extraction `reqrun_dc4f9ebc3743425cb27238064af85092` 与 Trace `run_8ff3fdfa4ad84c22abc80e2ce808a5c0`，累计 attempts 从 7 → 8，dataset SHA-256 仍为 `851909dfa62c65f6b0d5c33fe0b114c4a3da64d1ec28e4b5a9a490cc53253106`。只读审查确认历史 blocking Bad Case 已修正：`至少覆盖以下方向中的两项` 保持 `must_have`，模型微调 / RAG / Agent / Prompt Engineering 四个子方向均为 `preferred`，未再错误要求四项全部满足。当前 v9 Run 为 5/20 可用 Extraction、15 deferred；真实 DB integrity ok，Requirement Extractions 62 / Traces 188 / MatchReports 0 / UserFeedback 0。Backend 657、Web 77、typecheck/build/E2E Smoke/compileall 与 `git diff --check` 均通过；本切片不修改业务代码、不迁移真实 DB、不自动扩跑剩余 Case。下一轮可从同一 immutable Continue review 继续一个小批次（建议最多 5 次），若再遇 429/503/504 立即 fail-fast，后续恢复仍每轮最多 1 次 probe。
- 2026-08-16：针对 v9 多次 HTTP 504 做根因分析：失败 Trace 均在约 60 秒返回（60.19s / 60.93s），而本地 `REQUIREMENT_EXTRACTOR_TIMEOUT_SECONDS=180`，且当前 OpenAI-compatible gateway 为 `tokenrhythm.studio`，因此 504 是上游 gateway 约 60 秒超时，不是 JobLens 客户端 timeout。完成运行控制修复 `c1d1a43`：Provider unavailable error 增加结构化 HTTP status；429/503 仍立即 fail-fast；504 仅在同一次显式 Provider attempt budget 仍有余额时，对同一 Case 自动重试 1 次，首个 504 与 retry 都分别计 attempt、保留独立 Trace、消耗预算；第二次仍 504 立即 fail-fast，预算为 1 时绝不越界。Backend 660、Web 77、typecheck/build/E2E Smoke/compileall 均通过。随后从同一 v9 Continue Run 以 5-attempt budget 执行下一小批：Case 5–8 四个成功，Case 9 因 validator 将不同职责共享同一 section-level `evidenceSpan` 误判为 duplicate 而失败；修复 duplicate identity 为 `(type, normalizedCapability, originalText, evidenceSpan)`（`91c4a3c`），保留真正完全重复项 fail-closed，Backend 661 passed，Case 9 单次重试成功。v9 Run 当前达到 10/20 可用 Extraction、累计 attempts=14、10 deferred、dataset hash 不变。对 Case 5–9 的只读质量抽查又发现新的 blocking sibling-alternative 缺陷：Case 6 JD `熟悉C++或Python编程语言` 被拆成 `C++ must_have` + `Python must_have`，错误把“二选一”变成“两项都必须”；因此不得继续扩跑剩余 10 个，下一最小切片应先修复“模型直接拆分显式 或/or 备选项但未生成 parent group”的确定性语义护栏，再从同一 v9 Continue Run 恢复。
- 2026-08-16：完成下一最小语义修复 `requirement-extractor-v10 / requirement-extraction-v3 / requirement-semantics-v3`。v10 仅在多个 `must_have skill` 共享同一 exact-grounded `originalText/evidenceSpan`、capability 不同，且原文明确包含 `或/或者/or` 并且没有 `优先/加分` 等软化标记时触发 sibling-alternative repair：从原 JD 句合成一个 `must_have constraint`，并把各 capability child 降为 `preferred`；普通 `A、B 等框架` 枚举不触发。真实 v9 Case 6 冻结输出离线重放后，`熟悉C++或Python编程语言` 被修复为一个 mandatory group + `C++/Python` 两个 non-blocking child。新增正例与防误伤回归，Backend 663、Web 77、typecheck/build/E2E Smoke 均通过。由于 extractor/semantic policy 已变更，v9 的 10/20 历史证据保持冻结且不得与 v10 混跑；下一步必须新建 v10 正式 Canary。
- 2026-08-16：执行全新 v10 正式 Canary Run `reqacceptrun_5e13223777ba414286b2ea5e580e5871`，3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。Case 0 的尾部优先与示例项、Harness 的 waiver 与“至少一个方向”均未复发历史 blocking 错误；但 Case 2 暴露新的 capability scope blocker：JD 为 `具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验`，Requirement 保留了正确原文和 `must_have`，却把 `normalizedCapability` 单独收窄成 `LangChain`。Eligibility 对 `must_have skill` 会直接按该字段判断 missing，因此只具备 Dify/LangGraph 的候选会被错误淘汰，v10 不得 Continue。
- 2026-08-16：完成 `requirement-extractor-v11 / requirement-extraction-v3 / requirement-semantics-v4`。当 exact-grounded 的单条 `must_have skill` 本身包含显式 `至少 N / one of / 任意一个` 等 cardinality/alternative 语义，却只绑定一个 normalized capability 时，v11 保留 mandatory 原文但将其转为 `constraint` 并清除单一 capability，避免 Eligibility 把某个示例误当唯一硬门槛；preferred/bonus 软条件和普通非备选 skill 不变。真实 v10 Case 2 冻结输出离线重放后，上述 LangChain/LangGraph/Dify 条目变为 `constraint must_have / normalizedCapability=null`。新增正例与软条件防误伤回归，Backend 665、Web 77、typecheck/build/E2E Smoke 均通过；v10 仍停在人工 Canary 门禁，v11 只允许做 readiness，必须先由用户真实 Stop v10 后才能启动新的 live Canary。
- 2026-08-16：用户已对 v10 提交不可变 `stop` 后启动全新 v11 Canary Run `reqacceptrun_0108cf55d8dd456a9563c1490eec2c58`，3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。真实审查确认 v11 的 inline alternative 修复生效：Case 2 `具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验` 已为 `constraint must_have / normalizedCapability=null`，Harness waiver 仍为 preferred。但 Case 0 又出现 provider 输出形态：`熟悉智能体技术栈...,有落地项目经验者优先` 与 `主导千万级AI项目经验,熟悉车企数字化转型路径者优先` 被作为 combined `must_have` 保留，同时尾部 soft Requirement 已另行输出；这会使 hard Requirement 的 `originalText` 含不应成为硬证据的一段优先条件，尤其 experience Eligibility 的严格证据判断可能误判 missing，因此 v11 不得 Continue。完成 `requirement-extractor-v12 / requirement-extraction-v3 / requirement-semantics-v5`：mixed-clause repair 现在同时处理 provider 已标为 must-have 的 combined clause，将尾部 narrow preferred suffix 从 hard Requirement 移除，并复用已存在的等价 soft item（忽略句末标点差异）避免重复。真实 v11 Case 0 冻结 Trace 离线重放后，两条 hard Requirement 均收敛为纯硬前缀，两个已有 soft Requirement 各保留一条。Backend 666、Web 78、typecheck/build/E2E Smoke 均通过；v11 仍停在人工 Canary 门禁，v12 仅允许 readiness，必须先由用户真实 Stop v11 后再启动 live Canary。
- 2026-08-16：用户已对 v11 提交不可变 `stop` 后启动全新 v12 Canary Run `reqacceptrun_5716bc5fee7b46d19d90bf79b955be04`。预算严格为 3 次：Case 0 与 Case 2 成功，Harness Case 因模型再次把 JD 原文 `但至少要能独立 owner 一个核心方向` 改写为 `至少能独立 owner 一个核心方向` 而被 `grounding-v1` fail-closed，属于随机非原文改写，不应放宽 grounding。只读审查同时确认 v12 mixed-scope 修复在 Case 0 生效，但 Case 2 出现新的 provider 输出形态：同一 `至少一种 Agent 框架` 要求被标为 `experience must_have`，绕过只覆盖 skill 的 inline-alternative 护栏，仍可能使 Eligibility 错误 hard-missing。完成 `requirement-extractor-v13 / requirement-extraction-v3 / requirement-semantics-v6`：inline cardinality protection 从 `must_have skill` 泛化到 `must_have skill/experience`，exact-grounded 且显式 `至少 N / one of / 任一` 的条目统一保留原文并转为 `constraint must_have / normalizedCapability=null`；软条件与普通 experience 不变。真实 v12 Case 2 冻结输出离线重放后已正确转为 mandatory constraint。Backend 667、Web 78、typecheck/build/E2E Smoke 均通过；v12 仍停在人工 Canary 门禁，v13 只能 readiness，必须先由用户真实 Stop v12 后再启动 live Canary。
- 2026-08-16：v13 已在用户停止上一轮后执行全新正式 Canary Run `reqacceptrun_d90a70d3f77947ecb1b1b7be18c5ee2f`，3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。只读审查确认此前 mixed trailing preferred、Harness waiver/方向组均保持正确，但 Case 2 暴露两个新的 blocking mixed-clause 问题：`熟练使用Python,具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验` 被 `inline_alternative_group` 整句转成 constraint，吞掉 Python 硬技能；同时 `本科及以上,计算机相关专业,2年以上开发经验,有LLM/Agent应用落地项目经验` 被 provider 合并成单个 education must-have，而 Eligibility education evaluator 只检查学历层级，会错误放过两类经验门槛。因此 v13 不得 Continue。完成 `requirement-extractor-v14 / requirement-extraction-v3 / requirement-semantics-v7`：对 exact-grounded 的“硬技能前缀 + 后续至少一种/one of”混合句，保留 hard skill 并仅将 alternative 后缀转为 mandatory constraint；对 must-have education 中逗号分隔、且后半段全部为显式经验条件的窄形态，拆成 education + 独立 experience Requirements。真实 v13 Case 2 原文离线重放后得到 `本科/专业 education`、`2年以上经验 experience`、`LLM/Agent落地经验 experience`、`Python skill`、`至少一种Agent框架 constraint` 五条独立硬要求。Backend 669、Web 78、typecheck/build/E2E Smoke/compileall 均通过；v13 仍停在人工 Canary 门禁，v14 只允许 readiness，必须先由用户真实 Stop v13 后再启动 live Canary。
- 2026-08-16：用户 Stop v13 后启动全新 v14 Canary Run `reqacceptrun_0b473193c33042b69fa7f50b0af7bd2a`。预算 3 次：Case 0 / Harness 成功，Case 2 因 `Requirement 7 duplicates an earlier requirement` 被 validator fail-closed，0 missing Trace、dataset hash 不变。Trace 证明 duplicate 来自 v14 自身 deterministic repair：同一 `至少一种 Agent 框架` clause 被 Provider 按多个 capability 输出后，3 条都被 `inline_alternative_group` 转成相同 constraint；同一“学历 + 2 年经验 + LLM/Agent 项目经验”又以 education/experience 多种 Provider 类型出现，v14 仅拆 education copy，留下 broader 重复。完成 `requirement-extractor-v15 / requirement-extraction-v3 / requirement-semantics-v8`：mixed education/experience 原子化同时接受 education/experience provider type drift；仅对语义修复产生的 exact duplicate 做确定性收敛，普通 Provider 原生 duplicate 仍由 validator fail-closed；多个 capability 转成同一 inline alternative constraint 时只保留 1 条。真实 v14 Case 2 形态离线重放后稳定收敛为 5 条 hard gate：教育、2 年经验、LLM/Agent 落地经验、Python、至少一种 Agent 框架 constraint。Backend 671、Web 78、typecheck/build/E2E Smoke 均通过；v14 必须先人工 Stop，v15 只能先做 readiness。
- 2026-08-16：用户 Stop v14 后启动全新 v15 Canary Run `reqacceptrun_19d48446df454dacb4becbc135b4b412`。预算 3 attempts，Case 0 成功，Harness 首次 HTTP 504 后按既有预算内单次自动重试策略恢复成功，因此 Case 2 尚未执行便进入人工 `review_canary`。只读质量审查发现新的 blocking duplicate：Case 0 的 `8年以上AI产品/解决方案经验` 同时存在两条 must-have experience，`originalText` 相同但 `evidenceSpan` 分别为精确子句和完整父 JD 条目；当前 Eligibility 会逐条评估并计数，导致同一硬门槛被重复计入。完成 `requirement-extractor-v16 / requirement-extraction-v3 / requirement-semantics-v9`：仅收紧语义修复产物的原子收敛身份，由 `type + originalText + evidenceSpan` 改为 `type + importance + originalText`，使 mixed education/experience repair 生成的精确原子项与已有父证据副本收敛为一条，同时不静默去重普通 Provider 原生条目。新增真实形态回归，Backend 672、Web 78、typecheck/build/E2E Smoke 均通过；v15 不得 Continue，必须先人工 Stop，v16 仅可 readiness。
- 2026-08-16：用户 Stop v15 后启动全新 v16 Canary Run `reqacceptrun_d8eec41a1a2545a39a09bf8b6f4abdbd`，3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。Case 2 已稳定为五条独立 hard gate（学历、2 年开发经验、LLM/Agent 落地经验、Python、至少一种 Agent 框架 constraint），但只读审查仍发现两个 blocker：Case 0 的 `8年以上AI产品/解决方案经验` 仍出现无句号/有句号两份副本，说明 repair convergence 未归一化句末标点；Harness 虽有 `至少在以下一个方向非常熟练` mandatory group，但 React / Electron / Python 因后续 `不要求 React / Electron / Python / 工程化四个方向都精通` 再次出现，旧规则要求 child 在整份 JD 全局唯一而放弃降级，导致三个方向入口仍为 must-have。完成 `requirement-extractor-v17 / requirement-extraction-v3 / requirement-semantics-v10`：repair 原子身份忽略句末标点；alternative child 改为要求 exact 文本在某一个明确 group scope 内唯一，而不要求全 JD 唯一，scope 外重复说明文字不再阻断降级，scope 内多次出现仍保持 fail-safe。新增两类真实形态回归，Backend 674、Web 78、typecheck/build/E2E Smoke 均通过；v16 不得 Continue，必须先人工 Stop，v17 仅可 readiness。
- 2026-08-16：用户 Stop v16 后执行全新 v17 Canary Run `reqacceptrun_66c6614e34bf43b9a4d6b14461b7420d`，3/3 Provider 调用成功、0 failure、17 deferred、Trace 完整、dataset hash 不变。只读审查确认 Case 0 的 `8年以上AI产品/解决方案经验` 已收敛为单条，Harness 四个方向均为 preferred，Case 2 的五个核心 hard gate 继续稳定；但 Harness mandatory group `工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)` 被 Provider 标成 `experience must_have`。当前 Eligibility 对无年限 must-have experience 在没有整句完全一致 Profile 证据时会判 `missing`，仍可能错误淘汰满足某一方向的候选人，因此 v17 不得 Continue。完成 `requirement-extractor-v18 / requirement-extraction-v3 / requirement-semantics-v11`：仅对无 normalized capability、显式 alternative-group、且 marker 前缀不含年限/经验硬门槛的 must-have experience 做 deterministic type-drift normalization，转为 `constraint must_have`；`3年以上经验 + 至少一个方向` 等真实 experience prefix 不被吞掉。新增正例与防误伤回归，Requirement workflow 38 passed，Backend 676、Web 78、typecheck/build/E2E Smoke 均通过；v17 必须先人工 Stop，v18 仅可 readiness。
- 2026-08-16：用户 Stop v17 后执行 v18 Canary Run `reqacceptrun_5762e4898469487f9551f6376cc09930`，预算 3 attempts：Case 0 与 Harness 成功，Case 2 因 `Requirement 22 duplicates an earlier requirement` 被 validator fail-closed，2 extracted / 1 failed / 17 deferred，Trace 完整、dataset hash 不变。真实审查确认 v18 目标修复生效：Case 0 的 8 年经验仍只有一条，Harness mandatory group 已稳定为 `constraint must_have` 且四个方向为 preferred。Case 2 失败来自 Provider 在同一次输出中把 `具备上下文管理与复杂意图拆解能力` 完全重复输出两次（type / importance / normalizedCapability / originalText / evidenceSpan 全相同，仅 confidence 为 0.90/0.85），semanticRepairs 仅有既有 `inline_alternative_group`，不是 deterministic repair 新增 duplicate。维持既定安全边界：普通 Provider 原生 duplicate 继续 fail-closed，不为通过 Canary 而静默去重或 bump 语义版本。下一步应人工 Stop 本轮 v18，再以同一 v18 版本启动全新 3-case Canary 复测随机性；若 exact provider duplicate 稳定复现，再单独评估可观测的 exact-duplicate normalization/重试策略。
- 2026-08-16：用户 Stop 首轮 v18 后，以相同 `requirement-extractor-v18 / requirement-semantics-v11` 启动全新 retry2 Run `reqacceptrun_c4830fc32c504fe0b3a16210fa114d05`。Case 0/Harness 复用同版本已成功 extraction，3 次新 Provider 预算实际覆盖 Case 2/3/4，三次均成功，证明首轮 Case 2 的 exact provider duplicate 未稳定复现。只读质量审查同时确认历史 Case 4 `至少覆盖以下方向中的两项` 的四个方向 child 已全部降为 preferred，但发现两个新的 blocking scope 问题：父级 `具备 LLM 应用工程实战经验,至少覆盖以下方向中的两项` 仍作为 fused `experience must_have`，会把 cardinality 交给 literal experience evaluator；以及 `精通 Python 或 Go 或 Java 至少一门语言` 在 Provider importance 漂移为 Python must-have / Go、Java preferred 时没有合成 mandatory alternative group，仍会错误绑定 Python。完成 `requirement-extractor-v19 / requirement-extraction-v3 / requirement-semantics-v12`：真实 experience prefix 与后续 cardinality group 拆成独立 experience + constraint，数值年限门槛也保留；explicit-OR sibling grouping 接受同一 exact-grounded source 下 must/preferred importance drift，并统一合成一个 mandatory constraint、所有 capability child 降为 preferred。新增真实 Case 4 形态回归，Requirement workflow 40 passed，Backend 678、Web 78、typecheck/build/E2E Smoke 均通过；当前 v18 retry2 不得 Continue，必须先人工 Stop，v19 仅可 readiness。
- 2026-08-16：用户 Stop v18 retry2 后启动全新 v19 Canary Run `reqacceptrun_b1ef3041b3b24974b5b6334fdd5a4b65`，严格 3 attempts，Case 0/Harness/Case 2 三次均成功，0 failure、17 deferred、Trace 完整、dataset hash 不变。只读审查确认前三个历史高风险点稳定：Case 0 的 8 年经验仅保留 1 条且尾部优先独立为 preferred；Harness mandatory group 为 `constraint must_have`、四个方向均为 preferred、waiver 仍为 preferred；Case 2 的学历、2 年开发经验、LLM/Agent 落地经验、Python、至少一种 Agent 框架五个核心 hard gate 完整且无 duplicate。当前未发现新的 blocking 语义回归，因此建议人工 Continue，仅用于允许扩展验证；v19 新增的 Case 4 cardinality/explicit-OR 修复尚未在本轮前三案中真实覆盖，Continue 后应优先 bounded 扩跑至 Case 4/6，再决定是否继续全量。
- 2026-08-16：用户实际对首轮 v19 提交不可变 `stop`，因此不能续跑原 Run；保持相同 v19 代码启动 retry2 Run `reqacceptrun_b1c37e53b54942daa4741df866d0f1be`。Operator 首次请求 4 个新 Extraction 被 `initial_canary_limit_exceeded / canary_budget_must_be_one_to_three` 在 0 Provider call、0 DB write 状态下阻止，随后按合法 3-attempt 初始预算执行：Case 0-2 复用，Case 3 成功、Case 4 因 `Requirement 10 originalText does not occur in Job description` 被 grounding/validator fail-closed、Case 5 成功，Case 6 尚未执行。失败 Trace 证明该 Requirement 将 Case 4 的父级 cardinality 行与后续多个 bullet 非连续聚合为一条并改写分隔符，继续维持 `grounding-v1` 严格拒绝；同时同一 Trace 暴露两个 exact-grounded 的真实下游风险：`精通 Python 或 Go 或 Java 至少一门语言` 被 Provider 作为单条 `skill must_have / normalizedCapability="Python, Go, or Java"`，而 Eligibility 仅做 capability 完全相等匹配，会错误 missing；以及 experience/cardinality 父级若 Provider type 漂移为 `skill`，v19 的经验拆分会被绕过。完成 `requirement-extractor-v20 / requirement-extraction-v3 / requirement-semantics-v13`：cardinality 词法加入 `至少一门`，使单条组合语言要求归一为 mandatory constraint；experience-prefix/cardinality 拆分改为 exact-text 驱动，允许 Provider type 为 experience/skill，但前缀必须被既有显式经验正则完整匹配，并强制产出 `experience must_have + constraint must_have`，不放宽 grounding。Requirement workflow 42 passed，Backend 680、Web 78、typecheck/build/E2E Smoke 均通过；v19 retry2 不得 Continue，必须先人工 Stop，v20 仅可 readiness。
- 2026-08-17：用户 Stop v19 retry2 后启动全新 v20 Canary Run `reqacceptrun_a9d1e7a6c795409281ccf74b569d7e5b`，严格 3 attempts，Case 0/Harness/Case 2 三次均成功，0 failure、17 deferred、Trace 完整、dataset hash 不变。历史问题继续稳定：Case 0 的 8 年经验仅 1 条且尾部优先独立；Harness waiver 为 preferred、mandatory group 为 constraint、方向 child 均为 preferred；Case 2 的学历、2 年开发经验、LLM/Agent 落地经验、Python 与至少一种 Agent 框架保持独立。只读下游审查同时发现新的 blocking under-enforcement：Case 2 `熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力` 被 Provider 合成单条 `skill must_have / normalizedCapability=Prompt工程`，以及 `理解RAG、向量数据库、Function Calling等核心技术` 被合成 `skill must_have / normalizedCapability=RAG`；Eligibility 的 skill evaluator 仅做 normalized capability 完全相等匹配，因此只具备 Prompt 或 RAG 即可能错误把整个复合硬要求判 matched。完成 `requirement-extractor-v21 / requirement-extraction-v3 / requirement-semantics-v14`：对 exact-grounded、无 soft/alternative 的复合 must-have skill，当多个逗号子句均带显式硬能力谓词，或文本为 `理解 A、B、C 等核心技术` 一类明确 all-of 技术列表时，归一为 `constraint must_have / normalizedCapability=null`，避免单一 capability 虚假通过；`如 LangChain、AutoGPT 等` 示例列表明确不触发。Requirement workflow 45 passed，Backend 683、Web 78、typecheck/build/E2E Smoke 均通过；v20 不得 Continue，必须先人工 Stop，v21 仅可 readiness。
- 2026-08-17：用户 Stop v20 后启动全新 v21 Canary Run `reqacceptrun_9e68802640f04deeb0ffc6e5eb1d57ab`，严格 3 attempts，Case 0/Harness/Case 2 三次均成功，0 failure、17 deferred、Trace 完整、dataset hash 不变。v21 的目标修复在真实 Case 2 生效：`熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力` 与 `理解RAG、向量数据库、Function Calling等核心技术` 均被 `compound_hard_skill_constraint` 归一为 `constraint must_have / normalizedCapability=null`，避免单一 capability 虚假 matched，同时 Provider 已拆出的结构化 Prompt、上下文管理等原子 must-have skill 仍保留。继续只读审查发现 Harness 新的 blocking type drift：Provider 将抽象评价 `工程能力扎实` 单独输出为 `skill must_have / normalizedCapability=engineering ability`；Eligibility 对 must-have skill 仅做技能名完全相等匹配，候选人即使满足 React/Electron/Python/工程化方向，只要 Profile 没有字面名为 `engineering ability` 的 Skill 就会被错误判 missing。完成 `requirement-extractor-v22 / requirement-extraction-v3 / requirement-semantics-v15`：仅对 exact-grounded、must-have、无 soft/alternative、且属于小型 allowlist 的抽象评价能力（工程/综合/学习/沟通/协作/表达/分析/抗压能力及扎实/较强/优秀等评价后缀）归一为 `constraint must_have / normalizedCapability=null`；`具备企业级AI系统架构设计能力` 等具体技术能力明确保持 skill。Requirement workflow 47 passed，Backend 685、Web 78、typecheck/build/E2E Smoke 均通过；v21 不得 Continue，必须先人工 Stop，v22 仅可 readiness。
- 2026-08-17：用户 Stop v21 后启动全新 v22 Canary Run `reqacceptrun_137c47ed0b2d48eb839de301a8853003`。严格 3 attempts：Case 0 首次成功；Harness 首次 HTTP 504 后按既有预算内单次重试策略恢复成功，因此共消耗 3 attempts，Case 2 deferred，2 extracted / 0 failed / 18 deferred、Trace 完整、dataset hash 不变。v22 成功结果未再次出现 Provider 原生的 `工程能力扎实` skill，因此抽象能力修复尚未被 live 直接命中；但只读下游审查发现两个新的 blocking Provider 形态：Case 0 的 `优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案` 被保存为单条 `skill must_have` 且 normalizedCapability 只覆盖前半段，存在 partial-match under-enforcement；Harness 的 `熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验` 被融合为单条 `experience must_have`，把硬技能与经验事实交给 literal experience evaluator，存在 false missing。完成 `requirement-extractor-v23 / requirement-extraction-v3 / requirement-semantics-v16`：compound all-of 识别接受 `优秀的/较强的/良好的…能力` 评价型子句与后续显式硬能力子句；新增 `split_skill_experience`，仅对 exact-grounded、must-have、恰好两段的 `硬技能子句 + 明确经验子句` 做保守拆分，技能侧无安全原子 capability 时转 mandatory constraint，经验侧保持 must-have experience，不放宽 grounding。Requirement workflow 49 passed，Backend 687、Web 78、typecheck/build/E2E Smoke 均通过；v22 不得 Continue，必须先人工 Stop，v23 仅可 readiness。
- 2026-08-17：v22 已由用户提交不可变 `stop`，随后 v23 Run `reqacceptrun_71fa33f534a4490bacab52c8a8bd6f25` 进入正式 Canary。Case 0 首次成功，真实输出已命中 v23 的 compound hard requirement 修复：`优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案` 被归一为 `constraint must_have / normalizedCapability=null`，不再允许只匹配前半段能力即通过整条硬要求。Harness Case 首轮与补足 3-attempt Canary 边界的 recovery attempt 均为 Provider HTTP `503`；人工提交不可变 `Continue` review `reqacceptcanary_f1b0321be2bd4ef7a69e6b0762905576`，仅表示允许受控恢复，不代表 v23 质量通过。Continue 后严格执行 1 次 outage recovery probe，Harness 再次 HTTP `503`，因此当前累计 `attemptedCalls=4`、1 extracted / 1 failed / 18 deferred，所有失败均有 Trace，dataset SHA-256 保持 `851909dfa62c65f6b0d5c33fe0b114c4a3da64d1ec28e4b5a9a490cc53253106` 不变。按既有 fail-fast/outage 策略停止继续 Provider 重试；Provider 恢复后下一动作只应先对 Harness 做单次 bounded recovery probe，成功后优先审查 `熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验` 是否被 `split_skill_experience` 正确拆为技能侧 mandatory constraint 与经验侧 must-have experience，再决定是否扩跑 Case 2/4。
- 2026-08-17：`deepseek-v4-flash` 健康检查恢复：普通 Chat Completions 与 `json_schema` 结构化最小探针均返回 HTTP 200。继续同一 v23 Run 做 1 次 bounded Harness recovery，成功生成 Extraction `reqrun_9ae63262436f4183aa714967b9c2add7` / Trace `run_f38037c19d534e0e9e0b9e94beb4ab75`；只读审查确认 `split_skill_experience` 在真实 Provider 输出上生效，`熟练使用 AI Agent 工具进行真实软件开发` 被归一为 `constraint must_have`，`对 Agent 产品有高强度使用经验` 保持独立 `experience must_have`。随后 bounded 扩跑 Case 2–4：Case 3 成功；Case 2 再次出现 Provider exact duplicate，同一复合 RAG hard requirement 经 deterministic repair 后形成三条完全相同的 constraint，validator fail-closed；Case 4 再次出现将 `至少覆盖以下方向中的 两项:` 与四个 bullet 非连续拼接成一条 quote 的 grounding 失败。进一步历史对账发现 v18 曾因 alternative-group scope 只识别 `4.` 而不识别真实 JD 的 `4 熟练使用...`，把独立 `熟练使用 PyTorch 或 TensorFlow` 错降为 preferred。完成 `requirement-extractor-v24 / requirement-extraction-v3 / requirement-semantics-v17`：仅对最终语义完全相同且 importance 一致的 exact duplicate 做可观测去重；仅当非连续 cardinality aggregate 的整个 tail 可由同一编号 scope 内的 separately grounded children 精确覆盖时恢复唯一 grounded header；alternative scope 新增相邻编号 sibling 边界识别，阻止 scope 泄漏到后续独立 hard gate。Requirement workflow 52 passed，Backend 690 passed；grounding-v1 未放宽，importance 冲突 duplicate 仍 fail-closed。v23 继续保留为历史 live 证据，v24 必须走全新 readiness / Canary。
- 2026-08-17：v24 readiness 通过后启动全新 Canary Run `reqacceptrun_54e02ad2afb7463ebf3e97f9dbab7970`，3/3 Provider 调用技术成功、0 failure、17 deferred、Trace 完整、dataset hash 不变；但只读质量审查发现三个 blocking type/coverage drift，因此人工提交不可变 `stop` review `reqacceptcanary_3848d95fe5904ccbbd8919e070b3efef`。Case 0 的 Provider 仅将 `优秀的跨部门沟通与业务理解能力` 保存为 `skill must_have`，而 exact evidenceSpan 已包含同一句后半段 `能快速定位痛点并设计技术方案`，造成复合硬要求 under-enforcement；Harness 将 `熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验` 直接标成 `skill must_have`，绕过 v23 只针对 experience type 的拆分；同时显式 `至少一个方向` cardinality parent 出现 `responsibility must_have` type drift。完成 `requirement-extractor-v25 / requirement-extraction-v3 / requirement-semantics-v18`：skill-type fused split 仅扩展到 exact-grounded `硬技能 + 对…经验` 形态，避免误伤 `Python + 具备框架项目经验`；显式 must-have alternative group 的 responsibility type drift 归一为 constraint；新增 `expand_compound_hard_evidence_span`，仅当 originalText/evidenceSpan 均 exact-grounded 且 evidence 中缺失后缀是显式硬能力、无 soft/cardinality marker 时，从原始 JD slice 恢复完整 compound hard constraint。Requirement workflow 56 passed，Backend 694 passed；grounding-v1 与 prompt v3 均保持不变，v25 必须走全新 readiness / Canary。
- 2026-08-17：v25 Run `reqacceptrun_a2cc8143902641c2a68e32545ccda260` 在 Flash 双层健康检查通过后执行首轮 3-case Canary，3/3 技术成功、0 failure、17 deferred，但只读质量审查再次发现 Evaluator-sensitive drift，因此提交不可变 `stop` review `reqacceptcanary_62c913f4669745c3a6ff0f59f62e06a8`。Case 0 将明确经历事实 `需要有车端经验` 标为 `skill must_have / normalizedCapability=车端经验`，会把经历证据错误收紧为同名技能匹配；同一 Case 把 `如预测、决策、NLP、CV等` 从 `精通AI常见场景(...)` 的 exact evidenceSpan 中拆成独立 `domain must_have`；Harness 将 `有良好的工程习惯` 标为 `skill must_have / Engineering Habits`。完成 `requirement-extractor-v26 / requirement-extraction-v3 / requirement-semantics-v19`：exact-grounded、无 soft/cardinality marker 的显式 `需要有/有/具备…经验` skill type drift 归一为 experience；抽象评价规则窄化扩展到工程习惯/工程实践/工程素养/测试或质量安全意识等评价短语并转 constraint；standalone example child 仅在与前置非 example must-have parent 共享同一 exact evidenceSpan 时删除，没有该 parent 的 example-shaped requirement 明确保留。Requirement workflow 60 passed，Backend 698 passed；grounding-v1 和 prompt v3 不变，v26 仅允许全新 readiness / Canary。
- 2026-08-17：v26 Run `reqacceptrun_d448c1e97dbd415486dcd96cbad0a693` 首轮 Canary 3/3 技术成功，v25 的 standalone example hard gate、Engineering Habits 同名技能门槛以及 Harness skill+experience/cardinality drift 均未再出现；但 Case 0 将明确 hard experience `需要有车端经验,非车端经验的无法到副总师的层级` 保存为 `constraint must_have`。由于 Eligibility 对 constraint 缺证据时只给 conditional，而明确 experience hard gate 缺失应 blocked，且人工 Requirement Review 有 `wrong_type` issue code，因此提交不可变 `stop` review `reqacceptcanary_c0c420fdf93a4a4ebc0ee0e28872bcb5`。完成 `requirement-extractor-v27 / requirement-extraction-v3 / requirement-semantics-v20`：`normalize_experience_type_drift` 扩展到所有非-experience must-have type；若 exact-grounded 两段文本的第一段是显式 `需要有/有/具备…经验`，第二段仅是窄化匹配的 `非/没有/无…无法/不能/不满足/不符合/不可…` 否定性解释后果，则只保留第一段为 `experience must_have`；若第二段本身是另一个 hard requirement 则明确不改。Requirement workflow 62 passed，Backend 700 passed；grounding-v1 与 prompt v3 不变，v27 必须走全新 readiness / Canary。
- 2026-08-17：v27 Run `reqacceptrun_65867486028f4186be02f1e49996c326` 在第二轮 Flash 双层健康检查通过后启动；Case 0 成功、Harness HTTP 503 后 fail-fast，Case 2 deferred。Case 0 只读审查发现车端 hard experience 仍为 constraint；规则条件与 regex 均满足，最终定位为该 exact 句子在 JD 中原样重复两次，`_unique_exact_span` 因多次出现返回 None，导致语义 split 被不必要地阻止。提交不可变 `stop` review `reqacceptcanary_2a11392b9c3a4c35a0789f8c44cd28d3`。完成 `requirement-extractor-v28 / requirement-extraction-v3 / requirement-semantics-v21`：仅在 `normalize_experience_type_drift` 的 deterministic semantic split 中，将“全 JD 唯一位置”要求改为“Provider item 是 exact JD substring 且保留前缀是该 item 的 exact substring”；相同文本即使在 JD 中重复出现也可安全收敛，因为不需要选择不同 raw 文本。Grounding recovery 的唯一匹配规则完全不变。重复 JD 真实形态回归、Requirement workflow 62 passed，Backend 700 passed；v28 仅允许全新 readiness / Canary。
- 2026-08-17：v28 Run `reqacceptrun_ab5592d9e2c34922ab357054463f3f12` 在 Flash 双层健康检查通过后完成首轮 Canary 3/3，0 failure、17 deferred；只读审查确认历史高风险点稳定：Case 0 的 `需要有车端经验` 已为 `experience must_have`，standalone 示例项不再成为独立 hard gate，复合 AI 场景/架构与沟通方案要求完整；Harness waiver、mandatory cardinality、四方向 child、Agent 工具 + 高强度产品使用经验及工程习惯稳定；Case 2 教育/经验/Python/至少一种 Agent 框架及复合 Prompt/RAG hard gate 完整。提交不可变 `Continue` review `reqacceptcanary_1f504730bd184f298ba61a1714a38801`，仅授权 bounded 扩展、不代表正式质量批准。Provider 随后出现 plain 200 / json_schema 503 抖动；第二轮双探针恢复后执行 3-case Resume，Case 3 `泛医疗行业大模型解决方案专家` 成功生成 Extraction `reqrun_50a54864694e46c79404a4b851f53f7a` / Trace `run_6065a1ec2b4744bbacb884dbd2f67b21`，Case 4 遇到 HTTP 503 后 fail-fast，Case 5 deferred。Case 3 质量审查发现新的 blocking importance drift：JD `岗位要求` 第 2 条中的 `熟悉基于DeepSeek的微调、训练、建立智能体应用` 无任何 `优先/加分/可选` 软化词，却被 Provider 标为 `preferred`，与 Prompt“显式 requirements section 默认 must_have”的合同直接冲突。完成 `requirement-extractor-v29 / requirement-extraction-v3 / requirement-semantics-v22`：新增 `requirement_section_default_must_have`，仅对 `originalText == evidenceSpan`、唯一 exact-grounded、以显式要求谓词开头、无 soft marker、且最近章节标题为岗位要求/任职要求/任职资格/requirements/qualifications 的 preferred/bonus 提升为 must-have；职责/描述章节不处理，真正 soft wording 不提升，alternative child 后续仍可按 cardinality scope 降回 preferred，同文 importance 冲突仍 fail-closed。Requirement workflow 65 passed，Backend 703 passed。当前 Provider recovery probe 再次出现 plain 200 / json_schema 503，因此 v29 尚未启动 live Run；恢复后应先过双 200 health gate，再走全新 v29 readiness / Canary。
- 2026-08-17：将反复人工执行的 Flash 双探针固化为正式 `scripts.check_requirement_provider_health` 运维门禁。默认 Plan 模式零 Provider 调用；只有同时显式 `--execute-health-probe --confirm-live-cost` 才执行最多两次极小 live probe，plain 失败立即停止，plain 成功后才验证与 Requirement Extractor 同 API style 的 `json_schema` 结构化路径；仅双探针都返回 HTTP 200 且 payload 可解析时输出 `readyForRequirementLiveRun=true`。门禁只记录 status/latency/traceId 与安全 upstream error code/message，不写 Acceptance DB、不泄露 Key/完整响应。真实演练仍为 plain HTTP 200（Trace `trace_a8517b9e-c525-41ed-8648-11ec53665457`）/ json_schema HTTP 503 `SERVICE_BUSY`（Trace `trace_a6726ac9-6d60-4cd0-881b-077552a37370`），因此继续禁止启动 v29 Live Canary。新增 6 个 health-gate tests，Backend 全量 709 passed；下一动作仍是等待 gate 返回 healthy 后立即执行 v29 zero-call readiness，再启动全新 3-attempt Canary。

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
- 已完成 MatchReport 持久化 runtime wiring：`match_reports` snapshot ORM、Repository/Query Repository、显式 Unit of Work 与 `20260810_0016` migration 定义已接入 `POST /match-report`；成功 runtime 追加一个不可变 snapshot 并返回 `dbWrites=1`。在任何 Semantic/Provider 工作前先检查 `match_reports` 表，缺表时稳定返回 `409 match_report_persistence_not_ready`，不会偷偷建表、写 Trace 或产生 Provider 成本。临时 SQLite 已验证 upgrade/downgrade、历史追加不覆盖、未 commit rollback；2026-08-11 真实业务 DB 已在 verified 0015 backup 后升级到 `20260810_0017`，`match_reports` schema 已正式就绪且当前为空。
- 已完成 `Match Eval v1` 基础设施：保留 3 条 Contract/Safety cases，并新增 10 条人工标注 synthetic quality cases；报告 verdict/evidence accuracy、workflow success、Trace coverage、混淆矩阵与逐案例 reason/Trace。fixture 全量验证 10/10 通过仅证明 harness 可重复，不代表真实模型质量。
- live Match Eval operator 默认不写正式业务 DB，真实 Provider 必须显式 `--confirm-live-cost` 且设置 `--max-cases`；当前没有自动质量放行阈值，真实结果必须人工复核。
- 已完成首轮 3-case `deepseek-v4-flash` live Semantic Match Canary：3 条 workflow 全部成功、2 条需要 Provider 且 Trace coverage=100%；Java direct 正确为 `matched`，无候选场景正确为 deterministic `not_matched`，MCP related 人工期望 `partial` 但模型返回 `not_matched`，首轮 verdict/evidence accuracy 均为 66.7%。该结果显示模型在 related-but-not-explicit 边界偏保守，不构成 release 通过证据，也未触发自动阈值或继续扩跑。
- 已完成 `Semantic Match prompt v2` 小型校准：加入 MCP/Function Calling 与 FastAPI/Python API 两个 `partial` 正例、MCP/React AI UI 的 `not_matched` 反例以及 Java direct 的 `matched` 锚点；同时明确 related 候选只是检索信号、不能自动 `partial`，related-only 仍绝不能 `matched`。synthetic quality Eval 10/10 与全量回归通过。
- 已完成 5-case `deepseek-v4-flash` Prompt v2 live Calibration Canary：3 个 related/transferable 正例全部为 `partial`，MCP/React AI UI 负例保持 `not_matched`，Java direct 保持 `matched`；verdict/evidence accuracy、workflow success、Trace coverage 均为 100%，且 `partial -> matched=0`、`not_matched -> partial=0`。首轮 v1 中 MCP `partial -> not_matched` 的过度保守错误在 v2 中被修复。该 5-case 校准集仍只是小样本边界证据，不构成 release 通过；v2 五次调用共 3002 input tokens，较 v1 Prompt 明显增加输入成本，后续扩大样本时需继续观察质量/成本权衡。
- 已完成 `semantic-match-blind-holdout-v1` 的 10-case `deepseek-v4-flash` live Eval：9/10 通过，verdict/evidence accuracy=90%，workflow success/Trace coverage=100%。3 个 `matched`、4 个 `partial` 全部正确；3 个 `not_matched` 中有 1 条 Kafka requirement + cron batch Evidence 被模型判为 `partial`，暴露“表面流程相似被误当可迁移核心能力”的假阳性边界。该 holdout 已消费，后续 Prompt 调整不得再把它当无偏验证集；正式业务 DB 未写入。
- 已完成 `Semantic Match prompt v3` 假阳性边界校准：`partial` 现在要求 Evidence 与 Requirement 共享 core mechanism / protocol-runtime semantics / data model / API pattern / implementation concern；generic scheduling、generic CRUD、共享业务场景或同属大类不再足以构成 `partial`。同时明确一般技术知识只能判断输入中已出现能力的关系，不能补造用户职业事实。synthetic quality harness 与全量回归通过。
- 已完成 `semantic-match-blind-holdout-v2` 的 10-case `deepseek-v4-flash` live Eval：3 `matched` / 4 `partial` / 3 `not_matched` 全部正确，verdict/evidence accuracy、workflow success、Trace coverage 均为 100%；10 条全部真实进入 Provider，使用 `semantic-match-v3`。该 holdout 与 calibration、已消费 holdout v1、Prompt v3 完整示例均保持不重复，正式业务 DB 未写入。该结果提供新的泛化证据，但仍不构成自动 release approval，也不能替代 ROADMAP 的 20 个真实岗位人工评审。
- 已完成 20 岗位人工 Match 评审的只读 readiness gate：`GET /api/v1/match-review/readiness` 复用每个岗位的 Match Input Readiness，并额外要求 `match_reports` persistence schema 已就绪；只有 20/20 岗位输入可信且持久化准备完成时才 `readyForHumanReview=true`。2026-08-11 persistence schema 已就绪；当前仍是 20 个 Job、0 个 input-ready，因此继续因 Requirement 人工事实门禁 fail-closed，且 readiness 本身 `dbWrites/providerCalls/traceRunsCreated` 均为 0。
- MatchReport 正式 DB migration 已完成；尚未完成 20 岗位人工 Match 评审本身与基于 UserFeedback 的人工基准。Requirement 真实人工基线未通过前仍不能执行正式 Match。

### 任务

1. `Eligibility Gate`（确定性 / 半确定性硬条件判定）— v1 已完成；
2. `Evidence Retrieval`（从 UserProfile 拉相关 Evidence）— v1 deterministic candidate retrieval 已完成；
3. `Semantic Match`（LLM，基于 Evidence 与 JobRequirement）— guarded v1 已完成，真实 Provider 质量待验；
4. `MatchReport` Structured Output（`eligibility` / `recommendation` / `matchedRequirementIds` / `missingRequirementIds` / `evidenceLinks`）— immutable persistence + runtime fail-closed wiring 与正式 DB migration 已完成；
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
- 已完成受控 Batch Match HTTP contract：`POST /api/v1/match-batch` 复用上述 application orchestrator，`jobIds` 至少 1 个且 `maxReadyJobs` 在请求层硬限制为 1–10，不在 API 层复制 Match 策略；真实 DB smoke 使用现有岗位验证，在 Requirement 人工基线未通过时只返回 `input_blocked` 与结构化 blocker，`dbWrites/providerCalls/traceRunsCreated` 均为 0。2026-08-11 persistence migration 已完成，但 Requirement 人工基线仍未通过，因此尚未真实执行 Match。
- 已完成 50-job 显式安全恢复契约：单次 Batch 请求最多声明 50 个岗位，但每轮仍只执行最多 10 个 `ready` 岗位；响应新增 `resumeJobIds`，只包含因本轮执行上限而**确定尚未运行**的 `deferred_limit` 岗位，并通过 `executionComplete` 表示是否仍有安全可继续的工作。失败任务不会自动加入恢复集合，因为异常路径不能可靠证明 Provider/Trace/DB 副作用是否已经发生。测试已验证 50 个全部 ready 的岗位可通过 5 轮显式续跑完成，同时每轮调用上限保持 10；该能力不等于正式业务已完成 50 岗位 Match，当前只剩真实 Requirement 人工基线门禁未满足。
- 已完成 UserFeedback 领域契约与确定性校验首切片：decision 固定为 `interested / maybe / rejected`，反馈必须绑定具体 immutable `matchReportId + jobId`；reasons 使用稳定枚举并去重，`rejected` 至少一个结构化 reason，`other` 必须附 note。同步收紧跨组件 JSON Schema 与 example；本切片不落库、不新增 API、不触发 migration。
- 已完成 UserFeedback persistence foundation：新增 immutable `user_feedback` ORM、Repository/Query Repository、显式 Unit of Work 与 `20260810_0017` migration 定义；Feedback 以外键绑定 `match_reports.id + jobs.id`，支持按 Feedback ID、MatchReport、Job 回查历史，追加写不覆盖旧反馈，未 commit 自动 rollback。新增只读 persistence readiness gate 与 SQLAlchemy schema inspector，同时要求 `match_reports` 和 `user_feedback` 表存在，缺失时返回结构化 blocker 且 `dbWrites/providerCalls/traceRunsCreated` 均为 0。2026-08-11 真实业务 DB 已通过 verified backup + checkpoint 升级到 `20260810_0017`，两张 persistence 表正式存在且迁移后均为空。
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
- 已完成 Phase 6 Job-based Target Cohort 选择体验：新增只读 `GET /api/v1/target-cohort/gaps/candidates`，把岗位池与最新 UserFeedback/MatchReport 作为可选辅助信息投影给用户；`POST /api/v1/target-cohort/gaps` 继续兼容原 `selectedFeedbackIds`，同时新增显式 `selectedJobIds` manual cohort 输入，因此普通用户不再需要复制内部 Feedback ID。`/gaps` 页面改为岗位卡片选择、反馈筛选、搜索与 P0/P1 Gap 结果卡片，技术 Requirement/Profile/Evidence IDs 默认收进折叠依据；未反馈、`maybe`、`interested`、`rejected` 都只是解释性 overlay，不会被 Web 擅自推断成目标集合。Backend 仍沿用 Requirement release → capability normalization → confirmed Profile comparison → SkillGap → Action Plan 的确定性链路，不写 DB、不调用 Provider、不创建 Trace。
- 2026-08-13：优化能力差距页面的阻塞状态体验。系统现在会区分“用户职业背景是否已准备”和“目标岗位要求是否已准备”，并用岗位名称和可执行下一步替代主界面的内部错误码；技术原因只放在折叠详情。后端仍保持只读和 fail-closed，不会在岗位要求未通过可信门禁时生成技能差距。

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
- 已完成面试前补习清单的最小确定性事实层：只消费上述 Interview Question Facts 中 `must_have / preferred` 且证据状态为 `unevidenced / missing` 的 `skill` Requirement，按既有优先级保留顺序，并透传 Requirement 原文、capability、importance、Profile Skill IDs 与 Evidence 缺口状态；`unevidenced` 只要求补齐已确认 Evidence，`missing` 要求先存在已确认 Profile Skill 再补齐与该 Skill 关联的 confirmed Evidence。`supported`、`bonus` 和非 skill Requirement 不进入本轮清单；上游 facts 不可用或 provenance 缺失时 fail-closed。该契约不生成课程、预计工时、学习资源或虚构项目，不写 DB、不调用 Provider、不创建 Trace。
- 已完成 Phase 7 只读 Job Preparation 聚合入口：新增 application bundle 与 `GET /api/v1/job-preparation/{job_id}`，先复用 Preparation Readiness，门禁未通过时在读取 Profile/Requirement facts 前 fail-closed；通过后只读取冻结的 Profile 与精确 Requirement Extraction，并按依赖顺序组合 Resume Delta、项目/经历排序、Story Facts、Interview Facts、Study Checklist 五个既有确定性事实层。接口不生成自由文本简历/答案/课程，不调用 Provider、不创建 Trace、不写 DB；真实业务 DB Smoke 在当前 Requirement 正式人工门禁未通过时返回 `factsUsable=false` 且三类副作用计数均为 0。
- 已完成 Phase 7 最小 Web 只读验收入口：岗位详情新增“查看投递与面试准备”入口，`/jobs/[id]/prepare` 仅通过 server-side Backend client 消费上述聚合 bundle，按 Resume Delta、项目/经历排序、Story Facts、Interview Facts、Study Checklist 五类展示现有事实；`factsUsable=false` 时只展示 Backend blockers，不在 Web 复制 Match/Gap/Prepare 策略，不直接调用 Provider、不创建 Trace、不写 DB。Web architecture test、全量测试、TypeScript、production build、E2E Smoke 与 Backend 全量测试均通过。

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
