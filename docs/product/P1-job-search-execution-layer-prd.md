# P1 Job Search Execution Layer 产品需求文档

- 状态：Active Engineering / vNext 1.2
- 对应缺口：**4. 真正的“求职执行层”**
- 前置条件：vNext 1.0 Agent Runtime 已完成；vNext 1.1 Core Engineering 已完成。v1.1 真实 Provider 模型质量门仍属于独立 Release Promotion HUMAN_GATE，但不阻塞本阶段可离线验证、无外部副作用的工程开发
- 核心目标：把 JobLens 从“分析和建议系统”推进为“可执行的求职准备工作台”，让 Ranking / Gap / Preparation 的结果能落到 Resume、面试、学习、Evidence 和 Application 状态上
- 明确边界：第一阶段**不自动投递、不自动联系招聘者**；所有影响用户职业事实或外部世界的动作必须经过人工确认
- 关联 Runtime PRD：`docs/product/P1-career-agent-langgraph-vnext.md`
- 关联 Tool Loop PRD：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`

---

## 1. 背景与问题

JobLens 当前已经可以回答：

- 哪些岗位值得优先投入；
- 为什么；
- 哪些 Requirement 已有 Evidence；
- 主要 Skill Gap；
- 当前应优先补什么；
- 面试 / 简历准备应该关注哪些事实。

但目前大部分输出仍然停留在“事实层 / 建议层”。例如：

```text
Resume Delta
Project Priority
Story Facts
Interview Facts
Study Checklist
```

这些能力能告诉用户“应该做什么”，但没有形成统一的执行工作区。用户仍然需要自己在多个页面之间完成：

- 针对某岗位整理一份简历版本；
- 准备可讲的项目 / STAR；
- 练习岗位相关面试问题；
- 完成学习 / Evidence Action；
- 记录投递状态；
- 回看这些行动有没有改变 Match / Ranking。

因此 vNext 1.2 要把“分析结果”转成“可执行任务和可追踪产物”。

---

## 2. 产品目标

### 2.1 一句话目标

> 用户选中一个真实岗位后，JobLens 能基于已确认 Evidence 和 released JobRequirement，为这个岗位建立一个 Application Workspace，持续管理简历版本、面试准备、学习 / Evidence 行动和投递状态，并把行动结果重新接回 Match / Growth Loop。

### 2.2 第一阶段用户价值

用户能完成：

```text
选一个岗位
→ 查看“为什么值得准备”
→ 建立 Application Workspace
→ 生成 Resume Delta Proposal
→ 用户审核后保存岗位专用 Resume Variant
→ 进入 Interview / Mock
→ 完成 Study / Evidence Action
→ 更新 Application Status
→ 新 Evidence 回流 Profile
→ Re-match / Ranking Change
```

---

## 3. 非目标

第一阶段明确不做：

- 一键自动投递；
- 自动填写招聘网站表单；
- 自动给 HR 发消息；
- 自动发送邮件；
- 自动伪造项目 / 指标 / STAR；
- 自动将生成内容写入 confirmed Profile；
- 自动替用户标记 `applied / interviewing / rejected`；
- Multi-Agent；
- 云端 ATS / CRM 复杂平台；
- 大规模简历模板市场。

---

## 4. 核心模块

vNext 1.2 第一版拆成五个模块：

1. **Application Workspace**；
2. **Resume Variant**；
3. **Interview / Mock**；
4. **Study / Evidence Action**；
5. **Application Status / Timeline**。

它们必须复用同一岗位事实身份：

```text
job_id
match_report_id
requirement_extraction_id
profile_id + version
```

不允许不同模块各自重新解析 JD。

---

# 5. Application Workspace

> 工程状态（2026-09-27）：A1 第一纵向切片已落地。Backend 提供 `POST /api/v1/application-workspaces` 与 `GET /api/v1/application-workspaces/{workspace_id}`；创建前只读取已经 released 的 Requirement、current Profile/SearchIntent 与 current MatchReport，任一事实不 ready 或 Match 身份 stale 都 fail-closed，不触发 Provider。创建请求显式携带 actor 与 idempotency key，并冻结 source snapshot + current fact fingerprint；同一 actor/idempotency key 重放返回原 Workspace，冲突 Job 拒绝。持久化采用 additive `application_workspaces` migration，尚未自动迁移用户真实数据库。

## 5.1 目标

为一个岗位建立单一执行上下文。

建议模型：

```text
ApplicationWorkspace
├── workspace_id
├── job_id
├── status
├── created_at
├── updated_at
│
├── source_snapshot
│   ├── profile_id
│   ├── profile_version
│   ├── search_intent_id
│   ├── search_intent_version
│   ├── requirement_extraction_id
│   └── match_report_id
│
├── resume_variant_ref
├── interview_session_refs[]
├── action_item_refs[]
└── timeline_refs[]
```

### 5.2 创建条件

Workspace 只能在：

- Job 存在；
- Requirement Release 可用；
- current MatchReport 可读；

时创建。

如果 Requirement / Match 不 ready，返回 blocker，不自动补跑 Provider。

### 5.3 Workspace 首页

必须展示：

```text
岗位
当前 Recommendation
关键 Evidence
Hard Gaps
Resume 状态
Interview 状态
Action Items
Application Status
最近变化
下一建议动作
```

---

# 6. Resume Variant

> 工程状态（2026-09-27）：A3 provenance + human review lifecycle 已落地。Workspace 可通过只读 Preparation / Resume Delta 生成 grounded Resume Variant Proposal；只有同时带 `Requirement ID + confirmed Evidence ID` 的 highlight 才能进入可保存内容，missing / unevidenced gap 仅作为 unresolved requirement 返回，禁止伪装成用户经历。Proposal 会与 Workspace 冻结的 Profile version / Requirement Extraction 做 stale 校验；用户显式保存时携带 actor + idempotency key，先形成 `draft` Variant，系统不得自我批准；只有同一 actor 再显式调用 `POST /api/v1/application-workspaces/{workspace_id}/resume-variants/{variant_id}/review` 才转为 `reviewed`，重复 review 幂等、跨 actor review fail-closed。Engineering Complete 审计进一步关闭了 draft → review 的 stale 漏洞：首次人工审核前必须重新读取 current Preparation facts，并再次核对 Profile identity/version 与 Requirement Extraction；事实已变化时在状态写入前 fail-closed，旧 draft 不能静默升级为 reviewed。全程 Provider calls=0，不自动写回 Profile。当前完成的是 provenance-safe 结构化内容与审核状态闭环；自由文案编辑仍不得绕过 Evidence provenance。

## 6.1 目标

不是“重写一份看起来更厉害的简历”，而是：

> 基于用户已确认事实，为一个岗位生成一个有 provenance 的 Resume Proposal，用户审核后保存为岗位专用 Variant。

### 6.2 数据模型

```text
ResumeVariant
├── variant_id
├── workspace_id
├── status
│   ├── draft
│   ├── reviewed
│   └── archived
├── source_profile_id
├── source_profile_version
├── requirement_extraction_id
├── sections[]
├── provenance[]
└── created_at
```

### 6.3 Resume Proposal 必须包含

- 建议突出哪些已有 Evidence；
- 建议弱化 / 删除哪些无关内容；
- 项目顺序建议；
- 每条修改对应 Requirement；
- 哪些 Gap 无法通过简历改写解决。

### 6.4 生成边界

允许：

- 重新组织顺序；
- 压缩已有描述；
- 基于已有 Evidence 改写表达；
- 针对岗位强调真实经历。

禁止：

- 新增不存在的项目；
- 新增不存在的技能；
- 编造量化指标；
- 把 Requirement 文案直接写成用户经历；
- 把 generated proposal 自动写回 Profile。

### 6.5 Provenance

每段生成内容必须能够回溯到：

```text
Profile Evidence ID(s)
Job Requirement ID(s)
```

如果一段内容没有 Evidence source，不得进入可保存 Variant。

---

# 7. Interview / Mock

> 工程状态（2026-09-27）：A4 第一纵向切片已落地。Application Workspace 可直接复用 released Requirement + current Interview Facts 生成确定性练习问题集，不重新读取 raw JD、不调用 Provider；每道题只暴露该 Requirement 已确认的 Evidence ID。用户提交回答时显式附带自己实际使用的 Evidence ID，Review 只接受属于该 Requirement 的 confirmed Evidence，跨 Requirement / 不存在的 Evidence 会标记为 ungrounded 并要求 Retry。当前 Review 有意不对自由文本做“语义打分”，因此不会伪造 STAR 完整度、事实一致性或录用概率；后续若引入模型反馈，必须继续受 Provider/Human Gate 与 provenance 约束。

## 7.1 目标

把当前 Interview Facts 从“准备项列表”升级为可执行练习。

### 7.2 第一阶段支持

```text
Requirement-based Question Set
→ 用户回答
→ Evidence Grounded Review
→ Feedback
→ Retry
```

### 7.3 Question 生成依据

问题只能来自：

- released JobRequirement；
- current MatchReport hard gap / supporting evidence；
- confirmed Profile Evidence；
- Job Preparation Interview Facts。

不能重新读取 raw JD 自由发挥。

### 7.4 Answer Review

评价维度：

```text
事实一致性
是否回答 Requirement
Evidence 覆盖
结构清晰度
是否存在未被 Profile 支撑的声明
缺失信息
```

不得评价成：

```text
“录用概率 85%”
```

### 7.5 STAR 辅助

系统可以：

- 基于已有 Evidence 提示“还缺 Situation / Action / Result 哪一段”；
- 询问用户补充真实事实；
- 帮用户整理已经输入的事实。

系统不能：

- 自动生成不存在的成绩；
- 编造用户没有说过的责任范围。

---

# 8. Study / Evidence Action

> 工程状态（2026-09-27）：A5 第一纵向切片已落地。Application Workspace 可把当前 Job Preparation 的 Study Checklist 物化为可持久化 Execution Action，保留 Requirement ID、capability 与 completion criteria；用户可显式推进 `todo → in_progress → done / skipped`，并通过 expected status 防止 stale 覆盖。`done` 只记录行动完成，不自动创建 Profile Evidence、不改变 Match / Ranking，也不触发 Provider；新的真实职业事实必须进入 A6 Evidence Proposal → Human Confirm 边界。

## 8.1 目标

把 Skill Gap / Study Checklist 转成可跟踪 Action Item。

### 8.2 Action 类型

第一阶段：

```text
learn
practice
collect_evidence
improve_resume
prepare_interview
```

### 8.3 ActionItem

```text
ExecutionActionItem
├── action_id
├── workspace_id
├── type
├── status
│   ├── todo
│   ├── in_progress
│   ├── done
│   └── skipped
├── source_requirement_ids[]
├── source_gap_capability?
├── description
├── completion_criteria[]
├── user_note?
├── created_at
└── completed_at?
```

### 8.4 完成不等于能力已具备

`done` 只表示：

> 用户完成了行动。

> 工程状态（2026-09-27）：A6 Human Confirm + zero-provider explicit Re-match 已落地。只有 `done` 且带真实 Requirement + capability 来源的 Action 才允许创建 Evidence Proposal；Proposal 中的 Evidence 类型、摘要、来源和 Skill Level 必须由用户显式提供，系统不从“行动完成”推断职业事实。Proposal 初始状态固定为 `pending_confirmation`，冻结 source Profile identity/version，并支持 actor + idempotency。用户随后必须以同一 actor 显式 Confirm；确认前重新校验 current Profile identity/version，stale 时 fail-closed。确认成功才通过既有 `SaveProfileUseCase` 生成新的 immutable Profile version，并在 Proposal 上记录 confirmed Profile identity/version/time；重复确认幂等。Engineering Complete 审计进一步补齐 Timeline 审计链：确认成功或确认请求重放都会确保唯一 `evidence_confirmed` Event 存在，不会因为重试重复记账。确认后可由用户显式触发 Workspace Re-match：执行前先复用 Eligibility + Evidence Retrieval 判断现有 Semantic Match 是否需要 Provider；若存在需要语义判断的候选证据，自动路径在任何 Match 写入前以 `application_rematch_provider_required` fail-closed。只有整次 Match 可证明 Provider calls=0 时才生成新的 immutable MatchReport，并复用 Match Improvement 输出前后 Recommendation、resolved Requirement、此次 Evidence 目标 Requirement 是否真正解除，以及 `improved / unchanged / weakened` Ranking signal；同时写入 `rematch_completed` Timeline Event，Recommendation 发生真实变化时再幂等补充 `ranking_changed` Event。自动任务不会把“可能改善”伪造成 Match 结果，也不会继承任何 live-cost 授权。

不等于：

> Profile 已确认该能力。

如果行动产生新的真实经历，需要：

```text
Action Complete
→ Evidence Proposal
→ User Review
→ Confirmed Profile
→ Re-match
```

---

# 9. Application Status / Timeline

> 工程状态（2026-09-27）：A2 第一纵向切片已落地。用户可通过显式 actor + idempotency key + expected status 更新 Workspace 状态，stale expected status 会以 conflict fail-closed；每次成功变更生成不可变 `status_changed` Timeline Event，可按 Workspace 读取。第一阶段仍不允许 Agent 根据聊天自动写状态，也未接入任何外部招聘网站事件。

## 9.1 目标

让用户记录真实求职进度，而不是自动猜测。

第一阶段状态：

```text
considering
preparing
ready_to_apply
applied
interviewing
offer
rejected
withdrawn
```

### 9.2 状态写入原则

所有状态必须来自：

- 用户显式操作；或
- 未来连接器返回的可验证外部事件。

Agent 不能根据聊天内容默认写状态。

### 9.3 Timeline

记录：

```text
workspace_created
resume_variant_saved
action_completed
status_changed
mock_interview_completed
evidence_confirmed
rematch_completed
ranking_changed
```

---

# 10. Agent 在执行层中的职责

Agent 可以：

- 根据当前 Workspace 状态建议下一步；
- 生成 Resume Proposal；
- 生成面试问题；
- 评价用户回答；
- 将 Gap 转成 Action Item；
- 在 Action 完成后建议补 Evidence；
- 在 Evidence 更新后触发“是否需要 Re-match”的 PendingAction；
- 总结 Workspace 进展。

Agent 不可以：

- 代替用户确认职业事实；
- 自动标记已投递；
- 自动发送简历；
- 自动联系 HR；
- 绕过 Requirement / Match Release Gate。

---

# 11. Agent Tool 设计

vNext 1.2 建议新增粗粒度 Tool：

```text
get_application_workspace
create_application_workspace
get_resume_proposal
save_resume_variant
get_interview_session
submit_mock_answer
list_execution_actions
update_execution_action
update_application_status
```

其中分类：

### 可自动 read

```text
get_application_workspace
get_resume_proposal   # 若为 read-only cached proposal
get_interview_session
list_execution_actions
```

### 必须 Human Gate

```text
create_application_workspace
save_resume_variant
update_execution_action
update_application_status
```

### Provider Cost Gate

如果 `get_resume_proposal` / interview generation 需要 Provider，则通过 PendingAction / existing cost policy 执行，不能隐藏成本。

---

# 12. API 建议

```text
POST /api/v1/application-workspaces
GET  /api/v1/application-workspaces/{id}

POST /api/v1/application-workspaces/{id}/resume-proposals
POST /api/v1/application-workspaces/{id}/resume-variants
GET  /api/v1/application-workspaces/{id}/resume-variants

POST /api/v1/application-workspaces/{id}/interview-sessions
POST /api/v1/interview-sessions/{id}/answers

GET  /api/v1/application-workspaces/{id}/actions
POST /api/v1/application-workspaces/{id}/actions
PATCH /api/v1/execution-actions/{id}

POST /api/v1/application-workspaces/{id}/status
GET  /api/v1/application-workspaces/{id}/timeline
```

所有写 API 必须支持：

- actor；
- idempotency key；
- current fact fingerprint；
- conflict handling。

---

# 13. Stale Protection

Workspace 允许长期存在，但每个生成物必须记录 source snapshot。

如果：

```text
Profile v3 → v4
Requirement Extraction changed
MatchReport changed
```

旧 Resume Variant 可以继续作为历史 artifact，但必须标记：

```text
outdated_source
```

新的生成 / Review 必须基于 current facts。

不能静默用旧 Resume Variant 冒充最新建议。

---

# 14. Growth Loop 集成

执行层最终必须重新接回现有 Growth Loop：

```text
Gap
→ Action
→ Learn / Practice
→ New Real Evidence
→ Evidence Proposal
→ Human Confirm
→ Profile New Version
→ Re-match
→ Requirement Delta
→ Ranking Signal
→ Workspace Next Action
```

这是 vNext 1.2 最重要的闭环，而不是“生成一份漂亮简历”。

---

# 15. Web UX

建议新增：

```text
/jobs/{jobId}/apply
```

或：

```text
/applications/{workspaceId}
```

Workspace 页面结构：

```text
Header
├── Job / Company
├── Application Status
├── Match / Recommendation
└── Next Best Action

Tabs / Sections
├── Overview
├── Resume
├── Interview
├── Actions
└── Timeline
```

### 15.1 Next Best Action

只能根据 current facts + Workspace state 生成，例如：

- 先解决 P0 Evidence Gap；
- Resume 已准备，下一步做 Mock Interview；
- 当前准备完成，等待用户确认是否标记 Ready to Apply；
- 新 Evidence 已确认，建议 Re-match。

不能因为“流程完整”就自动把状态往前推。

---

# 16. Eval

### 16.1 Resume Grounding Eval

至少 30 Case：

- generated sentence 是否都有 Evidence；
- 是否错误把 Requirement 变成经历；
- 是否出现虚构指标；
- 是否引用 stale Profile。

### 16.2 Interview Eval

至少 30 Case：

- 问题是否来自 Requirement；
- Feedback 是否能指出 unsupported claim；
- 是否错误鼓励编造；
- 是否混用其他 Job Requirement。

### 16.3 Execution State Eval

至少 20 Case：

- application status 只由用户改变；
- duplicate write 幂等；
- stale source 标记；
- action done 不等于 confirmed skill；
- Workspace 与 Job identity 不串。

---

# 17. Release Gate

vNext 1.2 第一阶段发布门槛：

- unsupported career fact generation = 0；
- Resume Variant provenance coverage = 100%；
- cross-job Requirement leakage = 0；
- automatic application status mutation = 0；
- duplicate write side effect = 0；
- stale source silent reuse = 0；
- Resume / Interview / Action / Status 四条主路径均可运行；
- Growth Loop 能从 Action 回到 Evidence / Re-match；
- Agent write actions 全部经过 Human Gate；
- Trace 可还原 proposal → confirm → write。

---

# 18. 版本拆分

## vNext 1.2-A：Application Workspace

- Workspace；
- Status；
- Timeline；
- current fact snapshot。

## vNext 1.2-B：Resume Execution

- Resume Proposal；
- provenance；
- review / save Variant。

## vNext 1.2-C：Interview / Mock

- Requirement questions；
- answer review；
- unsupported claim detection。

## vNext 1.2-D：Action → Evidence → Re-match

- ActionItem；
- Evidence Proposal；
- Profile confirm；
- Re-match / Ranking signal；
- Next Best Action。

---

# 19. 后续 P2 扩展

只有 vNext 1.2 真实使用稳定后才评估：

- Browser Computer Use 自动填表；
- 邮件 / Recruiter connector；
- 自动同步投递状态；
- Calendar interview scheduling；
- 求职 CRM；
- 自动跟进提醒。

这些都属于 `external_action`，必须有更严格授权、审计和撤销 / 恢复策略。

---

# 20. DoD

- [ ] Application Workspace；
- [ ] Resume Variant + provenance；
- [ ] Interview / Mock；
- [ ] Execution ActionItem；
- [ ] Application Status / Timeline；
- [ ] Human Gate for writes；
- [ ] stale source protection；
- [ ] Growth Loop 回流；
- [ ] Resume / Interview / State Eval；
- [ ] Web 工作台；
- [ ] Trace；
- [ ] 不自动投递、不自动联系招聘者。
