# ADR-0001：MVP 范围（v0.1 做 / 不做 / v0.2 才做）

## 状态

Superseded（范围细化，原 ADR-0001 决策精神保留，边界在 v2.0 重述）

> 原 ADR-0001「MVP 使用单 Career Agent，并将 Collector 独立为数据入口」的决策仍然成立，本文件在其基础上把 MVP 范围拆成 v0.1 / v0.2 / P1 三档，使边界更稳、开发者可立即开工。

## 决策

MVP 不再一次性做完所有事，而是先交付一个窄但硬的闭环（v0.1），再扩展到学习路线与准备（v0.2），最后用一个 Agent 编排成熟能力（P1）。

```text
MVP v0.1
Profile → SearchIntent → Job Pool → JobRequirement → Eligibility → Match → Ranking → UserFeedback

MVP v0.2
Target Cohort → Skill Gap → Action Plan → Resume / Interview

P1
Career Agent → 调用成熟 Workflow
```

---

## MVP v0.1 做

1. `Profile`：简历 → 带 Evidence 的 `UserProfile`；
2. `SearchIntent`：目标角色 / 城市 / 远程 / 薪资下限 / 硬约束 / 软偏好；
3. `Job Pool`：Collector JSON 导入、标准化、去重、查询；
4. `JobRequirement`：每岗抽取结构化需求（type / importance / evidenceSpan / confidence）；
5. `Match`：Eligibility（Eligible / Conditional / Blocked）+ Fit（Strong / Good / Stretch / Low）；
6. `Ranking`：基于 Eligibility + Fit + 软偏好批量排序；
7. `UserFeedback`：interested / maybe / rejected + 原因。

---

## MVP v0.1 不做

- 完整职业发现（用户无方向时的探索）；
- 长期课程系统；
- 自动投递 / 自动 Boss 打招呼；
- Multi-Agent；
- 复杂 Memory；
- 跨平台自动采集；
- 单岗位 Resume / Interview 准备（那是 v0.2）。

---

## MVP v0.2 才做

1. `Skill Gap`：基于 `JobRequirement` 聚合的差距（优先级不单看频率）；
2. `Action Plan`：最多 3 个 P0 / 5 个 P1；
3. `Resume Delta`：单岗位简历调整建议（非整份重写）；
4. `Interview Pack`：项目讲述重点 + 面试准备清单；
5. `Target Cohort`：由收藏岗位 / UserFeedback 聚合出的目标岗位集（概念从 `JobTarget` 演进）。

---

## P1 才做

- `Career Agent` 作为面向用户的统一入口，编排 v0.1 / v0.2 的成熟 Workflow；
- Collector API 同步（增量导入，保留 JSON 兜底）；
- Growth Loop（Action → Evidence → Re-match）；
- 多平台 Collector / GitHub 解析 / 多简历版本 / 定时提醒 / 面试复盘 / Offer 比较（价值验证后再做）。

---

## 原因

当前最大未验证价值不是“Agent 能否自动操作更多网站”，而是：

> 基于真实岗位和真实个人经历，能否产生可信、可解释、可执行的职业决策，并且能被评测。

先把 v0.1 这 8 步跑通、且每个 LLM Pipeline 从第一天接 Eval，可以最大限度复用现有 Collector，控制系统复杂度，并让开发者只需要盯着 Phase 1（Job Data Foundation）开工，不会被整个 JobLens 长期愿景拖住。

## 影响

- `docs/product/PRD-MVP.md` v2.0 按 v0.1 / v0.2 重写；
- `docs/roadmap/ROADMAP.md` 调整为 Phase 0.5 + 1–9；
- `packages/contracts/schemas/` 新增 `search-intent` / `job-requirement` / `user-feedback`；
- `AGENTS.md` 的 MVP Workflow 与开发规则同步更新。
