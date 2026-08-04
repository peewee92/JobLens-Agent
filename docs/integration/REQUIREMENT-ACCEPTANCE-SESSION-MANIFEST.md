# Requirement Acceptance Session Manifest

Status: P0-3B-3G operational contract

## Goal

Generate one stable, secret-free execution/evidence index for a formal Requirement Acceptance workflow without writing the database or calling the Provider.

## Command

```bash
cd services/backend

.venv/bin/python -m scripts.check_requirement_acceptance_readiness \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance" \
  --max-new-extractions 3 \
  --web-base-url http://localhost:3000 \
  --session-manifest ./artifacts/requirement-acceptance-session.json \
  --json
```

The readiness exit code remains authoritative:

```text
0  next action is currently executable
1  valid dataset, but blockers or a terminal stopped state remain
2  invalid dataset or Manifest write failure
```

A Manifest may be written for exit `0` or `1`. Invalid formal input exits before a Session identity can be built.

## Session identity

```text
schemaVersion = requirement-acceptance-session-v1
sessionId = reqacceptsession_<32 hex>
```

Hash inputs:

```text
datasetFingerprint
reviewer
title
provider
model
extractorVersion
promptVersion
```

Excluded from identity:

```text
generatedAt
requestedMaxNewExtractions
attemptedCalls
blockers
runId
batchId
```

Consequences:

- changing only the current call budget keeps the same Session ID;
- changing Provider/Model/Extractor/Prompt creates a new Session ID;
- changing Reviewer or Title creates a new Session ID;
- a blocked pre-configuration Manifest can have a provisional identity that changes once Provider/Model become defined.

## Top-level shape

```json
{
  "schemaVersion": "requirement-acceptance-session-v1",
  "sessionId": "reqacceptsession_xxx",
  "generatedAt": "2026-08-04T15:00:00+00:00",
  "state": "ready_for_provider_execution",
  "identity": {},
  "readiness": {},
  "execution": {},
  "evidence": {},
  "completionChecklist": {},
  "expectedEvidence": [],
  "privacy": {}
}
```

## States

```text
blocked
ready_for_provider_execution
awaiting_human_canary_review
stopped
awaiting_twenty_case_review
```

The Manifest does not create these states. They are projections of Readiness and persistent Run facts.

## Identity section

```json
{
  "datasetFingerprint": "sha256-hex",
  "sourceVersion": "1.4.5",
  "selectedCount": 20,
  "datasetFileName": "formal-review.json",
  "datasetPath": "/private/path/formal-review.json",
  "reviewer": "will",
  "title": "Real Requirement acceptance",
  "provider": "openai",
  "model": "configured-model",
  "extractorVersion": "requirement-extractor-v1",
  "promptVersion": "requirement-extraction-v1"
}
```

`datasetPath` is operationally useful but not public-safe. Redact it before sharing the Manifest externally.

## Readiness section

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": true,
  "readyForNextAction": true,
  "nextAction": "run_canary",
  "requestedMaxNewExtractions": 3,
  "databaseReachable": true,
  "databaseRevision": "20260805_0014",
  "migrationHead": "20260805_0014",
  "apiKeyConfigured": true,
  "blockers": []
}
```

Only the Boolean presence of an API Key is included. The value is never included.

## Execution section

```json
{
  "recommendedCommand": ".venv/bin/python -m scripts.operate_requirement_acceptance_canary ...",
  "recommendedCommandSha256": "sha256-hex",
  "dbWritesDuringManifestExport": 0,
  "providerCallsDuringManifestExport": 0
}
```

`recommendedCommand` exists only when Provider execution is currently allowed. It routes to the dedicated Canary or Controlled Resume Operator in Plan mode and never contains an API Key.

## Evidence section

```json
{
  "runId": "reqacceptrun_xxx",
  "runStatus": "partial",
  "attemptedCalls": 2,
  "batchId": null,
  "workbenchUrl": "http://localhost:3000/evals/requirements/canary/reqacceptrun_xxx",
  "manualReviewUrl": null,
  "canaryReview": {
    "reviewId": "reqacceptcanary_xxx",
    "decision": "continue",
    "reviewer": "will",
    "reviewedCaseIds": ["reqacceptcase_a", "reqacceptcase_b"],
    "reviewedExtractionIds": ["reqrun_a", "reqrun_b"],
    "reviewedTraceRunIds": ["run_a", "run_b"],
    "reviewedAt": "2026-08-04T15:30:00+00:00",
    "notesSha256": "sha256-hex",
    "notesCharacterCount": 84
  },
  "cases": [
    {
      "caseId": "reqacceptcase_a",
      "caseIndex": 0,
      "jobId": "job_a",
      "status": "extracted",
      "attemptCount": 1,
      "descriptionHash": "sha256-hex",
      "descriptionIsCurrent": true,
      "extractionId": "reqrun_a",
      "traceRunId": "run_a",
      "errorCode": null,
      "isPendingCanaryReviewEvidence": false,
      "isFrozenCanaryEvidence": true
    }
  ]
}
```

The Case list contains references/hashes only. It does not contain JD text or Trace output.

Before a decision, `isPendingCanaryReviewEvidence` marks attempted Cases that the Reviewer must inspect. After an immutable decision exists, those pending flags become false.

`isFrozenCanaryEvidence` is true only for IDs persisted in the immutable Canary Review. Later Resume attempts do not retroactively become pre-approval Canary evidence.

## Completion checklist

```json
{
  "formalDatasetValidated": true,
  "databaseAtMigrationHead": true,
  "liveProviderConfigured": true,
  "liveModelConfigured": true,
  "apiKeyConfigured": true,
  "canaryStarted": true,
  "canaryHumanDecisionRecorded": true,
  "allTwentyExtractionsReady": false,
  "manualReviewBatchCreated": false,
  "allTwentyHumanDecisionsCompleted": null,
  "modelQualityApproved": null,
  "matchPhaseAllowed": false
}
```

`null` means this Readiness/Run read model cannot prove the fact. It must not be silently converted to `false` or `true`.

## Privacy contract

```json
{
  "containsApiKey": false,
  "containsFullJobDescriptions": false,
  "containsRawTraceOutput": false,
  "containsHumanReviewNotes": false,
  "containsLocalDatasetPath": true,
  "publicPortfolioSafeWithoutPathRedaction": false
}
```

Do not publish the raw local Manifest without removing or rewriting `datasetPath`.

## Atomic-write behavior

The writer uses a unique temporary file in the target directory:

```text
write
→ flush
→ fsync
→ replace
```

Readers see the previous complete Manifest or the next complete Manifest, not a partial JSON file.

This does not provide:

- distributed locking;
- append-only history;
- digital signatures;
- trusted timestamps;
- protection against an authorized local user modifying the file.

## Blocked example

A blocked Manifest remains useful for handoff:

```json
{
  "state": "blocked",
  "readiness": {
    "workflowReady": false,
    "providerExecutionAllowed": false,
    "nextAction": "fix_blockers",
    "blockers": [
      {
        "scope": "workflow",
        "code": "database_migration_not_current",
        "message": "..."
      }
    ]
  },
  "execution": {
    "recommendedCommand": null,
    "providerCallsDuringManifestExport": 0
  }
}
```

## Recommended lifecycle

```text
1. Run Readiness + write Manifest
2. Fix workflow/provider blockers
3. Run Readiness again to same Manifest path
4. Execute the secret-free recommended command manually
5. Run Readiness again after Canary
6. Inspect Workbench and submit human decision
7. Run Readiness again after Continue/Stop
8. Resume only when allowed
9. Run Readiness after Batch creation
10. Finish 20 human decisions outside this Manifest's current proof boundary
```

## Scope exclusions

- automatic Provider execution;
- automatic database migration;
- Secret storage;
- complete JD or Trace export;
- automatic model quality approval;
- automatic Match release;
- append-only audit log;
- cryptographic signing;
- multi-writer conflict resolution.
