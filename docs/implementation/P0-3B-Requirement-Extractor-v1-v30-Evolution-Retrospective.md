# Requirement Extractor 演进复盘（精简版）

> 本文是 v1→v30 需求抽取器演进的**关键非重复里程碑**浓缩版，供对外阅读。
> 完整逐版本记录见 `backup/pre-cleanup-20260825` 标签（本地/历史保留）。

## 演进阶段（关键里程碑）

- **v42.8–v42.9 · 首个 evaluator-sensitive Bad Case**
  同一显式任职资格被 Provider 拆成多个互相重叠的 `must_have`，整行软条件被拆成多个独立 `preferred`。
  修复原则从"逐词打补丁"转为"恢复原始任职资格行"这一更接近业务语义的评估单元。

- **v42.10–v42.13 · Provider structured-output 故障分层**
  将此前被压扁成 `ValidationError` 的故障拆分为 `structured_output_json` / `validation` / `provider_response_shape` / refusal / transport 等阶段；
  并引入窄范围 deterministic child recovery（不扩大语义边界）。

- **v42.14–v42.30 · Bounded deterministic repair 系列**
  围绕 capability-scope、alternative direction、importance-drift、Provider schema（discriminated union 收口）做了一系列**最小安全增量**修复。
  每条都只修一个确证缺口，fail-closed 门禁 + 人工审核，避免语义边界漂移。

- **v42.31–v42.57 · Coverage / Cardinality / Fan-out / Duplicate 专项硬化**
  将 bonus-section、umbrella skill、technical-stack type、example leak 等真实 live drift 固化为窄范围 deterministic repair。

- **v42.69–v42.90 · 验收治理（质量门禁化）**
  逐步引入 coverage / evidence / replay / provider / resume / execution-lease gate、canary validation、trace divergence 检查，
  把抽取质量从"人工看"变成"可门禁、可回放、可追溯"。

- **v42.94–v42.95 · Provider retry & 残留 fan-out**
  修复 Provider retry 场景与 mixed-importance backend-component 残留 fan-out；并由此引出**韧性架构**（重试 / 退避 / 兜底 / 缓存回放）。

## 关键设计决策

1. 每次修复都是 **最小 bounded 安全增量 + fail-closed 门禁 + 人工审核**，防止语义边界漂移。
2. 抽取结果按 `(canonical_key + model + prompt_version)` 可版本化、可回放（见 ADR-0021）。
3. 验收与线上 Provider 解耦：离线 replay 全绿即过，线上调用仅作周期性冒烟。

## 踩坑与韧性架构（复盘要点）

**问题**：验收闸门强绑定线上 LLM Provider（deepseek-v4-pro），Provider 偶发 503/504，且代码无重试 / 退避 / 兜底，导致 fail-closed 空转。

**解决（分层）**：

- L0 · Resilience：超时 + 指数退避重试 + 每 provider 熔断。
- L1 · Result Cache / Replay：结果按 `(canonical_key, model, prompt_version)` 缓存，JD 抽过一次不再调 Provider。
- L2 · Provider 抽象 + 故障转移：统一 `LLMProvider` 接口；`ProviderRouter` 选主 → 失败 → 路由下一健康 provider。
- L3 · 验收与线上解耦：验收跑 fixture/replay（确定性）；线上 Provider 仅周期性 canary/冒烟 + 告警。
- L4 · 可观测 + 优雅降级：成功率 / p95 / 成本 / 回退指标；全挂时返回缓存 / 标记 stale / 排队重试。

**经验（AI 项目通用）**：把"基础设施故障（Provider 5xx）"与"确定性缺陷（语义错误）"分开；
验收必须可离线跑；进度用"端到端可演示切片数"度量，而非"文档版本号 / Provider 健康检查结果"。
