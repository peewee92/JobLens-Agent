import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdtemp, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const repoRoot = resolve(webRoot, "../..");
const backendRoot = join(repoRoot, "services/backend");
const backendBin = join(backendRoot, ".venv/bin");
const nextBin = join(webRoot, "node_modules/next/dist/bin/next");
const backendPort = 8891;
const webPort = 8892;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-requirement-review-e2e-"));
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

async function waitFor(url, attempts = 80) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Processes need time to bind their ports.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function html(path) {
  const response = await fetch(`${webUrl}${path}`);
  assert.equal(response.status, 200, `${path} should render`);
  return response.text();
}

async function review(runId, decision, notes) {
  return fetch(
    `${webUrl}/api/requirement-evals/${encodeURIComponent(runId)}/review`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({decision, reviewer: "smoke-reviewer", notes}),
    },
  );
}

try {
  const env = {...process.env, APP_ENV: "test", DATABASE_URL: databaseUrl};
  console.log("[requirement-smoke] migrating and seeding temporary database");
  for (const [command, args] of [
    [join(backendBin, "alembic"), ["upgrade", "head"]],
    [join(backendBin, "python"), ["-m", "scripts.seed_requirement_eval_review_smoke"]],
  ]) {
    const result = spawnSync(command, args, {
      cwd: backendRoot,
      env,
      encoding: "utf8",
    });
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }

  console.log("[requirement-smoke] starting FastAPI and production Next");
  start(
    join(backendBin, "uvicorn"),
    ["app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
    {cwd: backendRoot, env},
  );
  await waitFor(`${backendUrl}/api/v1/health`);
  start(process.execPath, [nextBin, "start", "-p", String(webPort)], {
    cwd: webRoot,
    env: {...process.env, NODE_OPTIONS: "", JOBLENS_BACKEND_URL: backendUrl},
  });
  await waitFor(`${webUrl}/evals/requirements`);

  console.log("[requirement-smoke] checking history and failed-case detail");
  const initialList = await html("/evals/requirements");
  assert.match(initialList, /尚无人工接受的 live Requirement baseline/);
  assert.match(initialList, /fixture-requirement-extractor/);
  assert.match(initialList, /simulated-live-failed/);
  assert.match(initialList, /simulated-live-eligible/);

  const failedDetail = await html(
    "/evals/requirements/reqeval_live_failed_smoke",
  );
  assert.match(failedDetail, /skill:Python:must_have/);
  assert.match(failedDetail, /run_req_live_failed_smoke/);
  assert.match(failedDetail, /记录为 rejected/);

  console.log("[requirement-smoke] enforcing review governance through Next proxy");
  const fixtureReview = await review(
    "reqeval_fixture_smoke",
    "rejected",
    "Fixture Requirement runs are pipeline evidence only and cannot be reviewed.",
  );
  assert.equal(fixtureReview.status, 422);

  const rejected = await review(
    "reqeval_live_failed_smoke",
    "rejected",
    "Missing must-have Requirement and wrong importance make this run unsafe.",
  );
  assert.equal(rejected.status, 201, await rejected.text());

  const accepted = await review(
    "reqeval_live_eligible_smoke",
    "accepted",
    "Reviewed every Requirement case and Trace; grounding and importance are valid.",
  );
  assert.equal(accepted.status, 201, await accepted.text());

  const duplicate = await review(
    "reqeval_live_eligible_smoke",
    "accepted",
    "A duplicate immutable Requirement Review must be rejected by the Backend.",
  );
  assert.equal(duplicate.status, 409);

  console.log("[requirement-smoke] verifying baseline and immutable reviews");
  const baselineResponse = await fetch(
    `${backendUrl}/api/v1/requirement-evals/baseline/accepted`,
  );
  assert.equal(baselineResponse.status, 200);
  const baseline = await baselineResponse.json();
  assert.equal(baseline.run.id, "reqeval_live_eligible_smoke");
  assert.equal(baseline.review.decision, "accepted");

  const finalList = await html("/evals/requirements");
  assert.match(finalList, /当前正式 baseline/);
  assert.match(finalList, /reqeval_live_eligible_smoke/);

  const acceptedDetail = await html(
    "/evals/requirements/reqeval_live_eligible_smoke",
  );
  assert.match(acceptedDetail, /accepted/);
  assert.match(acceptedDetail, /Reviewed every Requirement case and Trace/);

  const rejectedDetail = await html(
    "/evals/requirements/reqeval_live_failed_smoke",
  );
  assert.match(rejectedDetail, /rejected/);
  assert.match(rejectedDetail, /wrong importance/);

  console.log(
    "Requirement Eval review smoke passed: history → cases → reject/accept → baseline.",
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
      // Process may have already exited.
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
