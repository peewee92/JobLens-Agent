# 从后端到 Agent｜Requirement Eval 人工 Review 与正式 Baseline 实战

日期：2026-08-03
对应阶段：P0-3B-2
对应 ADR：`docs/decisions/0023-requirement-eval-human-review-and-accepted-baseline.md`

## 1. 这次真正解决了什么问题

上一阶段已经能够执行 Requirement Eval，并保存：

```text
Eval Run
Case Result
Trace ID
Gate 指标
历史 Baseline 对比
```

但系统仍然缺少一个关键事实：

> 哪一次真实模型运行，经过人类逐案例和 Trace 审查后，被正式接受为后续比较基线？

这次补齐的闭环是：

```text
Live Requirement Eval Run
→ 自动 Gate
→ 允许进入人工审查
→ 人类 accept / reject
→ 不可变 Review
→ 最近一次有效 accepted Review 成为正式 Baseline
```

它没有证明真实 OpenAI 模型已经可靠，也没有允许系统开始 Match。它只是建立了模型质量治理所需的工程机制。

---

## 2. 先预测，再看解释

在阅读 Diff 前，先写下自己的答案。

### 预测 1

Fixture Run 通过 10/10，可以被正式接受吗？

你的答案：

```text
[待填写]
```

### 预测 2

Gate 失败的 Live Run，可以执行哪些 Review？

你的答案：

```text
[待填写]
```

### 预测 3

`releaseEligible=true` 是否意味着模型已经获批？

你的答案：

```text
[待填写]
```

### 预测 4

为什么一条 Eval Run 只能有一条 Review？

你的答案：

```text
[待填写]
```

### 预测 5

两条 Live Run 都被 accepted 后，为什么不直接修改一个全局 `currentBaselineId`？

你的答案：

```text
[待填写]
```

### 预测 6

如果 Review 写数据库失败，之前的 Eval Run 和 Trace 应该怎样处理？

你的答案：

```text
[待填写]
```

### 预测 7

React 已经禁用了接受按钮，Backend 是否还需要重复验证？

你的答案：

```text
[待填写]
```

### 预测 8

自动测试构造的 `simulated-live` Run 被接受，能否作为真实 OpenAI 质量结论？

你的答案：

```text
[待填写]
```

---

## 3. 最小知识：四种状态不要混在一起

### 3.1 `gatePassed`

含义：

> 当前 Workflow 在当前固定 Dataset 上是否达到确定性阈值。

它来自自动评测，例如：

- Case Pass Rate；
- Workflow Success Rate；
- Capability Recall；
- Importance Accuracy；
- Forbidden Capability Rate。

它不包含人类判断。

### 3.2 `releaseEligible`

含义：

> 这次 Run 是否具备进入正式人工接受审查的自动条件。

当前规则：

```text
mode = live
AND gatePassed = true
```

Fixture 即使 10/10，也必须是：

```text
releaseEligible = false
```

### 3.3 `review.decision`

含义：

> 人类看过案例、失败原因和 Trace 后作出的不可变治理结论。

值只有：

```text
accepted
rejected
```

### 3.4 Accepted Baseline

含义：

> 最近一次满足正式条件的 accepted Live Run，用于后续版本比较。

查询条件：

```text
Review = accepted
Run mode = live
Gate passed
release eligible
```

它是从不可变历史中查询出的事实，而不是一个可随意覆盖的布尔字段。

---

## 4. 状态转换真值表

| Run 状态 | Accept | Reject | 可成为 Baseline |
|---|---:|---:|---:|
| Fixture + Gate 通过 | 否 | 否 | 否 |
| Fixture + Gate 失败 | 否 | 否 | 否 |
| Live + Gate 失败 | 否 | 是 | 否 |
| Live + Gate 通过 + release eligible | 是 | 是 | accepted 后可以 |
| 已有 Review | 否 | 否 | 保留首次不可变结论 |

这里一个容易混淆的点是：

> Gate 失败的 Live Run 仍应允许 rejected Review。

因为 rejected 也是有价值的人工证据，它说明：

- 人类确实审查过失败；
- 失败不是无人处理的临时状态；
- 后续可以回查当时为什么拒绝。

---

## 5. 后端分层是怎么落地的

### 5.1 Router

只负责：

```text
HTTP Request
→ Pydantic Schema
→ Use Case
→ HTTP Response
```

Router 不判断：

- Fixture 能不能 Review；
- Gate 是否足够；
- 是否已经 Review；
- 哪一条是 Baseline。

### 5.2 Application Use Case

`ReviewRequirementEvalRunUseCase` 负责真正政策：

```text
读取 Run
→ 检查是否存在
→ 检查是否已有 Review
→ 校验 reviewer / notes
→ 检查 mode
→ 检查 accept 条件
→ 创建 Review
→ 在短事务中提交
```

它不依赖 FastAPI、SQLAlchemy 或 ORM。

### 5.3 Repository

Repository 负责：

- 添加 Review；
- 查询 Review；
- 查询最新有效 Accepted Baseline；
- 把 ORM 数据转换成 Application Model。

Repository 不执行：

```text
commit
rollback
```

### 5.4 Unit of Work

Unit of Work 拥有：

```text
Session 生命周期
commit
rollback
```

Review 只有一条写入，因此事务应短小：

```text
政策校验
→ 开事务
→ INSERT Review
→ COMMIT
```

不应该把人工等待、模型调用或页面交互放进数据库事务。

---

## 6. 为什么 Review 必须不可变

错误做法：

```text
第一次 accepted
→ 第二次直接改成 rejected
```

这样会丢失：

- 谁第一次接受；
- 为什么接受；
- 什么时候接受；
- 哪些后续运行曾经以它为 Baseline。

当前设计通过两层限制：

1. Application 在创建前检查是否已有 Review；
2. 数据库对 `eval_run_id` 设置 Unique Constraint。

即使两个并发请求同时越过第一层，数据库仍能阻止第二条 Review。

---

## 7. 为什么 Baseline 不使用可变全局指针

常见实现：

```python
settings.current_requirement_baseline_id = run.id
```

问题：

- 覆盖后很难恢复历史；
- 不知道是谁批准的；
- 指针可能指向 Fixture 或失效 Run；
- 指针和 Review 数据可能不一致；
- 多请求更新时容易产生竞争状态。

当前实现从不可变 Review 历史推导：

```sql
accepted Review
JOIN valid Live Run
ORDER BY reviewed_at DESC, review_id DESC
LIMIT 1
```

这是一种常见的事件历史思维：

> 不修改过去事实，而是从历史事实计算当前状态。

---

## 8. Web 为什么仍然有权限判断 Helper

Web 中的 `reviewActionsForRequirementRun` 会决定：

- 接受按钮是否启用；
- 拒绝按钮是否启用；
- 展示什么原因。

但它只是 UX Guard：

```text
减少错误点击
解释当前状态
```

真正安全边界仍在 Backend，因为用户可以：

- 手工调用 API；
- 修改浏览器代码；
- 使用另一个客户端；
- 重放请求。

所以同一规则在前后端出现并不等于重复业务实现：

- Backend 是权威政策；
- Web 是从公开状态推导交互行为。

---

## 9. 一个真实开发失败：迁移字段长度漂移

本轮出现过一个具体错误：

```text
ORM: requirement_eval_reviews.eval_run_id = VARCHAR(90)
Migration 初稿: VARCHAR(100)
```

当时：

- 243 个后端行为测试通过；
- Review API 正常；
- Web Smoke 正常。

但 `alembic check` 报告：

```text
Detected type change from VARCHAR(100) to String(90)
```

这说明：

> 业务测试通过，不等于数据库 Schema 与 ORM 一致。

修正方式：

1. 把 0009 migration 改为长度 90；
2. 本地数据库 downgrade 到 0008；
3. 重新 upgrade 到 0009；
4. 再执行 `alembic check`；
5. 在 migration test 中增加列长度断言。

最终证据：

```text
No new upgrade operations detected.
```

这个案例适合在面试中说明：

> 为什么 Migration Test、Upgrade/Downgrade 和 Metadata Drift Check 都需要存在。

---

## 10. 常见错误实现与失败案例

### 错误实现

```python
if run.gate_passed:
    run.is_baseline = True
```

### 失败案例

Fixture Extractor 在固定 Dataset 上得到 10/10：

```text
Gate passed = true
```

系统直接把它标记为 Baseline。后续 Match 以为这是已经验证的真实模型能力，但实际上：

- 没有真实 Provider 调用；
- 没有人类检查；
- 没有 reviewer 和 notes；
- 没有真实岗位样本；
- 没有任何生产质量结论。

结果是：

> 测试系统稳定地证明了一个假模型很稳定。

---

## 11. 本轮工程证据

### Backend

```text
244 tests passed
```

验证内容包括：

- Fixture Review 被拒绝；
- 失败 Live 只能 rejected；
- 合格 Live 可 accepted；
- 一条 Run 只有一条 Review；
- Accepted Baseline 查询；
- Review 持久化失败不产生半记录；
- API 404 / 409 / 422；
- CLI accepted-baseline 前置检查；
- Migration upgrade / downgrade；
- 架构边界。

### Web

```text
31 tests passed
TypeScript typecheck passed
Next production build passed
```

### 真实进程 Smoke

真实启动：

```text
FastAPI
Production Next
Temporary SQLite
```

完成：

```text
Requirement Eval 历史
→ 失败案例和 Trace
→ Fixture Review 422
→ 失败 Live rejected
→ 合格 Live accepted
→ 重复 Review 409
→ Accepted Baseline API
→ SSR 页面刷新
```

### Migration Drift

```text
Alembic check: No new upgrade operations detected
```

---

## 12. 尚未验证的内容

必须明确区分：

### 已验证

- 治理状态机和持久化机制；
- API/Web 闭环；
- simulated-live 测试路径；
- Fixture 与 Live 隔离；
- Accepted Baseline 查询和使用参数前置检查。

### 未验证

- 真实 OpenAI Requirement Eval；
- 真实模型成功使用 `--accepted-baseline` 的完整运行；
- 20 个真实岗位逐条人工审查；
- Dataset 是否代表武汉、Remote、AI Agent 等不同岗位；
- reviewer 身份认证和 RBAC；
- 模型成本、P95 延迟与重试策略；
- 是否已经具备进入 Match 的质量条件。

---

## 13. 面试问题与回答要点

### 问题 1

为什么 Gate 通过后还需要人工 Review？

回答要点：

- Gate 只验证固定数据集阈值；
- 数据集可能不完整；
- 业务语义和严重错误需要人工判断；
- 自动证据与治理批准是不同事实。

### 问题 2

为什么 Fixture 不能被 rejected？

回答要点：

- 本项目把 Review 定义为真实 Provider 的正式治理记录；
- Fixture 失败或通过属于工程测试结果；
- 给 Fixture 正式 Review 会混淆测试证据和模型发布证据。

### 问题 3

为什么失败 Live Run 允许 rejected？

回答要点：

- rejection 是人工审计事实；
- 表示失败已被检查；
- 可记录具体原因；
- 但永远不能成为 accepted baseline。

### 问题 4

为什么 Repository 不 commit？

回答要点：

- Repository 只负责集合式数据访问；
- Application 决定业务操作边界；
- UoW 统一管理事务；
- 方便测试和原子组合多个写入。

### 问题 5

Application 检查重复 Review 后，为什么数据库还要 Unique Constraint？

回答要点：

- 并发请求可能同时读取“尚无 Review”；
- Application 检查不是最终并发保证；
- 数据库约束是最后一致性边界。

### 问题 6

为什么 Baseline 查询按 Review 时间排序，而不是 Run 创建时间？

回答要点：

- Baseline 成为正式状态的时刻是 Review 被接受时；
- 一个较早 Run 可能较晚才被审查；
- 治理时间比运行时间更符合“当前批准版本”。

### 问题 7

为什么 Web 不能成为权限边界？

回答要点：

- 客户端可绕过；
- API 可直接调用；
- 多客户端必须共享同一政策；
- Backend 才是权威。

### 问题 8

为什么 243 个测试通过仍出现 Migration 问题？

回答要点：

- 大多数测试用 `Base.metadata.create_all`，不是实际 migration；
- 行为正确不代表历史迁移定义与 ORM 一致；
- 需要 Alembic upgrade/downgrade 和 drift check。

---

## 14. Demo 内容

### Demo 目标

3–5 分钟展示：

> JobLens 不让模型或自动分数自己宣布“可以上线”。

### Demo 步骤

1. 打开 `/evals/requirements`；
2. 展示 Fixture、失败 Live、合格 Live 三类 Run；
3. 说明 Fixture 10/10 仍不可正式 Review；
4. 打开失败 Live，展示 missing Requirement、wrong importance 和 Trace ID；
5. 提交 rejected Review；
6. 打开合格 Live，展示指标和 Case；
7. 提交 accepted Review；
8. 再次提交，展示不可变 Review 冲突；
9. 返回历史页，展示当前正式 Baseline；
10. 说明下一次真实 Live Eval 可用 `--accepted-baseline` 对比。

### Demo 中必须主动声明

```text
当前演示数据是 simulated-live Smoke 数据，
证明的是治理工作流，不是 OpenAI 模型质量。
```

---

## 15. 学习完成自检

在不看代码的情况下，尝试用 3 分钟解释：

```text
为什么一个模型从 Gate 通过到正式 Baseline，
必须经过 release eligibility、human Review 和 immutable history？
```

再画出：

```text
Router
→ Application Use Case
→ Query Repository
→ Review Unit of Work
→ Review Repository
→ Database
```

最后说明：

- 哪一层负责政策；
- 哪一层负责事务；
- 哪一层负责交互提示；
- 哪一层是最终并发约束。

只有能够解释这些权衡，本轮才算学习完成，而不只是代码完成。
