# ADR-0029｜Requirement Live Session Manifest

Status: Accepted

Date: 2026-08-04

## Context

Requirement Acceptance 真实验收跨越：

```text
Readiness
→ 1–3 live Canary
→ human continue/stop
→ resumable extraction
→ 20-case Manual Review Batch
→ 20 human decisions
```

一次业务验收会执行多条命令，并持续数小时或数天。仅依赖终端历史和聊天记录会导致：

- 同一 Session 被误拆成多个实验；
- 不同 Dataset/Model/Reviewer 被错误合并；
- Command、Run、Trace、Review 和 Batch 证据难以关联；
- 为追求可追溯性而复制 Secret、完整 JD 或 Raw Trace；
- 直接覆盖 JSON 时留下半文件。

Readiness Gate 已能判断下一安全动作，但还缺少一个可持久交接的、隐私受控的运行索引。

## Decision

新增 `requirement-acceptance-session-v1` JSON Manifest，由 Readiness CLI 通过：

```text
--session-manifest <path>
```

选择性写出。

### 1. Session Identity

稳定 Session ID 由以下字段的 canonical JSON SHA-256 生成：

```text
datasetFingerprint
reviewer
title
provider
model
extractorVersion
promptVersion
```

格式：

```text
reqacceptsession_<first-32-hex>
```

以下字段不进入身份：

```text
manifest generatedAt
requested maxNewExtractions
attemptedCalls
blockers
runId
batchId
```

理由：它们属于 Invocation 或 Session 状态，而不是业务 cohort 身份。

### 2. Manifest 是可更新状态快照，不是不可变审计日志

相同 Session 可以多次覆盖同一目标 Manifest，以反映：

```text
blocked
ready_for_provider_execution
awaiting_human_canary_review
stopped
awaiting_twenty_case_review
```

不可变业务事实仍由数据库中的 Run、Extraction、Trace、Canary Review 和 Manual Review 记录提供。

### 3. Reference-only Evidence Pack

Manifest 保存：

- Run/Case/Job IDs；
- Extraction/Trace/Review/Batch IDs；
- description hash；
- Case status、attempt count、error code；
- frozen Canary Case 标记；
- readiness blockers；
- command hash；
- completion checklist。

默认不保存：

- API Key；
- 完整 JD；
- Raw Trace Output；
- Human Review Notes 正文。

Review Notes 仅保存 SHA-256 和字符数，支持后续同一私有来源的完整性比对，不把正文扩散到 Manifest。

### 4. Local path is operational but not public-safe

Manifest 保存数据集绝对路径以支持本地复现，并明确：

```text
containsLocalDatasetPath = true
publicPortfolioSafeWithoutPathRedaction = false
```

公开作品集前必须删除或重写路径。

### 5. Atomic file write

写入流程：

```text
unique temp in target directory
→ write
→ flush
→ fsync
→ atomic replace target
→ cleanup temp on error
```

同目录保证 replace 不跨文件系统。

这防止半文件，但不解决多个 writer 的业务级 lost update。当前本地单用户阶段不引入锁服务。

### 6. No new side effects

Manifest 导出：

```text
DB writes = 0
Provider calls = 0
```

它不自动迁移数据库、不配置 Provider、不触发 Extraction、不提交人工决策。

### 7. Match remains blocked

Manifest 中：

```text
allTwentyHumanDecisionsCompleted = null
modelQualityApproved = null
matchPhaseAllowed = false
```

直到真实 20 Case Review 和显式质量结论完成，不得把 Manifest 或 Batch creation 当成 Match 放行证据。

## Consequences

### Positive

- 多次命令共享稳定 Session Identity；
- Readiness、Run、Trace、Review 和 Batch 可被一份文件索引；
- Secret/JD/Raw Trace 默认不扩散；
- blocked 状态也能形成明确交接材料；
- 原子写入避免半 JSON；
- 作品集可展示真实工程治理结构。

### Negative

- Manifest 本身可被覆盖，不是 append-only audit log；
- 包含本地路径，公开前要脱敏；
- Notes hash 无法证明 Reviewer 判断正确；
- 没有数字签名或可信时间戳；
- 多进程同时写同一文件仍可能最后写入者覆盖；
- Manual Review 是否全部完成目前仍是未知值。

## Alternatives rejected

### Use timestamp as Session ID

拒绝。每次 Invocation 都产生新身份，破坏同一 Run 的证据链。

### Use database Run ID as Session ID

拒绝。Run 只有在 Import 后存在；blocked readiness 阶段仍需要身份，而且 Session identity 应由业务 cohort 决定。

### Dump full evidence into one JSON

拒绝。会扩大 JD、Trace 和 Notes 的敏感数据面，且复制数据可能与数据库事实漂移。

### Add a new database Session table

本切片拒绝。当前需求是零写入的运行交接产物；数据库不可变事实已由 Run/Review 等表承担。

### Add distributed file locking

本切片拒绝。当前本地单用户 MVP 不需要引入锁服务；并发冲突作为明确未验证边界保留。

## Verification

- deterministic identity tests；
- changed-model identity test；
- privacy/redaction assertions；
- frozen Canary evidence assertions；
- atomic writer filesystem test；
- CLI Manifest output test；
- Backend full regression；
- Web/Collector regression；
- `git diff --check`。

## Revisit when

- Manifest 进入团队共享或 CI artifact；
- 需要 append-only history；
- 需要签名、可信时间戳或不可抵赖审计；
- 多个 worker 会更新同一个 Session；
- Manual Review completion 需要进入自动化 release gate。
