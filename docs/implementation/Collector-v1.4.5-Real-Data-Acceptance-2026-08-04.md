# Collector v1.4.5 真实数据验收与 v1.4.6 修复记录

Date: 2026-08-04

Status: v1.4.5 Requirement 正式输入、远程语义和四文件一致性通过；整页辅助文本存在 1 个非阻断 CJK 部首残留，已修复为 v1.4.6

## 1. 验收输入

本轮检查以下同批次真实浏览器导出：

- `boss-job-filter-requirement-review-v1.4.5-2026-08-04T08-31-15-681Z.json`
- `boss-job-filter-diagnostics-v1.4.5-2026-08-04T08-31-15-681Z.json`
- `boss-job-filter-report-v1.4.5-2026-08-04T08-31-15-681Z.json`
- `boss-job-filter-v1.4.5-2026-08-04T08-31-15-681Z.csv`

三个 JSON 的生成时间相差不足 1 秒，配置版本均为 `1.4.5`，CSV 与 Report 属于同一批结果。

## 2. Requirement 正式样本门禁

```text
requiredSampleSize = 20
eligibleCount = 30
distinctEligibleCount = 27
nearDuplicateCount = 3
selectedCount = 20
status = ready
blockers = []
```

门禁数学关系成立：

```text
30 eligible - 3 near duplicates = 27 distinct eligible
```

三条近重复都属于“大模型工程化部署”同源 JD，分别与代表样本相似：

- `0.9471`
- `1.0000`
- `0.9755`

20 条正式样本逐条检查通过：

- URL 均能在完整 Report 中精确找到；
- 标题、公司、正文、来源、版本和质量字段一致；
- `detailSucceeded=true`；
- `descriptionQuality=full_jd`；
- `descriptionHasRoleEvidenceSignal=true`；
- `descriptionNoiseCount=0`；
- `requirementReviewEligible=true`；
- 阻断原因数组为空；
- 实际正文长度与 `descriptionLength` 完全一致；
- 按 JavaScript UTF-16 语义重算 FNV-1a 后，与 `descriptionHash` 完全一致；
- 未发现招聘者资料尾部、推荐职位、BOSS 安全提示或工商信息混入正式正文；
- 20 条已选样本之间没有达到 `0.82` 阈值的近重复正文。

结论：该文件可作为 Requirement Extraction 的正式 20 条人工验收输入。

## 3. 四文件与统计对账

```text
rawCards = 1123
duplicateRawHits = 695
uniqueCardsBeforeFilter = 428
report candidates = 428

finalAfterCrossScopeDedupe = 76
report jobs = 76
csv rows = 76
```

关系成立：

```text
1123 - 695 = 428
```

Report 的 76 条最终岗位 URL 全部唯一。CSV 按 URL 与 Report 逐条对账，岗位、公司、搜索范围、薪资、分类、技能、远程状态、JD 质量、长度、指纹、证据计数、验收资格、原文和正文均一致，没有缺失行或额外行。

详情配额与执行结果：

```text
detailTargetsPlannedAccepted = 30
detailTargetsPlannedRemoteCandidates = 10
detailTargetsDeferredAccepted = 17

detailAttempted = 40
detailSucceeded = 40
detailFailed = 0
```

按 URL 去重后的详情样本：

```text
detailCohortEnriched = 40
detailCohortFullJd = 37
detailCohortPartialJd = 3
detailCohortRequirementReviewEligible = 37
```

最终 76 条岗位：

```text
finalDetailEnriched = 31
fullJd = 30
partialJd = 1
cardOnly = 45
requirementReviewEligible = 30
```

三条详情样本被降级为 `partial_jd` 的原因符合门禁预期：一条正文不足 180 字，两条只有职责描述但缺少足够的职责/资格组合证据，均未进入正式样本。

## 4. 远程语义验收

本批统计：

```text
candidateRemoteConfirmed = 1
remoteConfirmed = 0
final byRemoteStatus = unknown: 76
```

唯一远程候选为：

```text
兼职远程全栈开发工程师（AI驱动型）
```

该岗位标题提供明确远程证据，但薪资为 `500-1000元/天`，当前月薪门槛不对日薪作错误换算，因此以“薪资无法解析”排除，没有进入最终岗位。

逐条搜索标题、地点、卡片文本和已裁剪 JD 后：

- 未发现 `远程支持` 被当成远程办公；
- 未发现 `远程监测` 被当成远程办公；
- 未发现推荐岗位中的“全国远程”污染当前岗位；
- 没有明确远程办公证据被漏标。

结论：v1.4.5 的远程语义修复通过真实数据文件级验收。

## 5. 文本规范化验收

对所有 candidate 的 `description` 扫描：

```text
康熙部首 / CJK 兼容字 / 零宽字符残留 = 0
```

正式 20 条 JD 和最终岗位正文均已规范化，不影响 Requirement、技能提取、哈希和近重复判断。

对整页辅助字段 `detailText` 扫描时发现一处残留：

```text
岗位：前端开发工程师-智能体交互/平台方向
公司：AutoAgents.ai
字符：⻓
码点：U+2ED3 CJK RADICAL C-SIMPLIFIED LONG
上下文：团队⻓期致力于推动企业数字化和智能化的发展
```

该字符位于公司介绍，不在已裁剪 JD `description` 内，因此：

- 不影响 20 条正式样本；
- 不影响 Requirement evidence；
- 不影响远程判断；
- 不影响本轮质量门禁。

但它说明 v1.4.5 只覆盖了康熙部首和兼容表意文字，没有完整覆盖 CJK Radicals Supplement。

## 6. v1.4.6 修复

`normalizeVisibleText` 已扩展：

- 扫描范围从 `U+2F00–U+2FD5` 扩展至 `U+2E80–U+2FD5`；
- 对本批真实数据观测到的 `⻓` 显式映射为 `长`；
- 继续通过 NFKC 处理已有康熙部首和兼容表意文字；
- 继续移除 `U+200B / U+2060 / U+FEFF`；
- 规范化同时作用于卡片文本、JD 正文和 `detailText`；
- Backend 新增 `1.4.6` 导入与 Requirement Extraction 门禁兼容。

新增回归样例：

```text
具备较⾼的⼯程能⼒\u200b，团队⻓期熟悉 RAG。
→
具备较高的工程能力，团队长期熟悉 RAG。
```

## 7. 最终批准边界

| 验收对象 | 结论 |
|---|---|
| v1.4.5 的 20 条 Requirement 正式 JD | 通过 |
| v1.4.5 的岗位证据与近重复门禁 | 通过 |
| v1.4.5 的远程岗位语义 | 通过 |
| v1.4.5 的 CSV / Report / Diagnostics 对账 | 通过 |
| v1.4.5 的正式 JD 字符规范化 | 通过 |
| v1.4.5 的整页辅助文本字符规范化 | 非阻断偏差，已修复 |
| v1.4.6 修复实现 | 通过 |

## 8. 工程回归

```text
scripts/verify.sh = passed
Collector JavaScript tests = passed
Backend pytest = 274 passed, 1 pre-existing deprecation warning
Web tests = 38 passed
TypeScript typecheck = passed
Next.js production build = passed
Alembic check = no new upgrade operations detected
```

本批 v1.4.5 的 20 条正式 JD 可以直接进入同一 provider / model / extractor / prompt cohort 的 Requirement Extraction 人工质量验收，不需要因为 `detailText` 中的公司介绍字符重新采集。
