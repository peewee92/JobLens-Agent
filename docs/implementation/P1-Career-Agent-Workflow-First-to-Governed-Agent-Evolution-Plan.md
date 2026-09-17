# JobLens Career Agent：从 Workflow-first 到受治理 Agent 的演进方案

> 文档目的：说明 JobLens 当前为什么采用 Workflow-first（工作流优先）设计、它是不是“真正的 Agent”、作为求职项目有哪些亮点与短板，以及后续如何在不破坏现有事实底座、评测和人工门禁的前提下，逐步升级为更有自主决策能力的 Career Agent。
>
> 适用范围：Phase 8 Career Agent 及其后续演进。
>
> 相关决策：`docs/decisions/0004-llm-workflow-agent-boundary.md`
>
> LangGraph Runtime 专项实施规划：`docs/implementation/P1-Career-Agent-LangGraph-Runtime-Integration-Plan.md`

---

## 1. 先给结论

JobLens 当前不是“不够 AI”，也不是一个普通 CRUD Workflow 项目。

它已经包含多条真正由大模型参与的能力链路：

- Resume → Profile Proposal；
- JD → JobRequirement Extraction；
- Evidence Retrieval；
- Semantic Match；
- Ranking；
- Skill Gap；
- Action Plan；
- Resume / Interview Preparation；
- Eval（评测）；
- Human Review（人工评审）；
- Canary（小规模真实验证）；
- Bad Case → Regression（错误案例固化为回归测试）。

但 **当前 Phase 8 的 Career Agent 入口确实更接近“受治理的 Workflow 编排器”，而不是高度自主的 Agent**。

当前形态大致是：

```text
调用方明确 goal
    ↓
CareerAgentEntrypoint
    ↓
构建受治理上下文
    ↓
确定性选择 Tool
    ↓
Tool Registry
    ↓
稳定 Workflow
```

例如：

```text
rank_jobs
→ rank_match_reports

review_gaps
→ target_cohort_gaps

prepare_job
→ job_preparation
```

这不是错误，而是一个合理的阶段性架构：

> **先把事实、业务 Workflow、评测和门禁做好，再逐步把“下一步做什么”的决策权交给 Agent。**

JobLens 后续真正需要补的，不是推倒现有 Workflow，而是在上面增加一层：

```text
自然语言目标
    ↓
任务理解 / 路由
    ↓
Agent 动态选择 Tool
    ↓
调用稳定 Workflow
    ↓
观察结果
    ↓
重新决定下一步
    ↓
必要时暂停等待人工确认
    ↓
继续执行 / 最终回答
```

最终定位应该是：

> **一个证据驱动、可评测、可追踪、有人类决策边界和成本门禁的职业 Agent。**

---

# 2. 为什么当前 Workflow-first 是合理的

## 2.1 Workflow 和 Agent 的核心区别

可以先用一个最简单的标准区分：

### Workflow

路径主要由程序提前确定：

```text
A
↓
B
↓
C
↓
D
```

例如：

```text
JD
↓
Requirement Extraction
↓
Eligibility
↓
Semantic Match
↓
Ranking
```

这些步骤本身可以包含大模型，但“下一步执行什么”主要由代码决定。

### Agent

下一步不完全提前写死，而是模型根据当前目标和执行结果动态决定：

```text
目标
↓
模型判断下一步
↓
调用工具
↓
得到结果
↓
模型重新判断
↓
继续 / 换工具 / 询问用户 / 完成
```

因此：

> **有没有调用大模型，不决定它是不是 Agent；关键看“下一步动作”是谁决定的。**

---

## 2.2 JobLens 为什么不能一开始就全部 Agent 化

JobLens 不是闲聊机器人，它涉及：

- 用户真实职业经历；
- 岗位真实要求；
- 匹配结果；
- 用户投递决策；
- Provider 调用成本；
- 人工 Review；
- 版本化事实；
- Release Gate（发布门禁）。

如果一开始直接做：

```text
用户说一句话
↓
Agent 自由读取简历和 JD
↓
自由调用 Provider
↓
自由重新匹配
↓
自由修改用户状态
```

会出现几个严重问题。

### 问题 1：事实不稳定

同一个岗位在不同 Prompt、不同模型、不同时间可能被重新解释。

JobLens 已经通过：

```text
Raw Job
↓
Versioned JobRequirement
↓
Match / Gap / Prepare 共用
```

建立统一事实底座。

Agent 不应该绕过它，重新随意读原始 JD。

### 问题 2：无法单独评测

如果：

```text
Requirement Extraction
Match
Ranking
Gap
Action Plan
```

全部揉在一个 Agent Prompt 里，出现错误时很难判断：

- 是抽取错了？
- 是匹配错了？
- 是排序错了？
- 是工具选错了？
- 还是最终回答总结错了？

Workflow-first 可以把每层独立评测。

### 问题 3：成本失控

真实 Provider 调用有成本。

如果 Agent 可以随时重新分析 20 个岗位，就可能因为一个普通问题触发大量模型调用。

JobLens 当前已经形成：

```text
Provider Cost
↓
Human Gate
↓
Bounded Run
```

这应该保留。

### 问题 4：Agent 不能替用户做职业决策

例如：

```text
interested
maybe
not_interested
```

这是用户自己的偏好和决定。

Agent 可以建议，但不应该擅自替用户提交。

---

# 3. JobLens 当前真正的亮点

作为面试项目，JobLens 的亮点不应该包装成：

> “我做了一个会聊天、会调用工具的求职 Agent。”

这种表达太普通。

真正有价值的是下面几层。

## 3.1 证据驱动，而不是让模型编经历

核心原则：

```text
重要推荐
↓
必须能追溯到
Profile Evidence / SearchIntent / JobRequirement / Market Facts
```

这比“模型读简历后自由发挥”更接近生产系统。

---

## 3.2 JobRequirement 作为统一事实底座

```text
Raw JD
↓
Requirement Extraction
↓
人工 / 自动质量门禁
↓
Versioned JobRequirement
        ↓
   ┌────┼────┐
   ↓    ↓    ↓
 Match Gap Prepare
```

这避免不同能力各自重新解释 JD。

---

## 3.3 AI + 人工的模型质量治理闭环

JobLens 已经形成非常适合作为面试故事的一条链：

```text
真实岗位
↓
模型抽取
↓
自动 Eval
↓
人工 Review
↓
发现 Bad Case
↓
定位错误类型
↓
Prompt / 语义规则修复
↓
固化 Regression Case
↓
新版本重新验证
↓
满足门禁后才能 Release
```

这比“不断改 Prompt，感觉效果变好了”更有工程含金量。

---

## 3.4 Workflow-first + Agent 编排边界清晰

现有 ADR-0004 的核心原则应该继续保留：

```text
LLM Capability
↓
Domain Workflow
↓
Career Agent
```

Agent 不重新实现：

- Requirement Extraction；
- Semantic Match；
- Ranking；
- Skill Gap；
- Prepare。

Agent 只组合这些成熟能力。

这是一个重要的系统设计亮点，而不是短板。

---

# 4. 当前 Phase 8 的真实短板

当前最大问题不是“没有 AI”，而是：

> **Agent 自主决策层还太薄。**

当前入口要求调用方提前给出：

```text
CareerAgentGoal
```

这意味着：

```text
用户目标理解
↓
选择哪个 Workflow
```

主要仍由调用方提前完成。

因此当前版本更准确的描述是：

> **受治理的 Career Workflow Orchestrator（职业工作流编排器）**。

如果简历直接写：

> “自主 Career Agent 根据自然语言目标动态规划并调用工具”

目前会经不起源码追问。

后续需要补的就是这一层。

---

# 5. 目标架构：受治理的自然语言 Career Agent

目标不是把所有东西改造成 Tool，也不是追求“越自由越智能”。

目标架构：

```text
                      用户自然语言
                           ↓
                  Career Agent Runtime
                           ↓
                  受治理 Career Context
                           ↓
               模型决定“下一步做什么”
                           ↓
              ┌────────────┼────────────┐
              ↓            ↓            ↓
           Ranking      Skill Gap     Preparation
              ↓            ↓            ↓
              └────── Stable Workflows ─┘
                           ↓
                       Tool Result
                           ↓
                     返回 Agent
                           ↓
              根据结果重新决定下一步
                           ↓
          ┌────────────────┼─────────────────┐
          ↓                ↓                 ↓
       再调用工具       请求人工确认        最终回答
```

外层必须继续保留：

```text
权限
成本门禁
最大轮数
超时
幂等
Trace
Eval
人工决策边界
```

---

# 6. 自然语言意图理解 / 路由怎么做

## 6.1 不要把“意图分类器”理解成必须独立存在的模型

小规模工具场景可以直接：

```text
用户问题
+
当前上下文
+
允许使用的工具说明
↓
LLM 直接选 Tool
```

工具少、语义差异明显时，这是最简单的方案。

JobLens 第一版自由文本 Agent 完全可以先采用这种方式。

---

## 6.2 JobLens 后续可以升级为分层路由

当工具增加以后，可以使用：

```text
用户请求
↓
硬规则
↓
语义路由 / 小模型路由
↓
不确定时交给强模型
↓
缩小可见 Tool 集合
↓
Career Agent
```

例如：

```text
“帮我看看这 20 个岗位最值得投哪几个”
→ ranking / match domain

“我和这些 Agent 岗最大的差距是什么？”
→ target cohort / skill gap domain

“明天面试 XX 公司，帮我准备”
→ job preparation domain
```

需要注意：真实用户经常一次表达多个目标。

例如：

> 哪些岗位最值得投？我的差距是什么？这周该学什么？

所以路由结果最好支持：

```json
{
  "goals": [
    "rank_jobs",
    "review_gaps",
    "build_action_plan"
  ]
}
```

而不是强制单标签分类。

---

# 7. Tool 设计原则

## 7.1 Agent Tool 不等于底层 API

不要变成：

```text
一个 HTTP API
=
一个 Agent Tool
```

更合理的是：

```text
Tool = 一个模型可以理解、可以安全调用的业务能力
```

JobLens 应继续暴露粗粒度 Workflow Tool，例如：

```text
rank_current_jobs
review_target_cohort_gaps
prepare_current_job
```

而不是把 Repository、数据库查询、每一个内部步骤全部暴露给模型。

---

## 7.2 Tool Capability 不等于 Tool Authority

可以翻译成：

> **Agent 知道怎么做，不代表系统允许它直接做。**

工具建议按风险分级。

### A. 只读工具

可以自动调用：

```text
get_current_profile
get_search_intent
rank_current_match_reports
get_current_job_preparation
review_existing_skill_gap
```

### B. 有成本但无用户数据副作用

需要成本门禁：

```text
reanalyze_job_requirements
run_semantic_match
refresh_missing_match_reports
```

### C. 修改用户真实状态

必须人工确认：

```text
submit_job_feedback
update_search_intent
accept_profile_evidence
```

### D. 对外副作用

MVP 继续不开放：

```text
auto_apply_job
send_recruiter_message
```

---

# 8. 推荐的 Agent Loop

JobLens 后续可以实现下面的循环：

```text
用户目标
↓
构建 Career Context
↓
模型判断下一步
↓
Tool Call
↓
Registry 校验：
    - Tool 是否存在
    - 参数是否合法
    - 上下文是否允许
    - 是否需要成本授权
    - 是否需要用户确认
↓
执行 Workflow
↓
Tool Result
↓
重新放回 Agent
↓
模型重新判断
    ├── 再调用 Tool
    ├── 请求用户确认
    ├── 说明证据不足
    └── Final Answer
```

这套循环的核心不是“模型多调用几次工具”，而是：

> **模型可以根据真实执行结果改变后续路径。**

---

# 9. 一个适合 Demo 和面试的完整场景

用户说：

> 我最近想重点找武汉的 Agent 岗，比较在意薪资，但担心 Python 和 RAG 不够。你帮我看看哪些岗位最值得投，再分析差距，给我安排这周学习重点。

理想执行轨迹：

```text
1. Career Agent 理解为多个目标：
   - 排名岗位
   - 分析目标岗位群
   - Skill Gap
   - Action Plan

2. 读取当前 Profile / SearchIntent

3. 调用 rank_current_jobs

4. 发现只有部分 Job 有 current MatchReport

5. Agent 判断：排名证据不完整

6. 尝试调用 refresh_missing_match_reports

7. Runtime 发现：该动作会产生 Provider 成本

8. Pause：
   “目前还有 16 个岗位缺少最新 MatchReport。
    是否允许先分析最多 5 个岗位？”

9. 用户批准 5 个

10. Resume Run

11. 完成最多 5 个 bounded Provider 调用

12. 再次 Ranking

13. 形成 Target Cohort

14. Skill Gap

15. Action Plan

16. 最终输出：
    - 最值得投的岗位
    - 为什么
    - 证据
    - 主要差距
    - 本周行动计划
```

这个场景同时展示：

- 自然语言目标理解；
- 多目标任务；
- 动态工具选择；
- 根据结果重新规划；
- Provider 成本门禁；
- 暂停 / 恢复；
- Evidence Grounding；
- Workflow 编排；
- 最终可解释输出。

---

# 10. 重新冻结后的开发顺序（2026-09-17）

当前 v0.1 / v0.2 主业务 Workflow 已经具备真实运行证据：Requirement Review 已放行，真实岗位已有完整 MatchReport / UserFeedback 覆盖，Target Cohort、Skill Gap、Action Plan、Job Preparation 与 Growth Loop 的工程主链均已存在。因此从本版本开始，**不再把继续增加 Growth Loop 小分支作为默认主线**。

新的版本顺序冻结为：

```text
v0.2 Freeze Candidate
  ↓
vNext 1.0 Agent Runtime
  ├─ Runtime Boundary
  ├─ LangGraph State / Checkpoint
  ├─ Durable HITL / Resume / Stale Guard
  └─ Trajectory Eval / Trace
  ↓
vNext 1.1 Natural Language + Bounded Tool Loop
  ├─ Career Intent
  ├─ Dynamic Tool Selection
  ├─ Multi-turn Tool Calling
  └─ Cost / Effect Gate
  ↓
vNext 1.2 Job Search Execution Layer
  ├─ Application Workspace
  ├─ Resume Proposal / Review
  ├─ Interview / Mock
  ├─ Study / Evidence Actions
  └─ Application Status
  ↓
vNext 1.3 MCP / External Agent Integration
  ↓
vNext 2.0 Continuous Career Agent
```

核心原则：

> **先让 Agent Runtime 可恢复、可中断、可评测，再让 LLM 拥有动态 Tool 决策；先把产品求职执行闭环做实，再做外部协议和长期自主运行。**

Growth Loop 从此进入“真实 blocker 驱动维护”模式：只处理 P0 用户价值 blocker、Evidence grounding / 数据一致性 / 安全问题，不再为了增加 commit 或页面分支继续横向扩张。

---

## P1-0：v0.2 Freeze Gate

目标：冻结当前 Workflow MVP，使后续 Agent 化不会同时改变业务事实层和 Runtime 层。

必须保持：

- Profile / SearchIntent / JobRequirement / MatchReport 的版本化事实边界；
- Eligibility / Ranking / Gap / Preparation 的现有 Workflow；
- Requirement Review / Release Gate；
- Evidence grounding；
- UserFeedback 由用户显式提交；
- Growth Loop 已有 `Evidence → Re-match → Improvement → Next Action` 主链。

只允许继续修：

- 真实 P0 / P1 用户闭环 blocker；
- 数据不一致；
- stale / provenance / grounding 问题；
- 安全问题；
- Agent Runtime 接入必须的稳定接口缺口。

不再做：

- 为 Growth Loop 增加低价值展示分支；
- 新的 Requirement semantic tuning（除非真实 P0 bad case）；
- Multi-Agent；
- 自动投递 / 自动联系招聘者。

---

## P1-A：Agent Runtime Boundary（vNext 1.0 / LG-0）

在任何自然语言路由之前先抽象框架无关 Runtime Port：

```python
class CareerAgentRuntime(Protocol):
    def run(self, request): ...
    def resume(self, request): ...
    def get_state(self, thread_id): ...
    def cancel(self, thread_id): ...
```

实现分为：

```text
WorkflowCareerAgentRuntime
LangGraphCareerAgentRuntime
```

简单只读查询继续走 Workflow Runtime；只有跨步骤、需要 State / Checkpoint / HITL 的任务才进入 LangGraph。

### 验收

- 当前 `CareerAgentEntrypoint` 行为不变；
- 上层 API 不依赖 LangGraph 类型；
- Runtime contract 有单元测试；
- 现有 Agent / Workflow tests 全绿。

---

## P1-B：LangGraph State + Checkpoint（vNext 1.0 / LG-1）

第一条真实 Vertical Slice 固定为：

```text
Ranking
→ propose Target Cohort
→ interrupt
→ human decision
→ Skill Gap
```

第一阶段只使用已经发布的 Profile / SearchIntent / MatchReport / JobRequirement，`provider_calls = 0`。

必须实现：

- 显式 State，不使用 messages-only；
- conditional routing；
- SQLite-first persistent checkpoint；
- thread / run 状态查询；
- Runtime step / tool / retry limits；
- Runtime Trace。

### 验收

- 进程重启后仍能读取 pending thread；
- Checkpoint 只保存事实引用 / version / fingerprint，不复制 raw Resume / JD；
- business-state writes = 0；
- Runtime state write 与业务事实 write 指标分离。

---

## P1-C：Durable Human-in-the-loop（vNext 1.0 / LG-2）

HITL 不再只是页面按钮或 URL handoff，而是 Runtime 的正式状态边界。

第一版审批对象：`Target Cohort Proposal`。

支持：

```text
approve
edit
reject
```

并实现：

- Interrupt Payload；
-跨请求 Resume；
- stale Profile / SearchIntent / MatchReport 校验；
- duplicate resume 幂等；
- cancel；
- browser close / service restart recovery；
- Human Decision 不可由 Agent 代签。

详细需求见：`docs/product/P1-career-agent-durable-hitl-prd.md`。

---

## P1-D：Trajectory Eval + Trace Release Gate（vNext 1.0 / LG-3～LG-4）

LangGraph Runtime 只有在轨迹可评测后才算完成。

至少覆盖：

- expected / forbidden nodes；
- expected / forbidden tools；
- interrupt / resume；
- stale state；
- duplicate resume；
- runtime limits；
- provider_calls；
- business_state_writes；
- grounding refs；
- terminal state。

第一版至少 20 条 deterministic trajectory cases，全部通过才允许进入自然语言 Agent Loop。

---

## P1-E：自由文本 → 结构化 Career Intent（vNext 1.1）

Runtime / HITL / Eval 稳定以后，才允许引入自然语言变量。

输入：

```text
用户自然语言
+ Governed Career Context Summary
+ 当前页面 / Job scope（若有）
```

输出结构化 Intent：

```json
{
  "goals": [],
  "job_ids": [],
  "current_job_id": null,
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": 0.0
}
```

第一步仍只理解，不执行有副作用 Workflow。

### 验收

至少 60 条 NLU Eval，覆盖单目标、多目标、模糊表达、当前岗位引用、越界请求、需要澄清与不可处理请求。

详细需求见：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`。

---

## P1-F：Dynamic Tool Selection + Bounded Multi-turn Tool Loop（vNext 1.1）

把当前显式 `CareerAgentGoal → Tool` 演进为：

```text
Goal / State
→ Model selects Tool
→ Registry.invoke()
→ Tool Result
→ Model decides next step
→ Tool / Ask Human / Finish
```

但 Tool 继续只暴露稳定的粗粒度 Workflow，不把 Repository / 内部函数全部 Tool 化。

必须加入：

- maxTurns；
- maxToolCalls；
- unknown tool fail-fast；
- duplicate call detection；
- tool replay / idempotency；
- context budget；
- timeout / cancellation；
- structured tool error；
- execution trace；
- no-op / loop detection。

第一阶段动态 Tool Loop 只开放 read-only / transient tools。产生 Provider 成本或业务写入的 Tool 必须进入下一层 Effect Gate。

---

## P1-G：Effect / Cost / Human Gate（vNext 1.1）

对以下动作统一产生 `PendingAction`：

- Provider 成本动作；
- Profile / SearchIntent 修改；
- UserFeedback 写入；
- Application 状态变化；
- 未来外部系统动作。

`PendingAction` 至少说明：

- action type；
- why；
- scope；
- estimated provider calls / cost class；
- business writes；
- required human decision；
- expiration / fingerprint。

Agent 可以提出，不能代签。

---

## P1-H：Job Search Execution Layer（vNext 1.2）

当 Agent Runtime 和 Tool Loop 稳定后，才把“分析”推进到“执行准备”。

第一阶段包含：

```text
Job Application Workspace
→ Resume Delta Proposal
→ Human Review / Save Variant
→ Interview / Mock Preparation
→ Study / Evidence Action
→ Application Status Tracking
```

明确不包含自动投递和自动联系招聘者。

所有生成内容必须引用确认的 Profile Evidence / released JobRequirement；生成内容首先是 Proposal，不自动回写确认事实。

详细需求见：`docs/product/P1-job-search-execution-layer-prd.md`。

---

## P1-I：MCP / External Agent Integration（vNext 1.3）

在内部 Runtime / Tool Registry 已稳定后，再将粗粒度只读能力通过 MCP 暴露给外部 Agent。

第一阶段仍坚持：

- local-first / STDIO；
- read-only / transient；
- 不自动触发 Provider；
- 不复制业务规则；
- JobLens Backend 仍是事实与 Policy 来源。

已有需求见：`docs/product/P1-joblens-mcp-pi-extension.md`。

---

## P2：Continuous Career Agent（vNext 2.0）

只有 vNext 1.x 在真实使用中稳定后才进入长期自主 Agent：

```text
Career Goal
→ Periodic Job Refresh
→ Compare / Rank
→ Notify
→ Gap / Action Plan
→ New Evidence
→ Re-match
→ Plan Update
```

此阶段才评估：

- scheduler / background jobs；
- durable long-term memory；
- proactive notifications；
- periodic re-evaluation；
- cross-session plan；
- 远程 MCP / 多用户权限。

仍不默认等价于自动投递或 Multi-Agent。

---

# 11. 不建议现在做什么

## 不做 1：Multi-Agent 炫技

现在不要把：

```text
Ranking Agent
Gap Agent
Resume Agent
Interview Agent
```

全部拆成独立 Agent。

目前这些业务边界已经有成熟 Workflow，拆 Agent 只会增加：

- handoff；
- context 复制；
- Trace 复杂度；
- 工具选择错误；
- 成本；
- Eval 难度。

先把单 Agent Loop 做扎实。

---

## 不做 2：把所有内部函数变成 Tool

Tool 越细不代表越 Agent。

应该继续坚持：

```text
Agent Tool
≈
稳定业务 Workflow
```

而不是 Repository method。

---

## 不做 3：为了“智能”取消人工门禁

Agent 的自主性应该体现在：

```text
选择路径
选择工具
根据结果重新规划
```

而不是体现在：

```text
绕过用户决定
自动花钱
自动提交反馈
自动投简历
```

---

# 12. JobLens 作为面试项目应该怎么定位

不要说：

> “这是一个 AI 求职聊天机器人。”

推荐定位：

> **JobLens 是一个证据驱动的职业 Agent。它先把用户经历和岗位要求建立成版本化、可追溯的事实，再通过 Match、Ranking、Skill Gap 和 Preparation Workflow 形成稳定业务能力；Career Agent 位于这些能力上方，负责根据用户自然语言目标动态编排。对于 Provider 成本和用户决策，Agent 必须经过人工门禁，整个过程有 Trace、Eval 和 Bad Case Regression。**

---

# 13. 面试时如何回答“这到底是 Workflow 还是 Agent？”

推荐回答：

> 当前底层核心业务是 Workflow-first，这是我有意做的设计，而不是能力不足。Requirement Extraction、Match、Ranking 这类路径明确、需要稳定评测的能力，我先做成确定性 Workflow；Agent 不重复实现业务逻辑，而是位于上层，根据用户目标选择和组合这些 Workflow。早期 Phase 8 入口为了保证可测试性，使用显式 Goal 和只读 Tool；后续再逐步增加自由文本路由、多轮 Tool Loop、暂停恢复和成本门禁。我的目标不是让模型越自由越好，而是在明确边界中让它动态决策。

如果继续追问“Agent 的自主性体现在哪里”，回答：

```text
它可以决定：
- 当前需要哪些 Workflow；
- 以什么顺序调用；
- 工具结果不足后下一步怎么办；
- 什么时候需要补充信息；
- 什么时候需要请求人工确认；
- 什么时候已经足够回答。

它不能决定：
- 凭空创造用户经历；
- 推翻确定性 Eligibility；
- 绕过 Provider 成本授权；
- 替用户提交 interested / reject；
- 绕过人工 Review；
- 自动投递岗位。
```

---

# 14. JobLens 与 Ahoy 的项目分工

两个项目不要讲成重复项目。

## Ahoy

证明：

> 我参与过真实企业 Agent 的生产工程。

重点：

- B2B；
- 企业权限；
- Tool Calling；
- SSE Streaming；
- Context；
- Memory；
- KB / RAG；
- Trace；
- Token / Cost；
- Human-in-the-loop；
- 多端真实产品约束。

## JobLens

证明：

> 我能自己从 0 到 1 设计并实现一个 AI 应用 / Agent 系统。

重点：

- Python / FastAPI；
- 领域建模；
- Structured Output；
- Evidence Grounding；
- Requirement / Match；
- Eval；
- Human Review；
- Bad Case Regression；
- Provider Gate；
- Workflow + Agent Runtime。

两者组合起来比重新做一个普通聊天 Agent 更有说服力。

---

# 15. 是否需要另外做 Paper Agent / Travel Agent

结论：

> **JobLens 不应该因为“当前 Agent 自主性偏低”而被放弃。优先补全 JobLens Career Agent。**

如果时间足够，需要额外做一个 7～14 天的小项目专门练“动态 Agent Loop”，Travel Agent 比 Paper Agent 更适合当前求职目标。

## Paper Agent 更适合展示

```text
论文检索
PDF 解析
RAG
引用
Reranker
研究型检索
```

更偏：

- RAG；
- Research Agent；
- 算法 / 学术工具。

## Travel Agent 更适合展示

```text
自然语言目标
实时工具
多约束规划
天气 / 路线 / 地点
动态重规划
预算
Human-in-the-loop
```

更贴近：

- AI Application Engineer；
- Agent Application Engineer；
- AI Product Engineer。

但优先级仍然是：

```text
1. Ahoy：真实生产 Agent 案例
2. JobLens：个人旗舰 Agent 项目
3. agent-learning-lab：底层原理证明
4. Travel Agent：有余力再做的 1～2 周专项练习
```

---

# 16. 最终完成标准

JobLens Career Agent 真正可以作为强面试项目时，应至少具备：

- [ ] 用户可以直接输入自由自然语言目标；
- [ ] 支持单目标和多目标识别；
- [ ] Agent 能动态选择稳定 Workflow Tool；
- [ ] Tool Result 会重新进入 Agent Loop；
- [ ] Agent 可以根据结果改变后续路径；
- [ ] 有最大轮数、超时、取消和重复调用保护；
- [ ] 有 Tool / Agent Trace；
- [ ] 有路由 Eval；
- [ ] 有 Tool Selection Eval；
- [ ] 有执行轨迹 Eval；
- [ ] 有最终回答 / Evidence Eval；
- [ ] Provider 成本调用有明确 Human Gate；
- [ ] 用户真实状态修改有明确 Human Gate；
- [ ] Run 可以暂停并安全恢复；
- [ ] 不允许 Agent 绕过确定性 Eligibility；
- [ ] 不允许 Agent 重新发明 Profile / JobRequirement 事实；
- [ ] Demo 可以完整展示 Ranking → Gap → Action Plan 的动态链路；
- [ ] README / 架构图 / Demo 视频能解释 Workflow 与 Agent 的边界。

---

# 17. 一句话架构原则

> **JobLens 不追求“模型越自由越智能”，而是让模型在可信事实、稳定 Workflow、成本门禁、人工决策和评测体系构成的边界内，自主决定下一步。**
