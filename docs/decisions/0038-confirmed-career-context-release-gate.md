# ADR-0038｜Confirmed Career Context Release Gate

- Status: Accepted
- Date: 2026-08-05
- Scope: Phase 2 → Phase 4 input trust boundary

## Context

Future `MatchReport` consumes three fact sources:

```text
UserProfile + SearchIntent + JobRequirement
```

`JobRequirement` already has a model-cohort and per-job release gate. The
personal side has a different trust boundary:

- a Profile extractor produces only a reviewable Proposal;
- Profile Eval/accepted baseline governs Proposal quality;
- only an explicit save creates a confirmed immutable `UserProfile` version;
- `SearchIntent` is also explicitly confirmed and versioned;
- Match must never consume raw resume text or unconfirmed model output.

Before this decision, Match could read the latest Profile/SearchIntent, but no
single read model proved that both versions existed and that the Profile's
Skill→Evidence graph remained complete.

## Decision

Add a read-only `Confirmed Career Context Release Gate`.

### 1. Trust boundary

The Gate trusts only the latest explicitly confirmed versions:

```text
confirmationBoundary = explicit_versioned_user_confirmation
```

It deliberately does **not** require or read an accepted Profile Eval baseline.
Profile Eval answers whether an LLM Proposal cohort is trustworthy; this Gate
answers whether the user's current confirmed business facts are complete enough
for future Match.

### 2. Profile invariants

A Profile is not releasable when any of the following is true:

- no confirmed Profile version exists;
- headline is blank;
- years of experience is negative;
- no Evidence exists;
- Evidence key/summary/source is blank;
- Evidence keys are duplicated case-insensitively;
- no Skill exists;
- Skill names are duplicated case-insensitively;
- a Skill has no Evidence link;
- a Skill references an Evidence ID absent from the same Profile version.

The policy intentionally requires at least one Evidence-backed Skill. A
headline-only Profile is a valid draft/confirmation record but is not sufficient
for evidence-based Match.

### 3. SearchIntent invariants

A SearchIntent is not releasable when:

- no confirmed SearchIntent version exists;
- no non-blank target role exists;
- target roles are duplicated after trim/case-fold normalization;
- minimum salary is negative.

Other SearchIntent dimensions remain optional by domain design.

### 4. Derived state and atomic version-pair identity

`releaseEligible` is recalculated on every read from the current confirmed
versions. It is not stored as a mutable boolean because a newer Profile or
SearchIntent version must immediately change the Match input identity.

The repository selects the current Profile ID and SearchIntent ID in one SQL
statement, then loads those exact immutable versions. This prevents the Gate
from composing two independently observed "current" values during concurrent
confirmation saves. It does not lock future writes; it creates a reproducible
version pair for the current read.

The response exposes:

- Profile ID/version/createdAt and Evidence/Skill counts;
- SearchIntent ID/version/createdAt and target-role count;
- structured blocker codes;
- explicit zero-side-effect counters.

Future Match must persist the exact Profile and SearchIntent IDs/versions it
consumed. A later version does not rewrite a historical MatchReport.

### 5. No hidden model or operational work

The Gate:

- does not call a Provider;
- does not inspect Profile Eval baseline;
- does not create a Trace;
- does not write Profile/SearchIntent versions;
- does not calculate Eligibility, semantic fit, recommendation or score.

### 6. UI boundary

`/profile` displays Backend release facts and blockers. The Web layer must not
reimplement Evidence/reference policy. If the release query fails, Profile and
SearchIntent editing remains available and the Gate error is shown separately.

## Consequences

### Positive

- Match receives explicit, reproducible personal-side version identities;
- raw resume/Proposal output cannot silently become Match evidence;
- corrupt or incomplete Skill→Evidence links fail closed;
- missing Profile and SearchIntent are reported independently;
- Profile Eval governance and confirmed business facts remain conceptually
  separate;
- the Profile page becomes an actionable pre-Match checklist.

### Trade-offs

- a manually confirmed Profile with no Evidence-backed Skill remains blocked;
- the Gate validates structural trust, not whether the user's self-report is
  objectively true;
- no authentication/RBAC currently proves who performed the confirmation;
- future multi-user support must scope `PROFILE_KEY` and `SEARCH_INTENT_KEY` by
  authenticated user.

## Rejected alternatives

### Require accepted Profile Eval baseline for every confirmed Profile

Rejected because a user may manually enter and confirm facts without an LLM.
The Eval baseline governs Proposal generation, not the truth status of an
explicit confirmation.

### Treat Profile existence as sufficient

Rejected because an empty Profile or broken Skill→Evidence graph cannot support
explainable Match.

### Store `profile.matchReady = true`

Rejected because readiness depends on two independently versioned aggregates and
must change immediately when either receives a new version.

### Let the Web calculate readiness

Rejected because Backend and future Match would otherwise drift from the UI's
interpretation of trusted facts.

## Verification

Required evidence:

- pure policy truth-table tests;
- SQLite/API tests for missing, complete and corrupted references;
- query-side zero version/Trace growth;
- Web architecture tests preventing policy duplication;
- production FastAPI + Next + migrated SQLite Smoke;
- Backend full suite, Web tests, typecheck and production build.
