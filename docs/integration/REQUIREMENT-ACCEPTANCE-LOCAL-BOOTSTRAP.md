# Requirement Acceptance Local Bootstrap CLI

Status: P0-3B-3H operational contract

## Goal

Safely prepare a formal Requirement acceptance dataset and local SQLite schema before any paid Provider call.

This CLI does not:

- import Jobs;
- create Acceptance Runs;
- call an LLM Provider;
- submit Canary decisions;
- restore a failed migration automatically.

## Plan command

```bash
cd services/backend
.venv/bin/python -m scripts.bootstrap_requirement_acceptance \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "Real Requirement acceptance" \
  --max-new-extractions 3 \
  --json
```

Plan mode is the default.

Expected semantics:

```json
{
  "mode": "plan",
  "planValidated": true,
  "applyExecuted": false,
  "localPreparationSucceeded": false,
  "providerCalls": 0,
  "acceptanceDomainWrites": 0
}
```

A valid plan means the operation is safe to attempt. It does not mean files were staged or migrations were applied.

## Apply command

When migration is pending, stop the Backend first and run:

```bash
cd services/backend
.venv/bin/python -m scripts.bootstrap_requirement_acceptance \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "Real Requirement acceptance" \
  --max-new-extractions 3 \
  --apply \
  --confirm-backend-stopped \
  --receipt ../../data/private/requirement-acceptance/receipts/bootstrap.json \
  --json
```

`--confirm-backend-stopped` is an operator acknowledgement. The command does not detect process state.

If the database already equals Alembic Head, dataset-only staging does not require this acknowledgement.

## Arguments

```text
dataset                         formal 20-JD Collector review JSON
--reviewer <text>               stable future Run owner
--title <text>                  stable future Run identity
--max-new-extractions <1-20>    passed only to post-bootstrap Readiness
--web-base-url <url>            used by Readiness navigation URLs
--private-root <path>           must resolve under project data/private
--apply                         perform local file/schema mutations
--confirm-backend-stopped       required for pending SQLite migration
--receipt <path>                must resolve under selected private root
--json                          machine-readable output
```

## Sequence

```text
1. load and validate formal dataset
2. build mutation-free plan
3. require explicit --apply
4. atomically stage dataset under data/private
5. create SQLite online backup if migration is pending
6. verify backup integrity and source revision
7. mark migrationAttempted=true
8. run Alembic upgrade head
9. mark migrationApplied=true only after upgrade returns
10. verify live revision=head
11. verify live integrity=ok
12. rerun Requirement Readiness using staged dataset
13. write optional private Receipt
```

## Private file layout

Default root:

```text
data/private/requirement-acceptance/
├── datasets/
│   └── formal-<datasetFingerprintPrefix>.json
├── backups/
│   └── joblens-<UTC>-<revision>.db
└── receipts/
    └── bootstrap.json
```

`data/private/` is Git-ignored.

The CLI resolves final dataset, backup and Receipt paths. Symlink escape outside the private root is rejected.

## Dataset staging

The staged file is verified using:

- byte count;
- SHA-256;
- atomic replace.

If the destination already exists:

- identical bytes are reused;
- different bytes cause a hard failure;
- existing content is never overwritten.

## SQLite backup

Backup uses:

```python
sqlite3.Connection.backup()
```

It does not use plain `cp`/`shutil.copyfile`.

The backup is accepted only after:

```text
PRAGMA integrity_check = ok
source alembic revision captured
SHA-256 captured
byte count captured
```

Existing backup paths are never overwritten.

## Migration status

Receipt fields are deliberately separate:

```json
{
  "migrationAttempted": true,
  "migrationApplied": false
}
```

This state is possible because SQLite/Alembic DDL may be non-transactional.

`migrationApplied=true` means the Alembic call returned successfully. Local preparation is still not successful until post-revision and post-integrity checks pass.

## Failure behavior

### Dataset validation failure

```text
exit 2
no stage
no backup
no migration
no Provider call
```

### Backup failure

```text
exit 2
migrationAttempted=false
migrationApplied=false
```

A successfully staged dataset may remain and can be reused.

### Migration failure

```text
exit 2
migrationAttempted=true
migrationApplied=false
verifiedBackupPath=<private path>
```

The CLI does not automatically restore. The operator must inspect the live DB and backup before an explicit recovery action.

### Post-verification failure

```text
exit 2
localPreparationSucceeded=false
verified backup retained
Provider not called
```

## Apply success example

```json
{
  "mode": "apply",
  "planValidated": true,
  "applyExecuted": true,
  "localPreparationSucceeded": true,
  "mutations": {
    "datasetStaged": true,
    "databaseBackupCreated": true,
    "migrationAttempted": true,
    "migrationApplied": true
  },
  "databaseRevisionAfter": "20260804_0013",
  "databaseIntegrityAfter": "ok",
  "readiness": {
    "nextAction": "fix_blockers",
    "providerExecutionAllowed": false
  },
  "providerCalls": 0,
  "acceptanceDomainWrites": 0
}
```

The example shows that local preparation may succeed while Provider configuration remains blocked.

## Receipt semantics

Receipt is an optional output write and is reported separately:

```json
{
  "outputWrites": {
    "receiptRequested": true,
    "receiptPath": "/private/path/bootstrap.json",
    "receiptWritten": true,
    "receiptError": null
  }
}
```

Receipt may include local source/database paths and is not public-portfolio-safe without redaction.

## Exit codes

```text
0  plan valid, or Apply completed with verified local preparation
2  invalid dataset/path/backup/migration/post-check/receipt
```

Provider blockers after a successful Apply do not change the bootstrap exit code. They are reported inside nested Readiness.

## Security and scope

The command source must not contain or invoke:

- `build_job_requirement_extractor`;
- `ImportJobsUseCase`;
- `PrepareRequirementAcceptanceBatchUseCase`;
- `OPENAI_API_KEY` value handling;
- Provider HTTP calls.

## Recovery boundary

This slice creates and identifies a verified backup but does not implement restore. A future restore command must independently define:

- process/connection safety;
- preservation of failed DB for diagnostics;
- restore verification;
- operator authorization;
- backup retention.
