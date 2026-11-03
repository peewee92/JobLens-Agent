# P1 Provider Eval 成本治理复盘：Cost Budget / Canary / Replay Cache

- 日期：2026-09-24
- 范围：vNext 1.1 Career Intent / Tool Selection Provider Eval
- 目标：在不降低 Release Gate 可信度的前提下，把 Prompt/Model 日常调试从“反复跑完整真实 Cohort”改造成“离线优先、小样本验证、正式 Gate 单次执行、相同证据零调用复用”。

---

## 1. 事故背景

2026-09-24 本地调试 `deepseek-v4.1-flash` 时，服务商控制台显示约：

```text
总费用：¥48.64
计费方式：约 ¥0.08 / 次请求
```

对应约 608 次真实 Provider 请求。

从服务商日志可以看到请求高度规律：

```text
每 3～5 秒一条
输入约 1.1k～1.2k tokens
输出约数百 tokens
模型固定 deepseek-v4.1-flash
```

这和 JobLens Provider Eval 的批量 Dataset 执行特征一致，而不是普通用户聊天。

当前 vNext 1.1 正式质量门包含：

```text
Intent          60 cases
Tool Selection  44 cases
合计           104 cases
```

在当前服务商约 `¥0.08 / 次` 的收费模式下，一次完整 Gate 理论成本约：

```text
104 × ¥0.08 = ¥8.32
```

如果 Prompt 调优期间反复跑完整 Gate、分类重跑、超时后重跑，再叠加 health probe / 单 case probe，几轮之后就会快速累积到数十元。

---

## 2. 根因

### 2.1 最大问题不是单次 Token，而是调用次数

这次服务商近似按“请求次数”收费，因此当前最重要的成本指标不是：

```text
单次 input tokens
单次 output tokens
```

而是：

```text
Provider HTTP Attempts
```

即使把一次请求从 1200 tokens 优化到 800 tokens，只要服务商仍按每次请求固定收费，账单下降也可能非常有限。

### 2.2 把 Release Gate 当成了日常 Prompt 调试工具

错误流程：

```text
改 Prompt
→ 跑完整 60 + 44
→ 看 Bad Case
→ 再改 Prompt
→ 再跑完整 60 + 44
→ 某次命令超时
→ 再重新跑
```

正确流程应是：

```text
离线回归
→ 小样本 Canary
→ 只修真实 Bad Case
→ Canary 稳定
→ 正式 Release Gate 只跑一次
```

### 2.3 命令超时不代表 Provider 没有计费

如果 104-case Gate 已经成功发送前 70 个真实请求，随后 DevSpace 命令因为 300 秒超时退出：

```text
前 70 次 Provider 请求仍然已经发生
```

因此“命令没有拿到最终报告”不能等同于“没有花钱”。

### 2.4 原脚本缺少真正的硬成本预算

原 `check_career_provider_gates.py` 有：

```text
--execute-provider-gate
--confirm-live-cost
```

它能防止误触发 live Provider，但一旦用户确认成本，脚本缺少：

```text
单轮 HTTP attempt 硬上限
人民币预算上限
开发 Canary
相同测量结果复用
```

尤其 Retry 发生时，一个 Eval Case 可能对应多个 HTTP attempts。

### 2.5 “最新 Snapshot”不能直接充当 Replay Cache

最新状态文件会被后续 dry-run / blocked run 覆盖。

因此：

```text
latest snapshot
```

和：

```text
paid replay evidence
```

必须分离。

---

## 3. 本轮工程改造

### 3.1 默认改为小样本 Canary

现在脚本默认只选：

```text
Intent          5 cases
Tool Selection  5 cases
总计           10 cases
```

选择不是简单取前 10 条，而是优先按 Eval Category 做确定性代表性抽样。

按当前价格估算：

```text
10 × ¥0.08 ≈ ¥0.80
```

正式 60 + 44 必须显式增加：

```bash
--full-release-gate
```

这避免“只是想看看 Prompt 改得怎么样”却默认花完整 Gate 的钱。

---

## 4. Provider Call Budget：真正按 HTTP Attempt 限制

新增硬预算：

```text
max_provider_attempts
```

它不是只限制 Case 数，而是在 `OpenAICareerIntentModel` 真正发 HTTP 请求之前检查。

因此以下情况全部消耗同一预算：

```text
正常请求
429 retry
连接失败 retry
5xx retry
```

一旦达到上限：

```text
Provider request 不再发送
→ fail-closed
→ 返回 provider call budget exhausted
```

默认：

```text
maxProviderCalls = plannedProviderCalls
```

也就是说默认不给 Retry 额外收费空间。

如果确实希望给 Retry 留余量，必须显式提高 `--max-provider-calls`。

---

## 5. Cost Budget：把调用预算翻译成人民币

新增：

```bash
--estimated-cost-per-call-cny
--max-cost-cny
```

当前默认估算：

```text
¥0.08 / request
```

例如：

```bash
python -m scripts.check_career_provider_gates \
  --execute-provider-gate \
  --confirm-live-cost \
  --max-provider-calls 10 \
  --max-cost-cny 0.80
```

如果预算和计划不匹配：

```text
Provider 调用发生前直接拒绝
```

注意：

`estimated-cost-per-call-cny` 是本地成本保护参数，不代表服务商官方账单真值。服务商定价变化后必须同步调整。

---

## 6. Replay Cache：相同测量不再重复付费

新增独立目录：

```text
data/local/career-provider-gate-cache/
```

它和：

```text
data/local/career-provider-gates.json
```

职责不同。

### Latest Snapshot

回答：

> 最近一次运行是什么状态？

### Replay Cache

回答：

> 这个完全相同的 Provider Gate 以前是否已经真实测过？

Replay Key 包含：

```text
provider
model
base URL（不含 API key）
API style
enable_thinking
max completion tokens
prompt version
schema version
Intent dataset SHA-256
Tool Selection dataset SHA-256
run mode
selected Intent case IDs
selected Tool case IDs
```

任何一个关键测量条件变化，都会产生新的 `runFingerprint`。

API Key 不进入 Fingerprint，也不会写进 Snapshot / Cache。

如果：

```text
runFingerprint 完全一致
+ 上次状态已经真实 measured（PASS / FAIL）
```

则默认：

```text
REPLAY CACHE HIT
Provider calls this run = 0
```

只有明确希望重新花钱测量时才允许：

```bash
--refresh-replay-cache
```

---

## 7. 新的推荐研发流程

### 阶段 A：纯离线开发

```text
修改 Prompt / Contract
→ deterministic tests
→ Eval contract tests
→ provider calls = 0
```

这一阶段禁止因为“想看看模型效果”直接跑完整 Cohort。

### 阶段 B：小样本 Canary

先 Dry Run：

```bash
cd services/backend
python -m scripts.check_career_provider_gates
```

默认：

```text
Provider calls = 0
planned calls = 10
estimated cost ≈ ¥0.80
```

人工确认费用后才运行：

```bash
python -m scripts.check_career_provider_gates \
  --execute-provider-gate \
  --confirm-live-cost \
  --max-cost-cny 0.80
```

如果 Canary 仍明显失败：

```text
停止
→ 读 Bad Case
→ 修改 Prompt / Model / Eval
→ 不跑完整 104
```

### 阶段 C：正式 Intent / Tool Selection Release Gate

只有 Canary 稳定后才允许：

```bash
python -m scripts.check_career_provider_gates \
  --full-release-gate \
  --execute-provider-gate \
  --confirm-live-cost \
  --max-provider-calls 104 \
  --max-cost-cny 8.32
```

正常情况下：

```text
Intent 60
Tool Selection 44
Provider Calls 104
Estimated Max Cost ¥8.32
```

如果完全相同的 Release Identity 已经测过：

```text
Replay Cache Hit
→ 0 新调用
```

---

## 8. Token 优化策略

### Token Usage 已进入 Gate 结果

Provider Adapter 现在会累计兼容 OpenAI Usage 字段：

```text
prompt_tokens / input_tokens
completion_tokens / output_tokens
total_tokens
```

Gate Snapshot 会记录：

```text
providerInputTokens
providerOutputTokens
providerTotalTokens
```

因此下一轮成本复盘可以直接区分：

```text
调用次数过多
vs
单次 Prompt / Schema 过大
vs
模型输出过长
```

不再只根据账单反推。

### P0：先优化调用次数

当前服务商按次收费时，优先级：

```text
减少真实 Provider Calls
>
减少单次 input/output tokens
```

主要措施：

1. 离线测试优先；
2. Canary 替代完整 Gate 调试；
3. 相同 Fingerprint Replay；
4. HTTP Attempt 硬预算；
5. Retry 不再拥有无限隐式成本；
6. 正式 Gate 只在发布节点执行。

### P1：压缩单次 Token

当前 Career Intent 输出通常远小于 2048 completion tokens。

后续可以做一个独立、受评测保护的实验：

```text
CAREER_INTENT_MAX_COMPLETION_TOKENS
2048
→ 1024
→ 768
```

只有在：

```text
Intent accuracy 不下降
Tool Selection accuracy 不下降
malformed output 不增加
```

时才允许降低生产默认值。

不要为了省 Token 直接压到很低，否则 JSON Schema 输出被截断会造成新的 malformed output。

### P1：Prompt 压缩

Prompt 可以继续去除重复说明，但必须满足：

```text
先用 Eval 证明语义等价
再缩短
```

不能为了少几百 input tokens 重新引入：

```text
runtime scope 过度澄清
unknown / clarification 混乱
rank_jobs / review_application 边界错误
unsafe request 降级执行
```

### P1：Thinking 关闭验证

配置继续保持：

```text
CAREER_INTENT_ENABLE_THINKING=false
```

但第三方兼容服务可能仍返回 reasoning 元数据，因此要以服务商真实 Usage / Billing 为准，不把这个字段本身当成成本已经归零的证据。

---

## 9. 自动任务成本边界

从 2026-09-24 起：

```text
每小时 JobLens 自动推进任务
Provider Calls 必须 = 0
```

自动任务允许：

```text
代码修改
离线 Eval
确定性测试
Git / ROADMAP 审计
读取已有 Provider evidence
```

自动任务禁止：

```text
Provider health live probe
Intent live case
Tool Selection live case
Requirement live extraction
Semantic Match live call
完整 60 + 44 Gate
```

真实付费 Gate 必须由当前人工会话显式授权，并在执行前报告：

```text
计划 calls
hard max calls
estimated cost / call
estimated max cost
```

---

## 10. 本轮验证

本轮实现全部使用 Mock / Disabled Provider，没有真实付费调用。

覆盖测试包括：

- Canary 默认 5 + 5；
- full release 显式 60 + 44；
- Canary Category 多样性；
- 人民币预算不足时 Provider 前拒绝；
- call budget 小于选中 cases 时 Provider 前拒绝；
- `runFingerprint` 相同配置稳定、模型变化后改变；
- Replay Cache 只复用完全一致且已 measured 的结果；
- `NOT_MEASURED` 不进入 Replay Cache；
- 429 Retry 也受真实 HTTP Attempt budget 限制；
- Provider usage token 会累计进 Gate Snapshot，便于继续压缩 input/output token。

---

## 11. 以后每次 Provider 调试前的检查表

```text
[ ] 能不能先用 deterministic / mock / replay 验证？
[ ] Prompt / Model / Schema / Dataset 是否真的发生变化？
[ ] 已经有相同 runFingerprint 的真实结果吗？
[ ] 是否只需要 Canary，而不是完整 Release Gate？
[ ] plannedProviderCalls 是多少？
[ ] maxProviderCalls 是多少？
[ ] 当前服务商单次估算多少钱？
[ ] estimatedMaxCost 是否可接受？
[ ] Retry 是否也包含在硬预算里？
[ ] 是否真的到了需要跑 60 + 44 的发布节点？
```

核心原则：

> **开发阶段优化的是“每获得一个新信息需要多少真实 Provider Calls”，而不是把完整 Release Gate 当作调试循环。**
