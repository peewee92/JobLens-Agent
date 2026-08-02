# ADR-0011 · Job Query Read Model 与主来源选择

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0003、ADR-0007、ADR-0008、P0-1 Job Data Foundation

## Context

Job Import 已能将标准化 Job、外部 JobSource 和批次审计写入 SQLite。下一步需要支持 Job Pool 列表和详情查询。

`Job` 与 `JobSource` 是一对多关系，而公共 Job Contract 只展示一个 `source/sourceUrl`。若直接 Join 所有 JobSource 后分页，同一 Job 会占据多行，造成重复、分页遗漏和 total 不一致。若直接返回 ORM，又可能泄漏 `canonical_key`、`source_raw` 和 `normalized_source_url`。

## Decision

### 1. 查询路径使用独立 Query Repository

新增：

```text
AbstractJobQueryRepository
SqlAlchemyJobQueryRepository
ListJobsUseCase
GetJobUseCase
```

查询路径与写入 Repository 分离：

- 写入路径关注幂等、事务和一致性；
- 查询路径关注筛选、稳定分页和公开 Read Model；
- 不拆服务、不拆数据库，只做模块内轻量 CQRS。

### 2. Query Repository 返回 Application Read Model

返回：

```text
JobListItem
JobDetail
JobPage
```

不返回 SQLAlchemy ORM Model，也不暴露 Session。

公共响应不包含：

```text
canonicalKey
canonicalKeyVersion
sourceRaw
normalizedSourceUrl
```

### 3. 主来源规则

每个 Job 只选择一个主来源：

```text
last_seen_at DESC
→ source_id ASC
```

当请求带 `source` 过滤时，主来源选择限制在该来源内，因此响应中的 `source` 与过滤条件一致。

### 4. 查询语义

- `q`：title/company/description 的不区分大小写字面量包含匹配；
- `city`：area 的不区分大小写字面量包含匹配；
- `minSalaryK`：`salary_max_k >= minSalaryK`，未知薪资不满足；
- `remoteStatus`：精确三态匹配；
- `source`：精确来源匹配；
- 排序：latest、salaryDesc、salaryAsc。

用户输入中的 `%` 和 `_` 作为普通字符处理，不作为 SQL LIKE 通配符。

### 5. 稳定分页

默认排序：

```text
primary_source.last_seen_at DESC
job.id ASC
```

薪资排序同样以 `job.id ASC` 作为最终 tie-breaker。

列表由同一 Repository 方法一次返回 `total + items`，确保 count 与分页项复用同一筛选定义。

### 6. 查询 Session 与 SQL 数量

查询不调用 commit。Query Repository 使用短生命周期 Session：

- 列表：固定两条 SELECT（count + items）；
- 详情：一条 SELECT；
- 不触发 ORM relationship 懒加载，避免 N+1。

## Consequences

### Positive

- 多来源岗位不会重复占分页行；
- API Contract 与数据库模型隔离；
- 查询能力可被 HTTP、Agent Tool、CLI 复用；
- total、items 和排序语义可测试；
- 不泄漏原始数据和内部身份字段。

### Cost

- 需要额外 Read Model、Port 和映射代码；
- offset pagination 在数据持续变化时仍可能产生跨请求漂移；
- SQLite LIKE 只适合 MVP 数据规模，不是最终全文搜索方案。

## Verification

自动测试必须证明：

- 城市、关键词、最低薪资、远程状态和来源筛选；
- 多来源只返回一个 Job；
- 主来源确定性选择；
- 稳定分页；
- 列表两条 SELECT、详情一条 SELECT；
- 查询不改变数据库记录；
- API 不返回 raw/canonical 字段；
- 缺失 Job 返回结构化 404。
