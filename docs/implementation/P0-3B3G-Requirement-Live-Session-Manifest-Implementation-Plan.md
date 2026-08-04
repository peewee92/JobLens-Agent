# P0-3B-3G｜Requirement Live Canary Session Manifest + Evidence Pack 实施计划

## 0. 当前切片

真实项目功能：

> 为一次正式 Requirement Acceptance 工作生成稳定 Session Identity、Readiness 快照、无密钥执行命令、Run/Case/Trace/Review 引用和完成清单，并以原子方式写入一个可重复更新的 JSON Manifest。

本次学习目标：

- 理解 control plane 与 provider execution 的区别；
- 理解稳定业务身份与一次命令 invocation 的区别；
- 学会设计 reference-only evidence pack；
- 学会做 privacy-by-default 的运维产物；
- 理解 atomic write、防半文件和并发临时文件冲突；
- 理解为什么运行证据不等于模型质量结论。

流程：

```text
formal dataset
→ zero-call Readiness
→ stable Session ID
→ optional secret-free command preview
→ Session Manifest atomic export
→ real Canary later
→ rerun Readiness and update same logical Session evidence
```

本切片仍然不：

- 配置或保存 API Key；
- 自动升级数据库；
- 调用 Provider；
- 自动 Continue/Stop；
- 自动审查 20 Cases；
- 进入 Match。

---

## 1. 业务风险与学习风险

### 业务风险：中高

没有 Manifest 时，真实运行容易依赖聊天记录、终端历史和人工复制：

- 同一数据集被不同 Title/Reviewer/Model 运行，却被误认为同一轮实验；
- Readiness 每次执行生成不同临时身份；
- 无法证明当时用的是哪个数据库 revision、模型和 Prompt cohort；
- Continue 后无法快速确认被冻结的 Canary Case/Trace；
- 为了“证据完整”直接导出完整 JD、Trace Output、人工备注甚至 Secret；
- 输出过程中进程中断，留下半个 JSON；
- 一个新的调用预算被错误当成新实验。

### 学习风险：高

Agent 容易替学习者跳过以下核心能力：

- 选择哪些字段构成 Session Identity；
- 区分“身份字段”和“状态字段”；
- 判断哪些证据应存引用，哪些不应复制原文；
- 解释为什么 `generatedAt` 和 `maxNewExtractions` 不属于身份；
- 解释为什么 Manifest 完整仍不能批准模型；
- 亲自判断真实 Canary 质量。

---

## 2. 核心机制应由谁完成

### 学习者必须先手写/解释

1. Session Identity 字段表：
   - datasetFingerprint；
   - reviewer；
   - title；
   - provider；
   - model；
   - extractorVersion；
   - promptVersion。
2. 解释为什么以下字段不进入 Session ID：
   - Manifest generatedAt；
   - 本次 `maxNewExtractions`；
   - 当前 blockers；
   - Run attemptedCalls；
   - Batch ID。
3. 为下列信息分类：身份 / 状态 / 证据引用 / 敏感内容。
4. 真实运行时亲自检查 Canary 并提交 Continue/Stop。
5. 真实 20 Case Review 和模型质量结论。

### Agent 完成的外围工作

- 稳定 Session ID 哈希；
- JSON Manifest 结构；
- Readiness CLI 参数接入；
- 证据引用投影；
- Secret/Raw JD/Raw Trace/Review Notes 排除；
- 原子文件写入；
- 测试、ADR、文档、Diff 审查和全仓库回归。

---

## 3. 事实、推断、假设和未知项

### 已确认事实

- 正式 20-JD 数据集曾生成 ready 版本，但上传目录与 DevSpace 主机隔离；
- 当前本地数据库 revision 为 `20260803_0010`；
- 代码 Alembic head 为 `20260804_0013`；
- Provider 当前为 `disabled`；
- Model 和 API Key 未配置；
- Readiness Gate、Canary Human Gate 和 Web Workbench 已完成；
- 当前仍不能执行真实 Provider Canary。

### 推断

- 一次 Acceptance Session 应跨多次 Readiness/Canary/Resume 命令保持同一身份；
- 数据集指纹和完整模型 cohort 是稳定身份的核心；
- 运维 Manifest 应保存证据引用和哈希，而不是复制敏感正文；
- Manifest 应能在 blocked 状态生成，帮助环境交接；
- 文件写入应原子化，避免半成品被当成证据。

### 假设

- 当前主要是单用户、本地运行；
- JSON 文件足以作为本阶段的运维交接格式；
- 数据集本地绝对路径可以保存在私有 Manifest，但公开作品集前需脱敏；
- Manifest 可重复覆盖同一目标文件，但 Session ID 由身份字段决定；
- Manual Review 完成状态暂时无法仅从 Readiness Run Detail 判断。

### 未知项

- 真实 Provider 的 Token/Latency/Rate Limit；
- 最终正式数据文件在 DevSpace 主机的路径；
- 最终模型名称；
- 真实 API Key 可用性；
- 20 Case Review 结论；
- 是否需要签名、不可变对象存储或远程审计仓库；
- 多进程同时更新同一个 Manifest 的最终冲突策略。

---

## 4. 共同完成标准

### 4.1 工程完成标准

| 标准 | 证据 |
|---|---|
| 同一业务 cohort 生成同一 Session ID | deterministic unit test |
| Model/Reviewer/Dataset 改变会改变 Session ID | identity unit test |
| GeneratedAt 与调用预算不改变 Session ID | identity design + test |
| Readiness CLI 可选择输出 Manifest | CLI help + CLI test |
| Manifest 包含 Readiness、Run、Case、Trace、Review 引用 | JSON assertions |
| Continue 后仅冻结 Review 中的 Canary Case | frozen-case assertions |
| 不输出 API Key、完整 JD、Raw Trace、Review Notes 正文 | redaction assertions |
| 命令不含 Secret，并保存 SHA-256 | JSON assertions |
| 输出采用同目录唯一临时文件 + fsync + atomic replace | writer test |
| 导出过程 Provider Calls=0 | manifest field + code review |
| 导出过程 DB Writes=0 | manifest field + code review |
| Match Phase 默认不允许 | completionChecklist assertion |

### 4.2 学习完成标准

学习者能不用看代码回答：

1. Session ID 为什么不能使用时间戳？
2. 为什么本次调用预算不是身份？
3. 为什么 Provider/Model/Extractor/Prompt 都必须进入身份？
4. 为什么保存 Trace ID 而不保存 Raw Trace Output？
5. 为什么 Review Notes 只保存哈希和字符数？
6. 原子 replace 解决什么，不能解决什么？
7. Manifest complete 为什么不代表 model approved？

### 4.3 作品集完成标准

可演示：

1. 相同身份重复运行得到相同 `sessionId`；
2. 改 Model 后 `sessionId` 改变；
3. blocked 状态仍可导出交接 Manifest；
4. live-ready 状态出现无密钥 command preview；
5. Continue 后 Manifest 只标记冻结的 Canary Cases；
6. 展示 privacy flags 和 completion checklist；
7. 展示测试结果和 ADR。

不能宣称：

- 生产级审计系统；
- 已完成真实 Provider 质量验收；
- 具备不可抵赖签名；
- 解决了多进程最终一致性；
- 已允许进入 Match。

### 4.4 用户价值假设

> 当一次真实 Agent/LLM 验收跨越环境准备、Canary、人工放行、Resume 和 20 条人工审核时，一个稳定、无密钥、引用式的 Session Manifest 能减少错模型、错数据集、错 Run、重复付费和证据丢失，并让工程师、Reviewer 和面试官理解每一步依据。

验证方式：

- 下一次真实 Canary 全程使用同一 Session ID；
- 操作者不需要从聊天历史恢复命令和证据 ID；
- 不会因重跑 Readiness 产生多个“实验身份”；
- 公开作品集可在去除本地路径后展示结构，而不暴露 JD/Secret。

---

## 5. 当前切片所需最小知识

### 5.1 Session Identity vs Invocation

```text
Session = 同一数据集 + 同一 Reviewer/Title + 同一模型 cohort
Invocation = 某次 Readiness / Canary / Resume 命令
```

一次 Session 可以包含多个 Invocation。

### 5.2 Identity 字段必须稳定且决定结果语义

进入 Session ID：

```text
datasetFingerprint
reviewer
title
provider
model
extractorVersion
promptVersion
```

不进入：

```text
generatedAt
maxNewExtractions
attemptedCalls
current blockers
runId / batchId
```

### 5.3 引用式证据

保存：

```text
Job ID
Case ID
Extraction ID
Trace ID
Review ID
Batch ID
descriptionHash
```

不复制：

```text
API Key
完整 JD
Raw Trace Output
人工 Notes 正文
```

### 5.4 原子文件写入

```text
same-directory unique temp file
→ write
→ flush
→ fsync
→ atomic replace target
```

它防止读到半文件，但不解决两个进程最后谁覆盖谁。

---

## 6. 先预测

实现前先写答案：

1. 两次运行只改变 `maxNewExtractions`，Session ID 是否变化？
2. 两次运行 Model 不同，能否共用 Session ID？
3. `runId` 为什么不作为 Session ID 的输入？
4. blocked 状态是否应该允许生成 Manifest？
5. Manifest 是否应该保存完整 Review Notes？
6. Continue 后新跑的 17 Cases 是否属于原 Canary 证据？
7. 文件 `write_text` 成功返回前崩溃可能留下什么？
8. atomic replace 能否解决两个并发 writer 的业务冲突？

---

## 7. 常见错误实现与失败案例

### 错误实现

```python
session_id = f"session-{datetime.now().isoformat()}"
manifest = {
    "apiKey": settings.openai_api_key,
    "jobs": [job.description for job in jobs],
    "traces": [trace.output for trace in traces],
    "reviewNotes": review.notes,
}
output.write_text(json.dumps(manifest))
```

问题：

- 每次重跑身份都变化；
- Secret 和敏感 JD 泄露；
- Raw Trace 复制扩大数据面；
- Review Notes 无默认隐私边界；
- 直接覆盖可能留下半 JSON；
- 无法区分同一 Session 的多个调用。

### 失败案例

```text
09:00 readiness max=3 → session_0900
09:20 canary max=3 → session_0920
10:00 continue
10:10 resume max=17 → session_1010
```

三个文件看起来是三个实验，实际上是同一数据集、同一模型 cohort。Reviewer 无法确认哪个 Continue 对应哪个 Canary。

正确实现中三次输出共享一个稳定 `reqacceptsession_*`，状态和证据引用逐步更新。

---

## 8. 1～3 小时 Tickets

| Ticket | 估时 | 内容 | 证据 |
|---|---:|---|---|
| T0 | 1h | 身份字段和隐私边界真值表 | Plan/ADR |
| T1 | 1–2h | Stable Session ID | unit tests |
| T2 | 2h | Manifest builder | JSON assertions |
| T3 | 1–2h | Run/Case/Trace/Review 引用投影 | tests |
| T4 | 1h | Privacy flags 与 notes hash | redaction tests |
| T5 | 1–2h | Atomic writer | filesystem test |
| T6 | 1–2h | Readiness CLI `--session-manifest` | CLI test/help |
| T7 | 1h | 独立 Diff 安全审查 | review notes |
| T8 | 1–2h | ADR、学习记录、Demo | docs |
| T9 | 人工 | 真实 Provider Session 使用 | 尚未执行 |

---

## 9. 范围冻结

本切片只允许修改：

- Requirement Acceptance application manifest module；
- Readiness CLI；
- 对应 tests；
- docs/README/roadmap。

不增加：

- 新数据库表；
- 新 HTTP API；
- Web Provider 按钮；
- 自动迁移；
- Secret store；
- cryptographic signing；
- Match/Ranking；
- Multi-Agent。

---

## 10. 完成标准对应证据

Manifest 的每个结论必须来自：

- Readiness 结果；
- Existing Run 数据库读模型；
- Case/Trace/Extraction/Review ID；
- deterministic hash；
- filesystem atomic-write test；
- CLI JSON response。

不接受：

- “代码看起来合理”；
- “Agent 说已完成”；
- README 声明；
- 没有断言的示例 JSON。

---

## 11. 独立 Diff 审查清单

- [ ] Session ID 是否包含 timestamp/budget？
- [ ] Provider/Model/Extractor/Prompt 是否都进入身份？
- [ ] Manifest 是否可能输出 Secret？
- [ ] 是否复制完整 JD 或 Trace Output？
- [ ] Continue 后 frozen Canary 标记是否正确？
- [ ] stopped/manual-review 状态是否误生成 Provider command？
- [ ] 临时文件是否唯一且同目录？
- [ ] 写入失败是否清理 temp？
- [ ] 是否新增了 DB/API/Provider side effect？
- [ ] `matchPhaseAllowed` 是否错误变为 true？

---

## 12. 学习验收问题

1. Session 与 Invocation 的区别是什么？
2. Session ID 为什么不包含 Run ID？
3. 为什么同一数据集换 Model 必须是新 Session？
4. 为什么 Manifest 可以在 blocked 状态生成？
5. 为什么完整 JD 不应默认进入 Evidence Pack？
6. Notes SHA-256 能证明什么，不能证明什么？
7. Atomic file replace 能防止哪类故障？
8. Manifest 有 Batch ID 后，为什么仍不能进入 Match？

---

## 13. 本次沉淀

- 测试：`services/backend/tests/test_requirement_acceptance_readiness.py`
- ADR：`docs/decisions/0029-requirement-live-session-manifest.md`
- 学习记录：`docs/implementation/P0-3B3G-Requirement-Live-Session-Manifest-Learning-Record.md`
- CLI 契约：`docs/integration/REQUIREMENT-ACCEPTANCE-SESSION-MANIFEST.md`
- 面试问题：学习记录第 9 节
- Demo：学习记录第 10 节

---

## 尚未验证

- 真实正式数据文件在 DevSpace 路径中的执行；
- 真实 OpenAI Provider；
- 真实 Token/Latency/Trace；
- 真实 Continue/Stop；
- 20 条人工 Review；
- Manifest 的远程存储、签名、权限控制；
- 多进程同时更新同一目标文件的业务冲突；
- Match Phase 放行。
