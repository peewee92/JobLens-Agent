# ADR-0007 · Job 身份、来源与远程状态模型

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** Product Owner / Senior Product Review / Architecture Review
- **Related:** P0-1 Job Data Foundation、ADR-0003（数据库策略）、ADR-0006（仓库策略）、COLLECTOR-CONTRACT

---

## 1. Context（背景）

在生成第一条业务 Migration 前，Job 模型存在四个会影响数据库长期稳定性的缺口：

1. P0-1 要支持远程岗位筛选，但 `Job` Contract 没有远程字段；
2. P0-1 使用 canonical job key 去重，但尚未明确是否持久化、是否对外暴露；
3. 架构中已有 `jobs` / `job_sources`，但两者的数据所有权不清晰；
4. Collector / 招聘网站的外部岗位 ID 与 JobLens 内部 `Job.id` 尚未区分。

这些问题如果在 Migration 之后才处理，会造成字段迁移、去重键重算、历史来源不可追溯，甚至让外部 ID 泄漏成系统主键。

---

## 2. Decision（决策）

### 2.1 远程状态采用三态，不使用单一布尔值

`Job` 对外读模型新增：

```text
remoteStatus: confirmed | rejected | unknown
remoteConfidence: high | medium | low
```

含义：

- `confirmed`：有明确证据支持远程办公；
- `rejected`：有明确证据要求到岗、坐班或不支持远程；
- `unknown`：JD 信息不足，不能判断；
- `remoteConfidence` 表示 Collector / 后端规则对该结论的置信等级，不表示概率。

P0-1 查询接口使用：

```http
GET /api/v1/jobs?remoteStatus=confirmed
```

而不是只使用 `remote=true/false`。产品界面对应三个可选项：

```text
支持远程 / 明确不支持 / 未确认
```

`SearchIntent.remoteAccepted` 表示用户是否接受远程工作；`Job.remoteStatus` 表示岗位事实。两者职责不同，禁止复用为同一字段。

### 2.2 canonical key 必须持久化，但不进入公共 Job Contract

数据库 `jobs` 表持久化：

```text
canonical_key
canonical_key_version
```

规则：

1. `canonical_key` 建立唯一索引，作为幂等导入和去重的内部身份键；
2. 它由 Backend Adapter / Normalizer 生成，不信任客户端直接传入；
3. 它不出现在 `packages/contracts/schemas/job.schema.json` 和普通 Job API Response 中；
4. `canonical_key_version` 用于未来算法升级与可追溯；
5. 一旦 Job 创建，canonical key 默认不可因标题或公司名称的小修改而自动变化；重算必须通过显式 re-key / merge 流程。

v1 生成优先级：

```text
优先：v1:{source}:id:{normalized_source_job_id}
其次：v1:{source}:url:{normalized_source_url_hash}
兜底：v1:{source}:fingerprint:{normalized(company + title + area) hash}
```

canonical key 是系统内部实现细节，不是业务展示字段，也不是安全凭证。

### 2.3 Job 与 JobSource 的职责冻结

#### Job：统一、稳定、面向业务的岗位实体

`Job` 保存用于查询、匹配和排序的标准化当前状态：

```text
id（JobLens internal ID）
canonical_key / canonical_key_version（仅持久化内部字段）
title / company / area
salary_min_k / salary_max_k
experience / education / description / skills
remote_status / remote_confidence
created_at / updated_at
```

它回答：

> JobLens 认为“这是哪个岗位”，以及当前用于产品功能的标准化事实是什么。

#### JobSource：来源身份、原始证据和采集状态

`JobSource` 保存某个外部来源对该岗位的记录：

```text
id（JobLens internal source row ID）
job_id（FK → jobs.id）
source
source_job_id（外部岗位 ID，可空）
source_url / normalized_source_url
source_version
source_raw
first_seen_at / last_seen_at / collected_at
created_at / updated_at
```

它回答：

> 这个 Job 从哪里来、外部怎么称呼它、原始数据是什么、何时首次和最近看到。

约束：

- `source_raw` 属于 `JobSource`，不直接存放在 `jobs`；
- `Job` API 可以为使用方便扁平返回 primary source 的 `source` / `sourceUrl` / `sourceVersion` / `collectedAt`，但这些字段由 `JobSource` 组装，不代表数据库重复存储；
- 一个 Job 未来可以关联多个 JobSource，以支持跨平台同岗位合并；
- JobSource 不是“每次导入事件”，不要用它代替导入批次明细。

### 2.4 导入批次与来源实体分离

`JobImport` 表示一次 report 导入批次，保存版本、快照和汇总。

为了能精确回答“该批次中的第 N 条数据如何处理”，第一条业务 Migration 增加轻量关联表：

```text
job_import_items
```

核心字段：

```text
id
import_id
input_index
job_id（可空）
job_source_id（可空）
outcome: created | updated | skipped | error
error_code / error_message（可空）
created_at
```

该表不重复保存 `source_raw`；原始数据仍归 `JobSource`，批次原始 report / source snapshot 归 `JobImport`。

### 2.5 内部 ID 与外部 ID 严格分离

#### JobLens internal ID

```text
Job.id
JobSource.id
JobImport.id
```

由 JobLens 生成，为不透明字符串，作为数据库主键和 API Resource ID。调用方不得解析其业务含义。

#### 外部来源 ID

```text
JobSource.source_job_id
```

由招聘网站或 Collector 提供/从 URL 稳定提取，仅在 `source` 范围内有意义：

```text
(source, source_job_id)
```

它可以为空、改变格式或被来源方回收，因此：

- 不能作为 `jobs.id`；
- 不能单独作为全局主键；
- 不能要求 Web / Agent 使用它关联 JobLens 资源。

`packages/contracts/schemas/job.schema.json` 中的 `id` 明确定义为 **JobLens internal Job ID**，不是 Collector Job ID。

---

## 3. Persistence 约束

第一条业务 Migration 至少包含：

```text
jobs
job_sources
job_imports
job_import_items
```

建议索引 / 唯一约束：

```text
UNIQUE jobs.canonical_key
INDEX jobs.remote_status
INDEX jobs.area
INDEX jobs.salary_min_k
UNIQUE job_sources(source, normalized_source_url)
INDEX job_sources(source, source_job_id)
INDEX job_import_items(import_id)
INDEX job_import_items(job_id)
```

`source_job_id` 可空，因此是否添加条件唯一索引由 SQLite / PostgreSQL 兼容性评审后决定；MVP 先以 `(source, normalized_source_url)` 唯一约束和 Application 层校验保证一致性。

---

## 4. API 与产品语义

### Job Pool 筛选

```http
GET /api/v1/jobs?remoteStatus=confirmed
GET /api/v1/jobs?remoteStatus=rejected
GET /api/v1/jobs?remoteStatus=unknown
```

未提供参数时不过滤远程状态。

### Job Response

- `id`：JobLens internal ID；
- `remoteStatus` / `remoteConfidence`：可展示、可筛选；
- `source` / `sourceUrl`：primary source 的便捷读字段；
- 不返回 `canonicalKey`；
- 默认不返回 `sourceRaw`，仅在后续诊断/管理接口按权限读取。

### 用户文案

- 不把 `unknown` 展示为“不支持远程”；
- 不把 `remoteConfidence` 展示为百分比；
- “远程岗位”默认指 `remoteStatus=confirmed`。

---

## 5. Consequences（后果）

### 正向

- 避免布尔远程状态造成误筛；
- 去重键稳定、可版本化、可建立数据库唯一约束；
- 标准化业务数据与原始来源证据分离；
- 外部平台 ID 变化不会破坏 JobLens 内部引用；
- 未来增加 LinkedIn / Wellfound 等来源时，不需要重做 Job 主键体系；
- 导入批次具备逐条追踪能力。

### 代价

- 第一条 Migration 从 3 张表增加到 4 张表；
- API 组装 Job 时需要读取 primary JobSource；
- Adapter / Normalizer 需要负责 URL 规范化、source job id 提取和 canonical key 生成。

这些成本在 Migration 前非常低，晚于 Migration 再修复的成本显著更高，因此现在接受。

---

## 6. 非目标

本 ADR 暂不解决：

- 跨招聘平台的语义合并算法；
- 多个来源之间的 primary source 自动选择；
- 历史每次抓取内容的完整版本存档；
- LLM 参与岗位去重；
- canonical key 对外查询接口。

MVP 只保证同一来源内的稳定去重与可追溯导入。
