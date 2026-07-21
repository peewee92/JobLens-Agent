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

v1.3.1 主要结构：

```json
{
  "version": "1.3.1",
  "generatedAt": "...",
  "config": {},
  "statistics": {},
  "jobs": [],
  "candidates": []
}
```

Agent 系统应优先导入 `jobs`，同时保留 `candidates` 作为诊断和后续重新筛选数据。

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
```

### 导入原则

1. 保留完整 `source_raw`；
2. Agent 侧的 skill extraction 不覆盖 Collector 原字段；
3. Derived field 标记提取器版本；
4. 使用 canonical job key 去重。

推荐 canonical key：

```text
优先：normalized URL job id
兜底：company + title + area
```

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
  "sourceVersion": "1.3.1",
  "received": 120,
  "created": 85,
  "updated": 30,
  "skipped": 5,
  "errors": []
}
```

---

## 5. P1 插件同步 API

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

## 6. 向后兼容

Agent Importer 不应强耦合 `1.3.1`。

建议：

```text
CollectorAdapterV1
CollectorAdapterV2
```

Importer 根据 report.version 选择 adapter。
