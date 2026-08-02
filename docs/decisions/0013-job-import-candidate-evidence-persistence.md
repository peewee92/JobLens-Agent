# ADR-0013 · Job Import Candidate 证据持久化

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0007、ADR-0009、ADR-0012、P0-1 Job Data Foundation

## Context

Collector report 同时包含：

```text
jobs        最终进入 Job Pool 的岗位
candidates  分类过程中的完整候选集合
```

此前 Backend 已完整读取 `candidates`，但只保存 `candidateCount`。导入完成后，被淘汰候选、pending detail 状态、Collector decision 和未知字段都会丢失，无法复现筛选过程或在规则升级后重新分析。

Candidate 不能直接创建成 Job：其中包含 rejected、incomplete 和 duplicate 记录。把 candidate 混入 Job Pool 会污染用户看到的岗位集合。

## Decision

新增不可变表：

```text
job_import_candidates
```

关系：

```text
JobImport 1 ───── N JobImportCandidate
```

每行保存：

- 原始 `candidate_raw` JSON；
- 原数组位置 `candidate_index`；
- best-effort 投影：keep / decision / pendingDetail / sourceJobId / URL / title / company；
- 创建时间。

关键规则：

1. 所有 candidate 都保存，包括字符串和 JSON null；
2. 结构化投影失败不丢弃 raw；
3. `(import_id, candidate_index)` 唯一；
4. candidates 与 Job/Source/Item 使用同一个 Unit of Work；
5. 致命导入错误会一起 rollback；
6. 重复导入创建新的 candidate snapshot，不做全局去重；
7. 删除 JobImport 时数据库级联删除 candidates；
8. 普通 API 不返回 `candidateRaw`。

审计详情新增脱敏汇总：

```text
candidateSummary.total
candidateSummary.kept
candidateSummary.rejected
candidateSummary.unknown
```

汇总通过批次详情查询中的相关子查询获得，详情仍保持两条外层 SELECT：一条批次（含汇总）、一条 items。

## Consequences

### Positive

- Collector 筛选过程可复现；
- 未来规则调整可基于原始 candidate 重新分析；
- rejected candidates 不污染 Job Pool；
- raw 与公开 API 继续隔离；
- 审计详情可以快速展示候选分布。

### Cost / Limits

- 数据量会明显增加；
- 当前未提供 candidate 列表或 raw 查询 API；
- 尚未设计压缩、对象存储或 retention policy；
- candidate 与最终 Job 没有直接 FK 对应；
- 结构化投影字段只是诊断索引，不是新的事实来源。

## Verification

必须由测试证明：

- Migration 0002 可升级、单独回退到 0001、再回退 base；
- 未知字段、字符串和 JSON null 原样保存；
- 重复导入生成独立 candidate snapshot；
- candidate 不增加 Job 数量；
- fatal conflict 时 candidates 全部 rollback；
- 删除 import 时 candidates 级联删除；
- 审计 API 返回正确 summary，但不返回 candidate raw；
- ORM metadata 与 Alembic 无漂移。
