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
const backendBin = join(backendRoot, ".venv/bin");
const nextBin = join(webRoot, "node_modules/next/dist/bin/next");
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
  const migration = spawnSync(join(backendBin, "alembic"), ["upgrade", "head"], {
    cwd: backendRoot,
    env: {...process.env, APP_ENV: "test", DATABASE_URL: databaseUrl},
    encoding: "utf8",
  });
  assert.equal(migration.status, 0, migration.stdout + migration.stderr);

  console.log("[smoke] starting FastAPI");
  start(join(backendBin, "uvicorn"), ["app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)], {
    cwd: backendRoot,
    env: {
      ...process.env,
      APP_ENV: "test",
      DATABASE_URL: databaseUrl,
      PROFILE_EXTRACTOR_PROVIDER: "fixture",
      REQUIREMENT_EXTRACTOR_PROVIDER: "fixture",
    },
  });
  await waitFor(`${backendUrl}/api/v1/health`);

  console.log("[smoke] starting Next.js");
  start(process.execPath, [nextBin, "start", "-p", String(webPort)], {
    cwd: webRoot,
    env: {...process.env, NODE_OPTIONS: "", JOBLENS_BACKEND_URL: backendUrl},
  });
  await waitFor(`${webUrl}/import`);

  console.log("[smoke] uploading DOCX, confirming Profile and saving SearchIntent");
  const resumeText = [
    "8 年前端经验，正在转向 AI 应用工程。",
    "工作经历：负责 Electron 桌面端与 React、TypeScript 业务开发。",
    "项目：参与 Agent 功能设计与前后端落地，所有内容均来自真实简历。",
  ].join("\n");
  const resumeDocxPath = join(tempRoot, "resume.docx");
  const makeDocx = spawnSync(
    join(backendBin, "python"),
    [
      "-c",
      "import html,os,sys,zipfile; ps=''.join('<w:p><w:r><w:t>'+html.escape(x)+'</w:t></w:r></w:p>' for x in os.environ['RESUME_TEXT'].splitlines()); xml='<?xml version=\"1.0\" encoding=\"UTF-8\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>'+ps+'</w:body></w:document>'; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); z.writestr('[Content_Types].xml','<Types/>'); z.writestr('word/document.xml',xml); z.close()",
      resumeDocxPath,
    ],
    {
      cwd: backendRoot,
      env: {...process.env, RESUME_TEXT: resumeText},
      encoding: "utf8",
    },
  );
  assert.equal(makeDocx.status, 0, makeDocx.stdout + makeDocx.stderr);
  const proposalForm = new FormData();
  proposalForm.set(
    "file",
    new Blob([await readFile(resumeDocxPath)], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }),
    "resume.docx",
  );
  const proposedProfile = await fetch(`${webUrl}/api/profile-proposals/file`, {
    method: "POST",
    body: proposalForm,
  });
  assert.equal(proposedProfile.status, 200);
  const proposal = await proposedProfile.json();
  assert.match(proposal.runId, /^run_/);
  assert.equal(proposal.yearsOfExperience, 8);
  assert.ok(proposal.evidence.every((item) => resumeText.includes(item.evidenceSpan)));

  const profilePayload = {
    expectedVersion: 0,
    headline: proposal.headline,
    yearsOfExperience: proposal.yearsOfExperience,
    evidence: proposal.evidence.map((item) => ({
      key: item.key,
      type: item.type,
      summary: item.summary,
      source: `resume proposal ${proposal.runId}`,
    })),
    skills: proposal.skills,
  };
  const savedProfile = await fetch(`${webUrl}/api/profile`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(profilePayload),
  });
  assert.equal(savedProfile.status, 200);
  const profileResult = await savedProfile.json();
  assert.equal(profileResult.version, 1);
  assert.ok(profileResult.skills.length >= 4);
  assert.ok(profileResult.skills.every((item) => item.evidenceIds.length >= 1));

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
  assert.match(profileHtml, /Agent/);
  assert.match(profileHtml, /从简历快速填充职业背景/);
  assert.match(profileHtml, /上传 PDF 或 DOCX/);
  assert.match(profileHtml, /不接受长期驻场/);
  assert.match(profileHtml, /已保存/);
  assert.doesNotMatch(
    profileHtml,
    /profileKey|intentKey|sourceRaw|candidateRaw|canonicalKey/,
  );

  console.log("[smoke] checking import page");
  const importHtml = await html("/import");
  assert.match(importHtml, /添加浏览器插件收集的岗位/);

  console.log("[smoke] importing Collector report through Next proxy");
  const report = JSON.parse(await readFile(samplePath, "utf8"));
  report.jobs[0].description = [
    "负责 AI 应用、RAG 和 Agent 能力建设。",
    "要求熟练掌握 Python 和 FastAPI。",
    "有 Docker 使用经验者优先。",
  ].join("\n");
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

  console.log("[smoke] rendering Job detail and extracting Requirements");
  const detailBefore = await html(`/jobs/${jobMatch[1]}`);
  assert.match(detailBefore, /负责 AI 应用、RAG 和 Agent 能力建设/);
  assert.match(detailBefore, /这个岗位还没有做要求分析/);
  const firstRequirementRun = await fetch(
    `${webUrl}/api/jobs/${jobMatch[1]}/requirement-extractions`,
    {method: "POST"},
  );
  assert.equal(firstRequirementRun.status, 201);
  const firstRequirements = await firstRequirementRun.json();
  assert.match(firstRequirements.extractionId, /^reqrun_/);
  assert.match(firstRequirements.traceRunId, /^run_/);
  assert.ok(firstRequirements.requirements.length >= 4);
  assert.ok(
    firstRequirements.requirements.every((item) =>
      report.jobs[0].description.includes(item.evidenceSpan),
    ),
  );
  const secondRequirementRun = await fetch(
    `${webUrl}/api/jobs/${jobMatch[1]}/requirement-extractions`,
    {method: "POST"},
  );
  assert.equal(secondRequirementRun.status, 201);
  const secondRequirements = await secondRequirementRun.json();
  assert.notEqual(secondRequirements.extractionId, firstRequirements.extractionId);
  const detailHtml = await html(`/jobs/${jobMatch[1]}`);
  assert.match(detailHtml, /岗位要求分析/);
  assert.match(detailHtml, /演示分析结果/);
  assert.match(detailHtml, /Python/);
  assert.match(detailHtml, /FastAPI/);
  assert.match(detailHtml, /查看分析详情/);
  assert.match(detailHtml, /trace=[\s\S]{0,30}run_/);
  assert.match(detailHtml, /打开原始岗位/);
  assert.doesNotMatch(detailHtml, /sourceRaw|canonicalKey|normalizedSourceUrl/);

  console.log("[smoke] rendering Import audit");
  const auditHtml = await html(`/imports/${importResult.importId}`);
  assert.match(auditHtml, /这批岗位处理得怎么样/);
  assert.match(auditHtml, new RegExp(importResult.importId));
  assert.match(auditHtml, /候选数据统计/);
  assert.doesNotMatch(auditHtml, /candidateRaw|sourceRaw|canonicalKey/);

  console.log(
    "Web smoke E2E passed: DOCX → proposal → profile → intent → import → requirements → jobs → audit.",
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
