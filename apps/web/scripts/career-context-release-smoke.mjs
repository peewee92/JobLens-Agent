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
const backendPort = 8895;
const webPort = 8896;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-career-context-release-"));
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
  return child;
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

async function putWeb(path, payload) {
  return fetch(`${webUrl}${path}`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

function databaseCounts() {
  const result = spawnSync(
    join(backendBin, "python"),
    [
      "-c",
      [
        "import sqlite3,sys",
        "c=sqlite3.connect(sys.argv[1])",
        "tables=['user_profiles','search_intents','trace_spans']",
        "print(','.join(str(c.execute(f\"select count(*) from {t}\").fetchone()[0]) for t in tables))",
        "c.close()",
      ].join(";"),
      databasePath,
    ],
    {cwd: backendRoot, encoding: "utf8"},
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim().split(",").map(Number);
}

try {
  const backendEnv = {
    ...process.env,
    APP_ENV: "test",
    DATABASE_URL: databaseUrl,
    PROFILE_EXTRACTOR_PROVIDER: "disabled",
    REQUIREMENT_EXTRACTOR_PROVIDER: "disabled",
  };

  console.log("[career-context-release-smoke] migrating isolated SQLite");
  const migration = spawnSync(join(backendBin, "alembic"), ["upgrade", "head"], {
    cwd: backendRoot,
    env: backendEnv,
    encoding: "utf8",
  });
  assert.equal(migration.status, 0, migration.stdout + migration.stderr);
  assert.deepEqual(databaseCounts(), [0, 0, 0]);

  console.log("[career-context-release-smoke] starting FastAPI and production Next");
  start(
    join(backendBin, "uvicorn"),
    ["app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
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
  await waitFor(`${webUrl}/profile`);

  const empty = await responseJson(
    await fetch(`${backendUrl}/api/v1/career-context/release-readiness`),
  );
  assert.equal(empty.releaseEligible, false);
  assert.deepEqual(
    empty.blockers.map((item) => item.code).sort(),
    ["profile_missing", "search_intent_missing"],
  );
  assert.equal(empty.dbWrites, 0);
  assert.equal(empty.providerCalls, 0);
  assert.equal(empty.traceRunsCreated, 0);
  const emptyPage = await pageHtml("/profile");
  assert.match(emptyPage, /还需要补充一些信息，才能用于后续岗位匹配/);
  assert.match(emptyPage, /还没有保存你的职业背景/);
  assert.match(emptyPage, /还没有保存你的求职偏好/);
  assert.match(emptyPage, /查看技术详情/);

  const profilePayload = {
    expectedVersion: 0,
    headline: "Frontend Engineer moving into Agent application engineering",
    yearsOfExperience: 8,
    evidence: [
      {
        key: "spinach-desktop",
        type: "work",
        summary: "Built Electron collaboration and Agent features.",
        source: "confirmed by user",
      },
      {
        key: "joblens",
        type: "project",
        summary: "Built a FastAPI and Next.js evidence-based job tool.",
        source: "confirmed by user",
      },
    ],
    skills: [
      {
        name: "React",
        level: "strong",
        evidenceKeys: ["spinach-desktop"],
      },
      {
        name: "Agent Application Engineering",
        level: "working",
        evidenceKeys: ["spinach-desktop", "joblens"],
      },
    ],
  };
  const profile = await responseJson(await putWeb("/api/profile", profilePayload));
  assert.equal(profile.version, 1);

  const profileOnly = await responseJson(
    await fetch(`${backendUrl}/api/v1/career-context/release-readiness`),
  );
  assert.equal(profileOnly.releaseEligible, false);
  assert.deepEqual(profileOnly.blockers.map((item) => item.code), [
    "search_intent_missing",
  ]);

  const intentPayload = {
    expectedVersion: 0,
    targetRoles: ["Agent Engineer", "AI Application Engineer"],
    cities: ["武汉"],
    remoteAccepted: true,
    minimumSalaryK: 20,
    seniority: "senior",
    employmentTypes: ["full_time"],
    excludeKeywords: ["博彩"],
    hardConstraints: ["不接受长期驻场"],
    softPreferences: ["AI 产品有真实用户"],
  };
  const intent = await responseJson(
    await putWeb("/api/search-intent", intentPayload),
  );
  assert.equal(intent.version, 1);

  const beforeReadiness = databaseCounts();
  const released = await responseJson(
    await fetch(`${backendUrl}/api/v1/career-context/release-readiness`),
  );
  const afterReadiness = databaseCounts();
  assert.deepEqual(beforeReadiness, [1, 1, 0]);
  assert.deepEqual(afterReadiness, beforeReadiness);
  assert.equal(released.releaseEligible, true);
  assert.equal(released.confirmationBoundary, "explicit_versioned_user_confirmation");
  assert.equal(released.profileVersion, 1);
  assert.equal(released.profileEvidenceCount, 2);
  assert.equal(released.profileSkillCount, 2);
  assert.equal(released.searchIntentVersion, 1);
  assert.equal(released.searchIntentTargetRoleCount, 2);
  assert.deepEqual(released.blockers, []);
  const serialized = JSON.stringify(released);
  assert.doesNotMatch(serialized, /profileKey|intentKey|acceptedBaseline|apiKey|model/);

  const releasedPage = await pageHtml("/profile");
  assert.match(releasedPage, /你的信息已准备好，可用于后续岗位匹配/);
  assert.match(releasedPage, /真实经历/);
  assert.match(releasedPage, /已确认技能/);
  assert.match(releasedPage, /目标岗位/);
  assert.match(releasedPage, /查看技术详情/);
  assert.match(releasedPage, /dbWrites=[\s\S]{0,30}0/);
  assert.match(releasedPage, /providerCalls=[\s\S]{0,30}0/);

  console.log(
    "Career context release smoke passed: missing → profile-only → confirmed Profile+SearchIntent released with zero query side effects.",
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
