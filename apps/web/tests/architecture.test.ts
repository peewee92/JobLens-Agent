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

test("the local dev server stays on the documented port even when PORT is inherited", async () => {
  const packageJson = JSON.parse(await readFile(join(webRoot, "package.json"), "utf8")) as {
    scripts?: {dev?: string};
  };
  assert.match(packageJson.scripts?.dev ?? "", /next dev --port 3000/);
});

test("local loopback hosts can hydrate Next.js dev client resources", async () => {
  const config = await readFile(join(webRoot, "next.config.ts"), "utf8");
  assert.match(config, /allowedDevOrigins:\s*\["127\.0\.0\.1", "localhost"\]/);
});

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

test("Profile page consumes Backend career-context release facts without implementing policy", async () => {
  const source = await readFile(join(webRoot, "app/profile/page.tsx"), "utf8");
  assert.match(source, /fetchCareerContextReleaseReadiness/);
  assert.match(source, /releaseReadiness\.releaseEligible/);
  assert.match(source, /releaseReadiness\.blockers/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /profileEval|acceptedBaseline|OPENAI_API_KEY/);
  assert.doesNotMatch(
    source,
    /evidenceIds\.length\s*>|targetRoles\.length\s*>|yearsOfExperience\s*</,
  );
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

test("the Resume Proposal file field keeps drag-and-drop wired to the same file validation path", async () => {
  const source = await readFile(
    join(webRoot, "components/resume-proposal-panel.tsx"),
    "utf8",
  );
  assert.match(source, /onDragOver=/);
  assert.match(source, /onDrop=/);
  assert.match(source, /dataTransfer\.files/);
  assert.match(source, /validateResumeFile/);
  assert.match(source, /function selectResumeFile[\s\S]*setProposal\(null\)/);
});

test("the Job Requirement action keeps a native POST fallback when hydration is unavailable", async () => {
  const source = await readFile(
    join(webRoot, "components/job-requirement-extract-button.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\(\s*`\/api\/jobs\/\$\{encodeURIComponent\(jobId\)\}\/requirement-extractions`/);
  assert.match(source, /<form action=\{fallbackAction\} method="post" onSubmit=\{extract\}>/);
  assert.match(source, /type="submit"/);
  assert.match(source, /returnTo=/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /openai|requirement_extractor_provider/i);
});

test("the Job Requirement Route Handler delegates to Backend and safely redirects native form submissions", async () => {
  const source = await readFile(
    join(webRoot, "app/api/jobs/[id]/requirement-extractions/route.ts"),
    "utf8",
  );
  assert.match(source, /backendResponse/);
  assert.match(source, /returnTo === safeReturnTo/);
  assert.match(source, /NextResponse\.redirect\(target, 303\)/);
  assert.match(source, /requirementExtractionError/);
  assert.doesNotMatch(source, /OpenAI|FixtureJobRequirementExtractor|evidenceSpan/);
});

test("the Match Report Client runs only after explicit user action through same-origin proxy", async () => {
  const client = await readFile(
    join(webRoot, "components/job-match-report-panel.tsx"),
    "utf8",
  );
  const route = await readFile(
    join(webRoot, "app/api/jobs/[id]/match-report/route.ts"),
    "utf8",
  );
  const page = await readFile(join(webRoot, "app/jobs/[id]/page.tsx"), "utf8");

  assert.match(client, /fetch\(\s*`\/api\/jobs\/\$\{encodeURIComponent\(jobId\)\}\/match-report`/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(route, /backendResponse/);
  assert.doesNotMatch(client, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000|OPENAI_API_KEY/);
  assert.doesNotMatch(route, /recommendation\s*=|strong|stretch/);
  assert.doesNotMatch(page, /fetchJobMatchReport|\/match-report/);
});

test("the Batch Match Ranking Route Handler only proxies the read-only Backend query", async () => {
  const route = await readFile(
    join(webRoot, "app/api/match-ranking/route.ts"),
    "utf8",
  );

  assert.match(route, /backendResponse/);
  assert.match(route, /\/api\/v1\/match-ranking/);
  assert.match(route, /jobId/);
  assert.match(route, /includeBlocked/);
  assert.match(route, /topN/);
  assert.doesNotMatch(route, /recommendation\s*=|strong|good|stretch|blocked/);
  assert.doesNotMatch(route, /OPENAI_API_KEY|SEMANTIC_MATCH_PROVIDER/);
});

test("Batch Match refresh stays explicit and proxies the bounded Backend command", async () => {
  const client = await readFile(
    join(webRoot, "components/recommendation-refresh.tsx"),
    "utf8",
  );
  const route = await readFile(
    join(webRoot, "app/api/match-batch/route.ts"),
    "utf8",
  );

  assert.match(client, /fetch\("\/api\/match-batch"/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /maxReadyJobs:\s*10/);
  assert.match(route, /backendResponse/);
  assert.match(route, /\/api\/v1\/match-batch/);
  assert.doesNotMatch(client, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000|OPENAI_API_KEY/);
  assert.doesNotMatch(route, /succeeded|blocked|recommendation\s*=/);
});

test("Requirement Analysis batch stays explicit and proxies only the bounded Backend command", async () => {
  const client = await readFile(
    join(webRoot, "components/recommendation-requirement-analysis.tsx"),
    "utf8",
  );
  const route = await readFile(
    join(webRoot, "app/api/requirement-batch/route.ts"),
    "utf8",
  );

  assert.match(client, /fetch\("\/api\/requirement-batch"/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /maxReadyJobs:\s*5/);
  assert.match(client, /confirmLiveCost:\s*true/);
  assert.match(client, /liveCostConfirmed/);
  assert.match(client, /本次确认只对这一轮有效/);
  assert.match(client, /Provider/);
  assert.match(client, /providerBlocked/);
  assert.match(client, /setProviderBlocked\(true\)/);
  assert.match(client, /disabled=\{state\.kind === "running" \|\| providerBlocked \|\| !liveCostConfirmed\}/);
  assert.match(route, /backendResponse/);
  assert.match(route, /\/api\/v1\/requirement-batch/);
  assert.doesNotMatch(client, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000|OPENAI_API_KEY/);
  assert.doesNotMatch(route, /targetRoles|intentSignals|requirementAnalysisNeededCount/);
});

test("recommendation feedback refreshes server coverage after a successful save", async () => {
  const client = await readFile(
    join(webRoot, "components/recommendation-feedback.tsx"),
    "utf8",
  );

  assert.match(client, /useRouter/);
  assert.match(client, /setSavedDecision\(decision\);\s*setSavedReasons\(normalizedReasons\);\s*setSavedNote\(note\);\s*setSelectedReasons\(decision === "rejected" \? normalizedReasons : \[\]\);\s*setSavedThisSession\(true\);\s*router\.refresh\(\);/s);
  assert.match(client, /savedThisSession && successHref/);
  assert.match(client, /successLabel/);
  assert.doesNotMatch(client, /window\.location\.reload/);
});

test("UserFeedback Route Handler only proxies the immutable Backend write", async () => {
  const route = await readFile(
    join(webRoot, "app/api/user-feedback/route.ts"),
    "utf8",
  );

  assert.match(route, /backendResponse/);
  assert.match(route, /\/api\/v1\/user-feedback/);
  assert.match(route, /method:\s*"POST"/);
  assert.doesNotMatch(route, /interested|maybe|rejected|role_fit|skill_gap/);
  assert.doesNotMatch(route, /OPENAI_API_KEY|SEMANTIC_MATCH_PROVIDER/);
});

test("Target Cohort Gap UI hides feedback IDs behind a human-readable Job selector", async () => {
  const client = await readFile(
    join(webRoot, "components/target-cohort-gap-panel.tsx"),
    "utf8",
  );
  const route = await readFile(
    join(webRoot, "app/api/target-cohort/gaps/route.ts"),
    "utf8",
  );

  assert.match(client, /fetch\("\/api\/target-cohort\/gaps", \{method: "GET"\}\)/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /item\.title/);
  assert.match(client, /item\.company/);
  assert.match(client, /item\.jobId/);
  assert.match(client, /selectedJobIds/);
  assert.match(client, /选择全部“感兴趣”/);
  assert.doesNotMatch(client, /selectedFeedbackIds|已选择岗位的反馈 ID|feedback-ids|parseFeedbackIds|textarea/);
  assert.match(client, /supportingJobIds/);
  assert.match(client, /supportingRequirementIds/);
  assert.match(client, /profileSkillIds/);
  assert.match(client, /evidenceIds/);
  assert.match(client, /completionCriteria/);
  assert.match(route, /backendResponse/);
  assert.match(route, /\/api\/v1\/target-cohort\/gaps\/candidates/);
  assert.match(route, /\/api\/v1\/target-cohort\/gaps/);
  assert.doesNotMatch(client, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000|OPENAI_API_KEY/);
  assert.doesNotMatch(route, /gapSeverity\s*=|targetCoverage\s*=|mustHaveRatio\s*=/);
});

test("Job Preparation page consumes only the Backend fact bundle without reimplementing policy", async () => {
  const page = await readFile(
    join(webRoot, "app/jobs/[id]/prepare/page.tsx"),
    "utf8",
  );
  const checklist = await readFile(join(webRoot, "components/application-checklist-progress.tsx"), "utf8");
  const checklistBuilder = await readFile(join(webRoot, "lib/application-checklist.ts"), "utf8");
  const backend = await readFile(join(webRoot, "lib/backend.ts"), "utf8");

  assert.match(page, /fetchJobPreparation/);
  assert.match(page, /resumeDelta/);
  assert.match(page, /experiencePriority/);
  assert.match(page, /storyFacts/);
  assert.match(page, /interviewFacts/);
  assert.match(page, /studyChecklist/);
  assert.match(page, /ApplicationChecklistProgress/);
  assert.match(page, /buildApplicationChecklistItems/);
  assert.match(checklistBuilder, /先突出最有把握的真实经历/);
  assert.match(checklistBuilder, /再补最关键的准备缺口/);
  assert.match(checklistBuilder, /最后准备最高优先级面试问题/);
  assert.match(page, /returnPrepare/);
  assert.match(page, /补充这项真实 Evidence/);
  assert.match(page, /系统不会因为打开链接就声称缺口已改善/);
  assert.match(page, /fetchMatchImprovement/);
  assert.match(page, /resolvedRequirementIds\.includes\(focusRequirementId\)/);
  assert.match(page, /missingRequirementIds\.includes\(focusRequirementId\)/);
  assert.match(page, /不把返回链接本身当成成功证据/);
  assert.match(page, /listNewlySupportedRequirements/);
  assert.match(page, /这次新增 Evidence 还命中了其他真实 Requirement/);
  assert.match(page, /不把“可能有帮助”当成已经改善/);
  assert.match(page, /继续最新准备清单/);
  assert.match(page, /returnImport=\$\{encodeURIComponent\(returnImportId\)\}/);
  assert.match(page, /返回本次导入查看最新批次结果/);
  assert.match(page, /prepareEvidenceJobs/);
  assert.match(page, /prepareEvidenceQuery/);
  assert.match(page, /prepareAlternativeEvidenceJobs/);
  assert.match(page, /prepareAlternativeEvidenceQuery/);
  assert.match(page, /evidenceAttributionQuery/);
  assert.match(page, /returnImportProgressHref/);
  assert.match(page, /completionHref=\{returnImportProgressHref\}/);
  assert.match(page, /afterPreparation=/);
  assert.match(page, /focusImpactRequirementIds/);
  assert.match(checklist, /id="application-checklist"/);
  assert.match(checklist, /申请准备清单/);
  assert.match(checklist, /不会修改 MatchReport、Evidence 或 Ranking/);
  assert.match(checklist, /这份岗位申请准备清单已完成/);
  assert.match(checklist, /不代表系统已经替你投递/);
  assert.match(checklist, /返回本次导入继续处理/);
  assert.match(checklist, /completionHref/);
  assert.match(checklist, /localStorage/);
  assert.match(backend, /\/api\/v1\/job-preparation\/\$\{encodeURIComponent\(jobId\)\}/);
  assert.doesNotMatch(page, /fetch\(/);
  assert.doesNotMatch(checklist, /fetch\(/);
  assert.doesNotMatch(checklistBuilder, /fetch\(/);
  assert.doesNotMatch(page, /OPENAI_API_KEY|SEMANTIC_MATCH_PROVIDER|gapSeverity\s*=|mustHaveRatio\s*=/);
});

test("Import detail revalidates local application checklist progress against current preparation facts", async () => {
  const page = await readFile(join(webRoot, "app/imports/[id]/page.tsx"), "utf8");
  const summary = await readFile(join(webRoot, "components/application-checklist-summary.tsx"), "utf8");

  assert.match(page, /afterPreparation/);
  assert.match(page, /fetchJobPreparation/);
  assert.match(page, /buildApplicationChecklistItems/);
  assert.match(page, /ApplicationChecklistSummary/);
  assert.match(page, /当前无法用这批岗位的最新 JobPreparationBundle 校验/);
  assert.match(summary, /applicationChecklistFingerprint/);
  assert.match(summary, /parseApplicationChecklistState/);
  assert.match(summary, /localStorage/);
  assert.match(summary, /不代表已经投递/);
  assert.match(summary, /interestedCandidates/);
  assert.match(summary, /isApplicationChecklistComplete/);
  assert.match(summary, /准备下一个尚未完成的感兴趣岗位/);
  assert.match(summary, /fallbackHref/);
  assert.match(summary, /application-batch-handoff-summary/);
  assert.match(summary, /这批感兴趣岗位的当前申请准备已经收敛/);
  assert.match(summary, /为什么现在先做这一步/);
  assert.match(summary, /fallbackReason/);
  assert.match(summary, /batchRemainder\.pendingDecision/);
  assert.match(summary, /batchRemainder\.matchReady/);
  assert.match(summary, /batchRemainder\.requirementBlocked/);
  assert.match(summary, /batchRemainder\.evidenceBlocked/);
  assert.match(summary, /batchRemainder\.maybe/);
  assert.match(page, /pendingDecision: pendingApplyDecisionCount/);
  assert.match(page, /unknownReadiness: unknownReadinessCount/);
  assert.match(page, /afterPreparationInterestedPreparationResults/);
  assert.match(page, /Promise\.allSettled/);
  assert.match(page, /afterPreparationFallbackAction/);
  assert.match(page, /current MatchReport、没有 hard blocker/);
  assert.match(page, /Requirement 已达到 release \/ Match readiness/);
  assert.match(page, /Evidence action 精确命中/);
  assert.match(page, /当前批次没有其他可执行目标，导入下一批岗位/);
  assert.doesNotMatch(summary, /fetch\(/);
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

test("Requirement manual review keeps issue choices aligned and long requirement lists collapsible", async () => {
  const detailPage = await readFile(
    join(webRoot, "app/evals/requirements/manual/[id]/page.tsx"),
    "utf8",
  );
  const caseForm = await readFile(
    join(webRoot, "components/requirement-case-review-form.tsx"),
    "utf8",
  );
  const styles = await readFile(join(webRoot, "app/globals.css"), "utf8");

  assert.match(detailPage, /<details className="requirement-review-requirements">/);
  assert.match(detailPage, /查看抽取出的 Requirements/);
  assert.match(detailPage, /必须.*优先.*加分/);
  assert.match(caseForm, /className="review-issue-grid"/);
  assert.match(caseForm, /className="review-issue-option"/);
  assert.match(styles, /\.review-issue-option\s*\{[^}]*align-items:\s*center/s);
  assert.match(styles, /\.review-issue-option input\s*\{[^}]*width:\s*18px/s);
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

test("Requirement Canary keeps implementation metadata behind developer details", async () => {
  const detailPage = await readFile(
    join(webRoot, "app/evals/requirements/canary/[id]/page.tsx"),
    "utf8",
  );
  const reviewForm = await readFile(
    join(webRoot, "components/requirement-canary-review-form.tsx"),
    "utf8",
  );

  assert.match(
    detailPage,
    /<details className="canary-technical-details">[\s\S]*?<summary>技术详情（开发调试）<\/summary>/,
  );
  assert.match(detailPage, /JD 原文依据/);
  assert.match(detailPage, /岗位原文/);
  assert.match(detailPage, /抽取结果（\{requirements\.length\}）/);
  assert.doesNotMatch(detailPage, /<h3>Trace 摘要<\/h3>/);
  assert.doesNotMatch(detailPage, /Evidence：/);
  assert.match(reviewForm, /我已确认本次调用没有技术错误/);
  assert.doesNotMatch(reviewForm, /我已检查 Trace 状态、耗时、Token 与错误/);
  assert.doesNotMatch(
    reviewForm,
    /disabled=\{pending !== null \|\| !evidenceChecked \|\| !stopAllowed\}/,
  );
  assert.match(
    reviewForm,
    /disabled=\{pending !== null \|\| !stopAllowed\}/,
  );
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
