# JobLens Agent 评估与追踪

> 配套 ADR-0005（Eval 从第一天开始）与 ADR-0004（能力分层）。Eval 不是最后一个 Phase，而是每个 LLM Capability 的开发基础设施。

## 1. 总原则

- 每个 LLM Capability 从第一个 Pipeline 起就配套 Eval 数据集与断言；
- Eval 数据集随代码入库，用 `pytest` + 固定评测集可重复运行；
- 所有运行必须落 Trace，保证可复现、可比较；
- `score` 只用于内部排序，不参与 Eval 通过判定，也不解释为概率。

---

## 2. 四类 Eval

### 2.1 Profile Eval（Profile Extraction）

评估简历 → `UserProfile` 的抽取质量。

- 数据集：≥ 10 条真实/脱敏简历；当前 `profile-extraction-v1.jsonl` 已提供 10 条脱敏代表性文本；
- 断言：
  - 关键技能必须关联到至少一个 `Evidence` 或显式标记“缺少证据”；
  - 不得编造简历中不存在的项目/公司/成绩；
  - `yearsOfExperience` 与原文一致（容差范围内）。

当前 Phase 2B 实现区分：

- Fixture CI Gate：验证 Structured Output、evidenceSpan、引用、Trace 和 Eval 机制；
- Live Provider Eval：使用配置模型和凭证运行，衡量真实模型质量。

Fixture 通过率不能作为生产模型质量结论。当前验证环境尚未执行 live-provider Eval。

### 2.2 Requirement Eval（Requirement Extraction）

评估 JD → `JobRequirement` 的抽取质量（最重要，因为它是统一事实来源）。

- 数据集：≥ 10 条真实 JD；
- 断言：
  - `must_have` 与 `bonus` 区分合理，关键门槛不降为 bonus；
  - `evidenceSpan` 精确指向 JD 原文片段；
  - 同义能力已归一（`normalizedCapability`，如 “React.js” → “React”）；
  - `type` 分类不跨类（如“本科以上”应为 `education`/`constraint`，不是 `skill`）。

### 2.3 Match Eval（Single/Batch Match）

评估 `Eligibility` + `Fit` + `UserFeedback` 闭环。

- 数据集：≥ 20 条真实岗位 + 对应 `UserFeedback` 作为人工基准；
- 断言：
  - 硬条件（城市/薪资下限/明确学历门槛/明确必须年限/远程）由确定性代码判定，不被 LLM 推翻；
  - `MatchReport` 必须有 `evidenceLinks`，且能指向 `UserProfile` Evidence 或 `JobRequirement.evidenceSpan`；
  - `Blocked` 岗位的硬约束原因可解释；
  - 与人工 `UserFeedback` 的 Top-N 重合率（interested/maybe）达到预设阈值；
  - 数字 `score` 未作为“概率/百分比”展示给用户。

### 2.4 Agent Eval（P1）

评估 Career Agent 的编排质量（P1 才做）。

- 数据集：多轮对话目标样例；
- 断言：
  - Agent 只调用已稳定 Workflow，不自行实现业务能力；
  - 不绕过 `Eligibility` 等确定性规则；
  - 最终回复可追溯到对应 Workflow 输出与领域模型。

---

## 3. 门禁（Gate）

任何 LLM Capability 合并前必须满足：

- Structured Output 解析成功率 ≥ 98%；
- 不得生成 `UserProfile` 中不存在的项目事实；
- `MatchReport` 必须有 evidence；
- `Gap`（v0.2）P0 必须至少被目标岗位集中的真实 `JobRequirement` 支持；
- 所有运行有 Trace 落库。

---

## 4. 统一 Trace 结构

每次能力运行写一条 Trace，字段：

```text
run_id          本次运行唯一 id
capability      能力名（profile_extraction / requirement_extraction / match / agent）
version         领域/抽取器版本
model           使用的 LLM 模型
prompt_version  Prompt / Extractor 模板版本
input_refs      输入来源引用（profile_version / job_id / requirement_extractor_version）
output          结构化输出（或引用 artifact id）
latency         耗时（ms）
tokens          token 用量
error           错误信息（若有）
created_at      时间
```

落库表：`trace_spans`（Alembic 0004）。Profile Extraction Trace 只保存简历 SHA-256 与字符数，不保存完整简历文本；结构化 proposal 作为 output 保存，供 Eval/问题定位使用。

### Trace 用途

- 比较不同 `extractorVersion` / `model` / `prompt_version` 的质量差异；
- 复现某次 Match 结果，回答“为什么这周和上周不一样”；
- 作为 Eval 失败时的定位入口。

---

## 5. 与阶段的关系

```text
Phase 2  Profile + SearchIntent      → Profile Eval 起步
Phase 3  Requirement Intelligence    → Requirement Eval 起步（关键）
Phase 4  Single Job Match            → Match Eval 起步
Phase 5  Batch Ranking + Feedback    → UserFeedback 纳入 Match Eval 基准
Phase 8  Career Agent                → Agent Eval 起步
```

Eval 贯穿始终，不集中在某一 Phase。
