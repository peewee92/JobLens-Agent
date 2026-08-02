# ADR-0010 · HTTP / Application 边界与错误映射

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0008、ADR-0009、P0-1 Job Data Foundation、JOB-IMPORT-API-CONTRACT

## Context

`ImportJobsUseCase` 已经负责 Adapter、Normalizer、幂等判断、批次统计和事务。下一步需要通过 FastAPI 暴露 `POST /api/v1/job-imports`，但不能把已经稳定的业务逻辑复制进 Router。

同时，Collector report 允许单条 Job 校验失败后继续导入其他合法条目。如果 HTTP Request DTO 将每一条 Job 强类型化，FastAPI 会在进入 Use Case 前整批返回 422，破坏已冻结的错误隔离规则。

## Decision

### 1. Router 只依赖 ImportJobsUseCase

调用链固定为：

```text
HTTP Router
→ ImportJobsUseCase
→ Repository Port / Unit of Work
→ SQLAlchemy / SQLite
```

Router 不允许：

- 注入裸 Session；
- 调用 Repository；
- 查询 canonical key；
- 决定 created / updated；
- commit / rollback。

### 2. Request 宽松，Response 强类型

HTTP 层只要求请求顶层是 `dict[str, Any]`。Collector envelope 和单条 Job 由 Application Adapter 逐条校验。

公开响应使用 Pydantic DTO，并序列化为 camelCase：

```text
import_id      → importId
source_version → sourceVersion
```

Application Result 不承担 HTTP Contract 职责。

### 3. 成功状态码为 201

每次成功导入都会创建新的 `JobImport` 审计资源，因此返回：

```http
201 Created
```

即使部分条目为 `error + skipped`，只要批次成功提交，仍返回 201，并通过响应中的 `skipped/errors` 表达部分失败。

### 4. Application Error 映射到 HTTP

```text
RequestValidationError              → 422 request_validation_error
InvalidCollectorReportError         → 422 invalid_collector_report
UnsupportedCollectorVersionError    → 422 unsupported_collector_version
ImportIdentityConflictError         → 409 import_identity_conflict
Unexpected Exception                → 500 internal_server_error
```

Application 层不导入 FastAPI，不携带 HTTP Status Code。

### 5. 未知错误不泄漏内部信息

500 响应只返回稳定通用消息。数据库 URL、本地路径、堆栈等信息只进入服务端日志。

### 6. 缺少 version 时返回 422

当前不存在安全可用的“保守 Adapter”。因此缺少 `version` 视为无效 Collector report，不自动猜测版本。

## Consequences

### Positive

- HTTP、Agent、CLI 未来都可复用同一个 Use Case；
- 单条坏 Job 不会被 FastAPI 提前整批拒绝；
- HTTP Contract 与内部模型解耦；
- 错误状态码稳定且不泄漏内部实现；
- Router 保持极薄，事务边界不被破坏。

### Cost

- OpenAPI 不能完整描述每个 Collector Job 字段；
- 需要单独维护 Application Model 和 HTTP Response DTO；
- 请求错误与业务错误需要集中映射。

## Verification

必须由自动测试证明：

- 合法 report 返回 201 并真实写入四张表；
- 重复导入返回 updated，Job 数量不增加；
- 单条错误返回 201 + skipped/errors；
- 不支持版本返回 422 且数据库无新增；
- 身份冲突返回 409 且整批回滚；
- 未知错误返回通用 500，不泄漏内部路径；
- OpenAPI 注册该路由；
- Router 不导入 ORM、Repository 或 SQLAlchemy，也不管理事务。
