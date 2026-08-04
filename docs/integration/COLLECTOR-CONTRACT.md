# JobLens Collector → Career Agent 接入契约

## 1. 当前接入策略

### MVP

```text
浏览器插件
→ 下载 boss-job-filter-report-*.json
→ Web 上传
→ POST /api/v1/job-imports
```

### P1

```text
浏览器插件
→ POST JobLens Agent API
→ 增量同步
```

---

## 2. 当前 Collector Report 结构

v1.4.2 主要结构（Backend 同时兼容 v1.3.1、v1.4.0 与 v1.4.1）：

```json
{
  "version": "1.4.2",
  "generatedAt": "...",
  "config": {},
  "statistics": {},
  "jobs": [],
  "candidates": []
}
```

Agent 系统优先导入 `jobs`，并按 `JobImport` 完整持久化 `candidates`，作为诊断和后续重新筛选数据；普通 API 只公开 candidate 汇总，不公开 raw。

---

## 3. Job 字段映射

Collector 已提供的高价值字段包括：

```text
scope
scopeTypes
searchCities
searchProvinces
searchCityCodes
searchKeyword
hitCount
title
categories
relevanceScore
salary
salaryMinK
salaryMaxK
salaryMonths
annualMinWan
annualMaxWan
area
remoteStatus
remoteConfidence
company
experience
education
skills
tags
publishedAt
recruiterActive
url
collectedAt
rawText
description
descriptionSource
descriptionSelectorTrust
descriptionSanitized
descriptionStartMarker
descriptionStopMarker
descriptionQuality
descriptionLength
descriptionHash
descriptionNoiseCount
detailAttempted
detailSucceeded
requirementReviewEligible
requirementReviewIneligibilityReasons
source
sourceUrl
sourceVersion
```

### 导入原则

1. Collector payload 是外部输入，不直接决定 JobLens internal ID；
2. 完整原始岗位数据保存到 `JobSource.source_raw`；
3. Agent 侧的 skill extraction 不覆盖 Collector 原字段；
4. Derived field 标记提取器版本；
5. Backend 生成、持久化并版本化 internal canonical job key；
6. `remoteStatus` 使用 `confirmed` / `rejected` / `unknown` 三态，不压缩成布尔值；
7. Collector v1.4.x 的 JD 质量字段作为 Requirement Extraction 的输入门禁证据，但仍原样保存在 `JobSource.source_raw`；
8. `detailSucceeded=true` 只表示详情页读取成功，不能替代 `requirementReviewEligible=true`。

canonical key v1：

```text
优先：v1:{source}:id:{normalized source job id}
其次：v1:{source}:url:{normalized source URL hash}
兜底：v1:{source}:fingerprint:{company + title + area hash}
```

`canonicalKey` 是 Backend 内部去重字段，不由 Collector 提供，也不进入普通 Job API Response。

### 身份映射

```text
Job.id
= JobLens 生成的内部资源 ID

JobSource.sourceJobId
= 招聘网站 / Collector 提供或从 URL 提取的外部岗位 ID
```

两者禁止复用。外部 ID 只在 `(source, sourceJobId)` 范围内有意义，可以为空，也可能随来源规则变化。

### 远程状态映射

Collector v1.3.1+ 当前已经输出：

```text
remoteStatus: confirmed | rejected | unknown
remoteConfidence: high | medium | low
```

Backend 保留这两个语义；普通“远程岗位”筛选指 `remoteStatus=confirmed`，不能把 `unknown` 当作 `rejected`。

---

## 4. MVP Import API 建议

```http
POST /api/v1/job-imports
Content-Type: application/json
```

请求：直接上传 Collector report。

响应：

```json
{
  "importId": "...",
  "sourceVersion": "1.4.2",
  "received": 120,
  "created": 85,
  "updated": 30,
  "skipped": 5,
  "errors": []
}
```

---

## 5. Requirement 人工质量验收数据集

Collector v1.4.2 额外导出：

```text
boss-job-filter-requirement-review-v1.4.2-*.json
```

该文件仍符合 Job Import 顶层结构，但 `jobs` 只包含：

```text
descriptionQuality = full_jd
requirementReviewEligible = true
detailSucceeded = true
```

`qualityGate.status=ready` 仅表示已选满 20 条独立完整 JD。`eligibleCount` 是原始合格岗位数，`distinctEligibleCount` 是移除近重复 JD 后的独立样本数；门禁依据后者。招聘者资料尾部、卡片摘要、页面正文兜底和近重复代招岗位都不能用于凑数。被排除的近重复岗位记录在 `excludedNearDuplicates`。

## 6. P1 插件同步 API

插件增加：

```text
JobLens API URL
API Token
同步岗位按钮
```

同步建议只发送：

- `jobs`
- `candidates`（可选）
- `config`
- `statistics`
- collector version

不要把 diagnostics 中的大量失败样例默认上传。

---

## 7. 向后兼容

Agent Importer 当前显式支持 `1.3.1`、`1.4.0`、`1.4.1` 与 `1.4.2`，未来仍不应把业务代码强耦合到单一版本。

建议：

```text
CollectorAdapterV1
CollectorAdapterV2
```

Importer 根据 report.version 选择 adapter。
