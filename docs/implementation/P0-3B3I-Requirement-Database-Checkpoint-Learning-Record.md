# P0-3B-3I｜Requirement Database Preparation Checkpoint 学习记录

## 本轮最小知识

### 1. Checkpoint 不是日志文件

日志回答“发生过什么”，Checkpoint 回答“系统已经安全完成到哪一步，以及下一步能否继续”。

本轮状态：

```text
planned
→ backup_verified
→ migration_attempted
→ applied
```

`failed` 不会清空历史状态，而是保留 Backup、Attempt 和失败事实。

### 2. Operation Identity 与 Invocation Identity

一次命令运行是 Invocation；从一个 DB Head 升级到另一个 Head 是 Operation。

Checkpoint ID 使用：

```text
database absolute path + target migration head
```

它不使用运行时间，因此同一 Operation 重跑仍会定位到同一个 Receipt。

### 3. Retry 不是默认安全策略

只有下面的状态可以安全续跑：

```text
backup_verified + database still at source revision
```

因为 Receipt 已证明 Backup 完成，同时 Migration 尚未记录为 attempted。

下面状态不能自动 Retry：

```text
migration_attempted + database not at target head
failed + migration.attempted=true + database not at target head
```

SQLite DDL 可能部分执行，而 Alembic Revision 不一定能完整表达所有已发生变化。

若 `failed` 但 `migration.attempted=false`，并且 Receipt 已包含可重新验证的 Backup，则说明失败发生在 Migration 前，可以复用 Backup 后继续。

### 4. Database facts 可以修复 Receipt，但不能反过来

如果：

```text
Receipt = migration_attempted
DB Revision = target head
Live Integrity = ok
Verified Backup = valid
```

说明 Migration 很可能已完成，只是最终 Receipt 未写入。此时可把 Receipt 收敛为 `applied`，不用重复 Migration，也不用 Restore。

如果：

```text
Receipt = applied
DB Revision = old/intermediate
```

不能相信 Receipt 自动改数据库。应视为 Drift 并停止。

### 5. 四种证据的职责

- SHA-256：文件字节是否变化；
- SQLite Integrity：内部结构是否一致；
- Alembic Revision：Schema 版本标识；
- Schema Query：预期表和列是否真实存在。

任何单项都不能替代其余证据。

## 预测题与解释

### 预测 1

Migration 已到 Head，但进程在写最终 Receipt 前崩溃，重跑应该：

A. 再运行一次 Migration
B. 自动 Restore
C. 验证 Backup、Revision、Integrity 后补写 Applied Receipt

正确答案：C。

### 预测 2

Receipt 是 `migration_attempted`，DB 仍显示旧 Revision，能否直接 Retry？

正确答案：不能。旧 Revision 不足以证明没有部分 DDL。

### 预测 3

Backup Hash 正确但 Integrity Check 失败，能否继续？

正确答案：不能。Hash 只证明它没有变化，不证明文件本身是有效 SQLite。

### 预测 4

Provider 未配置，能否完成数据库 Preparation？

正确答案：可以。Provider 与 Schema Migration 是两个独立 blocker。

## 常见错误实现

```python
if db_revision != head:
    backup = shutil.copy("joblens.db", "backup.db")
    alembic_upgrade()

return {"success": True}
```

问题：

- 普通复制可能遗漏 WAL；
- 没有 Backup Integrity 和 Revision；
- 没有阶段 Checkpoint；
- Crash 后无法判断是否重试；
- 部分 DDL 后会重复执行；
- `success` 不包含可追溯证据。

## 本轮真实结果

实施前：

```text
DB Revision = 20260803_0010
Alembic Head = 20260804_0013
Backend process = none
DB file holder = none
```

实际执行：

```text
0010 → 0011 → 0012 → 0013
```

实施后：

```text
Receipt State = applied
Backup Revision = 0010
Backup Integrity = ok
Backup Hash matches Receipt = true
Live Revision = 0013
Live Integrity = ok
New Acceptance tables = present
description_snapshot = present
Second Apply new Backup count = 0
Provider Calls = 0
Acceptance Domain Writes = 0
```

## 独立 Diff 审查发现

### 1. Inconclusive Migration 被错误允许重试

初版把 `migration_attempted` 和 `failed` 当成可以复用 Backup 后继续 Migration。

修正：`backup_verified` 或 `failed + attempted=false + verified backup` 可以续跑；Attempted 或 `failed + attempted=true` 且未到 Head 时停止。

### 2. Failure Summary 丢失 Backup Reuse 事实

初版即使复用 Backup 后失败，也输出 `backupReused=false`。

修正：失败摘要保留真实复用状态。

### 3. Receipt 只在初始阶段检查路径

修正：每次写 Receipt 前重新 Resolve，并确认仍位于 Private Root。

## 面试问题

1. 为什么 Migration Checkpoint ID 不包含时间戳？
2. SQLite Online Backup 与普通文件复制有什么区别？
3. 为什么 `migration_attempted + old revision` 不能自动 Retry？
4. 什么情况下可以根据数据库状态补写 Applied Receipt？
5. 为什么 Revision=Head 仍要检查 Integrity 和 Schema？
6. Backup 是回滚机制还是补偿证据？为什么？
7. 为什么不自动 Restore？
8. 如何证明第二次运行是幂等的？
9. Checkpoint Receipt 应该包含哪些信息，不应包含哪些信息？
10. 本轮为什么可以在 Provider 未配置时继续推进？

## 参考回答要点

- Operation ID 必须跨 Invocation 稳定；
- Backup、Attempt、Apply 三个阶段要先后持久化；
- 非事务 DDL 使“Revision 没变”不能证明“什么都没发生”；
- DB facts 是最终事实来源，Receipt 是操作证据；
- 自动 Restore 是新的高风险写操作；
- 幂等必须由第二次真实运行和 Backup 数量证明。

## 5 分钟 Demo

### 第 1 分钟：展示 Plan

```bash
cd services/backend
.venv/bin/python -m scripts.prepare_requirement_acceptance_database --json
```

解释 Checkpoint ID、source、target、planned Backup 和零写入。

### 第 2 分钟：展示 Apply

```bash
.venv/bin/python -m scripts.prepare_requirement_acceptance_database \
  --apply \
  --confirm-backend-stopped \
  --json
```

解释 `backup_verified → migration_attempted → applied`。

### 第 3 分钟：展示证据

- Backup Revision=0010；
- Live Revision=0013；
- 两边 Integrity=ok；
- Backup Hash 与 Receipt 一致。

### 第 4 分钟：展示故障测试

- Tampered Backup；
- Inconclusive Previous Attempt；
- Crash After Migration Before Final Receipt。

### 第 5 分钟：展示幂等与边界

再次运行 Apply：

- 不新建 Backup；
- 不重复 Migration；
- Provider Calls=0；
- Acceptance Domain Writes=0。

## 自测问题

1. 什么证据证明 Backup 可用于人工恢复？
2. 为什么 `failed + old revision` 不能直接重试？
3. 为什么 `migration_attempted + target head` 可以恢复 Receipt？
4. 如果 Receipt 已 Applied 但 DB 不在 Head，应采取什么策略？
5. 本轮完成后，为什么仍不能开始 Match？
