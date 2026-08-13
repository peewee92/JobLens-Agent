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

test("requirement extraction gives a clear live processing state for long requests", async () => {
  const button = await source("components/job-requirement-extract-button.tsx");
  const css = await source("app/globals.css");

  assert.match(button, /Analyzing job requirements…/);
  assert.match(button, /This can take a moment\./);
  assert.match(button, /role="status"/);
  assert.match(button, /aria-live="polite"/);
  assert.match(button, /requirement-processing-indicator/);
  assert.match(css, /\.requirement-processing-indicator/);
  assert.match(css, /\.loading-spinner/);
});

test("requirement readiness page leads with user decisions and hides technical evidence by default", async () => {
  const page = await source("app/evals/requirements/canary/readiness/page.tsx");
  const css = await source("app/globals.css");

  assert.match(page, /岗位要求分析准备情况/);
  assert.match(page, /现在能不能继续/);
  assert.match(page, /下一步做什么/);
  assert.match(page, /\{next\.label\}/);
  assert.doesNotMatch(page, /requirementAcceptanceNextActionLabels/);
  assert.match(page, /readiness-overview/);
  assert.match(page, /需要处理的事项/);
  assert.match(page, /确认本轮测试信息/);
  assert.match(page, /readiness-user-input-form/);
  assert.match(page, /<details className="readiness-advanced-details">/);
  assert.match(page, /技术详情与运行参数/);
  assert.match(css, /\.readiness-overview/);
  assert.match(css, /\.readiness-progress-grid/);
  assert.doesNotMatch(page, /<h2>人工参数<\/h2>/);
  assert.doesNotMatch(page, /<h2>证据身份<\/h2>/);
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

test("match report card leads with a recommendation and keeps AI execution explicit", async () => {
  const panel = await source("components/job-match-report-panel.tsx");
  const copy = await source("lib/match-report.ts");

  assert.match(panel, /完整匹配建议/);
  assert.match(panel, /生成完整匹配建议/);
  assert.match(panel, /核心优势/);
  assert.match(panel, /主要风险/);
  assert.match(panel, /AI/);
  assert.match(copy, /值得优先投/);
  assert.match(copy, /值得投/);
  assert.match(copy, /可以尝试/);
  assert.match(copy, /当前不建议优先投入/);
  assert.doesNotMatch(panel, /匹配度[:：]?\s*\d+%/);
  assert.doesNotMatch(panel, /score/);
});

test("Target Cohort Gap page is phrased around choosing Jobs instead of internal IDs", async () => {
  const page = await source("app/gaps/page.tsx");
  const panel = await source("components/target-cohort-gap-panel.tsx");

  assert.match(page, /别按感觉补技能/);
  assert.match(panel, /选择目标岗位/);
  assert.match(panel, /不需要再找任何 ID/);
  assert.match(panel, /感兴趣/);
  assert.match(panel, /再看看/);
  assert.match(panel, /分析这些岗位的共同能力差距/);
  assert.match(panel, /做到什么算补齐/);
  assert.match(panel, /查看技术依据/);
  assert.doesNotMatch(panel, /已选择岗位的反馈 ID|可用逗号、空格或换行分隔/);
});


test("Target Cohort Gap blockers explain readiness instead of exposing internal codes", async () => {
  const panel = await source("components/target-cohort-gap-panel.tsx");

  assert.match(panel, /这不是你的技能缺口/);
  assert.match(panel, /你的职业背景已确认，可以用于对比/);
  assert.match(panel, /岗位要求还没有完成质量确认/);
  assert.match(panel, /查看岗位要求准备状态/);
  assert.match(panel, /准备完成后，你会在这里直接看到/);
  assert.match(panel, /查看技术原因/);
  assert.match(panel, /gapBlockerCopy/);
  assert.match(panel, /<details className="gap-technical-blockers">/);
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
