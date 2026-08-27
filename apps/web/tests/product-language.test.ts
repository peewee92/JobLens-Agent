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
  assert.match(layout, />优先投递</);
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

test("requirement eval overview exposes the lightweight offline MVP quality gate", async () => {
  const page = await source("app/evals/requirements/page.tsx");
  const backend = await source("lib/backend.ts");

  assert.match(page, /MVP 离线质量门/);
  assert.match(page, /离线要求回放/);
  assert.match(page, /离线 Top 5/);
  assert.match(page, /最近 Provider 冒烟/);
  assert.match(page, /providerSmokeCheckedAt/);
  assert.match(page, /providerSmokePlainStatusCode/);
  assert.match(page, /providerSmokeStructuredStatusCode/);
  assert.match(page, /不阻塞 MVP/);
  assert.match(page, /fetchMvpQualityStatus/);
  assert.match(backend, /\/api\/v1\/requirement-evals\/mvp-quality-status/);
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

test("recommendations page surfaces the MVP Top-N value without fake probability language", async () => {
  const page = await source("app/recommendations/page.tsx");
  const backend = await source("lib/backend.ts");
  const profileEditor = await source("components/profile-editor.tsx");
  const requirementBatch = await source("components/recommendation-requirement-analysis.tsx");
  const feedback = await source("components/recommendation-feedback.tsx");

  assert.match(page, /哪些岗位最值得我先投/);
  assert.match(page, /已有完整匹配/);
  assert.match(page, /查看为什么/);
  assert.match(page, /当前没有值得优先投的已分析岗位/);
  assert.match(page, /这些岗位当前有明确硬条件缺口/);
  assert.match(page, /当前缺少足够 Profile 证据的硬条件/);
  assert.match(page, /jobBlockers\.find/);
  assert.match(page, /requirement\.originalText/);
  assert.match(page, /去补对应证据/);
  assert.match(page, /focusRequirement=\$\{requirement\.requirementType\}/);
  assert.match(page, /硬条件缺口较少的岗位排在前面/);
  assert.match(page, /这不是成功概率/);
  assert.match(page, /哪些资料最可能解锁更多岗位判断/);
  assert.match(page, /当前 Profile 没有足够证据支撑这些硬条件/);
  assert.match(page, /补充我的真实经历/);
  assert.match(page, /补教育经历/);
  assert.match(page, /focus=education/);
  assert.match(page, /fetchMatchBlockerSummary/);
  assert.match(page, /RecommendationFeedback/);
  assert.match(page, /已反馈/);
  assert.match(page, /还差.*个岗位需要你的真实判断/);
  assert.match(page, /继续完成反馈/);
  assert.match(page, /待反馈/);
  assert.match(page, /已反馈/);
  assert.match(page, /feedback-/);
  assert.match(page, /反馈状态暂不可用/);
  assert.match(page, /不会把读取失败误报成“0 个已反馈”/);
  assert.match(page, /你的反馈会帮助 JobLens 判断推荐是否符合真实求职选择/);
  assert.match(feedback, /其他/);
  assert.match(feedback, /补充说明（可选）/);
  assert.match(feedback, /选择“其他”时请说明原因/);
  assert.match(feedback, /initialNote/);
  assert.match(feedback, /note,/);
  assert.match(page, /RecommendationRefresh/);
  assert.match(page, /RecommendationRequirementAnalysis/);
  assert.match(requirementBatch, /分析下一批/);
  assert.match(requirementBatch, /Provider 当前不可用/);
  assert.match(requirementBatch, /joblens:requirement-provider-cooldown-until/);
  assert.match(requirementBatch, /30 \* 60 \* 1000/);
  assert.match(requirementBatch, /sessionStorage\.setItem/);
  assert.match(requirementBatch, /sessionStorage\.removeItem/);
  assert.match(page, /initialReasons=/);
  assert.match(feedback, /initialReasons/);
  assert.match(feedback, /你当前的选择：.*原因/);
  assert.match(feedback, /type="checkbox"/);
  assert.match(feedback, /selectedReasons/);
  assert.match(feedback, /toggleReason/);
  assert.match(feedback, /可多选/);
  assert.match(feedback, /aria-pressed/);
  assert.match(feedback, /savedDecision === decision/);
  assert.match(feedback, /setSelectedReasons\(decision === "rejected" \? normalizedReasons : \[\]\)/);
  assert.match(page, /重新计算当前输入已准备好的岗位/);
  assert.match(page, /\/profile\?next=\/recommendations#profile-evidence/);
  assert.match(page, /没有完整 MatchReport 的岗位不会被偷偷猜一个名次/);
  assert.match(page, /fetchMatchRanking/);
  assert.match(page, /fetchLatestUserFeedback/);
  assert.match(page, /fetchMatchReviewReadiness/);
  assert.match(page, /下一批先分析哪些岗位/);
  assert.match(page, /还需要岗位要求分析/);
  assert.match(page, /查看并分析岗位要求/);
  assert.match(page, /明确求职方向更接近/);
  assert.match(page, /fetchRecommendationCoverage/);
  assert.match(backend, /\/api\/v1\/recommendation-coverage/);
  assert.match(backend, /topN/);
  assert.match(backend, /\/api\/v1\/match-blockers/);
  assert.match(profileEditor, /id="profile-evidence"/);
  assert.doesNotMatch(page, /匹配度[:：]?\s*\d+%/);
  assert.doesNotMatch(page, /成功概率[:：]?\s*\d+%/);
});

test("profile can return to recommendations only through the whitelisted save continuation", async () => {
  const page = await source("app/profile/page.tsx");
  const editor = await source("components/profile-editor.tsx");

  assert.match(page, /requestedNext === "\/recommendations"/);
  assert.match(page, /afterProfileSaveHref/);
  assert.match(editor, /router\.push\(afterProfileSaveHref\)/);
  assert.match(editor, /正在返回岗位优先级/);
  assert.match(page, /requestedFocus === "education"/);
  assert.match(page, /focusRequirementType/);
  assert.match(page, /requestedRequirementFocus/);
  assert.match(editor, /focusRequirementType/);
  assert.match(editor, /补充能证明技能的真实经历/);
  assert.match(editor, /补充能证明专项经验的真实经历/);
  assert.match(editor, /先补教育事实，再回到岗位优先级重算/);
  assert.match(editor, /学历层级、专业和岗位明确要求的院校限定/);
  assert.match(editor, /\+ 添加教育经历/);
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
