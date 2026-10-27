# Contracts

This package is the source of truth for cross-component domain structures.

Layout:

- `schemas/` — JSON Schema 契约（见下）
- `examples/` — 各契约的示例 payload（随真实样例出现时填充）

Schemas:

- `system-readiness.schema.json` — 只读运行就绪检查；连接、迁移版本及所需表全部通过时 HTTP 200，否则 503；不自动迁移，不调用模型

- `user-profile.schema.json` — 已确认的版本化职业画像；每个 Skill 至少关联一个 Evidence ID，偏好不再重复内嵌
- `profile-extraction-proposal.schema.json` — 简历文本生成的待确认 Profile Proposal，包含 evidenceSpan 与 run/model/prompt 版本，不代表 confirmed fact
- `profile-eval-run-detail.schema.json` — 不可变 Profile Eval Run 详情；记录 dataset/provider/model/prompt/gate 版本、聚合指标、逐案例失败与 Trace 引用，不包含简历文本
- `job.schema.json` — 标准化 Job 读模型；`id` 为 JobLens internal ID，包含三态远程信息和 JD 质量门禁；`sourceRaw` 由 Backend 的 JobSource 持久化，不进入普通 Job Contract
- `collector-requirement-review-dataset.schema.json` — Collector v1.4.6 导出的 Requirement 人工质量验收数据集；只包含具备岗位职责/任职条件证据、无页面噪声、无招聘者尾部且经过近重复去重的 `full_jd` 岗位，20 条独立样本齐备才标记 `ready`
- `job-page.schema.json` — Job Pool 分页响应，包含 `total / limit / offset / items`
- `job-import-detail.schema.json` — 单次导入审计详情，包含批次统计、快照、candidateSummary 和逐条 outcome；错误 raw / candidateRaw 不进入公开契约
- `search-intent.schema.json` — 独立版本化求职意向，区分 hardConstraints 与 softPreferences
- `job-requirement.schema.json` — 单条 evidence-grounded JobRequirement；包含 Extraction ID、原文、归一化能力、importance、evidenceSpan、confidence 与 extractorVersion
- `job-requirement-extraction.schema.json` — 不可变 Requirement Extraction Run；记录 Job/input hash/provider/model/prompt/Trace 与逐条 Requirements，作为 Match/Gap/Prepare 统一事实来源
- `evidence-retrieval.schema.json` — Phase 4 只读候选证据检索结果；区分 `direct / related` 与检索依据，只返回已确认 Profile Evidence，不包含 `matched/status` 等 Match verdict 字段
- `semantic-match.schema.json` — Phase 4 Semantic Match 暂态结果；保留 deterministic `eligibility / eligibilityStatus`，另行输出 `matched / partial / not_matched` 语义判断，Provider 无权输出或升级 Eligibility、推荐等级或分数；当前 promptVersion 为 `semantic-match-v3`，在 v2 的 transferable-capability 校准上进一步约束“表面流程相似 ≠ shared core mechanism”
- `semantic-match-eval-case.schema.json` — Match Eval JSONL 单案例契约；人工标注 expected verdict / evidence IDs，并显式携带冻结 Eligibility 与 Candidate Evidence
- `semantic-match-eval-report.schema.json` — Match Eval 自包含报告；包含 verdict/evidence accuracy、workflow success、Trace coverage、混淆矩阵、逐案例结果和临时 Eval Trace 摘要，不代表自动 release gate
- `user-feedback.schema.json` — 用户对推荐的人类反馈；必须绑定 immutable `matchReportId`，decision 为 `interested / maybe / rejected`，reasons 使用稳定枚举，`rejected` 至少一个 reason，`other` 必须附 note
- `job-target.schema.json` — 目标岗位集，v0.2 演进为 TargetCohort
- `match-report.schema.json` — Phase 4 persisted MatchReport snapshot；组合 immutable Eligibility 与 Semantic Match，Backend policy 输出 `strong / good / stretch / low / blocked`，包含可追溯 strengths/risks/requirementResults/evidenceLinks，不包含百分制匹配概率；runtime 成功时 `dbWrites=1`
- `skill-gap.schema.json` — 能力差距；v0.2，P1 增强优先级字段

领域关系见 `docs/architecture/DOMAIN-MODEL.md`。

### 匹配规则 v2（主流程阶段 2A）

`MatchReport.policyVersion` 独立于模型和提示词版本。新响应输出 `match-policy-v3`；旧快照缺字段按 `match-policy-v1` 读取，保留历史原结论，当前排序排除非当前版本。Schema 将此字段设为可选以兼容历史样例，不能因此把缺字段解释为当前版本。v2 的资格 `missing` 仅表示已确认事实不满足（本轮实现总工作年限不足）；缺少技能、教育或专项年限证据为 `conditional`。语义 `not_matched` 表示证据未支持，不是用户能力否定。

### 当前规则 v3（主流程阶段 2B）

当前新报告为 `match-policy-v3`，沿用 v2 的未知／冲突语义，新增 `searchIntentId`、`searchIntentVersion`、`preferenceChecks`。`preference-check.schema.json` 定义单项规则、稳定原因码、用户意向字段与岗位字段引用，示例见 `examples/preference-check.example.json`。资格、语义匹配、完整报告、排序接口消费同一检查结果，不伪造岗位要求标识。

旧响应与历史样例可缺少新增字段；当前生产报告始终绑定意向版本和内部偏好输入指纹。当前排序排除旧规则、未绑定、意向改变或关键岗位字段变化的报告。历史报告不重解释、不覆盖。内部指纹不经网页或 MCP 暴露；MCP 公开形状保持原有过滤。

薪资使用 K/月的现有规范字段，仅按边界比较；城市为保守的中文城市标记比较，不支持任意地址推理。目标级别、工作形式和自由文本硬条件未具备可靠岗位事实时返回待核实。排除词的检查范围明确限定为岗位名称与公司，不扫描原始 JD。


### 保存的匹配结果（主闭环 2C）

- `match-report-history.schema.json` 对应 `GET /api/v1/jobs/{jobId}/match-reports`，按时间倒序返回此岗位的不可变报告。
- `reportId / createdAt / isCurrent / staleReasons` 是外层元数据；内层 `report` 是原始结果，不按当前规则重写历史。
- 历史原始计数描述生成报告时的行为，不是本次读取的调用／写入次数。读取历史不触发模型、业务写入或自动重算。
- `dbWrites` 允许历史／演示快照原样记录零；正式 POST 成功仍保存一条报告并返回 `dbWrites=1`。
- 当前性复用后端排序的资料身份／版本、意向身份／版本、要求提取、规则版本及偏好输入指纹检查。过期仍可阅读，但不进入当前排序。


### 推荐分组与目标确认（主闭环 2C）

| 原始推荐 | 网页分组 | 可进入默认目标 |
| --- | --- | --- |
| `strong` / `good` | 优先投入 | 是 |
| `stretch` | 挑战／待核实 | 是，但不是条件已全部满足 |
| `low` | 证据不足 | 否；仍可查看与反馈 |
| `blocked` | 暂不建议 | 否 |

- 默认目标建议最多三个，不足三个不补位；显式 `topN` 允许 1–5；人工确认最多五个；单次岗位范围最多五十个。
- `career-agent-run-request.schema.json`、`career-agent-resume-request.schema.json`、`career-agent-run-state.schema.json` 与 Python 公开模型由契约同步测试校验，网页状态类型集中于 `lib/contracts.ts`。
- `targetSuggestionMode=challenge_only` 明确只有挑战目标；`supported` 表示建议中存在 `strong/good`；历史运行缺字段时为 null，不重新解释旧提案。
- 只有 low 时 `status=blocked/currentStep=target_evidence_insufficient`，仍保存完整排序报告引用，供诊断和恢复校验。
- 默认建议与全量排序分开：不过滤排序工具的可读低证据结果、不在界面重新计算分数；人工反馈不改写推荐事实。
- 原先 `topN=6..10` 现在明确拒绝，不静默截断。
- 运行状态增加 `revision` 与 `legacyReadOnly`：新存储每次合法迁移递增修订，状态与事件同事务提交；竞争失败返回 409 `career_agent_state_conflict`。修订不能替代命令内容幂等或执行租约。
- 旧文件仅只读投影最近状态：旧完成运行明确无原始结果快照；旧未完成运行显示 `stale/legacy_reanalysis_required`，要求新建分析。`legacyReadOnly=true` 的状态不可继续，不导入旧事件、不双写旧文件。

### 显式继续分析

- `POST /api/v1/career-agent/runs/{thread_id}/continue` 无请求体；恢复已经接受的输入和人工决定，不允许借继续接口替换岗位、数量或决定。
- 成功响应沿用 `career-agent-run-state.schema.json`。`created`、已保存排序的 `running`、已确认的 `resuming` 可推进；等待确认或终态只返回状态。旧只读运行不可推进，运行缺失返回 404。
- 查询运行不领取租约、不执行业务。租约令牌只存于后端，不进入公开状态；竞争或租约失效返回 409 `career_agent_state_conflict`，保存失败整体回滚并返回 503 `career_agent_save_failed`。
- 这不是模型自动重试协议；当前继续只调用零模型、只读的排序和差距流程。网页错误恢复与完整保存结果是独立交付范围。

### 最近运行与命令重试

- `GET /api/v1/career-agent/runs?limit=10` 返回 `career-agent-run-list.schema.json`，`limit` 为 1–20；按主运行的更新时间及 threadId 倒序稳定排列，不查询或导入旧独立文件，不执行工作流或新增事件。
- 状态响应新增可空 `decisionActionId`，用于判断本地请求是否已经被服务端接受，或等待点是否被另一页面的决定消耗。摘要和租约令牌仍不公开。
- 网页发送前保存原始开始／确认命令，网络重试沿用完整原标识和内容；本地日志是传输恢复辅助，不是业务事实或进度来源。
- `/agent?threadId=...` 可只读找回运行；本地引用丢失时可通过最近列表打开。等待确认和显式继续规则不变，打开页面不会自动推进。

### 已保存的职业分析

`career-agent-analysis-result.schema.json` 定义 `GET /api/v1/career-agent/runs/{thread_id}/result`，组合已有差距与准备响应，包含原事实绑定和派生的当前适用性。`career-agent-analysis-result.example.json` 为非空差距的纯合成示例；不是模型质量证据。运行状态新增可空 `resultId`；原完成运行没有快照时不伪造结果。MCP 公开工具结构不变。

### 保存分析到求职执行（主闭环 4A）

`analysis-execution-request/result/status.schema.json` 定义开始执行命令及只读查询；`workspace-saved-preparation.schema.json` 定义工作区引用的原始准备材料；`application-workspace.schema.json` 和 `application-execution-action.schema.json` 包含当前分析/行动创建来源引用。命令包含 `commandId/resultId/jobIds`，同标识不同内容冲突；不改变现有 MCP 工具公开形状。契约一致性由 `test_analysis_start_execution.py` 验证。

`workbench.schema.json` 定义首页只读汇总：准备情况、最近运行与保存结果引用、目标工作区、最近事实变化和推导的下一步。工作区展示上限不参与全量已执行目标计数。无副作用 GET；不新增产品进度存储。

`workspace-command-error.schema.json` 定义工作区业务保存失败：`error.code/message/retryable/repairAction/correlationId`。保存结果未确认时返回 503；网页保留错误状态并提示先查询原记录再重试，不当作成功或自动确认新事实。既有提案/状态成功响应形状保持不变。


### 职业事实提案核对

`create-evidence-proposal.schema.json` / `evidence-proposal.schema.json` 定义提案输入和结果，原始行动资料/分析/提取版本与 `confirmationBaseProfileId/Version` 分开，`originProposalId` 关联显式重新核对的原始提案。命令摘要仅内部持久化，不公开。

`evidence-context.schema.json` 定义只读可选要求（`options` 为 `[requirementId, normalizedCapability]` 二元组）和当前核对版本；网页类型 `ApplicationEvidenceContext` 消费相同字段。`reconsider-evidence-proposal.schema.json` 定义重新核对命令，需版本、幂等标识及明确确认。历史字段缺失按原来源基准回退，不伪造新快照。Python 结构与四份共享契约逐项比对，浏览器走实际接口。

`analysis-update-plan.schema.json` 定义限定范围更新的只读预检：原运行/结果引用、当前资料/意向版本、逐岗位状态、可复用报告、首批重算候选及修复入口。`maxNewAnalyses=5`，`advisoryOnly=true`；不包含执行成功或授权含义，不填造模型调用计数。Python 契约逐项比对共享模式；TypeScript `AnalysisUpdatePlan` 由页面消费并通过渲染与实际浏览器验证。

### 更新分析：预检、启动与有界规则重算（5C-1）

- 预检响应增加 `inputDigest`，仅用于检查用户刚核对的范围、事实版本与报告标识是否变化，不是模型授权。
- `POST /api/v1/career-agent/runs/{sourceThreadId}/updates` 请求遵循 `analysis-update-start.schema.json`，返回既有运行状态。固定范围内可复用的报告直接使用；每次最多重算 5 个规则可判定的岗位，需要模型的步骤只保存等待状态。
- 新运行绑定不可变的来源运行/结果、范围、摘要及报告标识。状态响应提供 `updateSourceThreadId`、`updateSourceResultId`、`updateScope`；旧运行这些字段为空。
- 同线程/运行/请求标识和内容返回原运行，内容不同返回 409；重放不隐式继续。接受后中断由既有显式 Continue 推进。
- 分批阶段 `POST /runs/{threadId}/continue` 使用 `career-agent-continue-request.schema.json`，包含命令标识、预期修订与是否明确仅分析完成岗位；每次最多尝试 5 个岗位。相同命令不推进下一批，不同内容冲突。其他已有继续阶段仍支持空请求。
- 运行响应增加 `updateSteps/updatePartial`；步骤公开岗位、提取、状态、报告、尝试数与稳定错误码。保存结果响应增加 `updatePartial/unanalysedJobIds`，明确部分范围，不伪装整批完成。
- 409/503 包含原因码、是否可重试、修复动作和请求关联标识。503 可能发生在接受后，不代表服务端一定没有保存；网页保留原请求供核对和重放。

### 保存结果比较（5C-2）

`analysis-comparison.schema.json` 对应只读 `GET /career-agent/runs/{threadId}/comparison`：来源结果、固定范围/版本、推荐及证据覆盖变化、逐要求理由/引用、偏好判断、目标增减和可比较排序。`signal` 为保存判断的变化，不是能力评分；要求或策略不同使用 `not_comparable`，归档缺失/未完成使用 `unavailable`，不可比时 `rankChange=null`。没有调用次数常量或隐式执行。`career-agent-analysis-result.schema.json` 增加可空来源运行/结果标识，旧运行为空。Python 模式逐项同步，TypeScript/实际浏览器消费。
