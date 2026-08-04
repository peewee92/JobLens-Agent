# Collector v1.4.2 真实数据验收与 v1.4.3 修复记录

日期：2026-08-04

## 1. 验收输入

本轮使用同一次真实 BOSS 采集导出的四个文件：

- `boss-job-filter-report-v1.4.2-2026-08-04T04-08-01-635Z.json`
- `boss-job-filter-diagnostics-v1.4.2-2026-08-04T04-08-01-635Z.json`
- `boss-job-filter-requirement-review-v1.4.2-2026-08-04T04-08-01-635Z.json`
- `boss-job-filter-v1.4.2-2026-08-04T04-08-01-635Z.csv`

配置仍为武汉 + 全国远程、19 个关键词、每组最多 2 页、`detailMode=matched`、`detailLimit=40`。

## 2. v1.4.2 正确通过的部分

### 2.1 四个导出一致

- 完整报告包含 79 条最终岗位，CSV 同样包含 79 条，职位 URL 一一对应；
- Requirement 文件中的 19 条岗位都能在完整报告中按 URL 找到；
- 标题、公司、地区、薪资、description、descriptionLength、descriptionHash、质量字段完全一致；
- 所有有 description 的岗位均可重新计算出相同的 JavaScript UTF-16 长度与 FNV-1a 32 位指纹。

### 2.2 质量门禁正确阻断

真实导出结果：

```json
{
  "requiredSampleSize": 20,
  "eligibleCount": 23,
  "distinctEligibleCount": 19,
  "nearDuplicateCount": 4,
  "selectedCount": 19,
  "status": "blocked",
  "blockers": ["insufficient_distinct_full_jd_jobs"]
}
```

本次 v1.4.2 没有把 23 条岗位记录误报成 23 条独立样本，也没有为了凑满 20 条而放宽门槛，因此 `blocked` 是正确结果。

### 2.3 招聘者尾部治理有效

- 本轮 23 条 `full_jd` 中未发现招聘者姓名、活跃状态、BOSS 安全提示、竞争力分析、推荐职位或页脚噪声；
- 最终岗位中唯一的 `partial_jd` 是谷宇云的“大模型应用开发工程师”，正文清理后 138 字，因 `description_too_short` 被正确阻断；
- 未再次出现依靠招聘者资料把短 JD 撑到 180 字的情况。

### 2.4 近重复证据正确

4 条被排除记录均可从完整报告找到，实际相似度与导出值一致：

1. 微派两个 `AI Agent工程师` 岗位：description 完全相同，相似度 `1.0000`；
2. 三个额外“大模型工程化部署”岗位，相对于代表岗位的相似度分别为 `0.9471 / 1.0000 / 0.9755`。

所有 `duplicateOfUrl` 都指向正式保留的代表样本。

## 3. 发现的问题

### 3.1 详情配额仍按 v1.4.0 的 20 条目标分配

诊断结果：

```text
detailAttempted = 40
detailSucceeded = 40
finalDetailEnriched = 24
fullJd(final) = 23
cardOnly(final) = 55
detailCohortFullJd = 38
```

由这些计数可以还原：

- 40 个详情名额中只有 24 个最终进入通过岗位；
- 另外 16 个用于全国远程候选；
- 其中 15 个虽然抓到了完整 JD，但最终因没有远程证据而不属于正式目标岗位；
- 同时仍有 55 个已通过岗位只保留卡片，没有补采详情。

v1.4.2 已经要求“20 条独立 JD”，但详情目标选择仍只固定预留 20 个已通过岗位。出现 4 条近重复和 1 条短 JD 后，24 个已补采通过岗位只产生 19 条独立完整 JD。

因此问题不是门禁过严，也不是市场中没有第 20 条岗位，而是详情配额策略没有随独立样本门禁升级。

### 3.2 明显重复卡片仍会优先消耗详情名额

微派的两个岗位：

```text
AI Agent工程师
AI Agent 工程师
```

除标题空格外，公司、地区、薪资和最终 JD 完全相同，但两个 URL 都被补采，消耗了两个详情名额。

Collector 不应删除或覆盖来源记录，但在正式验收的详情补采顺序中，应先采集卡片身份不同的岗位，把这种明显重复卡片延后。

## 4. v1.4.3 修复

### 4.1 已通过岗位增加详情预取缓冲

`matched` 模式从固定预留 20 个已通过岗位，调整为：

```text
正式样本目标 = 20
已通过岗位预取目标 = ceil(20 × 1.5) = 30
detailLimit = 40
全国远程候选剩余名额 = 最多 10
```

当 `detailLimit` 小于 30 时，以实际上限为准。门槛仍然是 20 条独立 `full_jd`，只是增加对短 JD、抓取失败和近重复的采集缓冲。

### 4.2 卡片级明显重复延后

详情补采前使用以下字段生成仅用于排序的卡片身份：

```text
normalized(title) + company + area + salary
```

规范化采用 NFKC、小写，并移除空格和标点。相同身份的后续卡片不会从报告删除，只会排到其他独立卡片之后再考虑补采。

### 4.3 新增详情配额诊断字段

完整报告与诊断新增：

```text
detailTargetsPlannedAccepted
detailTargetsPlannedRemoteCandidates
detailTargetsDeferredAccepted
```

用于直接回答：本轮详情名额中多少给了已通过岗位、多少给了远程候选、还有多少已通过岗位因上限未补采。

## 5. 不变的质量规则

v1.4.3 不做以下妥协：

- 不把 `partial_jd` 或 `card_only` 纳入正式样本；
- 不降低 180 字和页面噪声门禁；
- 不提高 0.82 近重复阈值来掩盖重复；
- 不使用非目标远程候选的 JD 凑通过岗位样本；
- 不删除完整报告中的原始岗位来源记录。

## 6. 预期复验结果

以本次数据规模重新采集时，默认 40 个详情目标应显示接近：

```text
detailTargetsPlannedAccepted = 30
detailTargetsPlannedRemoteCandidates = 10
detailAttempted <= 40
```

正式结论仍以真实输出为准：

```text
distinctEligibleCount >= 20
selectedCount = 20
status = ready
```

若 30 个已通过岗位补采后仍不足 20 条独立完整 JD，`status` 必须继续保持 `blocked`，再根据新增配额字段判断是详情质量、重复率还是 detailLimit 本身不足。

## 7. 工程验证

已完成：

```text
Collector JavaScript 语法检查通过
Collector 全部测试通过
Backend：268 passed
Web：38 passed
TypeScript typecheck 通过
Next.js production build 通过
Alembic：No new upgrade operations detected
Collector v1.4.3 契约关键约束检查通过
git diff --check 通过
```
