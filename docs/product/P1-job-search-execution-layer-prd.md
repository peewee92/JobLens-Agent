# P1 Job Search Execution Layer 产品需求文档

- 状态：Planned / vNext 1.2
- 对应缺口：**4. 真正的“求职执行层”**
- 前置条件：vNext 1.0 Agent Runtime 完成；vNext 1.1 Natural Language + Bounded Tool Loop 基本稳定
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
