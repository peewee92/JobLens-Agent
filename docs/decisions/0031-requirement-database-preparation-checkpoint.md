# ADR-0031｜Requirement Database Preparation Checkpoint

- Status: Accepted
- Date: 2026-08-05
- Scope: local SQLite operational preparation for Requirement Acceptance

## Context

Requirement Acceptance 已具备 Preflight、Run、Canary Gate、Web Workbench、Readiness、Session Manifest 和 Guarded Local Bootstrap，但真实本地数据库仍停在 `20260803_0010`，代码要求 `20260804_0013`。

原 Bootstrap 将正式 Dataset staging 和数据库 Migration 绑定在同一命令中。由于正式 20-JD 尚未进入 DevSpace，这种绑定会让一个可以独立解除的数据库 blocker 长期无法推进。

数据库 Migration 还存在崩溃恢复问题：

- Backup 已完成但 Migration 未开始；
- Migration 已开始但进程崩溃；
- Migration 已到 Head，但最终 Receipt 未写入；
- Receipt 与数据库 Revision 发生漂移。

## Decision

新增独立、可恢复的 SQLite Database Preparation Checkpoint。

### Stable identity

Checkpoint ID 基于：

```text
absolute database path
Alembic target head
```

不包含时间戳、Provider、Dataset、调用预算或 API Key。

### State machine

```text
planned
→ backup_verified
→ migration_attempted
→ applied
```

`failed` 保留最后已知阶段和错误证据。

### Persistence order

1. 创建 SQLite Online Backup；
2. 校验 Backup SHA-256、Byte Count、Integrity、Revision；
3. 原子写入 `backup_verified` Receipt；
4. 原子写入 `migration_attempted` Receipt；
5. 执行 Alembic Upgrade；
6. 校验 Live Revision、Integrity 和 Schema；
7. 原子写入 `applied` Receipt。

### Recovery rules

- `backup_verified + source revision`：可以继续 Migration；
- `failed + migration.attempted=false + verified backup + source revision`：失败发生在 Migration 前，可重新验证 Backup 后继续；
- `migration_attempted`，或 `failed + migration.attempted=true` 且未到 Head：禁止自动重试；
- `migration_attempted/failed + target head`：验证 Backup 和 Live DB 后收敛为 `applied`；
- `applied + non-target revision`：视为 Drift，禁止自动修复。

### Backup semantics

Backup 是显式补偿证据，不触发自动 Restore。

Restore 会覆盖当前数据库，因此需要独立命令、独立确认和单独 ADR，不属于本切片。

### Security and privacy

- Backup 和 Receipt 只能位于 Git 忽略的 `data/private` 下；
- Apply 时再次解析路径，阻止符号链接逃逸；
- Receipt 不包含 API Key、JD、Trace Raw Output 或 Provider Payload；
- CLI 不调用 Provider，不创建 Acceptance Domain Records。

## Alternatives considered

### 1. 继续等待正式 Dataset，再使用原 Bootstrap

拒绝。数据库 blocker 与 Dataset blocker 可以独立解除，继续绑定只会延迟真实验收。

### 2. 每次 Migration 都创建新 Backup，不复用 Checkpoint

拒绝。无法区分重复执行，也无法恢复 Backup 后、Migration 前的中断。

### 3. Migration 失败后自动 Retry

拒绝。SQLite 非事务 DDL 可能留下部分 Schema；旧 Revision 不足以证明数据库未变化。

### 4. Migration 失败后自动 Restore

拒绝。Restore 本身是高风险覆盖操作，会破坏故障现场并可能覆盖迁移后的新数据。

### 5. 只检查 Alembic Revision

拒绝。Revision 不能替代 Backup Integrity、Live Integrity、Schema Presence 和数据保留证据。

## Consequences

### Positive

- 数据库 blocker 可独立解除；
- 同一目标 Migration 有稳定操作身份；
- 崩溃后可以基于 Receipt 和数据库事实恢复；
- 已尝试但不确定的 Migration 不会被自动重试；
- 后续 Canary 可基于已到 Head 的真实数据库运行。

### Negative

- 增加一个私有 Receipt 文件；
- 操作者仍需真实确认 Backend 已停止；
- 不提供自动 Restore；
- 本地路径参与 Checkpoint Identity，迁移项目目录会产生新 Checkpoint ID。

## Verification

- 14 个 Database Checkpoint 定向测试；
- 真实 Alembic 0010→0013 集成测试；
- 本地真实 DB 已升级到 0013；
- Backup 保持 0010，Hash 与 Receipt 一致，Integrity 为 `ok`；
- Live DB Integrity 为 `ok`；
- 新表和 `description_snapshot` 列存在；
- 第二次 Apply 不创建新 Backup、不重复 Migration；
- Backend 全量、Web、Collector 与契约回归通过。
