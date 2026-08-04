# P0-3B-3I｜Requirement Database Preparation Checkpoint 实施计划

状态：已实施并在本地真实 SQLite 上完成一次 0010 → 0013 Migration

## 1. 当前真实项目功能

实现一个可恢复、可审计、幂等的本地 SQLite Migration Checkpoint，用于把 Requirement Acceptance 运行数据库从旧 Revision 安全准备到当前 Alembic Head，而不依赖正式 JD 数据、Provider 配置或 API Key。

```text
Plan
→ 创建/复用一致性备份
→ 验证 Backup SHA-256 / Integrity / Revision
→ 写入 backup_verified Receipt
→ 写入 migration_attempted Receipt
→ Alembic upgrade head
→ 验证 Live Revision / Integrity / Schema
→ 写入 applied Receipt
```

该功能不导入 Job，不创建 Acceptance Run，不调用 Provider。

## 2. 业务风险与学习风险

### 业务风险：高

- Migration 前没有可靠备份；
- SQLite WAL 数据未进入普通文件复制；
- 进程在备份后或 Migration 后崩溃；
- 上次 Migration 部分执行后被自动重试；
- Receipt 与真实数据库状态漂移；
- 备份被篡改后仍被复用；
- 数据库已到 Head，但最终 Receipt 未写入；
- 本地准备成功被误认为模型质量通过。

### 学习风险：高

- 把 Retry 当成所有失败的默认答案；
- 把 Alembic Revision 当成完整数据库正确性的唯一证据；
- 不区分 operation identity 与 invocation identity；
- 不理解 backup 是补偿证据，不是自动回滚；
- 把“脚本返回 0”当成唯一完成证据。

## 3. 人与受管理 Agent 的职责边界

### 学习者必须掌握

1. 画出 `planned → backup_verified → migration_attempted → applied` 状态机；
2. 解释为什么 `migration_attempted/failed + old revision` 不能自动重试；
3. 解释为什么 `database already at head + incomplete receipt` 可以根据数据库事实收敛；
4. 判断何时需要 Restore，何时只需补写 Receipt；
5. 检查真实 Backup、Receipt、Revision 与 Schema 证据；
6. 不把数据库准备当作 Provider 或模型质量结论。

### Agent 可完成

- 状态机、Receipt 和稳定 Checkpoint ID；
- SQLite Online Backup；
- Backup Hash、Integrity 和 Revision 校验；
- Alembic 运行入口；
- Crash recovery 和 fail-closed gate；
- 测试、ADR、CLI 契约、学习材料；
- 独立 Diff 审查与实际本地 Migration。

## 4. 事实、推断、假设、未知项

### 已确认事实

- 实施前本地 DB Revision 为 `20260803_0010`；
- 代码 Alembic Head 为 `20260804_0013`；
- 没有 Backend 进程或文件持有者；
- Provider、Model、API Key 未配置；
- 正式 20-JD 文件尚未进入 DevSpace；
- 实际 Migration 已完成到 `20260804_0013`；
- Backup 仍为 `20260803_0010`，Integrity 为 `ok`；
- Live DB Integrity 为 `ok`；
- 新 Acceptance 表和 `description_snapshot` 列已存在；
- 真实数据库中的既有核心表计数迁移前后未变化；
- 第二次 Apply 没有创建第二份 Backup。

### 推断

- 数据库环境 blocker 已解除；
- 下一阶段不再需要为数据库 Migration 编写额外说明层；
- 后续主要 blocker 是正式数据路径、Provider、Model、Key 和人工判断。

### 假设

- 当前是本地单用户 SQLite MVP；
- `--confirm-backend-stopped` 由操作者对真实环境负责；
- 私有备份和 Receipt 保存在 Git 忽略目录；
- 自动 Restore 不属于当前切片。

### 未知项

- 正式 20-JD 的最终 DevSpace 私有路径；
- 真实 Provider 和 Model；
- 真实 Canary 的 Token、延迟与错误率；
- 是否需要独立 Restore 命令；
- 多进程或团队环境的分布式 Migration Lock。

## 5. 四类完成标准

### 工程完成标准

- Plan 模式零写入；
- Checkpoint ID 对同一 DB + Head 稳定；
- Apply 前要求 Backend stopped acknowledgement；
- Backup 使用 SQLite Online Backup；
- Backup 必须通过 SHA-256、Byte Count、Integrity、Revision 四重校验；
- Backup 验证后立即持久化 Receipt；
- Migration 前持久化 `migration_attempted`；
- Migration 后验证 Revision、Integrity、Schema；
- Migration 失败记录 `failed`，不自动 Restore；
- 已尝试但未到 Head 时禁止自动 Retry；
- DB 已到 Head、Receipt 未完成时可恢复为 `applied`；
- 重跑 Applied Checkpoint 不新增 Backup、不重复 Migration；
- Provider Calls=0；
- Acceptance Domain Writes=0。

### 学习完成标准

学习者能独立解释：

- operation identity 为什么不含时间戳；
- `backup_verified` 与 `migration_attempted` 的安全差异；
- 为什么 old revision 不能证明没有部分 DDL；
- 为什么到 Head 后可以基于 DB facts 恢复 Receipt；
- Hash、Integrity、Revision、Schema 各自证明什么；
- 为什么不自动 Restore。

### 作品集完成标准

可演示：

- 只读 Plan；
- 真实 SQLite Online Backup；
- 0010→0013 Migration；
- Checkpoint Receipt；
- Crash recovery；
- Tampered Backup Gate；
- Inconclusive Migration No-Retry Gate；
- Idempotent Rerun；
- Provider/Domain 零调用边界。

不能声称：

- 已完成真实 Requirement 模型质量验收；
- 已实现生产级分布式 Migration；
- 已实现自动灾难恢复。

### 用户价值假设

> 把数据库准备变成一个有稳定身份、可恢复状态和多重证据的 Checkpoint，可以减少人工迁移时的数据损坏、重复执行和错误判断，并让后续真实 Canary 不再被本地 Schema 漂移阻塞。

本轮真实本地执行支持该假设，但还需要后续完整 Live Acceptance 流程验证最终业务价值。

## 6. 当前切片最小知识

### Operation Identity

Checkpoint ID 只包含：

```text
database absolute path
migration target head
```

不包含：

```text
execution timestamp
backup timestamp
Provider
API Key
JD dataset
```

因此同一次目标 Migration 重跑会找到相同 Receipt。

### Crash Recovery

```text
backup_verified + old revision
→ 可以继续 Migration

failed + migration.attempted=false + verified backup + old revision
→ 失败发生在 Migration 前，可重新验证 Backup 后继续

migration_attempted 或 failed + migration.attempted=true + old revision
→ 可能有部分 DDL，禁止自动重试

migration_attempted/failed + target head
→ DB 已完成，验证 Backup/Integrity 后收敛为 applied
```

### Evidence Layers

| 证据 | 证明内容 |
|---|---|
| Backup SHA-256 | Backup 字节未变化 |
| Backup Integrity | Backup SQLite 结构完整 |
| Backup Revision | Backup 对应预期起始 Schema |
| Live Revision | Alembic 已到目标版本 |
| Live Integrity | 迁移后 SQLite 结构完整 |
| Schema Presence | 预期新表、新列真实存在 |
| Data Counts | 选定既有表数据未意外变化 |
| Receipt | 操作阶段、引用和故障事实 |

## 7. 先预测再解释

学习者应先预测：

1. Migration 已到 Head，但进程未写最终 Receipt，重跑应该做什么？
2. Receipt 是 `migration_attempted`，DB 仍是 old revision，是否可以直接 Retry？
3. Backup Hash 正确但 Integrity 失败，能否继续？
4. Receipt 已 `applied`，DB 却回到 old revision，应如何处理？

正确解释见学习记录。

## 8. 常见错误实现与失败案例

```python
if current_revision != head:
    copy_database()
    alembic_upgrade_head()

write_json({"done": True})
```

问题：

- 没有稳定 operation identity；
- 没有阶段 Receipt；
- 没有 verified backup；
- Crash 后不知道应继续还是恢复；
- 部分 DDL 后可能自动重试；
- 没有 Live Integrity/Schema 检查；
- `done=true` 无法解释实际状态。

失败案例：

```text
backup verified
→ Receipt 写 migration_attempted
→ 0011 成功
→ 0012 部分 DDL 后进程崩溃
→ alembic_version 仍显示 0011 或旧值
```

正确行为：停止自动重试，保留 verified backup，让操作者检查并显式 Restore/Repair。

## 9. 1～3 小时 Tickets

| Ticket | 预计 | 结果 |
|---|---:|---|
| T0 风险、状态机、预测 | 1h | 完成 |
| T1 Checkpoint ID 与 Receipt Contract | 1–2h | 完成 |
| T2 Verified Backup Resume | 1–2h | 完成 |
| T3 Migration Attempt/Applied 状态 | 1–2h | 完成 |
| T4 Crash Recovery / No-Retry Gate | 2h | 完成 |
| T5 CLI Plan/Apply | 1–2h | 完成 |
| T6 真实 Alembic 集成测试 | 1h | 完成 |
| T7 真实本地 0010→0013 Apply | 1h | 完成 |
| T8 Diff 审查与全仓库回归 | 1–2h | 完成 |
| T9 ADR、学习记录、Demo | 1–2h | 完成 |

## 10. 完成标准与证据映射

| 标准 | 证据 |
|---|---|
| Plan 零写入 | CLI 测试 + 私有目录不存在断言 |
| Checkpoint ID 稳定 | Pure-function test |
| Backup 一致完整 | Backup Hash/Byte Count/Integrity/Revision |
| Migration 前失败可恢复、尝试后失败不自动 Retry | Pre-attempt recovery + failure second-run tests |
| Crash 后到 Head 可恢复 | Recovery test |
| 中间 Revision 停止 | Unexpected revision test |
| 真实 Migration 可运行 | Real Alembic integration test |
| 本地环境已升级 | Live DB `alembic_version=20260804_0013` |
| 新 Schema 存在 | 表和列查询 |
| 既有数据未变化 | 迁移前后选定表 COUNT |
| Idempotent | 第二次 Apply + 单一 Backup 文件 |
| 无 Provider/Domain 写入 | Source boundary test + CLI output |

## 11. 范围排除

- 正式 JD staging；
- Provider/Model/Key 配置；
- Provider 请求；
- Acceptance Run 创建；
- Canary Continue/Stop；
- 自动 Restore；
- PostgreSQL Migration；
- 分布式锁；
- Match。

## 12. 尚未验证

- Restore 命令与真实 Restore 演练；
- 进程级强制锁；
- 多 Writer 并发；
- 远程数据库；
- 正式数据与真实 Provider；
- 真实 20-case 人工质量结论。

## 13. 下一阶段

P0-3B-3J：Formal Dataset Private Handoff + Credential-backed Canary

```text
正式 20-JD 进入 data/private
→ Preflight / Readiness / Session Manifest
→ 配置 Provider / Model / Key
→ 1～3 条真实 Canary
→ 学习者人工检查
→ Continue 或 Stop
```
