import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdtemp, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {createServer} from "node:net";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const repoRoot = resolve(webRoot, "../..");
const backendRoot = join(repoRoot, "services/backend");
const backendBin = join(backendRoot, ".venv/bin");
async function freePort() {
  const server = createServer();
  await new Promise((ok, fail) => server.once("error", fail).listen(0, "127.0.0.1", ok));
  const port = server.address().port;
  await new Promise((ok, fail) => server.close((error) => error ? fail(error) : ok()));
  return port;
}
const backendPort = await freePort();
let webPort = await freePort();
while (webPort === backendPort) webPort = await freePort();
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-requirement-manual-review-"));
const databaseUrl = `sqlite+pysqlite:///${join(tempRoot, "joblens.db")}`;
const children = [];

function start(command, args, options) {
  const logs = [];
  const child = spawn(command, args, {
    ...options,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => logs.push(chunk.toString()));
  child.stderr.on("data", (chunk) => logs.push(chunk.toString()));
  children.push({child, logs, name: `${command} ${args.join(" ")}`});
  return child;
}

async function waitFor(url, child, attempts = 100) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (child.exitCode !== null || child.signalCode !== null) throw new Error(`Server exited before ready: ${url}`);
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Processes need time to bind.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function responseJson(response) {
  const text = await response.text();
  assert.ok(response.ok, `${response.status}: ${text}`);
  return JSON.parse(text);
}

async function pageHtml(path) {
  const response = await fetch(`${webUrl}${path}`);
  assert.equal(response.status, 200, `${path} should render`);
  return response.text();
}

async function postWeb(path, payload) {
  return fetch(`${webUrl}${path}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

try {
  const backendEnv = {
    ...process.env,
    APP_ENV: "test",
    DATABASE_URL: databaseUrl,
    CAREER_AGENT_CHECKPOINT_PATH: join(tempRoot, "checkpoints.db"),
    REQUIREMENT_EXTRACTOR_PROVIDER: "fixture",
    REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER: "disabled",
    SEMANTIC_MATCH_PROVIDER: "disabled",
    PROFILE_EXTRACTOR_PROVIDER: "disabled",
    CAREER_INTENT_PROVIDER: "disabled",
  };

  console.log("[manual-review-smoke] migrating and seeding simulated data");
  for (const [command, args] of [
    [join(backendBin, "alembic"), ["upgrade", "head"]],
    [
      join(backendBin, "python"),
      ["-m", "scripts.seed_requirement_manual_review_smoke"],
    ],
  ]) {
    const result = spawnSync(command, args, {
      cwd: backendRoot,
      env: backendEnv,
      encoding: "utf8",
    });
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }

  console.log("[manual-review-smoke] starting FastAPI");
  const backend = start(
    join(backendBin, "uvicorn"),
    [
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(backendPort),
    ],
    {cwd: backendRoot, env: backendEnv},
  );
  await waitFor(`${backendUrl}/api/v1/health`, backend);
  const seededCandidates = await responseJson(
    await fetch(`${backendUrl}/api/v1/requirement-review-batches/candidates?limit=100`),
  );
  assert.equal(seededCandidates.total, 20);
  assert.ok(
    seededCandidates.items.every(
      (item) => item.model === "simulated-live-requirement-model",
    ),
  );

  console.log("[manual-review-smoke] starting production Next");
  const web = start(
    "env",
    [
      "-u",
      "NODE_OPTIONS",
      join(webRoot, "node_modules/.bin/next"),
      "start",
      "-p",
      String(webPort),
    ],
    {cwd: webRoot, env: {...process.env, JOBLENS_BACKEND_URL: backendUrl}},
  );
  await waitFor(`${webUrl}/evals/requirements/manual`, web);

  console.log("[manual-review-smoke] selecting a coherent 20-extraction cohort");
  const initialPage = await pageHtml("/evals/requirements/manual");
  assert.match(initialPage, /正式验收准备状态/);
  assert.match(initialPage, /已可选取 20 条同版本候选/);
  assert.match(initialPage, /simulated-live-requirement-model/);
  assert.match(initialPage, /系统不会替你生成人工判断/);

  const candidates = await responseJson(
    await fetch(`${backendUrl}/api/v1/requirement-review-batches/candidates?limit=100`),
  );
  assert.equal(candidates.total, 20);
  const extractionIds = candidates.items.map((item) => item.extractionId);
  assert.equal(new Set(extractionIds).size, 20);
  assert.ok(candidates.items.every((item) => item.provider === "simulated-live"));

  const created = await responseJson(
    await postWeb("/api/requirement-review-batches", {
      title: "Smoke-only 20-case Requirement review",
      reviewer: "smoke-reviewer",
      extractionIds,
    }),
  );
  const batchId = created.summary.id;
  assert.equal(created.summary.sampleSize, 20);
  assert.equal(created.summary.reviewedCount, 0);
  assert.equal(created.summary.formalEvidenceEligible, false);
  assert.equal(created.summary.finalDecision, null);
  assert.equal(created.summary.matchReleaseEligible, false);

  const initialDetailPage = await pageHtml(
    `/evals/requirements/manual/${encodeURIComponent(batchId)}`,
  );
  assert.match(initialDetailPage, /负责使用 Python 和 FastAPI 构建 Agent 工作流/);
  assert.match(initialDetailPage, /Evidence：/);
  assert.match(initialDetailPage, /使用 Python 和 FastAPI 构建 Agent 工作流/);
  assert.match(initialDetailPage, /run_manual_smoke_/);
  assert.match(initialDetailPage, /进行中：/);

  console.log("[manual-review-smoke] posting 20 explicit smoke judgments");
  for (const [index, item] of created.cases.entries()) {
    const rejected = index === 0;
    const response = await postWeb(
      `/api/requirement-review-batches/${encodeURIComponent(batchId)}/cases/${encodeURIComponent(item.id)}/review`,
      rejected
        ? {
            decision: "rejected",
            issueCodes: ["wrong_normalization"],
            notes:
              "Smoke-only judgment: normalized capability covers only part of the seeded JD requirement.",
          }
        : {
            decision: "accepted",
            issueCodes: [],
            notes:
              "Smoke-only judgment: seeded JD and frozen extraction are aligned for workflow verification.",
          },
    );
    assert.equal(response.status, 201, await response.text());
  }

  const duplicate = await postWeb(
    `/api/requirement-review-batches/${encodeURIComponent(batchId)}/cases/${encodeURIComponent(created.cases[0].id)}/review`,
    {
      decision: "accepted",
      issueCodes: [],
      notes: "Duplicate smoke judgment must not overwrite the immutable first review.",
    },
  );
  assert.equal(duplicate.status, 409);

  const completed = await responseJson(
    await fetch(`${backendUrl}/api/v1/requirement-review-batches/${encodeURIComponent(batchId)}`),
  );
  assert.equal(completed.summary.reviewedCount, 20);
  assert.equal(completed.summary.acceptedCount, 19);
  assert.equal(completed.summary.rejectedCount, 1);
  assert.equal(completed.summary.staleCaseCount, 0);
  assert.equal(completed.summary.completed, true);
  assert.equal(completed.summary.formalEvidenceEligible, true);
  assert.equal(completed.summary.finalDecision, null);
  assert.equal(completed.summary.matchReleaseEligible, false);
  assert.deepEqual(completed.issueCodeCounts, {wrong_normalization: 1});

  const releaseBeforeFinalDecision = await responseJson(
    await fetch(
      `${backendUrl}/api/v1/jobs/job_manual_smoke_00/requirement-release-readiness`,
    ),
  );
  assert.equal(releaseBeforeFinalDecision.releaseEligible, false);
  assert.deepEqual(
    releaseBeforeFinalDecision.blockers.map((item) => item.code),
    ["accepted_baseline_missing"],
  );

  const jobBeforeFinalDecision = await pageHtml("/jobs/job_manual_smoke_00");
  assert.match(jobBeforeFinalDecision, /岗位要求还在准备中，暂时不会用于匹配/);
  assert.match(jobBeforeFinalDecision, /当前没有有效的岗位要求审核基线/);

  const completedPage = await pageHtml(
    `/evals/requirements/manual/${encodeURIComponent(batchId)}`,
  );
  assert.match(completedPage, /20 条正式人工质量证据/);
  assert.match(completedPage, /等待人工最终质量结论/);
  assert.match(completedPage, /允许该证据进入 Match/);
  assert.match(completedPage, /能力归一化错误/);
  assert.match(completedPage, /Smoke-only judgment/);

  console.log("[manual-review-smoke] freezing one explicit batch final decision");
  const finalDecision = await responseJson(
    await postWeb(
      `/api/requirement-review-batches/${encodeURIComponent(batchId)}/final-decision`,
      {
        decision: "accept_for_match",
        reviewer: "smoke-reviewer",
        notes:
          "Smoke-only final conclusion: the complete frozen cohort is accepted for Match gate lifecycle verification.",
      },
    ),
  );
  assert.equal(finalDecision.decision, "accept_for_match");
  assert.equal(finalDecision.acceptedCount, 19);
  assert.equal(finalDecision.rejectedCount, 1);
  assert.equal(finalDecision.evidenceFingerprint.length, 64);

  const duplicateFinalDecision = await postWeb(
    `/api/requirement-review-batches/${encodeURIComponent(batchId)}/final-decision`,
    {
      decision: "reject_for_match",
      reviewer: "smoke-reviewer",
      notes: "A second smoke final decision must not overwrite immutable history.",
    },
  );
  assert.equal(duplicateFinalDecision.status, 409);

  const acceptedBaseline = await responseJson(
    await fetch(`${backendUrl}/api/v1/requirement-review-batches/accepted-baseline`),
  );
  assert.equal(acceptedBaseline.batch.id, batchId);
  assert.equal(acceptedBaseline.batch.matchReleaseEligible, true);
  assert.equal(acceptedBaseline.decision.id, finalDecision.id);

  const releasedRequirementFacts = await responseJson(
    await fetch(
      `${backendUrl}/api/v1/jobs/job_manual_smoke_00/requirement-release-readiness`,
    ),
  );
  assert.equal(releasedRequirementFacts.releaseEligible, true);
  assert.equal(releasedRequirementFacts.blockers.length, 0);
  assert.equal(releasedRequirementFacts.acceptedBaselineBatchId, batchId);
  assert.equal(
    releasedRequirementFacts.acceptedBaselineDecisionId,
    finalDecision.id,
  );
  assert.equal(
    releasedRequirementFacts.acceptedBaselineEvidenceFingerprint,
    finalDecision.evidenceFingerprint,
  );

  const releasedJobPage = await pageHtml("/jobs/job_manual_smoke_00");
  assert.match(releasedJobPage, /岗位要求已准备好，可用于后续匹配/);
  assert.match(releasedJobPage, /这份岗位要求符合当前匹配规则/);

  const finalizedPage = await pageHtml(
    `/evals/requirements/manual/${encodeURIComponent(batchId)}`,
  );
  assert.match(finalizedPage, /Match 门禁已放行/);
  assert.match(finalizedPage, /人工接受：允许进入 Match/);
  assert.match(finalizedPage, new RegExp(finalDecision.evidenceFingerprint));

  console.log("[manual-review-smoke] creating a newer extraction to prove stale detection");
  const reextract = await postWeb(
    "/api/jobs/job_manual_smoke_00/requirement-extractions",
    {},
  );
  assert.equal(reextract.status, 201, await reextract.text());

  const stale = await responseJson(
    await fetch(`${backendUrl}/api/v1/requirement-review-batches/${encodeURIComponent(batchId)}`),
  );
  assert.equal(stale.summary.staleCaseCount, 1);
  assert.equal(stale.summary.formalEvidenceEligible, false);
  assert.equal(stale.summary.finalDecision, "accept_for_match");
  assert.equal(stale.summary.matchReleaseEligible, true);
  assert.equal(stale.finalDecision.id, finalDecision.id);
  assert.equal(stale.cases[0].review.decision, "rejected");

  const baselineAfterStale = await fetch(
    `${backendUrl}/api/v1/requirement-review-batches/accepted-baseline`,
  );
  assert.equal(baselineAfterStale.status, 200);

  const releaseAfterStale = await responseJson(
    await fetch(
      `${backendUrl}/api/v1/jobs/job_manual_smoke_00/requirement-release-readiness`,
    ),
  );
  assert.equal(releaseAfterStale.releaseEligible, false);
  assert.ok(
    releaseAfterStale.blockers.some(
      (item) => item.code === "extraction_cohort_mismatch",
    ),
  );

  const blockedJobPage = await pageHtml("/jobs/job_manual_smoke_00");
  assert.match(blockedJobPage, /岗位要求还在准备中，暂时不会用于匹配/);
  assert.match(blockedJobPage, /岗位分析版本与审核基线不一致/);

  const unaffected = await responseJson(await fetch(`${backendUrl}/api/v1/jobs/job_manual_smoke_01/requirement-release-readiness`));
  assert.equal(unaffected.releaseEligible, true);

  const stalePage = await pageHtml(
    `/evals/requirements/manual/${encodeURIComponent(batchId)}`,
  );
  assert.match(stalePage, /已过期：1 条不是当前版本/);
  assert.match(stalePage, /已过期版本/);
  assert.match(stalePage, /冻结审核基线有效，样本已有更新/);
  assert.match(stalePage, /每个岗位的当前描述和要求仍须单独检查/);
  assert.match(stalePage, new RegExp(finalDecision.evidenceFingerprint));

  console.log("[manual-review-smoke] checking that a failed trace still blocks its own job");
  // Only the disposable test database is modified; do not touch the user's database.
  const corruptTrace = spawnSync(join(backendBin, "python"), [
    "-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE trace_spans SET error = ? WHERE id = ?', ('simulated failure', 'run_manual_smoke_01')); c.commit(); c.close()",
    join(tempRoot, "joblens.db"),
  ], {encoding: "utf8"});
  assert.equal(corruptTrace.status, 0, corruptTrace.stderr);
  const failedTraceRelease = await responseJson(await fetch(
    `${backendUrl}/api/v1/jobs/job_manual_smoke_01/requirement-release-readiness`,
  ));
  assert.equal(failedTraceRelease.releaseEligible, false);
  assert.ok(failedTraceRelease.blockers.some((item) => item.code === "trace_failed"));
  const stillAccepted = await fetch(
    `${backendUrl}/api/v1/requirement-review-batches/accepted-baseline`,
  );
  assert.equal(stillAccepted.status, 200);

  console.log(
    "Requirement manual review smoke passed: select 20 → review → final accept → Job Requirement facts released → re-extract → changed job independently blocked, unaffected job retains frozen baseline.",
  );
} catch (error) {
  for (const item of children) {
    if (item.logs.length > 0) {
      console.error(`\n[${item.name}]\n${item.logs.join("")}`);
    }
  }
  throw error;
} finally {
  for (const {child} of children.reverse()) {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      // Process may have exited.
    }
  }
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 200));
  for (const {child} of children.reverse()) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      // Process is already gone.
    }
  }
  await rm(tempRoot, {recursive: true, force: true});
}
