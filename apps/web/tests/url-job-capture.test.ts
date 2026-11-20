import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {applyCaptureDraft, captureJobUrl, decodeCapture} from "../lib/url-job-capture";
import {localUrlCaptureOrigin, permitsLocalCaptureRequest} from "../lib/local-url-capture";

const draft = {title: "Engineer", company: "Example", description: "Build maintainable tools.", sourceUrl: "https://job.test/1"};
const response = {status: "captured", draft, qualityGrade: "card_only", extractionMethod: "static_html", diagnostics: {elapsedMs: 10}};

test("preview sends only the capture command and never submits manual import", async () => {
  const calls: string[] = [];
  const outcome = await captureJobUrl(draft.sourceUrl, new AbortController().signal, async (input, init) => {
    calls.push(String(input));
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), {url: draft.sourceUrl});
    return Response.json(response);
  });
  assert.deepEqual(calls, ["/api/job-imports/url-capture"]);
  assert.equal(outcome.kind, "captured");
  if (outcome.kind === "captured") assert.deepEqual(outcome.draft, draft);
});

test("an overwrite requires confirmation and preserves existing form text before it", () => {
  const fields = {title: {value: "My edits"}, company: {value: ""}, description: {value: ""}, sourceUrl: {value: ""}};
  assert.equal(applyCaptureDraft(fields, draft, false), "needs_confirmation");
  assert.equal(fields.title.value, "My edits");
  assert.equal(fields.description.value, "");
  assert.equal(applyCaptureDraft(fields, draft, true), "applied");
  assert.equal(fields.title.value, draft.title);
  assert.equal(fields.sourceUrl.value, draft.sourceUrl);
});

test("capture preview confirms only form fill, leaving current save status to the manual form", () => {
  const source = readFileSync(new URL("../components/url-job-capture-panel.tsx", import.meta.url), "utf8");
  const applied = source.match(/application === "applied" && <p>([^<]+)<\/p>/)?.[1];
  assert.ok(applied);
  assert.match(applied, /已将抓取结果填入下方表单/);
  assert.doesNotMatch(applied, /尚未保存|已保存/);
});

test("challenge, disallowed address, and missing browser never produce a draft", () => {
  assert.deepEqual(decodeCapture(200, {status: "needs_human_intervention", interventionReason: "captcha_detected", draft}),
    {kind: "error", message: "目标页面要求完成验证码。请改用浏览器插件或手动粘贴正文。"});
  assert.deepEqual(decodeCapture(403, {error: {code: "url_capture_ssrf_blocked"}}),
    {kind: "error", message: "这个链接指向不允许访问的网络地址。"});
  const missing = decodeCapture(200, {status: "failed", blockers: ["playwright_not_installed"]});
  assert.ok(missing.kind === "error" && missing.message.includes("手动粘贴"));
  assert.equal(decodeCapture(200, {...response, draft: null}).kind, "error");
});

test("a site's verification page or paused listing does not produce a draft", () => {
  assert.deepEqual(decodeCapture(200, {status: "needs_human_intervention", interventionReason: "anti_bot_challenge", draft}),
    {kind: "error", message: "目标页面限制了访问或触发了验证。请改用浏览器插件或手动粘贴正文。"});
  assert.deepEqual(decodeCapture(200, {status: "failed", blockers: ["posting_inactive"], draft}),
    {kind: "error", message: "招聘网站显示此岗位已结束或暂停招聘。请核对原链接或换一个岗位。"});
});

test("local proxy is off by default and does not open in either cloud mode", () => {
  const env = {JOBLENS_URL_CAPTURE: "1", WEB_BASE_URL: "http://127.0.0.1:3102"};
  const origin = localUrlCaptureOrigin(env);
  assert.equal(origin?.origin, env.WEB_BASE_URL);
  assert.equal(localUrlCaptureOrigin({}), null);
  assert.equal(localUrlCaptureOrigin({...env, JOBLENS_PUBLIC_DEMO: "1"}), null);
  assert.equal(localUrlCaptureOrigin({...env, NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD: "1"}), null);
  assert.equal(localUrlCaptureOrigin({...env, JOBLENS_BACKEND_URL: "https://cloud.test"}), null);
  const request = (header: string) => new Request(env.WEB_BASE_URL, {headers: {origin: header, host: "127.0.0.1:3102"}});
  assert.equal(permitsLocalCaptureRequest(request(env.WEB_BASE_URL), origin), true);
  assert.equal(permitsLocalCaptureRequest(request("https://foreign.test"), origin), false);
});
