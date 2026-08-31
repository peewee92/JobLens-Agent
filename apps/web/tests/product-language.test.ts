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

test("prepare keeps imported-batch feedback handoff grounded in the current match report", async () => {
  const page = await source("app/jobs/[id]/prepare/page.tsx");

  assert.match(page, /returnImport/);
  assert.match(page, /返回本次导入/);
  assert.match(page, /fetchMatchRanking/);
  assert.match(page, /fetchLatestUserFeedback/);
  assert.match(page, /RecommendationFeedback/);
  assert.match(page, /记录你的投递判断/);
  assert.match(page, /不会改写 MatchReport 或自动投递/);
  assert.match(page, /暂不开放反馈，避免覆盖未知历史判断/);
  assert.match(page, /返回本次导入查看反馈进度/);
  assert.match(page, /successHref=/);
  assert.match(page, /afterFeedback=/);
  assert.match(page, /afterMatchJobs/);
  assert.match(page, /afterMatchQuery/);
  assert.match(page, /返回本次导入继续下一步/);
});

test("import detail summarizes zero-provider next steps for the imported batch", async () => {
  const page = await source("app/imports/[id]/page.tsx");

  assert.match(page, /这批岗位下一步怎么处理/);
  assert.match(page, /已有当前匹配结果/);
  assert.match(page, /要求已准备，可进入匹配/);
  assert.match(page, /岗位要求还未准备好/);
  assert.match(page, /fetchJobRequirementReleaseReadiness/);
  assert.match(page, /fetchJobDetail/);
  assert.match(page, /fetchMatchRanking/);
  assert.match(page, /fetchMatchReviewReadiness/);
  assert.match(page, /ImportBatchMatch jobIds=\{matchReadyJobs\} importId=\{id\}/);
  assert.match(page, /这批岗位当前的匹配结果/);
  assert.match(page, /fetchLatestUserFeedback/);
  assert.match(page, /RecommendationFeedback/);
  assert.match(page, /已反馈 \{feedbackCoveredCount\}\/\{matchedCount\}/);
  assert.match(page, /feedbackDecisionCounts/);
  assert.match(page, /尚未判断/);
  assert.match(page, /requestedAfterFeedbackJobId/);
  assert.match(page, /刚完成一项投递判断/);
  assert.match(page, /已经按更新后的 latest UserFeedback、当前 Ranking 与 hard blocker 重新计算下一步/);
  assert.match(page, /下一步：判断/);
  assert.match(page, /下一步：处理真实 Evidence/);
  assert.match(page, /不声称反馈已完成，也不据此改变下一步/);
  assert.match(page, /pendingClearedReports/);
  assert.match(page, /pendingBlockedReports/);
  assert.match(page, /下一岗位：/);
  assert.match(page, /当前没有 hard blocker，先完成它的投递判断最省步骤/);
  assert.match(page, /先完成这个岗位的投递判断/);
  assert.match(page, /这批岗位现在还剩哪些待办/);
  assert.match(page, /可直接做投递判断/);
  assert.match(page, /仍需补真实证据/);
  assert.match(page, /当前已完成处理/);
  assert.match(page, /只有明确“不考虑”的岗位才退出后续 Evidence 待办/);
  assert.match(page, /下一步：\{nextStep\}/);
  assert.match(page, /已退出待办/);
  assert.match(page, /先补真实证据/);
  assert.match(page, /当前判断已记录/);
  assert.match(page, /做投递判断/);
  assert.match(page, /它们继续留在 Evidence Loop/);
  assert.match(page, /这些岗位当前都有 hard blocker/);
  assert.match(page, /先处理下一项真实证据/);
  assert.match(page, /batchEvidenceQueueTargets/);
  assert.match(page, /当前证据行动会影响/);
  assert.match(page, /这项证据对应当前待办队列中的/);
  assert.match(page, /完成真实 Evidence 核实后，优先回看它们的 Re-match 结果/);
  assert.match(page, /hard blocker 状态暂时无法可靠读取/);
  assert.match(page, /这批已有 MatchReport 的岗位都已经记录了投递判断/);
  assert.match(page, /id=\{`feedback-\$\{report\.reportId\}`\}/);
  assert.match(page, /投递判断：\{feedbackDecisionShortLabel/);
  assert.match(page, /本批处理进度：已处理 \{batchProcessedCount\}\/\{batchProcessingTotal\}/);
  assert.match(page, /还剩 \{batchProcessingRemaining\} 个岗位没有完成当前处理/);
  assert.match(page, /还没形成 MatchReport/);
  assert.match(page, /等待投递判断/);
  assert.match(page, /等待 Evidence 改善/);
  assert.match(page, /还没形成 MatchReport 的岗位卡在哪里/);
  assert.match(page, /Requirement 已 ready，可显式 Match/);
  assert.match(page, /Requirement 仍 blocked/);
  assert.match(page, /Readiness 暂无法确认/);
  assert.match(page, /ready 只代表可以由你显式发起 Match，不会自动调用 Provider/);
  assert.match(page, /无法确认的岗位不会被猜成 ready 或 blocked/);
  assert.match(page, /当前主行动：先判断/);
  assert.match(page, /当前主行动：先匹配 \{matchReadyJobs\.length\} 个已准备岗位/);
  assert.match(page, /当前主行动：先处理一个岗位要求/);
  assert.match(page, /当前主行动：继续下一项 Evidence/);
  assert.match(page, /不会用未知 readiness \/ blocker 状态替你猜/);
  assert.match(page, /id="batch-match"/);
  assert.match(page, /当前批次可以视为处理完成/);
  assert.match(page, /不把 unknown 状态塞进某个可执行队列/);
  assert.match(page, /不计算批次完成进度，也不会把未知状态误报成“已处理”/);
  assert.match(page, /batchProcessingComplete/);
  assert.match(page, /当前反馈状态暂时读取失败/);
  assert.match(page, /fetchMatchBlockerSummary/);
  assert.match(page, /selectNextEvidencePriority/);
  assert.match(page, /这批岗位下一项最值得核实的证据/);
  assert.match(page, /明确 rejected 的岗位不会继续驱动补证据/);
  assert.match(page, /去核实这项真实经历/);
  assert.match(page, /focusRequirementId=/);
  assert.match(page, /focusImpactJobs=/);
  assert.match(page, /previousEvidenceQueueResults/);
  assert.match(page, /刚才这项 Evidence 核实后，待办岗位发生了什么/);
  assert.match(page, /原计划观察 \{focusImpactJobIds\.length\} 个待办岗位/);
  assert.match(page, /已有 \{verifiedPreviousEvidenceQueueCount\} 个可以基于当前事实下结论/);
  assert.match(page, /<span>原计划观察<\/span>/);
  assert.match(page, /已解除 hard blocker/);
  assert.match(page, /仍有 hard blocker/);
  assert.match(page, /下一条剩余 Requirement/);
  assert.match(page, /当前下一 Evidence action 会覆盖这条 Requirement/);
  assert.match(page, /当前下一 Evidence action 不覆盖这条 Requirement/);
  assert.match(page, /currentEvidenceQueuePriorityTargets/);
  assert.match(page, /当前 action 会先帮助这些待办岗位/);
  assert.match(page, /这些目标来自当前 Evidence action 对真实 Requirement ID 的命中/);
  assert.match(page, /当前 action 没有可可靠列出的其他 queue target/);
  assert.match(page, /当前没有可可靠生成的下一 Evidence action/);
  assert.match(page, /当前 blocker 事实无法解析出 Requirement 原文/);
  assert.match(page, /暂无法验证/);
  assert.match(page, /现在最值得做/);
  assert.match(page, /clearedPendingDecisionReports/);
  assert.match(page, /按当前 Ranking 顺序/);
  assert.match(page, /先判断这个最高排名的已解锁岗位/);
  assert.match(page, /这项已完成 UserFeedback，不再占用本轮主下一步/);
  assert.match(page, /继续下一项 Evidence/);
  assert.match(page, /现在先不自动改节奏/);
  assert.match(page, /不把未知当成“补证据无效”/);
  assert.match(page, /可以转入投递判断/);
  assert.match(page, /缺少可比较的前后 MatchReport 或当前事实读取不完整/);
  assert.match(page, /returnImport=/);
  assert.match(page, /showImprovement/);
  assert.match(page, /fetchMatchImprovement/);
  assert.match(page, /这次补证据后，本批哪些岗位改善了/);
  assert.match(page, /newlySupportingEvidence/);
  assert.match(page, /已支撑岗位要求/);
  assert.match(page, /这个岗位现在还差什么/);
  assert.match(page, /下一条先看/);
  assert.match(page, /转向投递判断/);
  assert.match(page, /查看完整依据并进入投递判断/);
  assert.match(page, /已经明确标记为“不考虑”/);
  assert.match(page, /不会继续推动投递，也不会再要求为它补证据/);
  assert.match(page, /不判断它是否已经没有硬缺口/);
  assert.match(page, /现有 provenance 没有精确指出是哪条新增 Evidence/);
  assert.match(page, /这些已解决 Requirement 不会继续驱动下一证据行动/);
  assert.match(page, /当前 blocker 汇总仍包含已解决 Requirement/);
  assert.match(page, /当前这批岗位没有新的、可可靠确认的下一证据行动/);
  assert.match(page, /不会在打开页面时重新匹配或调用 Provider/);
  assert.match(page, /当前无法可靠读取反馈或硬条件缺口/);
  assert.match(page, /matchRecommendationLabels\[report\.recommendation\]/);
  assert.match(page, /有依据要求 \{report\.evidenceLinks\.length\} 条/);
  assert.match(page, /report\.summary \|\| matchRecommendationDescriptions/);
  assert.match(page, /查看全部优先投递/);
  assert.match(page, /还需处理岗位要求/);
  assert.match(page, /Requirement 已准备、等待匹配/);
  assert.match(page, /暂时无法确认的岗位/);
  assert.match(page, /blockers\.slice\(0, 2\)/);
  assert.match(page, /不会自动分析岗位、调用 Provider 或替你发起匹配/);
  assert.match(page, /真正的匹配仍必须由你显式点击发起/);
  assert.match(page, /不会被误报为“尚未准备”/);
  assert.match(page, /afterMatchJobs/);
  assert.match(page, /刚完成显式 Match 后，这些岗位进入了哪里/);
  assert.match(page, /等待投递判断/);
  assert.match(page, /进入 Evidence Loop/);
  assert.match(page, /暂无法确认迁移/);
  assert.match(page, /nextAfterMatchApplyReport/);
  assert.match(page, /下一步：先判断/);
  assert.match(page, /current Ranking 最高；没有新增评分/);
  assert.match(page, /下一步：处理当前最高价值 Evidence/);
  assert.match(page, /afterMatchPrepareQuery/);
  assert.match(page, /下一步：继续判断本轮 Match 解锁的/);
  assert.match(page, /本轮解锁岗位已判断完，继续处理真实 Evidence/);
  assert.match(page, /afterMatchJobs=\$\{encodeURIComponent\(requestedAfterMatchJobIds\.join\(","\)\)\}/);
  assert.match(page, /当前不强行切换到投递判断或下一 Evidence/);
  assert.match(page, /这轮 Match 里原本 blocked 的岗位，Re-match 后发生了什么/);
  assert.match(page, /本次实际观察/);
  assert.match(page, /新增解锁/);
  assert.match(page, /新增解锁岗位已经重新进入上面的 post-Match 投递判断队列/);
  assert.match(page, /为什么下一 Evidence 仍值得继续/);
  assert.match(page, /当前既有 Evidence Priority 仍精确命中这轮 Match 中/);
  assert.match(page, /它没有精确命中这轮 Match 里刚验证仍 blocked 的岗位/);
  assert.match(page, /这组岗位现在还剩多少要处理/);
  assert.match(page, /已解锁并完成反馈/);
  assert.match(page, /已解锁、等待反馈/);
  assert.match(page, /仍需 Evidence/);
  assert.match(page, /不会把单纯解除 blocker 当成用户已经做完投递判断/);
  assert.match(page, /当前只有不可验证结果，因此这里不声称 Evidence 已经改善或没有改善这些岗位/);
  assert.match(page, /这组 post-Match Evidence 已经收敛/);
  assert.match(page, /现在剩下的不是继续补 Evidence，而是完成已解锁岗位的真实 UserFeedback/);
  assert.match(page, /这里只结束这组观察目标，不代表整个 Import Batch 已完成/);
  assert.match(page, /回到批次：匹配/);
  assert.match(page, /回到批次：先处理一个岗位要求/);
  assert.match(page, /这批导入岗位也已经全部完成当前处理/);
  assert.match(page, /这批岗位最终怎么处理/);
  assert.match(page, /优先继续关注/);
  assert.match(page, /保留观察/);
  assert.match(page, /明确不考虑/);
  assert.match(page, /以下顺序直接沿用 current Ranking，不新增最终评分/);
  assert.match(page, /整批完成后，下一步做什么/);
  assert.match(page, /准备申请：/);
  assert.match(page, /复核观察岗位：/);
  assert.match(page, /调整求职偏好/);
  assert.match(page, /导入下一批岗位/);
  assert.match(page, /已验证 Evidence 改善/);
  assert.match(page, /不会把未知 readiness 猜成可执行状态/);
  assert.match(page, /不会再次运行 Match 或调用 Provider/);
});

test("import evidence continuation returns to the batch only after explicit rematch", async () => {
  const profile = await source("app/profile/page.tsx");
  const recommendations = await source("app/recommendations/page.tsx");
  const refresh = await source("components/recommendation-refresh.tsx");

  assert.match(profile, /returnImport/);
  assert.match(profile, /query\.set\("afterMatchJobs", afterMatchJobs\)/);
  assert.match(profile, /\^\[A-Za-z0-9_-\]\{1,120\}\$/);
  assert.match(recommendations, /returnImportId/);
  assert.match(recommendations, /afterMatchJobIds/);
  assert.match(recommendations, /showImprovement=1/);
  assert.match(recommendations, /focusImpactJobs=\$\{encodeURIComponent\(focusImpactJobIds\.join\(","\)\)\}/);
  assert.match(recommendations, /afterMatchJobs=\$\{encodeURIComponent\(afterMatchJobIds\.join\(","\)\)\}/);
  assert.match(refresh, /returnHref/);
  assert.match(refresh, /state\.kind === "success" && pendingJobIds\.length === 0/);
  assert.match(refresh, /回到这批岗位看改善结果/);
});

test("import batch matching is explicit, bounded, and never auto-resumes", async () => {
  const component = await source("components/import-batch-match.tsx");

  assert.match(component, /fetch\("\/api\/match-batch"/);
  assert.match(component, /maxReadyJobs: 10/);
  assert.match(component, /onClick=\{run\}/);
  assert.match(component, /只有你点击后才会执行/);
  assert.match(component, /可能调用已配置的模型/);
  assert.match(component, /setPendingJobIds\(result\.resumeJobIds\)/);
  assert.match(component, /item\.status === "succeeded"/);
  assert.match(component, /afterMatchJobs=/);
  assert.match(component, /router\.replace/);
  assert.doesNotMatch(component, /setTimeout\([^)]*run/);
  assert.doesNotMatch(component, /await run\(\)/);
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
  const refresh = await source("components/recommendation-refresh.tsx");

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
  assert.match(page, /focusJob=\$\{job\.id\}/);
  assert.match(page, /recomputeJob/);
  assert.match(page, /你刚为「/);
  assert.match(page, /排到重新计算的最前面/);
  assert.match(page, /focus-job-/);
  assert.match(page, /rankedDisplayItems/);
  assert.match(page, /blockedDisplayItems/);
  assert.match(page, /data-report-id/);
  assert.match(page, /focusReportId=/);
  assert.match(refresh, /scrollIntoView/);
  assert.match(refresh, /focus-job-\$\{focusJobId\}/);
  assert.match(refresh, /renderedReportId !== focusReportId/);
  assert.match(refresh, /framesRemaining = 120/);
  assert.match(page, /这次补充的证据已经让它进入优先候选/);
  assert.match(page, /重算后仍有 .* 条硬条件缺口/);
  assert.match(page, /硬条件缺口较少的岗位排在前面/);
  assert.match(page, /这不是成功概率/);
  assert.match(page, /哪些资料最可能解锁更多岗位判断/);
  assert.match(page, /下一步最值得先核实/);
  assert.match(page, /selectNextEvidencePriority/);
  assert.match(page, /normalizedCapability/);
  assert.match(page, /这个具体要求目前影响/);
  assert.match(page, /下一步会先围绕仍在考虑的岗位收敛/);
  assert.match(page, /只影响“不考虑”岗位的缺口不会继续驱动你补证据/);
  assert.match(page, /Match、Eligibility 和历史 blocker 事实不会因此被改写/);
  assert.match(page, /如果你确实有对应经历/);
  assert.match(page, /不要为了排名补造经历/);
  assert.match(page, /nextEvidenceProfileHref/);
  assert.match(page, /focusRequirementId=/);
  assert.match(page, /focusCapability=/);
  assert.match(page, /focusRequirementText=/);
  assert.match(page, /focusImpactJobs=/);
  assert.match(page, /evidenceActionHistory=/);
  assert.match(page, /最近连续两次核实同类事实后都拿到了可比较但未改善的结果/);
  assert.match(page, /行动前预期影响 vs\. 这次重算结果/);
  assert.match(page, /拿到了可比较的前后 MatchReport，其中 .* 个出现可验证改善/);
  assert.match(page, /当前缺少可比较的前后 MatchReport，暂不下结论/);
  assert.match(page, /不会冒充“没有改善”/);
  assert.match(page, /未改善也不代表这项经历无价值/);
  assert.match(page, /nextEvidencePriority\.examples\[0\]/);
  assert.match(page, /nextEvidenceJobId/);
  assert.match(page, /当前 Profile 没有足够证据支撑这些硬条件/);
  assert.match(page, /补充我的真实经历/);
  assert.match(page, /补教育经历/);
  assert.match(page, /focus=education/);
  assert.match(page, /fetchMatchBlockerSummary/);
  assert.match(page, /fetchMatchImprovement/);
  assert.match(page, /和上一次资料版本相比/);
  assert.match(page, /previousProfileVersion/);
  assert.match(page, /currentProfileVersion/);
  assert.match(page, /这次资料更新也改善了其他岗位/);
  assert.match(page, /这次哪些真实经历进入了岗位匹配依据/);
  assert.match(page, /newlySupportingEvidence/);
  assert.match(page, /supportingRequirements/);
  assert.match(page, /支撑 .* 个当前岗位/);
  assert.match(page, /Promise\.allSettled/);
  assert.match(page, /这次已经补齐的岗位要求/);
  assert.match(page, /这次新增需要核实的硬条件/);
  assert.match(page, /resolvedRequirements/);
  assert.match(page, /newlyMissingRequirements/);
  assert.match(page, /已经少了 .* 条硬条件缺口/);
  assert.match(page, /previousMissingRequirementCount/);
  assert.match(page, /currentMissingRequirementCount/);
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
  assert.match(page, /回到申请准备查看更新后的清单/);
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
  assert.match(page, /requestedFocusJob/);
  assert.match(page, /requestedFocusRequirementId/);
  assert.match(page, /focusRequirementId/);
  assert.match(page, /recomputeJob/);
  assert.match(page, /requestedRequirementFocus/);
  assert.match(page, /requestedFocusCapability/);
  assert.match(page, /requestedFocusRequirementText/);
  assert.match(page, /requestedFocusImpactJobs/);
  assert.match(page, /query\.set\("focusImpactJobs", focusImpactJobs\)/);
  assert.match(page, /requestedEvidenceActionHistory/);
  assert.match(page, /query\.set\("evidenceActionHistory", evidenceActionHistory\)/);
  assert.match(page, /split\(","\)/);
  assert.match(page, /slice\(0, 3\)/);
  assert.match(page, /slice\(0, 120\)/);
  assert.match(page, /slice\(0, 300\)/);
  assert.match(page, /query\.set\("focusRequirementId", focusRequirementId\)/);
  assert.match(page, /query\.set\("focusCapability", focusCapability\)/);
  assert.match(page, /query\.set\("focusRequirementText", focusRequirementText\)/);
  assert.match(editor, /focusRequirementType/);
  assert.match(editor, /focusCapability/);
  assert.match(editor, /当前重点核实/);
  assert.match(editor, /当前岗位要求/);
  assert.match(editor, /核对状态：已有直接 Evidence/);
  assert.match(editor, /核对状态：只有技能名，证据还不足/);
  assert.match(editor, /核对状态：当前没有精确事实/);
  assert.match(editor, /没有对应经历就保留缺口/);
  assert.match(editor, /否则保留缺口/);
  assert.match(editor, /仅用于核对你的真实经历，不会自动写入 Profile/);
  assert.match(editor, /只补你真实做过、能被现有经历证明的内容/);
  assert.match(editor, /补充能证明技能的真实经历/);
  assert.match(editor, /补充能证明专项经验的真实经历/);
  assert.match(editor, /先补教育事实，再回到岗位优先级重算/);
  assert.match(editor, /学历层级、专业和岗位明确要求的院校限定/);
  assert.match(editor, /\+ 添加教育经历/);
  assert.match(editor, /\+ 添加项目经历/);
  assert.match(editor, /\+ 添加工作经历/);
  assert.match(editor, /不会替你预填能力或经历事实/);
  assert.match(editor, /addEvidenceForCurrentRequirement\("project"\)/);
  assert.match(editor, /addEvidenceForCurrentRequirement\("work"\)/);
  assert.match(editor, /把这条新经历连接到当前技能/);
  assert.match(editor, /JobLens 不会自动替你关联/);
  assert.match(editor, /本轮不会根据岗位要求自动创建 Skill/);
  assert.match(editor, /我确认具备“\{focusCapability\}”，新增技能并关联这条经历/);
  assert.match(editor, /新技能会以“待确认”熟练度加入草稿/);
  assert.match(editor, /最终是否支撑当前 Requirement 只以保存后的 Re-match 为准/);
  assert.match(editor, /createFocusedSkillAndLinkEvidence/);
  assert.match(editor, /activeRequirementFocus === "skill"/);
  assert.match(editor, /level: "unknown"/);
  assert.match(editor, /linkFocusedEvidenceToExistingSkill/);
  assert.match(editor, /focusedExactSkillIndex >= 0/);
  assert.match(editor, /focusedSkillEvidenceIssue/);
  assert.match(editor, /保存前需要修复当前技能的 Evidence 关联/);
  assert.match(editor, /当前 Evidence 关联还没完整，暂不保存/);
  assert.match(editor, /JobLens 不会静默改写关联/);
  assert.match(editor, /重新选择真实 Evidence 后再保存/);
  assert.match(editor, /用当前真实经历“\{focusedEvidenceDraft\.key\.trim\(\)\}”修复关联/);
  assert.match(editor, /只会移除已确认失效的旧引用/);
  assert.match(editor, /不会自动创建新能力/);
  assert.match(editor, /repairFocusedSkillWithCurrentEvidence/);
  assert.match(editor, /改名会影响已有技能关联/);
  assert.match(editor, /直接保存新简称会让这些既有引用失效/);
  assert.match(editor, /这里只迁移已有引用，不会新增技能或能力判断/);
  assert.match(editor, /将这些已有技能引用迁移到/);
  assert.match(editor, /有经历简称已改名，但已有技能仍引用旧简称/);
  assert.match(editor, /请先迁移这些既有引用，或手动取消旧关联后再保存/);
  assert.match(editor, /migrateRenamedEvidenceReferences/);
});

test("focused evidence action returns with exact requirement identity and reports rematch outcome", async () => {
  const recommendations = await source("app/recommendations/page.tsx");

  assert.match(recommendations, /nextEvidenceRequirement/);
  assert.match(recommendations, /focusRequirementId=/);
  assert.match(recommendations, /resolvedRequirementIds\.includes\(focusRequirementId\)/);
  assert.match(recommendations, /missingRequirementIds\.includes\(focusRequirementId\)/);
  assert.match(recommendations, /刚才核实的要求：现在已有匹配依据/);
  assert.match(recommendations, /刚才核实的要求：仍缺少足够证据/);
  assert.match(recommendations, /刚才核实的要求：当前已不在硬缺口中/);
  assert.match(recommendations, /同一 Requirement ID 确认的变化/);
  assert.match(recommendations, /focusedRequirementEvidence/);
  assert.match(recommendations, /supportingRequirements\.some/);
  assert.match(recommendations, /requirement\.requirementId === focusRequirementId/);
  assert.match(recommendations, /这次直接进入该要求匹配依据的真实经历/);
  assert.match(recommendations, /首次进入这条 Requirement ID 的 Evidence/);
  assert.match(recommendations, /历史比较不足以证明一定是新增 Evidence 造成的/);
  assert.match(recommendations, /selectNextEvidencePriority/);
  assert.match(recommendations, /recentlyVerifiedRequirementToExclude/);
  assert.match(recommendations, /shouldDeferImmediateEvidenceRepeat/);
  assert.match(recommendations, /不会立刻重复推荐/);
  assert.match(recommendations, /下一项最值得核实/);
  assert.match(recommendations, /已解决的 Requirement 和只影响“不考虑”岗位的行动都不会继续占用下一步行动位/);
  assert.match(recommendations, /继续核实下一项真实证据/);
});

test("import improvement explains why the next evidence action changed", async () => {
  const page = await source("app/imports/[id]/page.tsx");

  assert.match(page, /为什么下一步是这一项/);
  assert.match(page, /刚补的真实 Evidence 已解决/);
  assert.match(page, /出现可验证改善/);
  assert.match(page, /这些要求已经从候选行动中排除/);
  assert.match(page, /当前仍未解决、且影响仍在考虑岗位最多的是下面这一项/);
  assert.match(page, /showImprovement && resolvedBatchRequirementIds\.size > 0/);
});

test("cleared import jobs show a fact-based apply decision summary", async () => {
  const page = await source("app/imports/[id]/page.tsx");

  assert.match(page, /现在为什么值得进入投递判断/);
  assert.match(page, /当前 Ranking 建议/);
  assert.match(page, /当前 MatchReport 依据/);
  assert.match(page, /Requirement → Evidence 关联/);
  assert.match(page, /你的当前判断/);
  assert.match(page, /不代表系统替你决定投递/);
  assert.match(page, /latestFeedback\?\.decision/);
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

test("focused evidence actions classify exact profile facts before asking for more evidence", async () => {
  const editor = await source("components/profile-editor.tsx");

  assert.match(editor, /"direct_evidence"/);
  assert.match(editor, /"skill_only"/);
  assert.match(editor, /"no_exact_fact"/);
  assert.match(editor, /核对状态：已有直接 Evidence/);
  assert.match(editor, /核对状态：只有技能名，证据还不足/);
  assert.match(editor, /核对状态：当前没有精确事实/);
  assert.match(editor, /如果可以，不必重复新增/);
  assert.match(editor, /不会根据相似词自动推断你具备这项能力/);
  assert.match(editor, /item\.name\.trim\(\)\.toLocaleLowerCase\(\) === normalizedCapability/);
  assert.match(editor, /matchingSkills\.flatMap/);
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

test("empty evidence content warns about affected skills before final review", async () => {
  const editor = await source("components/profile-editor.tsx");

  assert.match(editor, /清空内容会让已有技能失去证据/);
  assert.match(editor, /只移除这些技能引用/);
  assert.match(editor, /detachEmptyEvidenceReferences/);
  assert.match(editor, /不会自动替你补事实/);
});

test("global dangling evidence issues offer explicit locate and remove actions", async () => {
  const editor = await source("components/profile-editor.tsx");

  assert.match(editor, /定位到这项技能/);
  assert.match(editor, /只移除这些失效引用/);
  assert.match(editor, /focusSkillEditor\(issue\.skillIndex\)/);
  assert.match(editor, /removeDanglingEvidenceReferences/);
  assert.match(editor, /profile-skill-\$\{index\}/);
});
