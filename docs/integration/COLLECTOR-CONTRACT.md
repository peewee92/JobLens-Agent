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

1. Collector payload 是外部输入，不直接决定 JobLens internal ID；
2. 完整原始岗位数据保存到 `JobSource.source_raw`；
3. Agent 侧的 skill extraction 不覆盖 Collector 原字段；
4. Derived field 标记提取器版本；
5. Backend 生成、持久化并版本化 internal canonical job key；
6. `remoteStatus` 使用 `confirmed` / `rejected` / `unknown` 三态，不压缩成布尔值。

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

Collector v1.3.1 当前已经输出：

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
