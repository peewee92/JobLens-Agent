import assert from "node:assert/strict";
import {readFile, readdir} from "node:fs/promises";
import {join, resolve} from "node:path";
import test from "node:test";

const webRoot = resolve(import.meta.dirname, "..");

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, {withFileTypes: true});
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return sourceFiles(path);
      return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
    }),
  );
  return nested.flat();
}

test("browser-facing source never exposes the backend URL as NEXT_PUBLIC", async () => {
  const files = [
    ...(await sourceFiles(join(webRoot, "app"))),
    ...(await sourceFiles(join(webRoot, "components"))),
    ...(await sourceFiles(join(webRoot, "lib"))),
  ];
  for (const file of files) {
    const source = await readFile(file, "utf8");
    assert.doesNotMatch(source, /NEXT_PUBLIC_JOBLENS_BACKEND_URL/, file);
  }
});

test("the import Client Component calls only the same-origin proxy", async () => {
  const source = await readFile(join(webRoot, "components/import-form.tsx"), "utf8");
  assert.match(source, /fetch\("\/api\/job-imports"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
});

test("the Profile Client Component calls only same-origin proxies", async () => {
  const source = await readFile(join(webRoot, "components/profile-editor.tsx"), "utf8");
  assert.match(source, /fetch\("\/api\/profile"/);
  assert.match(source, /fetch\("\/api\/search-intent"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
});

test("the Resume Proposal Client Component calls only the same-origin proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/resume-proposal-panel.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\("\/api\/profile-proposals"/);
  assert.match(source, /fetch\("\/api\/profile-proposals\/file"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /fetch\("\/api\/profile"/);
});

test("the Job Requirement Client calls only its same-origin command proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/job-requirement-extract-button.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\(\s*`\/api\/jobs\/\$\{encodeURIComponent\(jobId\)\}\/requirement-extractions`/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /openai|requirement_extractor_provider/i);
});

test("the Job Requirement Route Handler delegates to Backend without extraction logic", async () => {
  const source = await readFile(
    join(webRoot, "app/api/jobs/[id]/requirement-extractions/route.ts"),
    "utf8",
  );
  assert.match(source, /backendResponse/);
  assert.doesNotMatch(source, /OpenAI|FixtureJobRequirementExtractor|evidenceSpan/);
});

test("Job detail consumes Backend Requirement release facts without reimplementing policy", async () => {
  const source = await readFile(
    join(webRoot, "app/jobs/[id]/page.tsx"),
    "utf8",
  );
  assert.match(source, /fetchJobRequirementReleaseReadiness/);
  assert.match(source, /releaseReadiness\.releaseEligible/);
  assert.match(source, /releaseReadinessError/);
  assert.doesNotMatch(source, /Promise\.all/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /acceptedCount\s*\/|rejectedCount\s*\/|0\.9/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|OPENAI_API_KEY/);
});


test("the Profile Eval Review Client calls only its same-origin command proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/profile-eval-review-form.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\(\s*`\/api\/profile-evals\/\$\{encodeURIComponent\(run\.id\)\}\/review`/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /profile-proposals|run_profile_eval|OPENAI_API_KEY/);
});

test("Profile Eval pages consume review facts instead of implementing backend policy", async () => {
  const listPage = await readFile(join(webRoot, "app/evals/profile/page.tsx"), "utf8");
  const detailPage = await readFile(
    join(webRoot, "app/evals/profile/[id]/page.tsx"),
    "utf8",
  );
  for (const source of [listPage, detailPage]) {
    assert.doesNotMatch(source, /fetch\(/);
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL/);
  }
});

test("Requirement Eval Review Client calls only its same-origin command proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/requirement-eval-review-form.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\(\s*`\/api\/requirement-evals\/\$\{encodeURIComponent\(run\.id\)\}\/review`/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /run_requirement_eval|OPENAI_API_KEY/);
});

test("Requirement Eval pages consume review facts instead of implementing backend policy", async () => {
  const listPage = await readFile(
    join(webRoot, "app/evals/requirements/page.tsx"),
    "utf8",
  );
  const detailPage = await readFile(
    join(webRoot, "app/evals/requirements/[id]/page.tsx"),
    "utf8",
  );
  for (const source of [listPage, detailPage]) {
    assert.doesNotMatch(source, /fetch\(/);
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL/);
  }
});

test("Requirement manual review Clients call only same-origin proxies", async () => {
  const batchForm = await readFile(
    join(webRoot, "components/requirement-review-batch-form.tsx"),
    "utf8",
  );
  const caseForm = await readFile(
    join(webRoot, "components/requirement-case-review-form.tsx"),
    "utf8",
  );
  const finalDecisionForm = await readFile(
    join(webRoot, "components/requirement-review-final-decision-form.tsx"),
    "utf8",
  );
  assert.match(batchForm, /fetch\("\/api\/requirement-review-batches"/);
  assert.match(caseForm, /`\/api\/requirement-review-batches\/\$\{encodeURIComponent\(batchId\)\}\/cases\/\$\{encodeURIComponent\(caseId\)\}\/review`/);
  assert.match(finalDecisionForm, /`\/api\/requirement-review-batches\/\$\{encodeURIComponent\(batchId\)\}\/final-decision`/);
  assert.doesNotMatch(finalDecisionForm, /acceptedCount\s*[><=]|rejectedCount\s*[><=]|0\.9|95%/);
  for (const source of [batchForm, caseForm, finalDecisionForm]) {
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
    assert.doesNotMatch(source, /OPENAI_API_KEY|run_requirement_eval/);
  }
});

test("Requirement manual review pages use server read models and no direct writes", async () => {
  const listPage = await readFile(
    join(webRoot, "app/evals/requirements/manual/page.tsx"),
    "utf8",
  );
  const detailPage = await readFile(
    join(webRoot, "app/evals/requirements/manual/[id]/page.tsx"),
    "utf8",
  );
  for (const source of [listPage, detailPage]) {
    assert.doesNotMatch(source, /fetch\(/);
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL/);
  }
  assert.match(detailPage, /description/);
  assert.match(detailPage, /traceRunId/);
  assert.match(detailPage, /evidenceSpan/);
  assert.match(detailPage, /matchReleaseEligible/);
  assert.match(detailPage, /evidenceFingerprint/);
});

test("Requirement Canary Client submits only an immutable human decision through same-origin", async () => {
  const source = await readFile(
    join(webRoot, "components/requirement-canary-review-form.tsx"),
    "utf8",
  );
  assert.match(
    source,
    /`\/api\/requirement-acceptance-runs\/\$\{encodeURIComponent\(runId\)\}\/canary-review`/,
  );
  assert.match(source, /checkedJd/);
  assert.match(source, /checkedRequirements/);
  assert.match(source, /checkedTrace/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /max-new-extractions|OPENAI_API_KEY|requirement-extractions/);
});

test("Requirement Canary pages consume Backend facts and never start Provider work", async () => {
  const listPage = await readFile(
    join(webRoot, "app/evals/requirements/canary/page.tsx"),
    "utf8",
  );
  const detailPage = await readFile(
    join(webRoot, "app/evals/requirements/canary/[id]/page.tsx"),
    "utf8",
  );
  for (const source of [listPage, detailPage]) {
    assert.doesNotMatch(source, /fetch\(/);
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|OPENAI_API_KEY/);
    assert.doesNotMatch(source, /maxNewExtractions|requirement-extractions\s*[,)]/);
  }
  assert.match(detailPage, /traceLatencyMs/);
  assert.match(detailPage, /traceInputTokens/);
  assert.match(detailPage, /evidenceSpan/);
  assert.match(detailPage, /canaryContinueAllowed/);
  assert.match(detailPage, /canaryStopAllowed/);
});

test("Requirement readiness page is read-only and cannot launch operational work", async () => {
  const source = await readFile(
    join(
      webRoot,
      "app/evals/requirements/canary/readiness/page.tsx",
    ),
    "utf8",
  );
  assert.match(source, /fetchRequirementAcceptanceReadiness/);
  assert.match(source, /method="get"/);
  assert.match(source, /dbWrites/);
  assert.match(source, /providerCalls/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|OPENAI_API_KEY/);
  assert.doesNotMatch(
    source,
    /execute-canary|confirm-live-cost|alembic upgrade|requirement-extractions/,
  );
});

test("Requirement Canary Route Handler only proxies the human decision", async () => {
  const source = await readFile(
    join(
      webRoot,
      "app/api/requirement-acceptance-runs/[runId]/canary-review/route.ts",
    ),
    "utf8",
  );
  assert.match(source, /backendResponse/);
  assert.match(source, /canary-review/);
  assert.doesNotMatch(
    source,
    /OpenAI|FixtureJobRequirementExtractor|maxNewExtractions|requirement-extractions/,
  );
});

test("Requirement manual review Route Handlers only proxy Backend commands", async () => {
  const createRoute = await readFile(
    join(webRoot, "app/api/requirement-review-batches/route.ts"),
    "utf8",
  );
  const reviewRoute = await readFile(
    join(
      webRoot,
      "app/api/requirement-review-batches/[batchId]/cases/[caseId]/review/route.ts",
    ),
    "utf8",
  );
  const finalDecisionRoute = await readFile(
    join(
      webRoot,
      "app/api/requirement-review-batches/[batchId]/final-decision/route.ts",
    ),
    "utf8",
  );
  for (const source of [createRoute, reviewRoute, finalDecisionRoute]) {
    assert.match(source, /backendResponse/);
    assert.doesNotMatch(source, /OpenAI|FixtureJobRequirementExtractor|formalEvidenceEligible/);
  }
});

test("public contract types exclude raw and internal stream fields", async () => {
  const source = await readFile(join(webRoot, "lib/contracts.ts"), "utf8");
  for (const forbidden of [
    "sourceRaw",
    "candidateRaw",
    "canonicalKey",
    "normalizedSourceUrl",
    "profileKey",
    "intentKey",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
