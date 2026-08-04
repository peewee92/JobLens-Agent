# P0-3B-3H 实施计划｜Requirement Local Live Bootstrap

## 1. 当前真实功能

本切片实现：

> 在真实 Requirement Provider 调用前，以显式 Plan/Apply 两阶段安全准备本地正式数据和 SQLite schema，并在完成后重新运行 Readiness。

流程：

```text
formal 20-JD dataset
→ formal preflight
→ plan only（默认，零 operational mutation）
→ explicit --apply
→ stage dataset into data/private
→ verified SQLite online backup
→ explicit Alembic upgrade
→ post-upgrade revision + integrity verification
→ rerun live Readiness
→ operator later runs 1–3 Provider Canary manually
```

这不是 Provider Runner，也不是自动恢复系统。

## 2. 学习目标

本次掌握的最小知识：

- Plan/Apply 两阶段命令；
- SQLite 在线备份与普通文件复制的区别；
- migration attempt 与 migration success 的区别；
- fail-closed 顺序；
- 幂等数据 staging；
- 文件 Hash、数据库 integrity 和 Alembic revision 的证据职责；
- 私有目录与符号链接逃逸；
- 为什么自动 restore 不是默认安全行为；
- local preparation ready 与 Provider/model quality ready 的区别。

## 3. 风险判断

### 业务风险：高

- 未备份就升级本地真实数据库；
- Backend 运行时执行 SQLite migration；
- 普通文件复制遗漏 WAL 中的已提交数据；
- 数据文件误写入 Git 跟踪目录；
- 备份损坏但仍继续 migration；
- migration 部分执行后仍显示成功；
- migration 完成后不核对 revision；
- 本地准备完成被误认为模型已经可用；
- 自动 restore 覆盖 migration 失败后的诊断现场。

### 学习风险：高

- 把“有备份文件”误认为“备份可恢复”；
- 把 `command.upgrade()` 返回误认为迁移完成；
- 把 Plan 成功误认为 Apply 已执行；
- 不区分 schema writes 与 Acceptance domain writes；
- 不理解 SQLite WAL/online backup；
- 把 Provider 缺失当成数据库准备失败。

## 4. 核心能力分工

### 学习者必须先完成

1. 手写以下顺序并解释为什么不能交换：

```text
validate dataset
→ stage private copy
→ backup SQLite
→ verify backup
→ attempt migration
→ verify live DB
→ rerun readiness
```

2. 预测并回答：
   - 备份成功但 migration 失败，是否继续？
   - 为什么不默认自动 restore？
   - Provider 未配置，能否先完成本地 DB 准备？
   - 为什么 `cp joblens.db backup.db` 不足以证明一致备份？
   - Plan 成功是否意味着 local preparation 已发生？
3. 真实执行时亲自确认 Backend 已停止。
4. 真实执行后亲自核对 Receipt 的 backup hash、revision 和 readiness blockers。
5. Provider 配置和 Canary 判断仍由学习者完成。

### Agent 可以完成

- Plan/Apply CLI；
- formal dataset preflight 复用；
- deterministic private destination；
- SHA-256 staging verification；
- SQLite online backup；
- backup integrity/revision verification；
- explicit Alembic upgrade；
- post-upgrade verification；
- secret-free Receipt；
- tests、ADR、学习记录和 Demo。

## 5. 事实、推断、假设和未知

### 已确认事实

- 当前本地数据库 revision 为 `20260803_0010`；
- 当前 code head 为 `20260804_0013`；
- Provider 为 disabled；
- Model 与 API Key 未配置；
- DevSpace 中没有正式 20-JD 文件；
- `data/private/` 已被 `.gitignore` 排除；
- Readiness、Session Manifest、Canary Workbench 已存在。

### 推断

- 下一真实阻塞不再是业务代码，而是本地数据和 schema 准备；
- 数据 staging 与 DB migration 可以在 Provider 未配置时先完成；
- migration 必须在显式 mutation 模式执行；
- SQLite online backup 比文件复制更适合可能存在 WAL 的数据库。

### 假设

- 当前 MVP 使用本地 SQLite；
- 操作者能在 Apply 前停止 Backend；
- 正式数据源由用户提供，项目不自动搜索个人目录；
- 私有运行文件允许保存在 `data/private/requirement-acceptance`。

### 未知

- 真实数据源最终路径；
- 当前 DB 是否由运行中的 Backend 占用；
- 真实 OpenAI Model 和 Key；
- migration 在真实 DB 上的耗时；
- 真实 Canary 成本、延迟和质量；
- 是否最终需要自动 restore 或人工 restore 工具。

## 6. 用户价值假设

> 一个能在真实调用前可重复、安全地准备数据和 DB 的 Bootstrap，可以减少本地环境漂移、数据丢失和错误付费调用，使用户更快进入真正有价值的人工 Canary 判断。

本切片只验证“安全准备机制可运行”，尚未验证它是否显著减少真实操作时间。

## 7. 完成标准

### 工程完成标准

1. 默认 Plan 不 stage、不 backup、不 migration、不调用 Provider；
2. 正式数据必须先通过现有 formal preflight；
3. private root 只能位于项目 `data/private`；
4. symlink 不能让 dataset/backup 逃逸 private root；
5. dataset staging 必须校验 byte count 和 SHA-256；
6. 相同 staged dataset 可复用，不同内容禁止覆盖；
7. pending migration 的 Apply 必须显式确认 Backend stopped；
8. migration 前必须创建 SQLite online backup；
9. backup 必须通过 `PRAGMA integrity_check` 并保存 source revision；
10. backup 失败时 migration 不得开始；
11. migration attempt 和 success 必须分开记录；
12. migration 后 live DB revision 必须等于 dynamic head；
13. migration 后 live DB integrity 必须为 `ok`；
14. Apply 后自动重跑 Readiness；
15. Receipt 只能写入 private root；
16. CLI 不包含 Provider、Import 或 Acceptance domain execution；
17. 不自动 restore；失败时保留 verified backup path。

### 学习完成标准

学习者能不用看代码解释：

- SQLite backup API 为什么优于普通复制；
- Plan、Attempted、Applied 三种状态；
- 为什么 Provider blocker 不阻止 schema bootstrap；
- 为什么 migration 失败后不默认自动恢复；
- Hash、integrity、revision 分别证明什么；
- 为什么 `--confirm-backend-stopped` 是声明，不是系统检测。

### 作品集完成标准

可展示：

- fail-closed sequence；
- online backup + integrity；
- actual Alembic 0010→Head integration test；
- symlink/private-data boundary；
- secret-free bootstrap Receipt；
- migration partial-failure evidence。

不得描述为：

- 已执行真实生产数据库迁移；
- 已具备自动灾难恢复；
- 已通过真实模型质量验收。

### 用户价值完成标准

只有当真实正式数据、真实本地 DB 和真实 Provider 环境完成一次操作，且用户确认过程比手工命令更安全、更清楚，价值假设才算验证。本轮仍为工程准备证据。

## 8. 最小知识

### 8.1 Plan 不等于 Apply

```text
planValidated=true
applyExecuted=false
localPreparationSucceeded=false
```

计划合法只表示“可以做”，不表示“已经做”。

### 8.2 SQLite online backup

SQLite 可能处于 WAL 模式。直接复制主 `.db` 文件不一定包含 WAL 中的数据。`sqlite3.Connection.backup()` 通过 SQLite 自身生成一致快照。

### 8.3 三层验证

```text
file SHA-256
→ 文件字节没有变化

PRAGMA integrity_check
→ SQLite 内部结构一致

alembic_version == head
→ schema 版本达到代码期望
```

三者不可互相替代。

### 8.4 Attempted 不等于 Applied

Alembic/SQLite DDL 可能不是全事务。调用开始后失败，可能留下部分 schema 变化。因此：

```text
migrationAttempted=true
migrationApplied=false
```

必须保留 verified backup 供人工恢复。

### 8.5 不默认自动 restore

自动 restore 可能：

- 覆盖失败现场；
- 在进程仍持有连接时再次破坏 DB；
- 掩盖部分 migration 影响；
- 让操作者误以为恢复成功。

当前策略：停止、记录 backup path、由操作者检查后明确恢复。

## 9. 常见错误实现

```python
if db_revision != head:
    shutil.copyfile("joblens.db", "backup.db")
    command.upgrade(config, "head")
print("ready")
```

问题：

- 没有 formal dataset validation；
- 文件复制可能遗漏 WAL；
- 没有 backup integrity；
- 可能覆盖旧 backup；
- 没有 Backend stopped acknowledgement；
- 没有区分 migration attempted/applied；
- 没有 post-revision/integrity；
- 没有 Readiness；
- 无法证明未调用 Provider。

### 失败案例

1. 在线 DB 使用 WAL；普通复制只复制 `.db`；backup 缺少最近提交；
2. migration 0011 成功、0012 失败；脚本只记录“migration failed”；
3. 自动 restore 在 Backend 仍运行时覆盖 DB；
4. 敏感 20-JD 被写进 `docs/` 并误提交；
5. Plan 模式显示 `localPreparationSucceeded=true`，操作者误以为已备份升级。

## 10. Tickets（每个 1～3 小时）

| Ticket | 内容 | 证据 |
|---|---|---|
| T0 | 风险、预测、范围冻结 | 本文 |
| T1 | Bootstrap Plan 和 private path | pure tests |
| T2 | Dataset atomic staging | hash/idempotency tests |
| T3 | SQLite online backup | backup DB + integrity test |
| T4 | Plan/Apply CLI | CLI JSON tests |
| T5 | Explicit migration + post-check | real Alembic integration test |
| T6 | Failure Receipt | partial migration test |
| T7 | Path/secret/source boundary | symlink/source tests |
| T8 | ADR/学习记录/Demo | docs |
| T9 | Full regression + Diff review | command output |
| T10 | Real local Apply | blocked by real dataset/operator confirmation |

## 11. 完成标准到证据映射

| 标准 | 证据 |
|---|---|
| Plan 零 operational mutation | CLI test + filesystem/DB assertions |
| formal dataset | existing preflight call |
| private path | CLI/private-root test |
| symlink escape | symlink failure test |
| staging verified | SHA-256 + byte test |
| backup consistent | backup DB query + integrity |
| backup before migration | failure injection call-order evidence |
| actual migration works | real 0010→Head test |
| attempt/applied distinct | partial migration failure JSON |
| post revision/integrity | apply test |
| readiness rerun | nested readiness JSON |
| no Provider/domain execution | source boundary test |
| Receipt private | receipt path test |
| no auto restore | partial DB remains + backup remains test |

## 12. 范围排除

- Provider call；
- API Key provisioning；
- automatic restore；
- PostgreSQL backup；
- cloud backup；
- queue/lease；
- production deployment migration；
- automatic Canary decision；
- Match/Ranking；
- multi-agent。

## 13. 尚未验证

- 真实 20-JD staging；
- 当前真实 `joblens.db` 0010→0013；
- Backend 是否实际停止；
- 真实 Provider Readiness；
- 真实恢复操作；
- 真实 Canary 与 20 人工决策。
