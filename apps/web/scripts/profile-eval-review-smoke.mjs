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
const backendPort = 8881;
const webPort = 8882;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-eval-review-e2e-"));
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
  return fetch(`${webUrl}/api/profile-evals/${encodeURIComponent(runId)}/review`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decision, reviewer: "smoke-reviewer", notes}),
  });
}

try {
  const env = {...process.env, APP_ENV: "test", DATABASE_URL: databaseUrl};
  console.log("[eval-smoke] migrating and seeding temporary database");
  for (const args of [
    ["run", "alembic", "upgrade", "head"],
    ["run", "python", "-m", "scripts.seed_profile_eval_review_smoke"],
  ]) {
    const result = spawnSync("uv", args, {
      cwd: backendRoot,
      env,
      encoding: "utf8",
    });
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }

  console.log("[eval-smoke] starting FastAPI and production Next");
  start("uv", ["run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)], {
    cwd: backendRoot,
    env,
  });
  await waitFor(`${backendUrl}/api/v1/health`);
  start(
    "env",
    ["-u", "NODE_OPTIONS", "pnpm", "exec", "next", "start", "-p", String(webPort)],
    {cwd: webRoot, env: {...process.env, JOBLENS_BACKEND_URL: backendUrl}},
  );
  await waitFor(`${webUrl}/evals/profile`);

  console.log("[eval-smoke] checking history and failed-case-first detail");
  const initialList = await html("/evals/profile");
  assert.match(initialList, /尚无人工接受的 live baseline/);
  assert.match(initialList, /fixture-profile-extractor/);
  assert.match(initialList, /simulated-live-failed/);
  assert.match(initialList, /simulated-live-eligible/);

  const failedDetail = await html("/evals/profile/eval_live_failed_smoke");
  assert.match(failedDetail, /missing expected skill: Agent/);
  assert.match(failedDetail, /run_live_failed_smoke/);
  assert.match(failedDetail, /记录为 rejected/);

  console.log("[eval-smoke] enforcing review governance through Next proxy");
  const fixtureReview = await review(
    "eval_fixture_smoke",
    "rejected",
    "Fixture runs are engineering evidence only and cannot receive formal review.",
  );
  assert.equal(fixtureReview.status, 422);

  const rejected = await review(
    "eval_live_failed_smoke",
    "rejected",
    "Case review found a missing Agent skill, so this live run is rejected.",
  );
  assert.equal(rejected.status, 201, await rejected.text());

  const accepted = await review(
    "eval_live_eligible_smoke",
    "accepted",
    "Reviewed every case and Trace; no unsupported career facts were found.",
  );
  assert.equal(accepted.status, 201, await accepted.text());

  const duplicate = await review(
    "eval_live_eligible_smoke",
    "accepted",
    "A duplicate immutable review must be rejected by the Backend.",
  );
  assert.equal(duplicate.status, 409);

  console.log("[eval-smoke] verifying accepted baseline and immutable reviews");
  const baselineResponse = await fetch(`${backendUrl}/api/v1/profile-evals/baseline/accepted`);
  assert.equal(baselineResponse.status, 200);
  const baseline = await baselineResponse.json();
  assert.equal(baseline.run.id, "eval_live_eligible_smoke");
  assert.equal(baseline.review.decision, "accepted");

  const finalList = await html("/evals/profile");
  assert.match(finalList, /当前正式 baseline/);
  assert.match(finalList, /eval_live_eligible_smoke/);

  const acceptedDetail = await html("/evals/profile/eval_live_eligible_smoke");
  assert.match(acceptedDetail, /accepted/);
  assert.match(acceptedDetail, /Reviewed every case and Trace/);

  const rejectedDetail = await html("/evals/profile/eval_live_failed_smoke");
  assert.match(rejectedDetail, /rejected/);
  assert.match(rejectedDetail, /missing Agent skill/);

  console.log("Profile Eval review smoke passed: history → cases → reject/accept → baseline.");
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
