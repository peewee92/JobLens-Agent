# P0-3B-3H 学习记录｜Requirement Local Live Bootstrap

## 1. 学习目标

本切片学习的不是“怎么跑一条 Alembic 命令”，而是：

> 如何把一次高风险的本地数据与 schema 准备，设计成可计划、可验证、失败即停止、且不会被误认为模型已通过的工程流程。

需要掌握：

- Plan/Apply；
- online backup；
- fail-closed；
- migration attempted/applied；
- private path boundary；
- evidence receipt；
- local readiness 与 model quality 的区别。

## 2. 先预测

先不看答案，写下你的判断：

1. Plan 验证成功，`localPreparationSucceeded` 应该是 true 还是 false？
2. Provider=disabled 时，是否可以先 stage 数据和升级 DB？
3. SQLite 使用 WAL 时，直接复制 `.db` 有什么风险？
4. Backup 文件存在，为什么仍不能开始 migration？
5. `fileSha256`、`integrityCheck`、`alembicVersion` 各证明什么？
6. Migration 调用抛错后，为什么要记录 `migrationAttempted=true`？
7. 为什么不默认自动 restore？
8. `--confirm-backend-stopped` 是系统事实还是用户声明？
9. 为什么 Receipt 必须留在 `data/private`？
10. Local bootstrap 成功后，为什么仍不能自动进入 Match？

## 3. 最小知识

### 3.1 Plan 与 Apply

Plan 回答：

```text
现在能不能安全执行？
会改哪些文件？
会备份到哪里？
migration 是否需要？
```

Apply 回答：

```text
这些 mutation 是否真的发生？
验证是否通过？
下一步是什么？
```

正确状态：

```json
{
  "planValidated": true,
  "applyExecuted": false,
  "localPreparationSucceeded": false
}
```

### 3.2 SQLite backup API

SQLite 可能使用：

```text
joblens.db
joblens.db-wal
joblens.db-shm
```

只复制主文件可能漏掉 WAL 中已经提交的数据。`Connection.backup()` 由 SQLite 自身生成一致快照。

但 online backup 完成仍不等于可恢复，需要继续验证：

```text
PRAGMA integrity_check = ok
sourceRevision 被保存
file SHA-256 被保存
```

### 3.3 三种证据

| 证据 | 能证明 | 不能证明 |
|---|---|---|
| SHA-256 | 文件字节一致 | SQLite 逻辑结构正确 |
| integrity_check | DB 内部结构一致 | schema 与代码匹配 |
| alembic revision | schema 版本标识达到 Head | 业务数据语义正确 |

### 3.4 Fail-closed 顺序

```text
backup failed
→ migration must not start

migration failed
→ readiness must not run

post revision mismatch
→ localPreparationSucceeded=false
```

不能“尽量继续”，因为后续操作会让失败原因更难定位。

### 3.5 Attempted 与 Applied

SQLite 的 Alembic 日志会提示：

```text
Will assume non-transactional DDL
```

这意味着 migration 失败时可能已经执行部分 DDL。

因此 Receipt 必须区分：

```text
migrationAttempted=true
migrationApplied=false
```

不能只写一个 `migrationSuccess=false`。

### 3.6 不自动 restore

自动 restore 看似安全，实际上需要解决：

- 是否还有进程连接 DB；
- migration 是否留下旁路文件；
- 是否需要保留现场诊断；
- restore 自身如何验证；
- backup 是否应继续保留；
- 谁授权覆盖当前 DB。

当前最小安全策略：

```text
stop
→ preserve backup
→ expose backup path
→ human inspects
→ explicit recovery later
```

### 3.7 私有路径与 symlink

只检查字符串前缀不够：

```text
data/private/requirement-acceptance/datasets
```

可能是一个指向 `docs/` 的符号链接。

正确做法：

```text
resolve final destination
→ verify it is still relative to resolved private root
```

### 3.8 Provider blocker 与 Bootstrap blocker

Provider 未配置时：

```text
local data/schema preparation can still succeed
readiness.nextAction = fix_blockers
providerExecutionAllowed = false
```

二者不是同一个层次。

## 4. 实现结构

```text
local_bootstrap.py
├── bootstrap plan
├── deterministic private paths
├── dataset atomic stage
├── SQLite online backup
├── hash/integrity/revision
└── bootstrap errors

bootstrap_requirement_acceptance.py
├── formal preflight
├── plan/apply CLI
├── private path enforcement
├── backend-stopped acknowledgement
├── Alembic upgrade
├── post verification
├── readiness rerun
└── secret-free receipt
```

## 5. 常见错误实现

```python
if current_revision != head:
    shutil.copy("joblens.db", "backup.db")
    command.upgrade(config, "head")

print("environment ready")
```

错误点：

1. 复制可能遗漏 WAL；
2. backup 没有 integrity check；
3. 可能覆盖旧 backup；
4. 没检查 Backend 是否停止；
5. migration 失败可能已有 partial DDL；
6. 没有 post revision；
7. 没有 Readiness；
8. 把本地环境 ready 说成整体 ready；
9. 没有 private data boundary；
10. 没有执行证据。

## 6. 故障案例

### Case A：Backup 失败

```text
stage dataset succeeded
backup failed
migrationAttempted=false
migrationApplied=false
```

Staged dataset 可以保留并复用，因为它不是 DB mutation。

### Case B：Migration 部分执行后失败

```text
backupCreated=true
migrationAttempted=true
migrationApplied=false
live DB revision=partial
verifiedBackupPath=...old revision...
```

系统不自动 restore。

### Case C：Provider 未配置

```text
localPreparationSucceeded=true
readiness.workflowReady=false
readiness.nextAction=fix_blockers
providerCalls=0
```

### Case D：Symlink 逃逸

```text
data/private/.../datasets -> docs/
```

Resolved destination 不在 private root，Apply 被拒绝。

## 7. 测试证据

- deterministic plan；
- Plan zero mutation；
- stage atomic/idempotent/hash；
- mismatched staged file rejection；
- SQLite backup content/integrity/revision；
- non-SQLite rejection；
- symlink escape rejection；
- backup failure blocks migration；
- partial migration records attempted/not-applied；
- explicit backend-stopped gate；
- private Receipt gate；
- actual Alembic 0010→Head；
- no Provider/Import/domain code in CLI。

## 8. 面试问题

1. SQLite WAL 模式下为什么普通文件复制可能不可靠？
2. `Connection.backup()` 解决了什么？
3. 为什么 backup 后还需要 integrity check？
4. 为什么 migration status 要区分 attempted 和 applied？
5. 非事务 DDL 对错误恢复有什么影响？
6. 为什么不在 Readiness 中自动 migration？
7. 为什么 Provider 未配置不应阻止 DB bootstrap？
8. 如何防止敏感数据通过 symlink 写出 private 目录？
9. 为什么自动 restore 不是显然正确的默认行为？
10. 如何证明一个 CLI 没有调用 Provider？
11. Plan 模式应该如何表达“验证成功但未执行”？
12. 你会如何把该方案扩展到 PostgreSQL？

## 9. 5 分钟 Demo

### 第 1 分钟：展示 Plan

```bash
python -m scripts.bootstrap_requirement_acceptance formal.json \
  --reviewer will \
  --title "Real Requirement acceptance" \
  --max-new-extractions 3 \
  --json
```

指出：

```text
applyExecuted=false
localPreparationSucceeded=false
providerCalls=0
```

### 第 2 分钟：展示 private destination 与 backup plan

解释 fingerprint 文件名和 Git ignore。

### 第 3 分钟：运行测试

展示：

```text
backup failure → migration not started
partial migration → backup retained
```

### 第 4 分钟：展示真实 Alembic integration test

```text
0010 → 0013
integrity_check=ok
```

### 第 5 分钟：展示 Apply Receipt

说明：

```text
local preparation succeeded
Provider still disabled
nextAction=fix_blockers
```

强调没有调用模型。

## 10. 作品集表述

可写：

> 为本地 SQLite 上的付费 LLM 验收流程设计了 Guarded Bootstrap。命令采用 Plan/Apply 两阶段，先将正式数据以 Hash 校验方式原子写入 Git-ignored 私有目录，再通过 SQLite online backup、integrity check 和 Alembic revision 证据保护 migration；对 partial DDL 失败记录 attempted/applied 和 verified backup，不自动恢复，完成后重新运行 Provider Readiness。

不能写：

> 建成了生产级自动灾备和零停机 migration。

## 11. 学习验收问题

不用看代码回答：

1. Plan 成功为何不等于 local preparation succeeded？
2. Provider disabled 时哪些动作仍能做？
3. 普通复制 SQLite 的风险是什么？
4. Backup 文件存在还缺哪两类验证？
5. migrationAttempted 与 migrationApplied 为什么必须分开？
6. 为什么不自动 restore？
7. symlink escape 如何发生，如何阻止？
8. `--confirm-backend-stopped` 能证明 Backend 真停了吗？
9. Apply 成功后为什么还要跑 Readiness？
10. 当前还缺什么才能执行真实 Canary？
