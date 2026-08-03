import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdtemp, readFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const repoRoot = resolve(webRoot, "../..");
const backendRoot = join(repoRoot, "services/backend");
const samplePath = join(repoRoot, "data/samples/collector-report-minimal.json");
const backendPort = 8871;
const webPort = 8872;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const tempRoot = await mkdtemp(join(tmpdir(), "joblens-web-e2e-"));
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
      // Processes need a moment to bind their ports.
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

try {
  console.log("[smoke] migrating temporary database");
  const migration = spawnSync("uv", ["run", "alembic", "upgrade", "head"], {
    cwd: backendRoot,
    env: {...process.env, APP_ENV: "test", DATABASE_URL: databaseUrl},
    encoding: "utf8",
  });
  assert.equal(migration.status, 0, migration.stdout + migration.stderr);

  console.log("[smoke] starting FastAPI");
  start("uv", ["run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)], {
    cwd: backendRoot,
    env: {...process.env, APP_ENV: "test", DATABASE_URL: databaseUrl},
  });
  await waitFor(`${backendUrl}/api/v1/health`);

  console.log("[smoke] starting Next.js");
  start(
    "env",
    ["-u", "NODE_OPTIONS", "pnpm", "exec", "next", "start", "-p", String(webPort)],
    {
      cwd: webRoot,
      env: {...process.env, JOBLENS_BACKEND_URL: backendUrl},
    },
  );
  await waitFor(`${webUrl}/import`);

  console.log("[smoke] saving Profile and SearchIntent through Next proxies");
  const profilePayload = {
    expectedVersion: 0,
    headline: "8 年前端经验，正在转向 AI 应用工程",
    yearsOfExperience: 8,
    evidence: [
      {
        key: "spinach-desktop",
        type: "work",
        summary: "负责 Electron 协作与 Agent 功能。",
        source: "confirmed by user",
      },
      {
        key: "joblens",
        type: "project",
        summary: "构建 FastAPI + Next.js 的求职研究产品。",
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
  const savedProfile = await fetch(`${webUrl}/api/profile`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(profilePayload),
  });
  assert.equal(savedProfile.status, 200);
  const profileResult = await savedProfile.json();
  assert.equal(profileResult.version, 1);
  assert.equal(profileResult.skills[1].evidenceIds.length, 2);

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
  const savedIntent = await fetch(`${webUrl}/api/search-intent`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(intentPayload),
  });
  assert.equal(savedIntent.status, 200);
  assert.equal((await savedIntent.json()).version, 1);

  const staleProfile = await fetch(`${webUrl}/api/profile`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...profilePayload, headline: "stale edit"}),
  });
  assert.equal(staleProfile.status, 409);

  const profileHtml = await html("/profile");
  assert.match(profileHtml, /8 年前端经验，正在转向 AI 应用工程/);
  assert.match(profileHtml, /Agent Application Engineering/);
  assert.match(profileHtml, /不接受长期驻场/);
  assert.match(profileHtml, /当前版本[\s\S]{0,30}1/);
  assert.doesNotMatch(
    profileHtml,
    /profileKey|intentKey|sourceRaw|candidateRaw|canonicalKey/,
  );

  console.log("[smoke] checking import page");
  const importHtml = await html("/import");
  assert.match(importHtml, /选择 Collector report/);

  console.log("[smoke] importing Collector report through Next proxy");
  const report = JSON.parse(await readFile(samplePath, "utf8"));
  const imported = await fetch(`${webUrl}/api/job-imports`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(report),
  });
  assert.equal(imported.status, 201);
  const importResult = await imported.json();
  assert.equal(importResult.created, 1);
  assert.match(importResult.importId, /^imp_/);

  const invalid = await fetch(`${webUrl}/api/job-imports`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify([]),
  });
  assert.equal(invalid.status, 422);

  console.log("[smoke] rendering filtered Job Pool");
  const jobsHtml = await html("/jobs?city=%E6%AD%A6%E6%B1%89&minSalaryK=20&remoteStatus=unknown");
  assert.match(jobsHtml, /AI 应用开发工程师/);
  assert.match(jobsHtml, /示例公司/);
  assert.match(jobsHtml, /15–30K/);
  const jobMatch = jobsHtml.match(/\/jobs\/(job_[a-z0-9]+)/);
  assert.ok(jobMatch, "Job list should include a detail link");

  console.log("[smoke] rendering Job detail");
  const detailHtml = await html(`/jobs/${jobMatch[1]}`);
  assert.match(detailHtml, /负责 AI 应用、RAG 和 Agent 能力建设/);
  assert.match(detailHtml, /打开原始岗位/);
  assert.doesNotMatch(detailHtml, /sourceRaw|canonicalKey|normalizedSourceUrl/);

  console.log("[smoke] rendering Import audit");
  const auditHtml = await html(`/imports/${importResult.importId}`);
  assert.match(auditHtml, /导入批次审计/);
  assert.match(auditHtml, new RegExp(importResult.importId));
  assert.match(auditHtml, /Candidate 汇总/);
  assert.doesNotMatch(auditHtml, /candidateRaw|sourceRaw|canonicalKey/);

  console.log(
    "Web smoke E2E passed: profile → intent → import → jobs → detail → audit.",
  );
} catch (error) {
  for (const processInfo of children) {
    console.error(`\n--- ${processInfo.name} ---\n${processInfo.logs.join("")}`);
  }
  throw error;
} finally {
  for (const {child} of children.reverse()) {
    if (child.exitCode === null && child.pid) {
      try {
        process.kill(-child.pid, "SIGTERM");
      } catch {
        // Process may already have exited.
      }
    }
  }
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 400));
  for (const {child} of children) {
    child.stdout?.destroy();
    child.stderr?.destroy();
    if (child.exitCode === null && child.pid) {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {
        // Process group is already gone.
      }
    }
  }
  await rm(tempRoot, {recursive: true, force: true});
}
