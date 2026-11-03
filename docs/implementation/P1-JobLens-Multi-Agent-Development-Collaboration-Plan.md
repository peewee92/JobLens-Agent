# JobLens 双电脑 / 多 AI Agent 协作开发方案

- 状态：Active / vNext 1.2 Engineering + vNext 1.1 Release Promotion
- 目标：在不破坏事实边界、发布证据和 Git 可审计性的前提下，让工程主线不再被外部 Provider HUMAN_GATE 长期阻塞。
- 当前工程主线：`vNext 1.2 Job Search Execution Layer`
- 并行发布泳道：`vNext 1.1 Provider Model Quality Release Promotion`
- 前置事实：`vNext 1.0 Agent Runtime` 的 LG-0～LG-4 已完成，`vNext 1.1 Core Engineering` 已完成。
- 当前双电脑具体任务分工与 Agent B 启动说明：`docs/implementation/P1-JobLens-Dual-Agent-Work-Allocation.md`

---

## 1. 核心原则

多 Agent 并行不等于多主线并行。

项目始终只有一个产品主线：

```text
vNext 1.1
→ vNext 1.2
→ vNext 1.3
→ vNext 2.0
```

Engineering progression 与 Release promotion 分开管理：Agent A 可以推进当前 `vNext 1.2` 工程主线，Agent B / 人工会话继续收口 `vNext 1.1` Provider 模型质量证据。禁止把未通过的 v1.1 Provider Gate 宣称为发布完成；也禁止 Agent A 提前进入 `vNext 1.3 MCP` 或任何 Multi-Agent 产品架构。

协作目标不是提高 commit 数，而是提高：

```text
Milestone Advancement
+ 可验证性
+ 合并吞吐
- 冲突
- 重复开发
- 假证据
```

---

## 2. 推荐角色模型

采用：

```text
                Integration Owner
                       │
             ┌─────────┴─────────┐
             │                   │
 Execution Layer Builder    Eval / Safety Builder
       电脑 A                  电脑 B
             │                   │
 Workspace → Execution     v1.1 Provider Gate
             │                   │
 Resume / Mock / Action    Eval → Guard → Trace
             └─────────┬─────────┘
                       ↓
               Integration Owner
```

### 2.1 Integration Owner

固定由主电脑 / 项目 Owner 承担。

职责：

- 决定当前 Active Milestone；
- 冻结跨 Agent Contract；
- 审核两个分支的 diff；
- 决定冲突时哪个实现为准；
- 合并 Core 与 Eval；
- 运行最终全量回归；
- 更新 ROADMAP / Milestone COMPLETE 状态；
- 决定何时进入下一阶段。

Integration Owner 独占以下类型文件的最终修改权：

- `docs/roadmap/ROADMAP.md`；
- 阶段状态 / Release Gate 结论；
- 关键架构边界；
- 根依赖 / lockfile 的最终合并；
- 跨 Agent 冲突裁决。

### 2.2 电脑 A：Execution Layer Builder（原 Core Builder）

当前小时自动推进任务归入该泳道。

目标：实现当前 vNext 1.2 的主产品执行层，让 Ranking / Gap / Preparation 真正落到可追踪的求职行动。

严格顺序：

```text
A1 Application Workspace + current fact snapshot
→ A2 Application Status / Timeline + idempotent write boundary
→ A3 Resume Variant + provenance + human review/save
→ A4 Interview / Mock + grounded answer review
→ A5 Execution ActionItem
→ A6 Action → Evidence → Re-match / Ranking signal
→ A7 Next Best Action / Web workspace vertical slice
```

职责：

- 优先交付真实用户价值纵向切片，而不是继续扩大 v1.1 case 数；
- 复用已有 Requirement / Match / Gap / Preparation / Growth Loop，不复制业务能力；
- 保持 evidence / ACL / release gate / Human Gate；
- 写操作必须有 actor / idempotency / stale / conflict 边界；
- 先失败回归，再实现；
- 提供 targeted tests；
- 只有稳定可复现的 v1.1 Core bug 才临时回切；v1.2 未形成工程闭环前不进入 v1.3。

默认主要修改区域：

```text
services/backend/app/agent/**
services/backend/app/application/**        # 仅当前 Slice 必须部分
services/backend/app/api/**                # 仅真正需要暴露 seam 时
对应 runtime / contract tests
```

Core Builder 不应主动承担大规模 Eval Dataset 建设，避免同时修改 Core + Eval 导致职责重叠。

### 2.3 电脑 B：Eval / Safety Builder

当前目标：保持 v1.1 Core handoff freeze，独立收口 Provider 模型质量 Release Promotion；只有真实 Gate 暴露稳定 Core bad case 时才回传 Agent A。不得用持续扩 Dataset 或重复付费 cohort 占用 Agent A 的 v1.2 主线。

严格顺序：

```text
B1 60+ Intent Eval Dataset
→ B2 Intent Eval Runner / Release Criteria
→ B3 40+ Tool Selection Eval
→ B4 unknown / invalid args / repeat / no-progress guards
→ B5 30+ Multi-turn Trajectory Eval
→ B6 Trace Replay / vNext 1.1 Release Gate
```

职责：

- 将 PRD 中验收标准变成可执行 Dataset / Eval；
- 用 Bad Case 锁定回归；
- 验证 forbidden tool / wrong scope / unauthorized write；
- 验证 maxTurns / maxToolCalls / retry / loop guard；
- 验证 grounding coverage；
- 默认使用 fixture / replay / isolated SQLite；
- 不重写 Runtime，不创建第二套 Agent Loop。

默认主要修改区域：

```text
services/backend/app/evals/**
data/evals/**
tests/**                            # Eval / guard / trajectory 范围
必要的 trace replay fixtures
```

---

## 3. vNext 1.1 历史并行节奏（已完成 Core 阶段）

### Cycle 1

电脑 A：

```text
CareerIntent schema
Intent Router
Grounded job reference resolution
Clarification / unsupported contract
```

电脑 B：

```text
60+ Intent Eval Dataset
single-goal
multi-goal
current-job / pronoun
clarification
unsupported / unsafe
```

共同完成标准：Intent Contract + Router + Intent Eval Gate。

### Cycle 2

电脑 A：

```text
Dynamic Tool Selection
coarse-grained Tool only
Tool Registry metadata / policy integration
```

电脑 B：

```text
40+ Tool Selection Eval
correct tool
forbidden tool
unnecessary tool
wrong job scope
invalid argument
```

### Cycle 3

电脑 A：

```text
Bounded Multi-turn Tool Loop
maxTurns
maxToolCalls
structured tool result replay
```

电脑 B：

```text
unknown tool
invalid args correction
same-tool loop
no-progress
bounded retry
stale termination
```

### Cycle 4

电脑 A：

```text
Context Budget / Compaction
Error Classification
PendingAction / Cost / Human Gate
```

电脑 B：

```text
30+ trajectory dataset
Trace replay
forbidden provider / business write
human auto-sign = 0
vNext 1.1 Release Gate
```

以上为 vNext 1.1 Core 阶段的历史节奏。自 2026-09-27 起，Provider Release Gate 继续约束 v1.1 发布声明，但不再阻塞 Agent A 进入 vNext 1.2 的安全工程切片。

---

## 4. Git 分支模型

### 4.1 禁止方式

禁止：

```text
两台电脑同时直接写 main
两个 Agent 共用同一个 feature branch
Agent A merge Agent B，同时 Agent B 又 merge Agent A
自动任务自动 merge main
```

### 4.2 推荐方式

共享基线：

```text
origin/main
```

每个 Slice 使用短生命周期独立分支：

```text
agent-a/vnext11-intent
agent-b/vnext11-intent-eval

agent-a/vnext11-tool-selection
agent-b/vnext11-tool-selection-eval

agent-a/vnext11-tool-loop
agent-b/vnext11-tool-loop-eval
```

每轮：

```text
fetch origin
→ 从最新共享基线创建自己的 Slice branch
→ 只修改自己的职责范围
→ tests
→ commit
→ push 自己的 branch
→ 输出 Handoff
```

Integration Owner：

```text
fetch
→ 审 Core diff
→ 审 Eval diff
→ 先合 Contract / Core
→ 再合 Eval / Regression
→ 解决冲突
→ 全量验证
→ 更新 ROADMAP
→ 合入 main
```

如果当前开发仍暂时由本机 `main` 自动提交，则在启用电脑 B 前必须先保证远端共享基线包含最新 vNext 代码；此后应尽快把自动任务切到 `agent-a/*` Slice branch，避免持续在 `main` 上产生并行写入。

---

## 5. 文件所有权

文件所有权不是永久边界，而是当前 Slice 的冲突预防规则。

### Core Builder 优先写

```text
services/backend/app/agent/**
services/backend/app/application/**
必要 API seam
核心 Runtime tests
```

### Eval / Safety Builder 优先写

```text
services/backend/app/evals/**
data/evals/**
Eval fixtures
Eval / guard / trajectory tests
```

### Integration Owner 优先写

```text
docs/roadmap/ROADMAP.md
阶段完成状态
README 的主路线描述
跨 Agent 架构决策
共享 dependency / lockfile 冲突
```

若某个 Slice 必须跨所有权修改，Handoff 中必须明确列出原因和改动路径。

---

## 6. Handoff Contract

Agent 之间不依赖聊天记忆同步，以 Git + Handoff 为准。

每个 Slice 完成必须报告：

```text
Base SHA:
Head SHA:

Milestone:
Slice:

Changed paths:

Contract changes:

Capability added:

Tests:
- targeted:
- backend full:
- web:
- typecheck:
- build:
- diff-check:

Provider attempts/completed:
Business writes:

Known blockers:

Files intentionally not touched:

Recommended next slice:
```

另外一个 Agent 开始前必须先读取：

1. 最新共享基线；
2. 最新 Handoff；
3. 当前 PRD；
4. 当前 Slice 的正式 Contract。

---

## 7. Provider / SQLite / 私有数据协作规则

### 7.1 Provider Single Writer

Provider 真实调用默认由主电脑 / Core Builder 统一执行。

电脑 B 默认使用：

- fixture；
- replay；
- frozen provider output；
- isolated tests。

只有明确进行 Intent / Tool Selection Model Eval 时，才单独授权真实 Provider Eval。

这样避免：

- 两台机器重复付费；
- 两套 Trace 难以归因；
- 同一 Eval Dataset 被不同时间模型响应污染。

### 7.2 SQLite 不跨电脑同步

禁止 Git 同步：

- 本地真实 SQLite DB；
- Runtime checkpoint DB；
- `.env`；
- API Key；
- 私有 Profile / Job 原始数据。

可以共享：

- Schema；
- migration；
- fixture；
- Eval Dataset；
- deterministic replay 数据；
- Contract / code。

真实 20-job / accepted baseline / Runtime 状态验证由主电脑作为最终事实源。

---

## 8. 自动推进任务的职责

当前每小时 JobLens 自动推进任务定义为 **Agent A / Core Builder**。

它应该：

1. 读取 AGENTS / ROADMAP / 当前 vNext 1.1 PRD；
2. 检查当前共享基线和未提交修改；
3. 只选择 vNext 1.1 当前顺序中的一个 Core Milestone Driver；
4. 先失败回归，再实现；
5. 运行 targeted tests / 必要全量验证；
6. commit 当前 Core Slice；
7. 双电脑模式正式启用后，只 push 自己的 `agent-a/*` branch；
8. 禁止自动 merge main；
9. 禁止提前做 vNext 1.2 / MCP / Multi-Agent / Dashboard。

当前最优先 Core Slice：

```text
CareerIntent Contract
→ Intent Router
→ grounded job reference resolution
→ clarification / unsupported request
```

后续按 PRD 顺序推进 Tool Selection → Bounded Loop → Context/Error → PendingAction/HITL。

---

## 9. 另一台电脑的职责

另一台电脑固定为 **Agent B / Eval + Safety Builder**，不与小时任务抢 Core 实现。

当前第一任务：

```text
基于 docs/product/P1-career-agent-natural-language-tool-loop-prd.md
冻结 60+ Intent Eval Dataset
```

覆盖至少：

```text
15 single-goal
15 multi-goal
10 current-job / pronoun
10 clarification
10 unsupported / unsafe
```

随后：

```text
Intent Eval Runner
→ 40+ Tool Selection Eval
→ Tool Loop Guards
→ 30+ Trajectory Eval
→ Trace Replay / Release Gate
```

如果 Core Contract 尚未冻结，电脑 B 应先做 Dataset / Eval contract / failing regression，不应自行发明 Runtime API。

---

## 10. 冲突处理规则

出现冲突时，优先级：

```text
AGENTS.md
→ 当前 PRD / Frozen Contract
→ Integration Owner 决策
→ Core Builder 当前正式 Contract
→ Eval fixture
```

原则：

- Eval 适配正式 Contract，而不是为了让 Eval 绿而修改产品 Contract；
- Core 不可为了省测试绕过 Eval / Guard；
- 任一 Agent 不得自行宣布 Milestone COMPLETE；
- 只有 Integration Owner 在两边合并并全量验证后更新 ROADMAP。

---

## 11. 最小协作管理面

不新增复杂 Agent 管理平台。

只保留三个真相源：

```text
Git commit / branch
= 代码真相

Handoff
= 本轮工程事实

ROADMAP
= 当前允许开发什么
```

避免新增重复的 progress.md、agent-status.md、sync-dashboard 等低价值状态文件。

---

## 12. 当前执行结论

当前推荐分工：

### 本机 / 当前小时自动推进

```text
角色：Execution Layer Builder
阶段：vNext 1.2
第一 Slice：Application Workspace + current fact snapshot
之后：Status/Timeline → Resume Variant → Interview/Mock → Action → Evidence → Re-match
Provider calls：始终 0
```

### 另一台电脑 / 其他 AI Agent

```text
角色：Eval / Safety Builder
阶段：vNext 1.1 Release Promotion
职责：复用已有 Dataset / Replay / Gate；仅在人工显式 live-cost 授权时执行真实 Provider 质量门
不得：重复扩 Dataset、反复付费 cohort、改写第二套 Runtime
```

### 项目 Owner / Integration Owner

```text
负责：共享基线、合并、冲突裁决、全量验证、ROADMAP、Release Promotion 与 Engineering Milestone 状态
```

该双泳道持续到 v1.1 Release Promotion 与 v1.2 Engineering 各自收口；两者状态独立，不再互相制造假阻塞。
