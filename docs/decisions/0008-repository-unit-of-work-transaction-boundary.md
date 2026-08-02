# ADR-0008 · Repository 与 Unit of Work 事务边界

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0002、ADR-0003、ADR-0007、P0-1 Job Data Foundation

## Context

后续 `ImportJobsUseCase` 会在一次业务动作中同时写入：

```text
JobImport
Job
JobSource
JobImportItem
```

如果每个 Repository 方法自行 `commit()`，中途任一步骤失败都会留下部分数据，例如 Job 已提交但 JobSource 创建失败，导致岗位池与导入审计不一致。

同时，若 Application 或 Router 直接散落 SQLAlchemy 查询，会让业务流程依赖 ORM、Session 和具体数据库实现，不利于测试、迁移 PostgreSQL 和后续 Agent Workflow 复用。

## Decision

### 1. Repository Port 由 Application 层拥有

接口位于：

```text
services/backend/app/application/ports/
```

它只暴露业务需要的持久化能力，不返回 SQLAlchemy ORM Model，不接收 Session，也不创建 Engine。

### 2. SQLAlchemy Repository 是 Infrastructure Adapter

实现位于：

```text
services/backend/app/repositories/
```

职责：

- 使用 SQLAlchemy 2.x `select()` 查询；
- 新增和更新 ORM Model；
- 必要时 `flush()`，以取得生成 ID、建立 FK 关系并提前暴露数据库约束错误；
- 不调用 `commit()` 或 `rollback()`。

### 3. Unit of Work 拥有 Session 和事务边界

`SqlAlchemyUnitOfWork`：

- 进入时从 `SessionLocal` 创建一个 Session；
- 为所有 Repository 共享同一 Session；
- Application 在全部步骤成功后显式调用 `commit()`；
- 未调用 commit、或发生异常时，在退出上下文时 rollback；
- 最后关闭 Session。

标准调用形态：

```python
with uow_factory() as uow:
    # query / add / update through repositories
    uow.commit()
```

### 4. FastAPI 注入 UoW Factory，而不是裸 Session

API 层只负责构造依赖。具体事务开始和结束由 Application Use Case 决定，因此 Endpoint 不直接操作 Session。

### 5. 幂等导入所需查询能力

Repository 第一版必须支持：

```text
find_job_id_by_canonical_key
find_source_id_by_external_id
find_source_id_by_normalized_url
```

后续 Use Case 按以下顺序判断创建或更新：

```text
canonical_key
→ source + external ID
→ source + normalized URL
```

## Consequences

### Positive

- 多表写入具备原子性；
- Repository 可替换为测试实现或其他数据库实现；
- Application 不依赖 SQLAlchemy；
- 后续 Agent / Workflow 可复用同一业务能力；
- 幂等查询有明确入口。

### Cost

- 增加 Port、Adapter 和 Unit of Work 层；
- 简单 CRUD 比直接在 Router 写 SQLAlchemy 多一些代码；
- 开发者必须理解 `flush` 与 `commit` 的区别。

该成本在当前阶段可接受，因为 Job Import 天然是一个多表、一致性要求较高的业务动作。

## Verification

必须由自动测试证明：

- Repository flush 后可取得 ID，但不会自行提交；
- 显式 UoW commit 后四表共同持久化；
- 不 commit 时全部回滚；
- 中途异常时全部回滚；
- canonical key / external ID / normalized URL 查询可定位已有记录。
