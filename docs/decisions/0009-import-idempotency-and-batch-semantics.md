# ADR-0009 · Job Import 幂等与批次语义

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0007、ADR-0008、P0-1 Job Data Foundation

## Context

`ImportJobsUseCase` 需要把 Collector 报告转换为稳定的岗位数据，同时满足：

- 重复导入不能制造重复 Job / JobSource；
- 每次导入都必须保留独立审计记录；
- 单条格式问题不能阻止其他合法岗位；
- 持久化身份冲突不能被静默修复；
- 批次统计必须与逐条结果一致；
- 一次批次只允许一次事务提交。

## Decision

### 1. 幂等作用于稳定业务实体，不作用于导入审计

重复导入同一报告时：

```text
Job            不重复创建
JobSource      不重复创建
JobImport      每次创建新批次
JobImportItem  每次记录新的逐条结果
```

第一次命中为 `created`，后续再次观察同一稳定身份为 `updated`。

### 2. created / updated 由 Application Use Case 决定

决策顺序：

```text
canonical_key
→ source + source_job_id
→ source + normalized_source_url
```

- canonical Job 和 Source 都不存在：created；
- canonical Job 已存在，Source 同属该 Job：updated；
- canonical Job 已存在，Source 不存在：更新 Job 并新增 Source，updated；
- Source 已存在但 canonical Job 不存在，或两者指向不同 Job：身份冲突，整批 rollback。

Repository 只负责查询和持久化，不决定业务 outcome。

### 3. 批次统计不变量

完成的批次必须满足：

```text
received = created + updated + skipped
```

Adapter / Normalizer 的单条问题：

- 写入 `JobImportItem.outcome=error`；
- 计入 `skipped`；
- 错误详情进入 `JobImport.errors`；
- 其他合法岗位继续处理。

### 4. 一次批次只 commit 一次

流程：

```text
adapt / normalize
→ open Unit of Work
→ create JobImport
→ persist all items
→ verify counters
→ update summary
→ one commit
```

循环内只允许 Repository flush，不允许 commit。任何未预期异常或身份冲突都会退出 Unit of Work 并 rollback 整批新写入。

### 5. 无法信任的报告不创建批次

Envelope 无效或 Collector 版本不支持时，在打开 Unit of Work 前失败，不创建 `JobImport`。

## Consequences

### Positive

- 重复导入不会膨胀岗位池；
- 每次用户操作仍有可追溯审计记录；
- 批次汇总与逐条明细可相互校验；
- 身份冲突不会被自动错误合并；
- 多表写入保持原子性。

### Cost

- 即使报告内容完全相同，也会新增 Import 审计记录；
- 合法岗位再次出现会计为 updated，而不是 no-op；
- 身份冲突需要后续显式 repair / merge 流程处理。

## Not Decided Yet

- 并发导入同一岗位的锁与重试策略；
- 单条数据库错误是否通过 SAVEPOINT 继续；
- canonical key 版本升级后的 merge / re-key；
- changed / unchanged 的更细粒度 outcome。

## Verification

自动测试必须证明：

- 首次导入 created；
- 重复导入 Job/Source 不增长但新增审计批次；
- 单条坏数据进入 error + skipped；
- 身份冲突整批 rollback；
- 不支持版本不产生批次；
- 一个成功批次只调用一次 commit。
