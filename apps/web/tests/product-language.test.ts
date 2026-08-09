import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {join, resolve} from "node:path";
import test from "node:test";

const webRoot = resolve(import.meta.dirname, "..");

async function source(path: string): Promise<string> {
  return readFile(join(webRoot, path), "utf8");
}

test("main navigation is organized around job seeker tasks instead of eval modules", async () => {
  const layout = await source("app/layout.tsx");
  assert.match(layout, />首页</);
  assert.match(layout, />我的背景</);
  assert.match(layout, />我的岗位</);
  assert.match(layout, />添加岗位</);
  assert.match(layout, /质量检查（高级）/);
  const primaryNav = layout.match(/<nav[\s\S]*?<\/nav>/)?.[0] ?? "";
  assert.doesNotMatch(primaryNav, /质量检查/);
  assert.doesNotMatch(layout, />画像评测</);
  assert.doesNotMatch(layout, />要求评测</);
});

test("profile primary copy uses user language and keeps implementation facts in technical details", async () => {
  const page = await source("app/profile/page.tsx");
  assert.match(page, /我的背景和求职偏好/);
  assert.match(page, /匹配准备情况/);
  assert.match(page, /careerContextReleaseLabel\(releaseReadiness\)/);
  assert.match(page, /查看技术详情/);
  assert.doesNotMatch(page, /未来 Match 的个人侧事实门禁/);
  assert.doesNotMatch(page, /本查询副作用/);
});

test("job detail keeps internal requirement metadata out of the ordinary user experience", async () => {
  const page = await source("app/jobs/[id]/page.tsx");
  const button = await source("components/job-requirement-extract-button.tsx");
  const css = await source("app/globals.css");

  assert.match(page, /岗位要求分析/);
  assert.match(page, /岗位原文依据/);
  assert.doesNotMatch(page, /查看技术详情/);
  assert.doesNotMatch(page, /查看分析详情/);
  assert.doesNotMatch(page, /Baseline：|Decision：|Evidence Fingerprint：/);
  assert.doesNotMatch(page, /<span className="code">\{blocker\.code\}<\/span>/);
  assert.doesNotMatch(page, /confidence=/);
  assert.doesNotMatch(page, /extractor=|provider=|model=|trace=/);
  assert.match(button, /requirement-action-button/);
  assert.match(css, /\.requirement-action-button[\s\S]*white-space:\s*nowrap/);
});

test("job detail explains deterministic eligibility without fake match scores", async () => {
  const page = await source("app/jobs/[id]/page.tsx");
  const eligibility = await source("lib/eligibility.ts");

  assert.match(page, /这个岗位适合我吗/);
  assert.match(page, /已匹配/);
  assert.match(page, /待确认/);
  assert.match(page, /明显缺失/);
  assert.match(page, /不使用模糊的百分制匹配分数/);
  assert.match(eligibility, /当前不建议优先投入/);
  assert.doesNotMatch(page, /匹配度[:：]?\s*\d+%/);
  assert.doesNotMatch(page, /score/);
});

test("home page explains the product as a simple job-search workflow", async () => {
  const page = await source("app/page.tsx");
  assert.match(page, /先把自己和岗位看清楚/);
  assert.match(page, /完善我的背景/);
  assert.match(page, /添加感兴趣的岗位/);
  assert.match(page, /查看岗位/);
  assert.doesNotMatch(page, /redirect\(/);
});

test("AI resume success auto-fills an empty career draft without silently replacing existing edits", async () => {
  const editor = await source("components/profile-editor.tsx");
  const panel = await source("components/resume-proposal-panel.tsx");

  assert.match(editor, /isBlankProfileDraft\(currentProfileDraft\(\)\)/);
  assert.match(editor, /applyProposal\(proposal, "auto"\)/);
  assert.match(panel, /自动填入下方职业背景草稿/);
  assert.match(panel, /用这份草稿替换当前编辑内容/);
  assert.match(panel, /自动填草稿 · 不自动保存/);
  assert.doesNotMatch(panel, /填到下方，继续检查和修改/);
});

test("career background defaults to card review and only expands the detailed editor on demand", async () => {
  const editor = await source("components/profile-editor.tsx");

  assert.match(editor, /AI 对我的理解/);
  assert.match(editor, /内容没问题，确认保存/);
  assert.match(editor, /有问题，编辑详情/);
  assert.match(editor, /待你确认/);
  assert.match(editor, /isProfileEditorOpen/);
  assert.match(editor, /setIsProfileEditorOpen\(true\)/);
  assert.match(editor, /完成编辑，返回审核/);
});
