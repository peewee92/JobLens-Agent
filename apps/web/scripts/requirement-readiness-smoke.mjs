import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdir, mkdtemp, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const repoRoot = resolve(webRoot, "../..");
const backendRoot = join(repoRoot, "services/backend");
const backendBin = join(backendRoot, ".venv/bin");
const backendPort = 8893;
const webPort = 8894;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-requirement-readiness-"));
const privateRoot = join(tempRoot, "private", "requirement-acceptance");
const databasePath = join(tempRoot, "joblens.db");
const databaseUrl = `sqlite+pysqlite:///${databasePath}`;
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
}

async function waitFor(url, attempts = 100) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
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

function databaseCounts(env) {
  const script = [
    "import json, sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "tables = ('job_requirement_extractions', 'trace_spans', 'requirement_acceptance_runs')",
    "counts = {name: connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in tables}",
    "connection.close()",
    "print(json.dumps(counts, sort_keys=True))",
  ].join("; ");
  const result = spawnSync(
    join(backendBin, "python"),
    ["-c", script, databasePath],
    {cwd: backendRoot, env, encoding: "utf8"},
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return JSON.parse(result.stdout);
}

try {
  await mkdir(privateRoot, {recursive: true});
  const backendEnv = {
    ...process.env,
    APP_ENV: "test",
    DATABASE_URL: databaseUrl,
    REQUIREMENT_ACCEPTANCE_PRIVATE_ROOT: privateRoot,
    REQUIREMENT_EXTRACTOR_PROVIDER: "disabled",
    REQUIREMENT_EXTRACTOR_MODEL: "",
    OPENAI_API_KEY: "",
    WEB_BASE_URL: webUrl,
  };

  console.log("[readiness-smoke] migrating isolated SQLite to head");
  const migration = spawnSync(join(backendBin, "alembic"), ["upgrade", "head"], {
    cwd: backendRoot,
    env: backendEnv,
    encoding: "utf8",
  });
  assert.equal(migration.status, 0, migration.stdout + migration.stderr);
  const before = databaseCounts(backendEnv);
  assert.deepEqual(before, {
    job_requirement_extractions: 0,
    requirement_acceptance_runs: 0,
    trace_spans: 0,
  });

  console.log("[readiness-smoke] starting FastAPI and production Next");
  start(
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
  await waitFor(`${backendUrl}/api/v1/health`);

  start(
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
  await waitFor(`${webUrl}/evals/requirements/canary/readiness`);

  const apiResponse = await fetch(
    `${backendUrl}/api/v1/requirement-acceptance-runs/readiness?reviewer=will&title=smoke-readiness&max_new_extractions=1`,
  );
  assert.equal(apiResponse.status, 200);
  const readiness = await apiResponse.json();
  assert.equal(readiness.datasetState, "missing");
  assert.equal(readiness.nextAction, "fix_blockers");
  assert.equal(readiness.databaseRevision, readiness.migrationHead);
  assert.equal(readiness.dbWrites, 0);
  assert.equal(readiness.providerCalls, 0);
  assert.equal(readiness.providerExecutionAllowed, false);
  assert.ok(
    readiness.blockers.some((item) => item.code === "formal_dataset_missing"),
  );
  assert.ok(
    readiness.blockers.some(
      (item) => item.code === "live_provider_not_configured",
    ),
  );
  assert.ok(
    readiness.blockers.some((item) => item.code === "live_model_not_configured"),
  );

  const pageResponse = await fetch(
    `${webUrl}/evals/requirements/canary/readiness?reviewer=will&title=smoke-readiness&maxNewExtractions=1`,
  );
  assert.equal(pageResponse.status, 200);
  const html = await pageResponse.text();
  assert.match(html, /Requirement 真实验收准备看板/);
  assert.match(html, /formal_dataset_missing/);
  assert.match(html, /live_provider_not_configured/);
  assert.match(html, /DB writes/);
  assert.match(html, /Provider calls/);
  assert.match(html, /先修复准备阻塞/);
  assert.doesNotMatch(html, /execute-canary|confirm-live-cost|sk-/);

  const after = databaseCounts(backendEnv);
  assert.deepEqual(after, before);
  console.log(
    "Requirement readiness smoke passed: isolated head DB + empty private root → fail-closed API/UI → zero domain writes and zero Provider calls.",
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
