import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

// Run only against dedicated synthetic accounts. No credentials are printed.
const origin = new URL(process.env.JOBLENS_CLOUD_SMOKE_ORIGIN ?? "").origin;
const {a, b} = JSON.parse(await readFile(process.env.JOBLENS_CLOUD_SMOKE_ACCOUNTS, "utf8"));
const marker = "JobLens Synthetic Workspace B";
const syntheticJob = `${marker} — 岗位隔离验收`;
const afterRestart = process.argv.includes("--after-restart");
const privateOnly = process.argv.includes("--private-only");

function browser() {
  const jar = new Map();
  return async function request(path, {method = "GET", body, originOverride = origin, headers = {}, accept = "json"} = {}) {
    const sent = [...jar.values()].filter(({path: scope}) => scope === "/" || path === scope || path.startsWith(scope + "/"));
    const r = await fetch(origin + path, {method, redirect: "manual", signal: AbortSignal.timeout(65000),
      headers: {Origin: originOverride, ...headers, ...(body && {"Content-Type": "application/json"}),
        ...(sent.length && {Cookie: sent.map(c => c.pair).join("; ")})}, body: body ? JSON.stringify(body) : undefined});
    for (const set of r.headers.getSetCookie()) {
      const [pair] = set.split(";", 1);
      const [name] = pair.split("=", 1);
      const scope = /;\s*Path=([^;]+)/i.exec(set)?.[1] ?? "/";
      if (name.startsWith("__Secure-neon-auth.")) {
        assert.equal(scope, "/private", "login cookies are limited to /private");
        for (const flag of ["Secure", "HttpOnly", "SameSite=strict"]) assert.ok(set.split(/;\s*/).includes(flag), `login cookie requires ${flag}`);
      }
      if (/;\s*Max-Age=0(?:;|$)/i.test(set) || pair === name + "=") jar.delete(name);
      else jar.set(name, {pair, path: scope});
    }
    if (path.startsWith("/private")) assert.ok(r.headers.get("cache-control")?.includes("no-store"), `${path} must not be served from cache`);
    const text = await r.text();
    return {status: r.status, location: r.headers.get("location"), text,
      data: accept === "json" && r.headers.get("content-type")?.includes("application/json") && text ? JSON.parse(text) : null};
  };
}

const start = (request, account) => request("/private/api/workspace-session", {method: "POST", body: {email: account.email, password: account.password}});
const guest = browser(), alpha = browser(), beta = browser();
if (!privateOnly) assert.equal((await guest("/demo")).status, 200);
const redirect = await guest("/private", {headers: {"x-joblens-private-sign-in-page": "1", "X-Joblens-Owner": a.id}});
assert.equal(redirect.status, 307);
assert.equal(new URL(redirect.location, origin).pathname, "/private/sign-in");
assert.equal((await guest("/private/sign-in")).status, 200);
assert.equal((await guest("/private/api/jobs")).status, 401);
assert.equal((await guest("/private/quality")).status, 404);
assert.equal((await guest("/private/api/workspace-session", {method: "POST", originOverride: "https://example.com", body: {}})).status, 403);
const unknownEmail = "uninvited-smoke@example.invalid";
const codeRequest = await guest("/private/api/workspace-session", {method: "POST", body: {mode: "send-code", email: unknownEmail}});
assert.equal(codeRequest.status, 202);
assert.ok(codeRequest.data.message.includes("如果这个邮箱已受邀"));
assert.equal((await guest("/private/api/workspace-session", {method: "POST", body: {mode: "verify-code", email: unknownEmail, code: "000001"}})).status, 401);
assert.equal((await guest("/private/api/jobs")).status, 401);
assert.equal((await start(alpha, a)).status, 204);
assert.equal((await start(beta, b)).status, 204);
for (const entry of ["/private", "/private/profile", "/private/jobs", "/private/applications", "/private/import"]) {
  const page = await alpha(entry);
  assert.equal(page.status, 200, entry);
  assert.ok(page.text.includes("这里仅显示你自己的记录"), entry);
}
const sample = await alpha("/private/api/jobs");
assert.equal(sample.status, 200);
assert.equal(sample.data.total, 3);
const sampleId = sample.data.items[0].id;
assert.equal((await alpha(`/private/api/jobs/${encodeURIComponent(sampleId)}/original`)).status, 200);
assert.equal((await beta(`/private/api/jobs/${encodeURIComponent(sampleId)}/original`, {headers: {"X-Joblens-Owner": a.id}})).status, 404);

const privateProfile = await beta("/private/profile");
if (afterRestart) assert.ok(privateProfile.text.includes(marker), "B profile survives process restart");
else if (!privateProfile.text.includes(marker)) {
  assert.equal((await beta("/private/api/profile", {method: "PUT", body: {expectedVersion: 0, headline: marker, skills: [],
    evidence: [{key: "test", type: "project", summary: "只用于验证持久化和账号隔离的合成经历", source: "合成验收"}]}})).status, 200);
}
const before = await beta("/private/api/jobs");
const ownJob = before.data.items.find(job => job.title === syntheticJob);
if (afterRestart) assert.ok(ownJob, "B job survives process restart");
else if (!ownJob) {
  assert.equal(before.data.total, 0);
  const saved = await beta("/private/api/job-imports/manual", {method: "POST", body: {title: syntheticJob,
    company: "合成验收公司", description: "此岗位用于测试个人工作台是否保存数据，内容为纯合成测试资料，不使用模型。"}});
  assert.ok([200, 201].includes(saved.status), `manual job save returned ${saved.status}`);
}
const savedJobs = await beta("/private/api/jobs");
assert.equal(savedJobs.status, 200);
assert.equal(savedJobs.data.total, 1);
assert.equal(savedJobs.data.items[0].title, syntheticJob);
assert.equal((await alpha(`/private/api/jobs/${encodeURIComponent(savedJobs.data.items[0].id)}/original`)).status, 404);
assert.ok((await beta("/private/profile")).text.includes(marker));
assert.ok(!(await alpha("/private/profile")).text.includes(marker));
if (!privateOnly) {
  assert.ok(!(await beta("/demo")).text.includes(marker));
  assert.equal((await beta("/api/demo/session", {method: "POST"})).status, 200);
  assert.ok(!(await beta("/jobs")).text.includes(marker));
}
assert.equal((await beta("/private/api/jobs")).data.total, 1);
assert.equal((await beta("/private/api/workspace-session", {method: "DELETE"})).status, 204);
assert.equal((await beta("/private/api/jobs")).status, 401);
assert.equal((await start(beta, b)).status, 204);
assert.equal((await beta("/private/api/jobs")).data.total, 1);
console.log(afterRestart ? "PASS — both isolated accounts retain their records after backend restart"
  : `PASS — guest, uninvited code requests, two hosted identities, writes, sign-out and sign-in${privateOnly ? "" : ", demo isolation"}`);
