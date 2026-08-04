# ADR-0030｜Guarded Local Bootstrap before Live Requirement Acceptance

- Status: Accepted
- Date: 2026-08-04

## Context

Requirement Acceptance 已具备：formal preflight、persistent Run、Canary budget、immutable human gate、Web Workbench、Readiness 和 Session Manifest。

当前真正阻塞是本地运行环境：

- 正式 20-JD 尚未进入 DevSpace 私有路径；
- 本地 SQLite revision 落后于 code head；
- Provider、Model、Key 尚未配置。

直接给出若干 shell 命令存在高风险：数据可能进入 Git、SQLite 可能在无一致备份时升级、migration 失败可能被误报成功。

## Decision

引入独立 CLI：

```text
scripts.bootstrap_requirement_acceptance
```

它只负责本地数据和 SQLite schema 准备，不负责 Provider 执行。

### 1. Plan/Apply 两阶段

默认是 Plan：

```text
planValidated=true/false
applyExecuted=false
localPreparationSucceeded=false
```

只有显式 `--apply` 才允许 staging、backup 和 migration。

### 2. 固定私有边界

Dataset、backup 和 Receipt 必须位于：

```text
data/private/...
```

路径 resolve 后仍必须在 private root 内。符号链接逃逸会被拒绝。

### 3. Dataset staging

- 先复用 formal preflight；
- 目标文件名由 dataset fingerprint 派生；
- 使用临时文件、fsync、atomic replace；
- 校验 byte count 与 SHA-256；
- 相同内容复用；不同内容禁止覆盖。

### 4. SQLite backup

使用 `sqlite3.Connection.backup()`，而不是普通文件复制。

Backup 必须：

- 不覆盖已有文件；
- 通过 `PRAGMA integrity_check`；
- 保存 source Alembic revision；
- 保存 file SHA-256 和 byte count。

### 5. Migration gate

若存在 pending migration：

- `--apply` 还必须提供 `--confirm-backend-stopped`；
- 只有 verified backup 成功后才调用 Alembic；
- 记录 `migrationAttempted` 和 `migrationApplied`；
- migration 后验证 revision=head；
- migration 后验证 live DB integrity=ok。

该确认只是操作者声明，不是进程检测。

### 6. Failure behavior

Migration 失败时：

- 立即停止；
- 不调用 Provider；
- 不继续 Readiness；
- 保留 verified backup path；
- 不自动 restore；
- Receipt 明确记录 attempt/success 状态。

### 7. Readiness rerun

本地准备成功后，使用 staged dataset 重新运行现有 Readiness，输出剩余 Provider/人工 blocker。

### 8. Write boundary

CLI 不导入或调用：

- LLM extractor builder；
- ImportJobsUseCase；
- PrepareRequirementAcceptanceBatchUseCase；
- Provider API。

`acceptanceDomainWrites=0` 不代表完全零写入；Apply 可能写 private files 和 schema。所有 mutation 分字段记录。

## Consequences

### Positive

- 减少手工命令顺序错误；
- 正式数据不会轻易进入 Git；
- migration 有一致且可验证的 SQLite backup；
- partial migration 不会被误报成功；
- Provider 缺失不阻止本地准备；
- 运行结果可作为作品集工程证据。

### Negative

- 当前只支持 SQLite；
- 需要操作者确认 Backend stopped；
- 不自动 restore；
- staging 成功后 backup 失败会留下可复用 staged file；
- Receipt 包含本地路径，只适合 private 使用；
- 无法检测另一个进程在确认后立即启动 Backend。

## Alternatives rejected

### 文档中给出 cp + alembic 命令

拒绝：无法验证顺序、WAL、backup integrity、post revision 和执行证据。

### 自动在 Readiness 中升级 migration

拒绝：Readiness 必须保持 read-only，不能把检查命令变成隐式 mutation。

### 普通复制 SQLite 文件

拒绝：可能遗漏 WAL 中数据，且无法证明一致快照。

### migration 失败后自动 restore

拒绝：可能覆盖失败现场或在连接仍存在时造成进一步损坏。恢复必须是独立、明确的后续动作。

### 自动配置 Provider 和 Key

拒绝：凭据所有权和成本决策属于操作者，不应由项目代码猜测。

## Verification

- Plan zero-mutation tests；
- dataset stage hash/idempotency tests；
- SQLite backup integrity/data/revision test；
- symlink escape tests；
- backup-failure-before-migration test；
- partial migration failure receipt test；
- actual Alembic 0010→Head integration test；
- source boundary test；
- full Backend/Web/Collector regression。

## Revisit when

- 数据库迁移到 PostgreSQL；
- 需要 production deployment migration；
- 需要自动 restore/rollback；
- 需要检测运行中的 Backend；
- 需要加密或签名 Receipt；
- 需要云端私有数据存储。
