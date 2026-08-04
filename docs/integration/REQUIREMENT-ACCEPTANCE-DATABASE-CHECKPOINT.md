# Requirement Acceptance Database Checkpoint CLI

Status: P0-3B-3I operational contract

## Goal

Prepare the local SQLite schema for live Requirement Acceptance independently from Dataset staging and Provider configuration.

The command must never:

- call an LLM Provider;
- import Jobs;
- create Requirement Acceptance Runs;
- submit Canary decisions;
- auto-restore the database.

## Plan command

```bash
cd services/backend
.venv/bin/python -m scripts.prepare_requirement_acceptance_database --json
```

Plan mode is read-only:

```text
providerCalls = 0
acceptanceDomainWrites = 0
applyExecuted = false
```

It reports:

- stable Checkpoint ID;
- database path;
- source Revision;
- target Alembic Head;
- whether Migration is needed;
- planned Backup path;
- stable Receipt path;
- blockers.

## Apply command

```bash
cd services/backend
.venv/bin/python -m scripts.prepare_requirement_acceptance_database \
  --apply \
  --confirm-backend-stopped \
  --json
```

`--confirm-backend-stopped` is required only when a Migration is pending.

The flag is an operator acknowledgement, not proof that no process is connected. Operational runbooks should additionally check process and file holders.

## Private root

Default:

```text
data/private/requirement-acceptance
```

Override:

```bash
--private-root /absolute/project/path/data/private/requirement-acceptance
```

The resolved path must remain under the project Git-ignored `data/private` directory.

## Stable Checkpoint identity

```text
checkpointId = sha256(
  absolute database path
  + target migration head
)
```

The identity intentionally excludes:

- invocation time;
- Backup timestamp;
- Provider and Model;
- API Key;
- Dataset;
- requested Provider budget.

## Receipt path

```text
data/private/requirement-acceptance/
  database-checkpoints/
    <checkpointId>.json
```

Receipt writes are atomic and checked against the private root at write time.

## State machine

```text
planned
→ backup_verified
→ migration_attempted
→ applied
```

Failure state:

```text
failed
```

### `planned`

No verified Backup exists in the Receipt.

### `backup_verified`

Backup has passed:

- SHA-256;
- Byte Count;
- SQLite `PRAGMA integrity_check`;
- source Alembic Revision.

This is the only incomplete state that may automatically continue Migration while the live database remains at the source Revision.

### `migration_attempted`

The attempt marker is persisted before Alembic begins.

If the live database is not at target Head, the command refuses automatic Retry because partial DDL may exist.

### `applied`

The live database has passed:

- target Revision check;
- SQLite Integrity check.

The operational run should separately verify expected new tables/columns when needed.

### `failed`

Failure details and last observed Revision are preserved.

- `migration.attempted=false` 且 Backup 可重新验证：说明失败发生在 Migration 前，可以续跑；
- `migration.attempted=true` 且 Live DB 未到 Head：下一次运行停止，要求显式检查、Restore 或 Repair。

## Crash recovery

### Backup done, Migration not attempted

```text
Receipt = backup_verified
DB = source revision
```

The command re-verifies and reuses the Backup, then continues.

### Migration reached Head, final Receipt missing

```text
Receipt = migration_attempted | failed
DB = target head
```

The command:

1. verifies the recorded Backup;
2. verifies Live DB Integrity;
3. marks Receipt `applied` with `recoveredAfterCrash=true`;
4. does not rerun Alembic;
5. does not restore the Backup.

### Failure before Migration attempt

```text
Receipt = failed
migration.attempted = false
verified Backup = valid
DB = source revision
```

The command re-verifies and reuses the Backup, then continues.

### Migration attempt is inconclusive

```text
Receipt = migration_attempted
or Receipt = failed with migration.attempted = true
DB != target head
```

The command returns exit code 2 and refuses automatic Retry.

## JSON output

Example applied result:

```json
{
  "schemaVersion": "requirement-acceptance-database-checkpoint/v1",
  "checkpointId": "reqacceptdb_<hash>",
  "state": "applied",
  "databasePath": "<private local path>",
  "sourceRevision": "20260803_0010",
  "currentRevision": "20260804_0013",
  "targetRevision": "20260804_0013",
  "migrationNeeded": false,
  "applyExecuted": true,
  "backupPath": "<git-ignored private path>",
  "backupVerified": true,
  "backupReused": false,
  "migrationAttempted": true,
  "migrationApplied": true,
  "recoveredAfterCrash": false,
  "integrityAfter": "ok",
  "receiptPath": "<git-ignored private path>",
  "blockers": [],
  "providerCalls": 0,
  "acceptanceDomainWrites": 0
}
```

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Plan valid or Apply verified complete |
| 2 | Unsafe/invalid state, blocked execution or failed operation |

## Completion evidence

A successful Apply is not proven by exit code alone. Required evidence:

- Receipt `state=applied`;
- Live DB `alembic_version=targetRevision`;
- Live DB Integrity=`ok`;
- Backup exists and matches Receipt SHA-256;
- Backup Integrity=`ok`;
- Backup Revision=`sourceRevision`;
- expected new schema is present;
- selected pre-existing data counts are preserved;
- idempotent rerun creates no additional Backup;
- Provider Calls=0;
- Acceptance Domain Writes=0.

## Security notes

The Receipt contains local filesystem paths and is not public-portfolio-safe without redaction.

It does not contain:

- API Key;
- Dataset contents;
- JD text;
- Provider payload;
- Trace Raw Output;
- Canary Review Notes.

## Relationship to other commands

```text
prepare_requirement_acceptance_database
→ bootstrap_requirement_acceptance
→ check_requirement_acceptance_readiness
→ prepare_requirement_acceptance
```

The Database Checkpoint removes only the local Schema blocker. It does not prove Dataset readiness, Provider readiness or model quality.
