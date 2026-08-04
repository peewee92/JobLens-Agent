# P0-3B-3E 学习记录｜Requirement Canary Review Web Workbench

## 1. 学习目标

本切片不是学习“怎么做一个漂亮页面”，而是学习：

> 如何把一个高风险 Agent/LLM 人工门禁，做成证据完整、策略不漂移、不能替人做判断的 Web 工作台。

需要掌握：

- Server Component 和 Client Component 的职责边界；
- exact version 与 latest state 的区别；
- Backend policy 与 UI presentation 的区别；
- same-origin command proxy；
- partial failure UI；
- human-in-the-loop 的证据冻结；
- 为什么 Review UI 不能包含自动判断。

## 2. 先预测

在阅读实现前先写答案：

1. Run Case 已有 `extractionId`，页面应该调用最新 Requirements 还是精确 Extraction？为什么？
2. `canaryContinueAllowed` 应由 React 计算还是 Backend 返回？
3. Client 是否应该提交 `reviewedCaseIds` 和 `reviewedTraceRunIds`？
4. 三条 Canary 中一条读取失败，页面应全部报错还是保留另外两条？
5. Provider 调用失败、没有 Requirements 的 Case 是否应该隐藏？
6. 为什么列表和详情页面适合 Server Component？
7. 为什么表单必须是 Client Component？
8. 为什么 Web 可以提交 Review，却不能执行下一批 Provider 调用？
9. Continue 与模型质量 Accepted Baseline 有什么区别？
10. 页面上的三个勾选框能否证明 Reviewer 真正理解了证据？

## 3. 最小知识

### 3.1 exact version 不是 latest

错误路径：

```text
Run Case.extractionId = reqrun_A
页面调用 GET /jobs/{id}/requirements
当前最新版本 = reqrun_B
```

页面看见的是 B，但人工决策冻结的是 A。

正确路径：

```text
GET /jobs/{jobId}/requirement-extractions/{extractionId}
```

审核对象必须与 Run 事实一致。

### 3.2 Canary JD 也必须冻结版本

只冻结 `extractionId` 还不够。假设：

```text
09:00 Run 调用模型，输入 JD_A
10:00 同一个 Job 被重新导入成 JD_B
11:00 Reviewer 打开页面
```

如果页面直接读取当前 `Job.description`，就会把：

```text
Extraction_A + JD_B
```

拼在一起，形成错误证据。

因此新 Run Case 会保存：

```text
descriptionSnapshot = 导入规范化后、真正送入模型的 Job.description
descriptionHash = SHA-256(descriptionSnapshot)
```

页面另外显示当前 Job hash，只用于判断是否 stale。当前文本不能覆盖历史快照。

还要注意：不能直接把 Collector 原始 `description` 当成模型输入快照，因为 Import normalizer 可能改变空白和结构。快照必须来自导入后的 persisted Job。

### 3.3 UI 不应复制后端门禁

假设 React 写：

```ts
const canContinue = run.attemptedCalls <= 3 && run.extractedCount > 0;
```

未来后端增加：

- Provider 限制；
- 每个 attempted Case 必须有 Trace；
- stopped/ready 状态；
- Reviewer 所有权；

React 很容易漏掉，形成“按钮可点但后端拒绝”甚至更危险的策略漂移。

本实现直接消费：

```text
canaryContinueAllowed
canaryStopAllowed
canaryReviewBlockReason
```

### 3.4 Server read / Client command

Server Component 适合：

- 读取 Run；
- 读取 Job；
- 读取精确 Extraction；
- 聚合证据；
- 不把 Backend 地址暴露给浏览器。

Client Component 只负责：

- 记录勾选和 notes；
- 调用 same-origin POST；
- 刷新页面。

### 3.5 partial failure 不是整页失败

Canary 最多只有三条。一条读取失败本身就是重要风险信号。

正确行为：

```text
Case 1 evidence OK
Case 2 read error → 单独显示
Case 3 evidence OK
```

而不是：

```text
Promise.all 任意失败
→ 整个页面 500
→ Reviewer 看不到其他证据
```

本实现对每个 Case 单独捕获错误。

### 3.6 failed Case 也是 Canary 证据

Canary 的目的不是展示模型最好的一面，而是尽早发现失败。

在人工决策前，候选证据集合使用：

```text
attemptCount > 0
```

而不是：

```text
extractionId != null
```

后者会隐藏失败调用。

人工决策提交后，证据身份必须切换为不可变的：

```text
reviewedCaseIds
```

否则 Continue 后剩余 17～19 条也会变成 attempted，页面会错误地暗示 Reviewer 在放行前看过它们。

### 3.7 勾选框只是 forcing function

“我已阅读 JD / Requirements / Trace”可以降低无脑点击概率，但不能证明：

- Reviewer 真的看了；
- Reviewer 理解正确；
- 决策合理。

真正持久化的审计证据仍是：

- Reviewer；
- notes；
- decision；
- 服务端冻结的 Case/Extraction/Trace IDs；
- reviewedAt。

## 4. 实现结构

### Backend

```text
GET /requirement-acceptance-runs
→ list summaries

GET /requirement-acceptance-runs/{runId}
→ detail + cases + trace summary + policy flags

POST /requirement-acceptance-runs/{runId}/canary-review
→ immutable human decision
```

### Web

```text
/evals/requirements/canary
→ Run list

/evals/requirements/canary/{runId}
→ exact evidence workbench

/api/requirement-acceptance-runs/{runId}/canary-review
→ same-origin proxy
```

## 5. 常见错误实现

```tsx
const visibleCases = run.cases.filter((item) => item.extractionId);
const canContinue = visibleCases.length > 0;

return visibleCases.map((item) => (
  <LatestRequirements jobId={item.jobId} />
));
```

问题：

1. 失败 Case 被隐藏；
2. 门禁在 React 重写；
3. 读取 latest，而不是 exact version；
4. 没有 Trace；
5. 页面产生成功样本偏差；
6. Reviewer 的 Continue 不可信。

## 6. 失败案例

真实调用：

```text
Case 1：成功，6 Requirements
Case 2：Structured Output 非法，Trace error
Case 3：成功，5 Requirements
```

错误 UI：

```text
只显示 Case 1、Case 3
→ Reviewer 以为 2/2 成功
→ Continue
```

正确 UI：

```text
显示三条 attempted Case
Case 2 显示 0 Requirements + Trace error
→ Reviewer 能看到 2/3，而不是 2/2
```

## 7. 你必须亲自做的练习

真实 Canary 出现后，至少选择一个 Case，手写：

```text
1. 这个 JD 的核心职责是什么？
2. 哪三条是最重要的 must-have？
3. 模型漏掉了什么？
4. 模型新增了什么但原文不支持？
5. importance 哪些合理/不合理？
6. evidenceSpan 是否完整、精确？
7. Trace 延迟/Token/错误是否可接受？
8. 你的 Continue/Stop 决策和理由是什么？
```

不能让 Agent 替你写第 8 条。

## 8. 面试问题

### 基础

1. 为什么审核页面必须读取 exact Extraction ID？
2. Server Component 和 Client Component 在这个页面如何分工？
3. same-origin Route Handler 解决了什么问题？
4. 为什么 failed Case 也必须显示？
5. 为什么 Trace output 没有直接完整暴露？

### 中级

6. 为什么 UI 不应该计算 Continue eligibility？
7. 如何防止一条证据读取失败导致整页不可用？
8. 为什么客户端不能提交 reviewed evidence IDs？
9. 如何证明 Web 页面不能触发 Provider 调用？
10. 为什么 checklist 不是可靠审计证据？

### 高级

11. 如果未来 Web 要启动 Provider Run，需要先增加哪些基础设施？
12. 如何处理 Reviewer 打开页面后，Run 数据被另一个进程修改？
13. 如何设计 ETag/version conflict 来防止 stale human decision？
14. 如何将 Trace summary 升级为完整 observability，而不泄露敏感数据？
15. 如何做键盘、屏幕阅读器和长 JD 的可访问性优化？
16. 如果 Run 数量达到十万，当前 list implementation 应如何演进？

## 9. 3–5 分钟 Demo

### 0:00–0:40｜背景

展示：

```text
CLI Run → 1–3 Canary → Human Gate → remaining calls
```

强调页面不能执行 Provider。

### 0:40–1:20｜Run 列表

打开：

```text
/evals/requirements/canary
```

说明 waiting-first 排序、attempted/completed/failed/deferred。

### 1:20–2:40｜证据详情

打开一个 Run：

- 完整 JD；
- exact Extraction ID；
- Requirements；
- importance；
- evidenceSpan；
- Trace 模型、Prompt、延迟、Token、错误。

指出 failed Case 不会被隐藏。

### 2:40–3:30｜人工判断

展示：

- 三个个人检查项；
- 自己写 notes；
- Continue/Stop 按钮来自后端 eligibility；
- 决策不可修改。

### 3:30–4:20｜失败路径

模拟/展示某个 Case evidence read error：

- 该 Case 显示错误；
- 其他 Case 仍可查看；
- Reviewer 可选择 Stop。

### 4:20–5:00｜工程证据

展示：

- Backend list/Trace/policy test；
- Web architecture test；
- exact extraction fetch；
- no Provider POST route；
- full test/build output。

## 10. 作品集表述

可表述为：

> 为真实岗位 Requirement Extraction 建立了 Human-in-the-loop Canary Review Workbench。系统通过 Backend-owned eligibility、persisted-model-input JD snapshot、exact-version Extraction、Trace summary、attempted-only evidence 和 immutable review command，避免成功样本偏差、JD/latest-data drift 与前端策略漂移；Web 只承担证据展示和短审批，付费 Provider 执行仍受 CLI 预算控制。

不要表述为：

> 建成了生产级 AI 审批平台。

因为尚未完成：

- 身份认证/RBAC；
- CSRF；
- 分布式并发控制；
- 真实 Provider 人工质量结论；
- 生产监控。

## 11. 学习验收问题

完成后不用看代码回答：

1. 为什么 exact Extraction 比 latest Requirements 更适合审核？
2. 为什么当前 Job.description 不能替代 Canary 当时的 JD？
3. 为什么快照必须来自 persisted Job，而不是 Collector 原始 description？
4. 决策前的 attempted Cases 与决策后的 reviewedCaseIds 为什么不能混为一谈？
5. `isCanaryEvidence` 和 `extractionId != null` 代表的集合有什么不同？
6. 为什么 eligibility 必须来自 Backend？
7. Client 实际提交了哪些字段？哪些字段由服务端冻结？
8. 一条 evidence read 失败时为什么不应隐藏整页？
9. Continue 为什么不是 Accepted Baseline？
10. 页面为什么没有 Provider 执行按钮？
11. 哪些自动化证据证明没有范围泄漏？
