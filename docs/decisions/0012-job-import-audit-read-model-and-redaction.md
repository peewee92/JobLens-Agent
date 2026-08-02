# ADR-0012 · Job Import 审计 Read Model 与错误脱敏

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0009、ADR-0010、P0-1 Job Data Foundation

## Context

`POST /api/v1/job-imports` 已保存批次统计、快照、逐条 outcome 和错误。用户需要查询某次导入为何 created/updated/skipped，并定位具体失败条目。

数据库中的 `job_imports.errors` 可能包含错误输入的 `raw`，用于内部诊断。直接序列化 ORM 会泄漏原始岗位内容，并把持久化结构绑定到公开 API。

## Decision

新增：

```text
GET /api/v1/job-imports/{importId}
```

采用独立只读路径：

```text
HTTP
→ GetJobImportDetailUseCase
→ AbstractJobImportQueryRepository
→ SQLAlchemy Query Repository
```

查询返回专用 Read Model：

- 批次统计；
- SearchIntent / Source Snapshot；
- 脱敏后的 errors：index/stage/code/message；
- 按 inputIndex 排序的 ImportItem；
- 关联 Job / JobSource ID。

明确禁止公开：

- `errors.raw`；
- `JobSource.sourceRaw`；
- canonical key；
- normalized source URL。

SQLAlchemy 实现固定使用两条 SELECT：一条批次、一条 items；不执行写入或 commit。批次不存在由 Application 抛 `JobImportNotFoundError`，HTTP 映射为 404。

## Consequences

### Positive

- 用户可追溯一次导入的统计、快照和逐条结果；
- 数据库可保留诊断 raw，公开 API 仍保持最小暴露；
- HTTP、Application 与 ORM 解耦；
- 未来 Agent 可读取可靠审计事实，而不是推测执行过程。

### Cost / Limits

- items 当前不分页，超大批次响应可能较大；
- 尚无管理员 raw 诊断接口；
- 尚未实现批次列表、重跑或删除；
- candidates 仍未完整持久化。

## Verification

必须由测试证明：

- POST 后可按 importId 查询；
- 统计与 items 顺序正确；
- DB 中存在 raw 时 Response 不含 raw；
- 查询固定两条 SELECT 且无写 SQL；
- 未知 importId 返回结构化 404；
- Application / Router 不依赖 ORM 或 SQLAlchemy。
