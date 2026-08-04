# P0-3B-3G 学习记录｜Live Canary Session Manifest + Evidence Pack

## 1. 本次真正要学什么

本切片不是学习“如何把对象写成 JSON”，而是学习：

> 如何为一个跨多次命令、包含真实模型成本和人工门禁的 Agent 工作流建立稳定身份，并用最小敏感数据保存可追溯证据。

关键能力：

- 业务身份建模；
- Session 与 Invocation 分层；
- 证据引用设计；
- privacy-by-default；
- 原子文件输出；
- Human-in-the-loop 边界；
- 可验证完成标准。

---

## 2. 先预测

先写答案，再看解释：

1. 同一数据集第一次 `max=3`，Continue 后第二次 `max=17`，Session ID 是否应改变？
2. 同一数据集从 Model A 切换 Model B，是否仍是同一 Session？
3. 为什么 `runId` 不适合作为 blocked readiness 阶段的 Session Identity？
4. Manifest 为什么可以保存 Trace ID，却不默认保存 Trace Output？
5. Review Notes 为什么只保存 hash 和长度？
6. Continue 后运行的 17 Cases 是否应标记为 frozen Canary evidence？
7. `fsync + replace` 能保证什么？
8. Manifest 的 `allTwentyExtractionsReady=true` 是否足以进入 Match？

---

## 3. 最小知识

### 3.1 Session 与 Invocation

```text
Session
= 一次稳定业务验收
= dataset + reviewer/title + model cohort

Invocation
= Session 中的某一次命令
= readiness / canary / resume / export
```

因此：

```text
max=3 → human continue → max=17
```

是一个 Session 的多个 Invocation。

### 3.2 身份字段的判断标准

一个字段应该进入身份，需要满足：

1. 稳定；
2. 会改变本轮证据的语义；
3. 两个值不同就不应混为同一次实验。

进入身份：

```text
datasetFingerprint
reviewer
title
provider
model
extractorVersion
promptVersion
```

不进入身份：

```text
generatedAt
maxNewExtractions
attemptedCalls
blockers
runId
batchId
```

### 3.3 为什么 Provider Cohort 必须完整

只保存 Model 不够：

```text
同一 Model
+ 不同 Prompt
→ 输出行为可能不同
```

只保存 Provider/Model 也不够：

```text
同一 Provider/Model/Prompt
+ 不同 Extractor code version
→ normalization/validation 可能不同
```

所以 cohort 至少包括：

```text
provider + model + extractorVersion + promptVersion
```

### 3.4 Reference-only Evidence

Manifest 是索引，不是事实数据库副本。

保存引用：

```text
caseId
jobId
extractionId
traceRunId
reviewId
batchId
descriptionHash
```

不复制正文：

```text
full JD
raw Trace output
review notes
API key
```

好处：

- 减少敏感数据扩散；
- 避免副本漂移；
- Manifest 更小、更适合交接；
- 事实仍由数据库不可变记录提供。

### 3.5 Review Notes Hash

```text
notesSha256 + notesCharacterCount
```

能做：

- 在拿到私有 Notes 时验证内容是否一致；
- 证明 Manifest 生成时对应某个确定文本。

不能做：

- 恢复 Notes；
- 证明 Reviewer 真的理解证据；
- 证明决策正确；
- 证明时间不可伪造。

### 3.6 Frozen Canary Evidence

决策前：

```text
attempted Cases = 当前 Canary 候选
```

决策后：

```text
reviewedCaseIds = 真正被冻结的 Canary Evidence
```

Continue 后新增的 Cases 即使有 attempt count，也不属于放行前已审核证据。

### 3.7 原子文件写入

错误：

```python
output.write_text(big_json)
```

进程中断时可能留下部分 JSON。

本实现：

```text
unique same-directory temp
→ write
→ flush
→ fsync
→ replace target
```

保证 Reader 看到旧完整文件或新完整文件。

仍不能保证：

- 两个并发 writer 谁应该赢；
- 内容是真实且未被恶意修改；
- 文件有可信签名。

---

## 4. 当前实现结构

### Pure identity

```text
requirement_acceptance_session_id(...)
→ canonical JSON
→ SHA-256
→ reqacceptsession_<32 hex>
```

### Manifest builder

```text
ReadinessResult
+ Existing Run
+ dataset path
+ extractor/prompt cohort
+ command preview
→ secret-free dict
```

### Writer

```text
write_requirement_acceptance_session_manifest(path, manifest)
→ atomic JSON file
```

### CLI

```bash
.venv/bin/python -m scripts.check_requirement_acceptance_readiness \
  /path/formal-review.json \
  --reviewer will \
  --title "Real Requirement acceptance" \
  --max-new-extractions 3 \
  --session-manifest ./artifacts/requirement-session.json \
  --json
```

---

## 5. 常见错误实现

```python
manifest = {
    "sessionId": str(uuid4()),
    "createdAt": datetime.now().isoformat(),
    "apiKey": settings.openai_api_key,
    "dataset": payload,
    "traces": [trace.output for trace in traces],
    "notes": review.notes,
}
Path("manifest.json").write_text(json.dumps(manifest))
```

错误：

- UUID 无法从业务身份复现；
- 同一 Session 每次运行变成新身份；
- API Key 泄露；
- 完整 Dataset/JD 扩散；
- Raw Trace 复制；
- Notes 正文扩散；
- 直接写目标文件可能留下半文件；
- 没有完成清单，也无法区分“已运行”和“质量已通过”。

---

## 6. 失败案例

团队成员看到三个文件：

```text
session-2026-08-04-0900.json
session-2026-08-04-0930.json
session-2026-08-04-1100.json
```

实际上它们分别是：

```text
Readiness
3-case Canary
17-case Resume
```

因为 ID 使用时间戳，无法证明三者属于同一模型 cohort。第二份文件又复制了完整 JD 和 API Key，被误传到作品集仓库。

正确方案：

```text
同一 reqacceptsession_xxx
状态从 blocked/ready
→ awaiting human review
→ ready for resume
→ awaiting 20-case review
```

公开时只需删除本地 dataset path，核心结构不含 Secret 和 JD 正文。

---

## 7. 测试解释

### Session identity test

证明：

- Provider 大小写规范化；
- 同一身份得到同一 ID；
- Model 改变得到不同 ID。

### Privacy test

证明 Manifest 不包含：

- Review Notes 正文；
- JD snapshot；
- `sk-` Secret；
- 自动模型批准。

### Frozen evidence test

模拟：

```text
4 attempted Cases
但 Review 只冻结 Case 0、1
```

断言只有 Case 0、1 的 `isFrozenCanaryEvidence=true`。

### Atomic writer test

证明：

- 目标目录可创建；
- 输出是完整 JSON；
- 临时文件不残留。

### CLI test

证明：

- `--session-manifest` 真正写出文件；
- stdout 与文件共享 Session ID；
- Provider Calls/DB Writes 为 0；
- API Key 不出现在任何输出。

---

## 8. 作品集表述

推荐：

> 为真实 LLM Requirement Acceptance 流程设计了稳定 Session Manifest。它用 Dataset Fingerprint 与完整 Model Cohort 生成可复现身份，把多次 Readiness/Canary/Resume 命令关联到同一 Session；Evidence Pack 只保存 Run、Extraction、Trace、Review、Batch 引用与 Hash，默认排除 API Key、完整 JD、Raw Trace 和人工备注，并通过 fsync + atomic replace 避免半文件。

不要写：

> 实现了生产级不可抵赖审计平台。

因为当前没有：

- 数字签名；
- append-only remote log；
- 权限控制；
- 多 writer 冲突治理；
- 真实 Provider 质量结论。

---

## 9. 面试问题

1. 你如何选择一个 Agent Eval Session 的业务主键？
2. 为什么 timestamp/UUID 不适合作为可复现实验身份？
3. Prompt Version 和 Extractor Version 为什么都属于 cohort？
4. 为什么 Evidence Pack 更适合保存引用而不是原始内容？
5. 你如何防止运维 JSON 泄露 Secret？
6. `fsync` 与 atomic rename 分别解决什么？
7. 原子文件写入为什么仍不能解决并发 lost update？
8. Human Review Notes 只存 hash 有什么收益和限制？
9. 如何区分“20 个 Extraction 完成”和“模型质量通过”？
10. 如果要生产化，你会如何加入签名、RBAC 和 append-only history？

---

## 10. 5 分钟 Demo

### 第 1 分钟：问题

展示一次真实验收包含多条命令，说明终端历史不能作为稳定证据链。

### 第 2 分钟：稳定身份

连续运行两次，仅改变调用预算：

```text
max=3
max=17
```

展示相同 Session ID；再改 Model，展示 ID 改变。

### 第 3 分钟：Privacy

打开 Manifest：

- 有 Dataset Fingerprint；
- 有 Run/Extraction/Trace IDs；
- 没有 API Key；
- 没有完整 JD；
- 没有 Raw Trace；
- Notes 只有 hash/length。

### 第 4 分钟：Human Gate

展示 Continue Review 只冻结两条 Canary Case；后续 attempted Cases 不会被标成放行前证据。

### 第 5 分钟：完成边界

展示：

```text
modelQualityApproved = null
matchPhaseAllowed = false
```

说明工程完成不等于质量结论，下一步仍必须运行真实 Canary 和 20 条人工审核。

---

## 11. 学习验收问题

1. Session 和 Invocation 有什么不同？
2. 为什么调用预算不进入 Session ID？
3. 为什么 Run ID 不进入 Session ID？
4. 为什么 blocked 状态生成的 provisional identity 可能在 Provider/Model 配置后变化？
5. 为什么完整 JD 不进入 Manifest？
6. Notes hash 能证明什么？
7. 为什么 Continue 后新调用的 Case 不属于 frozen Canary？
8. atomic replace 能防什么，不能防什么？
9. Manifest 中有 Batch ID 后还缺什么质量证据？
10. 什么时候才可以把 `matchPhaseAllowed` 设为 true？

---

## 12. 尚未验证

- 真实 ready 数据集在 DevSpace 可访问路径中的 Manifest；
- 真实 OpenAI command preview 与 Run；
- 真实 Continue/Stop 后的 Manifest 更新；
- 真实 20 Case Review；
- 多进程写同一目标文件；
- 文件签名与可信时间；
- 公开作品集路径脱敏流程；
- Match 放行策略。
