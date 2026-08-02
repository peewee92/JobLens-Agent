# P0-1 Job Data Foundation（岗位数据地基）

> 阶段：ROADMAP Phase 1。依赖：Phase 0.5 领域模型冻结。后续：Phase 2（Profile + SearchIntent）。
> 这一阶段**只做数据地基**，不碰 Profile / Match 的 LLM 能力。做完即可作为第一个可独立验收的节点。

## 1. 目标

把已有 JobLens Collector 的 JSON 正式、可复现地导入系统，形成可靠的 `Job Pool`，供后续 Profile / Requirement / Match 使用。

主链路：

```text
Collector JSON
→ Import
→ Normalize
→ Dedupe
→ Persist
→ Query
→ Job Pool
```

---

## 2. 功能需求（FR）

1. **FR-1 导入接口**：提供 `POST /api/v1/job-imports`，直接接收 Collector report JSON。
2. **FR-2 原始保留**：每个外部岗位来源记录通过 `JobSource.sourceRaw` 保留完整原始数据，不因已结构化而丢弃；普通 Job API 默认不返回原始数据。
3. **FR-3 标准化**：对薪资、城市、远程、技能、JD 做字段标准化（不覆盖 Collector 原字段）。
4. **FR-4 去重**：使用 canonical job key 去重，重复导入不产生大量重复岗位。
5. **FR-5 候选保留**：导入 `jobs` 的同时保留 `candidates`（诊断 / 后续重筛）。
6. **FR-6 批次记录**：每次导入记录 `Import Batch`（import id、source version、received/created/updated/skipped、errors）。
7. **FR-7 复现快照**：批次保存 `Source Snapshot` / `Collector Version` / `Collected At` / `SearchIntent Snapshot`（见 §8 与 COLLECTOR-CONTRACT）。
8. **FR-8 查询接口**：支持按城市、薪资区间、关键词、远程状态（`confirmed` / `rejected` / `unknown`）、来源筛选 Job Pool。
9. **FR-9 原始链接**：可打开岗位的原始 BOSS URL。
10. **FR-10 兼容策略**：Importer 根据 `report.version` 选择 adapter，不强耦合 `1.3.1`。

---

## 3. 业务规则（BR）

- **BR-1 去重主键**：Backend 生成并持久化带版本的内部 `canonicalKey`；优先使用 `normalized source job id`，其次 normalized URL，最后兜底 `company + title + area` 指纹。`canonicalKey` 不进入公共 Job Contract。
- **BR-2 幂等导入**：同一 report 重复导入，Job 数量基本不增加（created 接近 0，updated 反映字段变化）。
- **BR-3 字段优先级**：Agent 侧衍生字段标记 `extractorVersion`；Collector 原字段为权威来源，衍生字段不得覆盖原字段。
- **BR-4 错误隔离**：单条 Job 解析失败不影响整批，计入 `errors` 并返回。
- **BR-5 薪资标准化**：`salaryMinK` / `salaryMaxK` 由 `salary` / `annualMinWan` 等推导，缺失则 `null`。
- **BR-6 快照不可变**：导入批次的 `SearchIntent Snapshot` 与 `Source Snapshot` 一旦写入不可改，保证“为什么这批岗位 Python 比例高”可复现。

---

## 4. API

### 4.1 导入

```http
POST /api/v1/job-imports
Content-Type: application/json
```

请求体：直接上传 Collector report（结构见 COLLECTOR-CONTRACT §2）。

响应：

```json
{
  "importId": "imp_01H...",
  "sourceVersion": "1.3.1",
  "received": 120,
  "created": 85,
  "updated": 30,
  "skipped": 5,
  "errors": []
}
```

### 4.2 查询 Job Pool

```http
GET /api/v1/jobs?city=上海&minSalaryK=20&remoteStatus=confirmed&q=React&limit=50&offset=0
```

响应（分页）：

```json
{
  "total": 540,
  "items": [
    {
      "id": "job_...",
      "title": "AI 应用工程师",
      "company": "X",
      "area": "上海",
      "salaryMinK": 25,
      "salaryMaxK": 45,
      "sourceUrl": "https://...",
      "collectedAt": "2026-07-20T10:00:00Z"
    }
  ]
}
```

### 4.3 导入批次查询

```http
GET /api/v1/job-imports/{importId}
```

返回批次汇总、关联的 `SearchIntent Snapshot` / `Source Snapshot`，以及按 `inputIndex` 排序的逐条 outcome。数据库可保留错误 raw 用于诊断，但普通 API 只返回 index/stage/code/message。

---

## 5. 数据模型

### 5.1 Job（复用 `job.schema.json`）

面向查询、匹配和排序的标准化岗位读模型：`id`（JobLens internal ID）/ `title` / `company` / `area` / `salaryMinK` / `salaryMaxK` / `experience` / `education` / `description` / `skills` / `remoteStatus` / `remoteConfidence` / `source` / `sourceUrl` / `sourceVersion` / `collectedAt`。

数据库内部额外持久化 `canonical_key` / `canonical_key_version`，但不通过公共 Job Contract 暴露。

### 5.2 job_sources（来源）

```text
id                         # JobLens internal source row ID
job_id                     # FK → jobs.id
source
source_job_id              # 外部岗位 ID，可空
source_url
normalized_source_url
source_version
source_raw                 # 完整原始岗位数据
first_seen_at
last_seen_at
collected_at
created_at
updated_at
```

`Job` 是统一岗位实体；`JobSource` 负责外部身份、URL、原始证据和采集时间。Collector / 招聘网站 ID 只能写入 `source_job_id`，不能作为 `jobs.id`。

### 5.3 job_imports（批次）

```text
id
source_version
received
created
updated
skipped
errors (json)
search_intent_snapshot (json)   # §8
source_snapshot (json)          # §8
collector_version
collected_at
created_at
```

### 5.4 job_import_items（批次明细）

用于记录 report 中每一条输入的处理结果：`import_id` / `input_index` / `job_id` / `job_source_id` / `outcome` / `error_code` / `error_message`。它不重复保存 `sourceRaw`。

### 5.5 job_import_candidates（候选证据）

每个 `report.candidates` 条目作为不可变批次证据保存：`import_id` / `candidate_index` / `keep` / `decision` / `pending_detail` / `source_job_id` / `source_url` / `title` / `company` / `candidate_raw`。Candidate 不直接创建 Job；原始 JSON 完整保存，普通 API 只返回 kept/rejected/unknown 汇总。

### 5.6 持久化

- MVP：SQLite（ADR-0003）；
- Migration 0001：`jobs` / `job_sources` / `job_imports` / `job_import_items`；
- Migration 0002：`job_import_candidates`；
- 身份、来源和远程状态决策：ADR-0007；
- 迁移：Alembic（ADR-0002）。

---

## 6. 错误处理

| 场景 | 处理 |
| --- | --- |
| report 缺 `version` | 返回 422；当前不猜测 Collector 版本，避免错误解析 |
| 单条 Job 缺 `title`/`company`/`sourceUrl` | 跳过该条，计入 `errors` |
| 解析异常 | 捕获并计入 `errors`，不影响其他条 |
| 重复导入 | BR-2 幂等，created≈0 |
| adapter 不匹配 | 返回 422，提示支持的 report 版本 |

---

## 7. 兼容策略

- Importer 根据 `report.version` 选择 `CollectorAdapterV1` / `CollectorAdapterV2`；
- 不强耦合 `1.3.1`；新 Collector 版本只需新增 adapter；
- `sourceRaw` 全量保存，旧版本字段缺失不影响新版本导入。

---

## 8. 复现快照（与 COLLECTOR-CONTRACT 对齐）

每次导入必须保存，否则“市场分析”不可复现：

```text
Import Batch       批次 id 与汇总
Source Snapshot    搜索关键词 / 城市 / 省份 / 时间范围
Collector Version  插件版本
Collected At       采集时间
SearchIntent Snapshot  用户当时的目标角色/城市/薪资下限等
```

用途：回答“为什么这批岗位里 Python 比例这么高”需要知道——用什么关键词搜的、哪个城市、什么时间、哪个 Collector 版本、用户当时 SearchIntent 是什么。

COLLECTOR-CONTRACT §5 的 P1 插件同步也建议携带上述快照字段。

---

## 9. 验收标准

- [x] `POST /api/v1/job-imports` 可导入 Collector v1.3.1 report JSON；
- [x] 同一 JSON 重复导入两次，Job 数量基本不增加；
- [x] 每个 JobSource 保留完整 `sourceRaw`，普通 Job API 默认不返回；
- [x] 可按城市、薪资、关键词和三态 `remoteStatus` 筛选 Job Pool；
- [x] `Job.id` 为 JobLens internal ID，外部岗位 ID 只存于 `JobSource.sourceJobId`；
- [x] `jobs.canonical_key` 持久化并建立唯一约束，但不出现在普通 API Response；
- [x] Job List / Detail 返回原始 `sourceUrl`，前端可据此打开 BOSS URL；
- [x] 导入批次保存 `SearchIntent Snapshot` / `Source Snapshot` / `Collector Version` / `Collected At`；
- [x] 单条失败不中断整批，错误计入响应；
- [x] 可通过 `GET /api/v1/job-imports/{importId}` 查询批次统计、快照和逐条 outcome，且不暴露错误 raw；
- [x] `candidates` 按 import 完整持久化，保留 raw 和原始顺序，致命错误时同事务回滚；
- [x] 审计详情返回 candidateSummary，但不暴露 candidateRaw；
- [x] Web 可上传 Collector JSON、查看导入结果与审计、筛选 Job Pool 并打开 Job 详情；
- [x] Web 不暴露 Backend 地址或 raw/canonical 内部字段；
- [x] 提供至少 1 个 pytest 用例：幂等导入断言 created≈0。

> P0-1 Job Data Foundation 的 Backend 与最小 Web E2E 已完成。下一阶段进入 Phase 2 Profile + SearchIntent；不提前做 Match、Ranking 或 Agent Chat。
