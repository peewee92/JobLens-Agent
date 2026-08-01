# ADR-0005：Eval 从第一天开始

## 状态

Accepted

## 决策

**Eval 是开发基础设施，不是 Phase 6 的附加功能。**

每个 AI 能力从第一个 LLM Pipeline 起就配套 Eval：

```text
Profile Extraction   → Profile Eval
Requirement Extraction → Requirement Eval
Match                → Match Eval
（P1）Agent          → Agent Eval
```

## 约束

- 新增任何 LLM Capability，必须同时提交评测数据集与至少一条断言，否则视为未完成；
- Eval 数据集随代码入库，可重复运行（pytest + 固定评测集）；
- Trace 必须落库（run_id / capability / version / model / prompt_version / input_refs / output / latency / tokens / error），见 EVAL-AND-TRACE.md；
- 门禁：Structured Output 解析成功率 ≥ 98%；不得生成 Profile 中不存在的项目事实；MatchReport 必须有 evidence；Gap P0 必须由目标岗位集真实要求支持。

## 原因

- “可评估”是这个项目区别于 Prompt Demo 的关键（见 ROADMAP 总目标）；
- 把 Eval 推到后期，会导致核心能力无法回归、无法比较模型/抽提器版本差异；
- UserFeedback 天然成为 Match 的人工基准，应尽早纳入 Eval 统计。

## 影响

- `docs/architecture/EVAL-AND-TRACE.md` 定义各 Eval 与统一 Trace；
- `AGENTS.md` 开发规则第 1 条：“Eval 从第一个 LLM Pipeline 开始”。
