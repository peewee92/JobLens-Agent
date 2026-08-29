import Link from "next/link";

import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {RecommendationRefresh} from "@/components/recommendation-refresh";
import {RecommendationRequirementAnalysis} from "@/components/recommendation-requirement-analysis";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobPage,
  fetchMatchBlockerSummary,
  fetchMatchImprovement,
  fetchMatchRanking,
  fetchLatestUserFeedback,
  fetchMatchReviewReadiness,
  fetchRecommendationCoverage,
} from "@/lib/backend";
import type {RequirementType, SearchParams, UserFeedbackRecord} from "@/lib/contracts";
import {
  appendEvidenceActionHistory,
  consideredAffectedJobCount,
  listEvidencePriorityImpactTargets,
  parseEvidenceActionHistory,
  repeatedEvidenceActionKeys,
  selectEvidenceFocusJobId,
  selectNextEvidencePriority,
} from "@/lib/evidence-priority";
import {formatSalary} from "@/lib/format";
import {
  classifyMatchImprovementOutcome,
  shouldDeferImmediateEvidenceRepeat,
} from "@/lib/match-improvement-outcome";
import {
  matchRecommendationClasses,
  matchRecommendationDescriptions,
  matchRecommendationLabels,
} from "@/lib/match-report";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

function blockerRequirementTypeLabel(requirementType: RequirementType): string {
  switch (requirementType) {
    case "education":
      return "教育";
    case "skill":
      return "技能";
    case "experience":
      return "经验";
    case "domain":
      return "领域";
    case "responsibility":
      return "职责";
    default:
      return "其他";
  }
}

export default async function RecommendationsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const focusJobId = typeof params.focusJob === "string" ? params.focusJob : null;
  const focusRequirementId = typeof params.focusRequirementId === "string"
    ? params.focusRequirementId.trim().slice(0, 120) || null
    : null;
  const focusCapability = typeof params.focusCapability === "string"
    ? params.focusCapability.trim().slice(0, 120) || null
    : null;
  const focusRequirementText = typeof params.focusRequirementText === "string"
    ? params.focusRequirementText.trim().slice(0, 300) || null
    : null;
  const focusImpactJobIds = typeof params.focusImpactJobs === "string"
    ? params.focusImpactJobs.split(",").map((jobId) => jobId.trim().slice(0, 120)).filter(Boolean).slice(0, 3)
    : [];
  const previousEvidenceActionHistory = parseEvidenceActionHistory(
    typeof params.evidenceActionHistory === "string" ? params.evidenceActionHistory : null,
  );
  let jobs;
  try {
    jobs = await fetchJobPage(new URLSearchParams({limit: "50", offset: "0"}));
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位，请稍后重试。")
        : "暂时无法读取岗位，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
        </section>
        <ServiceError message={message} />
      </>
    );
  }

  if (jobs.items.length === 0) {
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
          <p className="lede">先加入真实岗位，JobLens 才能基于你的真实经历做有依据的选择。</p>
        </section>
        <section className="empty-state">
          <h2>还没有岗位可以比较</h2>
          <p>先从浏览器插件或导入页添加一批你真正考虑的岗位。</p>
          <Link className="button" href="/import">添加岗位</Link>
        </section>
      </>
    );
  }

  let ranking;
  try {
    ranking = await fetchMatchRanking(
      jobs.items.map((job) => job.id),
      {includeBlocked: true, topN: 50},
    );
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法生成岗位优先级，请稍后重试。")
        : "暂时无法生成岗位优先级，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
          <p className="lede">这里只使用已经生成并保存的完整匹配结果，不会为了凑排名临时编造依据。</p>
        </section>
        <ServiceError message={message} />
        <div className="actions">
          <Link className="button-secondary" href="/jobs">查看岗位</Link>
        </div>
      </>
    );
  }

  const jobById = new Map(jobs.items.map((job) => [job.id, job]));
  const availableReports = ranking.items
    .map((report) => ({report, job: jobById.get(report.jobId)}))
    .filter((item) => item.job !== undefined);
  const rankedCandidates = availableReports.filter(({report}) => report.recommendation !== "blocked");
  const rankedItems = rankedCandidates
    .slice(0, 5)
    .map((item, index) => ({...item, rank: index + 1}));
  const focusRankedCandidateIndex = focusJobId
    ? rankedCandidates.findIndex(({report}) => report.jobId === focusJobId)
    : -1;
  const focusRankedItem = focusRankedCandidateIndex >= 0
    ? {...rankedCandidates[focusRankedCandidateIndex], rank: focusRankedCandidateIndex + 1}
    : null;
  const rankedDisplayItems = focusRankedItem && !rankedItems.some(({report}) => report.jobId === focusJobId)
    ? [...rankedItems, focusRankedItem]
    : rankedItems;

  const blockedCandidates = availableReports.filter(({report}) => report.recommendation === "blocked");
  const blockedItems = blockedCandidates.slice(0, 5);
  const focusBlockedItem = focusJobId
    ? blockedCandidates.find(({report}) => report.jobId === focusJobId) ?? null
    : null;
  const blockedDisplayItems = focusBlockedItem && !blockedItems.some(({report}) => report.jobId === focusJobId)
    ? [...blockedItems, focusBlockedItem]
    : blockedItems;
  let blockerSummary = null;
  try {
    blockerSummary = await fetchMatchBlockerSummary(jobs.items.map((job) => job.id));
  } catch {
    // Ranking remains usable even if this secondary explanation read model is unavailable.
  }

  let reviewableJobIds: string[] = [];
  try {
    const readiness = await fetchMatchReviewReadiness();
    reviewableJobIds = readiness.reviewableJobIds;
  } catch {
    // Existing ranking remains readable even when the refresh readiness check is unavailable.
  }

  // Prioritize the job the user just supplemented evidence for, then the rest of the ready pool.
  const recomputeJobIds = focusJobId
    ? [focusJobId, ...reviewableJobIds.filter((id) => id !== focusJobId)]
    : reviewableJobIds;
  const focusJobTitle = focusJobId ? (jobById.get(focusJobId)?.title ?? null) : null;
  const focusJobReport = focusJobId
    ? availableReports.find((item) => item.report.jobId === focusJobId) ?? null
    : null;
  const focusJobNowBlocked = focusJobReport?.report.recommendation === "blocked";
  let focusImprovement = null;
  if (focusJobId && focusJobReport) {
    try {
      focusImprovement = await fetchMatchImprovement(
        focusJobId,
        focusJobReport.report.reportId,
      );
    } catch {
      // The current recommendation remains usable when comparison history is unavailable.
    }
  }

  const visibleImpactCandidates = [...rankedDisplayItems, ...blockedDisplayItems]
    .filter(({report}) => report.jobId !== focusJobId)
    .slice(0, 10);
  const visibleImpactResults = focusJobId
    ? await Promise.allSettled(
      visibleImpactCandidates.map(async ({report, job}) => ({
        report,
        job,
        improvement: await fetchMatchImprovement(report.jobId, report.reportId),
      })),
    )
    : [];
  const otherImprovedJobs = visibleImpactResults.flatMap((result) => {
    if (result.status !== "fulfilled") return [];
    const {improvement} = result.value;
    if (!improvement.comparable || improvement.previousProfileVersion === improvement.currentProfileVersion) return [];
    if (
      improvement.resolvedRequirementIds.length === 0
      && improvement.previousRecommendation === improvement.currentRecommendation
    ) return [];
    return [result.value];
  });

  const evidenceImpactById = new Map<
    string,
    {summary: string; jobs: Map<string, {title: string; requirementTexts: Set<string>}>}
  >();
  const collectEvidenceImpact = (
    jobId: string,
    jobTitle: string,
    improvement: NonNullable<typeof focusImprovement>,
  ) => {
    for (const evidence of improvement.newlySupportingEvidence) {
      const impact = evidenceImpactById.get(evidence.evidenceId) ?? {
        summary: evidence.summary,
        jobs: new Map<string, {title: string; requirementTexts: Set<string>}>(),
      };
      const jobImpact = impact.jobs.get(jobId) ?? {
        title: jobTitle,
        requirementTexts: new Set<string>(),
      };
      for (const requirement of evidence.supportingRequirements) {
        jobImpact.requirementTexts.add(requirement.originalText);
      }
      impact.jobs.set(jobId, jobImpact);
      evidenceImpactById.set(evidence.evidenceId, impact);
    }
  };
  if (focusJobId && focusJobTitle && focusImprovement?.comparable) {
    collectEvidenceImpact(focusJobId, focusJobTitle, focusImprovement);
  }
  for (const {job, improvement} of otherImprovedJobs) {
    if (job) collectEvidenceImpact(job.id, job.title, improvement);
  }
  const evidenceImpacts = Array.from(evidenceImpactById.entries()).map(([evidenceId, impact]) => ({
    evidenceId,
    summary: impact.summary,
    jobs: Array.from(impact.jobs.entries()).map(([jobId, item]) => ({
      jobId,
      title: item.title,
      requirementTexts: Array.from(item.requirementTexts),
    })),
  }));

  const focusedRequirementResolved = Boolean(
    focusRequirementId && focusImprovement?.resolvedRequirementIds.includes(focusRequirementId),
  );
  const focusedRequirementStillMissing = Boolean(
    focusRequirementId && focusJobReport?.report.missingRequirementIds.includes(focusRequirementId),
  );
  const focusedRequirementEvidence = focusRequirementId && focusImprovement?.comparable
    ? focusImprovement.newlySupportingEvidence.filter((evidence) =>
      evidence.supportingRequirements.some(
        (requirement) => requirement.requirementId === focusRequirementId,
      ),
    )
    : [];

  let coverage = null;
  try {
    coverage = await fetchRecommendationCoverage();
  } catch {
    // Current recommendations remain usable when the read-only coverage planner is unavailable.
  }

  let feedbackEntries: ReadonlyArray<readonly [string, UserFeedbackRecord | null]> = availableReports.map(
    ({report}) => [report.reportId, null] as const,
  );
  let feedbackStateAvailable = availableReports.length === 0;
  try {
    const latestFeedback = await fetchLatestUserFeedback(
      availableReports.map(({report}) => report.reportId),
    );
    const latestByReportId = new Map(
      latestFeedback.feedback.map((item) => [item.matchReportId, item] as const),
    );
    feedbackEntries = availableReports.map(({report}) => [
      report.reportId,
      latestByReportId.get(report.reportId) ?? null,
    ] as const);
    feedbackStateAvailable = true;
  } catch {
    // Recommendations remain usable, but unknown feedback state must not be reported as zero.
  }
  const feedbackByReportId = new Map(feedbackEntries);
  const feedbackCompletedCount = feedbackStateAvailable
    ? feedbackEntries.filter(([, feedback]) => feedback !== null).length
    : null;
  const feedbackRemainingCount = feedbackCompletedCount === null
    ? null
    : Math.max(availableReports.length - feedbackCompletedCount, 0);
  const nextFeedbackReportId = feedbackStateAvailable
    ? availableReports.find(({report}) => feedbackByReportId.get(report.reportId) === null)?.report.reportId ?? null
    : null;
  const feedbackByJobId = new Map(
    availableReports.flatMap(({report}) => {
      const feedback = feedbackByReportId.get(report.reportId);
      return feedback ? [[report.jobId, feedback] as const] : [];
    }),
  );
  const focusedRequirementShouldPause = shouldDeferImmediateEvidenceRepeat(
    focusImprovement,
    focusRequirementId,
    focusedRequirementStillMissing,
  );
  const recentlyVerifiedRequirementToExclude = focusRequirementId
    && (focusImprovement?.resolvedRequirementIds.includes(focusRequirementId) || focusedRequirementShouldPause)
    ? focusRequirementId
    : null;
  const currentEvidenceActionKey = focusRequirementId && focusCapability
    ? `${typeof params.focusRequirement === "string" ? params.focusRequirement : "skill"}:${focusCapability.trim().toLowerCase()}`
    : null;
  const evidenceActionHistory = focusedRequirementShouldPause
    ? appendEvidenceActionHistory(previousEvidenceActionHistory, currentEvidenceActionKey)
    : [];
  const deprioritizedEvidenceActionKeys = repeatedEvidenceActionKeys(evidenceActionHistory);
  const nextEvidencePriority = blockerSummary
    ? selectNextEvidencePriority(
      blockerSummary.priorityActions,
      feedbackStateAvailable ? feedbackByJobId : new Map(),
      recentlyVerifiedRequirementToExclude,
      deprioritizedEvidenceActionKeys,
    )
    : null;
  const evidenceFeedbackByJobId = feedbackStateAvailable ? feedbackByJobId : new Map<string, UserFeedbackRecord>();
  const nextEvidenceConsideredJobCount = nextEvidencePriority
    ? consideredAffectedJobCount(nextEvidencePriority, evidenceFeedbackByJobId)
    : 0;
  const nextEvidenceJobId = selectEvidenceFocusJobId(
    nextEvidencePriority,
    evidenceFeedbackByJobId,
  );
  const nextEvidenceRequirement = nextEvidencePriority && nextEvidenceJobId
    ? blockerSummary?.jobBlockers
      .find((item) => item.jobId === nextEvidenceJobId)
      ?.requirements.find((requirement) => nextEvidencePriority.requirementIds.includes(requirement.requirementId)) ?? null
    : null;
  const nextEvidenceImpactTargets = blockerSummary
    ? listEvidencePriorityImpactTargets(
      nextEvidencePriority,
      blockerSummary.jobBlockers,
      evidenceFeedbackByJobId,
    )
    : [];
  const nextEvidenceProfileHref = nextEvidencePriority
    ? `/profile?next=/recommendations&focusRequirement=${encodeURIComponent(nextEvidencePriority.requirementType)}&focusJob=${encodeURIComponent(nextEvidenceJobId ?? "")}${nextEvidenceRequirement ? `&focusRequirementId=${encodeURIComponent(nextEvidenceRequirement.requirementId)}` : ""}${nextEvidencePriority.normalizedCapability ? `&focusCapability=${encodeURIComponent(nextEvidencePriority.normalizedCapability)}` : ""}${nextEvidencePriority.examples[0] ? `&focusRequirementText=${encodeURIComponent(nextEvidencePriority.examples[0])}` : ""}${nextEvidenceImpactTargets.length > 0 ? `&focusImpactJobs=${encodeURIComponent(nextEvidenceImpactTargets.slice(0, 3).map((target) => target.jobId).join(","))}` : ""}${evidenceActionHistory.length > 0 ? `&evidenceActionHistory=${encodeURIComponent(evidenceActionHistory.join(","))}` : ""}#profile-evidence-focus`
    : null;
  const recommendationJobTitleById = new Map(
    jobs.items.map((job) => [job.id, job.title] as const),
  );
  const currentReportByJobId = new Map(
    availableReports.map(({report}) => [report.jobId, report] as const),
  );
  const expectedImpactResults = await Promise.all(
    focusImpactJobIds.map(async (jobId) => {
      const currentReport = currentReportByJobId.get(jobId);
      let improvement = jobId === focusJobId ? focusImprovement : null;
      if (!improvement && currentReport) {
        try {
          improvement = await fetchMatchImprovement(jobId, currentReport.reportId);
        } catch {
          // Missing comparison evidence must stay unknown instead of being mislabeled as no improvement.
        }
      }
      return {
        jobId,
        title: recommendationJobTitleById.get(jobId) ?? jobId,
        outcome: classifyMatchImprovementOutcome(improvement),
      };
    }),
  );
  const expectedImpactImprovedCount = expectedImpactResults.filter((item) => item.outcome === "improved").length;
  const expectedImpactVerifiedCount = expectedImpactResults.filter((item) => item.outcome !== "unverifiable").length;

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">优先投递</p>
        <h1>哪些岗位最值得我先投？</h1>
        <p className="lede">
          基于你确认过的经历、当前求职偏好和已经生成的完整匹配结果排序。这里只比较有可追溯依据的岗位，不把“匹配分数”当成功概率。
        </p>
      </section>

      {focusJobId && focusJobTitle ? (
        <section className="notice focus-return-banner">
          <strong>你刚为「{focusJobTitle}」补充了证据</strong>
          <p>
            下面已把这个岗位排到重新计算的最前面。重算后，这里会显示它现在是否值得优先投——而不是只停留在之前的硬缺口。
          </p>
          {focusJobReport ? (
            <p className="muted">
              {focusJobNowBlocked
                ? `重算后它仍有 ${focusJobReport.report.missingRequirementIds.length} 条硬条件缺口，可以继续补下面列出的证据。`
                : "这次补充的证据已经让它进入优先候选，下面也会按新结果排序。"}
            </p>
          ) : null}
          {focusRequirementId && focusJobReport ? (
            <div className={`review-result ${focusedRequirementResolved ? "review-accepted" : "review-pending"}`}>
              <strong>
                {focusedRequirementResolved
                  ? "刚才核实的要求：现在已有匹配依据"
                  : focusedRequirementStillMissing
                    ? "刚才核实的要求：仍缺少足够证据"
                    : "刚才核实的要求：当前已不在硬缺口中"}
              </strong>
              {focusCapability ? <p>核实能力：{focusCapability}</p> : null}
              {focusRequirementText ? <p>岗位要求：{focusRequirementText}</p> : null}
              <p className="muted">
                {focusedRequirementResolved
                  ? "这是根据前后 MatchReport 的同一 Requirement ID 确认的变化，不是根据关键词猜测。"
                  : focusedRequirementStillMissing
                    ? "这次保存后该 Requirement ID 仍在当前 MatchReport 的硬缺口里；如果没有真实经历可以证明，就继续保留缺口。"
                    : "当前报告已不把这条 Requirement ID 作为硬缺口，但历史比较不足以证明一定是新增 Evidence 造成的，因此这里只报告当前事实。"}
              </p>
              {focusedRequirementResolved && focusedRequirementEvidence.length > 0 ? (
                <div className="focus-improvement-facts">
                  <strong>这次直接进入该要求匹配依据的真实经历</strong>
                  <ul>
                    {focusedRequirementEvidence.slice(0, 3).map((evidence) => (
                      <li key={evidence.evidenceId}>{evidence.summary}</li>
                    ))}
                  </ul>
                  <p className="muted">
                    这里只显示前后 Profile 版本比较后，首次进入这条 Requirement ID 的 Evidence；不会用相似关键词或岗位文案反推你的经历。
                  </p>
                </div>
              ) : null}
              {(focusedRequirementResolved || focusedRequirementShouldPause) && nextEvidencePriority && nextEvidenceProfileHref ? (
                <div className="focus-improvement-facts">
                  <strong>
                    下一项最值得核实：{nextEvidencePriority.normalizedCapability ?? `${blockerRequirementTypeLabel(nextEvidencePriority.requirementType)}类事实`}
                  </strong>
                  <p>
                    当前仍影响 {nextEvidencePriority.affectedJobCount} 个已分析岗位，其中 {nextEvidenceConsideredJobCount} 个没有被你明确标记为“不考虑”，共对应 {nextEvidencePriority.missingRequirementCount} 条硬条件缺口。
                    {focusedRequirementShouldPause
                      ? "刚核实但可比较结果仍未改善的 Requirement 本轮不会立刻重复推荐；这只是避免机械重复，不代表你没有这项能力。"
                      : "已解决的 Requirement 和只影响“不考虑”岗位的行动都不会继续占用下一步行动位。"}
                  </p>
                  <div className="actions">
                    <Link className="button" href={nextEvidenceProfileHref}>
                      继续核实下一项真实证据 →
                    </Link>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
          {expectedImpactResults.length > 0 ? (
            <div className="focus-improvement-facts">
              <strong>行动前预期影响 vs. 这次重算结果</strong>
              <p>
                行动前你优先核实了 {expectedImpactResults.length} 个仍在考虑岗位；目前有 {expectedImpactVerifiedCount} 个拿到了可比较的前后 MatchReport，其中 {expectedImpactImprovedCount} 个出现可验证改善。
              </p>
              <ul>
                {expectedImpactResults.map((item) => (
                  <li key={item.jobId}>
                    <Link href={`/jobs/${item.jobId}`}>{item.title}</Link>
                    {item.outcome === "improved"
                      ? "：这次有可验证改善"
                      : item.outcome === "unchanged"
                        ? "：已完成前后比较，这次暂未观察到可验证改善"
                        : "：当前缺少可比较的前后 MatchReport，暂不下结论"}
                  </li>
                ))}
              </ul>
              <p className="muted">
                每个行动前记录的目标岗位都会单独读取这次 Profile 更新前后的 MatchReport；读取失败或历史不足时保持“暂不下结论”，不会冒充“没有改善”。已确认未改善也不代表这项经历无价值，更不会把相关性强行归因给某一条 Evidence。
              </p>
            </div>
          ) : null}
          {focusImprovement?.comparable ? (
            <div className="focus-improvement">
              <p className="focus-job-note">
                {focusImprovement.resolvedRequirementIds.length > 0
                  ? `和上一次资料版本相比，已经少了 ${focusImprovement.resolvedRequirementIds.length} 条硬条件缺口（${focusImprovement.previousMissingRequirementCount} → ${focusImprovement.currentMissingRequirementCount}）。`
                  : focusImprovement.currentMissingRequirementCount < (focusImprovement.previousMissingRequirementCount ?? 0)
                    ? `硬条件缺口从 ${focusImprovement.previousMissingRequirementCount} 条降到 ${focusImprovement.currentMissingRequirementCount} 条。`
                    : "和上一次资料版本相比，硬条件缺口暂时没有减少。"}
              </p>
              {focusImprovement.resolvedRequirements.length > 0 ? (
                <div className="focus-improvement-facts">
                  <strong>这次已经补齐的岗位要求</strong>
                  <ul>
                    {focusImprovement.resolvedRequirements.slice(0, 3).map((requirement) => (
                      <li key={requirement.requirementId}>{requirement.originalText}</li>
                    ))}
                  </ul>
                  {focusImprovement.resolvedRequirements.length > 3 ? (
                    <p className="muted">另有 {focusImprovement.resolvedRequirements.length - 3} 条要求已经不再是硬缺口。</p>
                  ) : null}
                </div>
              ) : null}
              {focusImprovement.newlyMissingRequirements.length > 0 ? (
                <div className="focus-improvement-facts">
                  <strong>这次新增需要核实的硬条件</strong>
                  <ul>
                    {focusImprovement.newlyMissingRequirements.slice(0, 3).map((requirement) => (
                      <li key={requirement.requirementId}>{requirement.originalText}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
          {evidenceImpacts.length > 0 ? (
            <div className="focus-improvement-facts">
              <strong>这次哪些真实经历进入了岗位匹配依据</strong>
              <ul>
                {evidenceImpacts.slice(0, 3).map((impact) => (
                  <li key={impact.evidenceId}>
                    <span>{impact.summary}</span>
                    <span className="muted"> · 支撑 {impact.jobs.length} 个当前岗位</span>
                    <ul>
                      {impact.jobs.slice(0, 3).map((jobImpact) => (
                        <li key={jobImpact.jobId}>
                          <Link href={`/jobs/${jobImpact.jobId}`}>{jobImpact.title}</Link>
                          {jobImpact.requirementTexts.length > 0
                            ? `：${jobImpact.requirementTexts.slice(0, 2).join("；")}`
                            : ""}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {otherImprovedJobs.length > 0 ? (
            <div className="focus-improvement-facts">
              <strong>这次资料更新也改善了其他岗位</strong>
              <ul>
                {otherImprovedJobs.slice(0, 3).map(({job, improvement}) => (
                  job ? (
                    <li key={improvement.currentReportId}>
                      <Link href={`/jobs/${job.id}`}>{job.title}</Link>
                      {improvement.resolvedRequirementIds.length > 0
                        ? `：少了 ${improvement.resolvedRequirementIds.length} 条硬条件缺口`
                        : improvement.previousRecommendation
                          ? `：从「${matchRecommendationLabels[improvement.previousRecommendation]}」变为「${matchRecommendationLabels[improvement.currentRecommendation]}」`
                          : ""}
                    </li>
                  ) : null
                ))}
              </ul>
              {otherImprovedJobs.length > 3 ? (
                <p className="muted">另有 {otherImprovedJobs.length - 3} 个当前展示岗位也发生了可验证改善。</p>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="result-bar">
        <span>岗位池 {jobs.total} 个 · 本轮比较前 {jobs.items.length} 个</span>
        <span>已有完整匹配 {availableReports.length} 个 · 当前优先候选 {rankedItems.length} 个</span>
        <span>
          {feedbackCompletedCount === null
            ? "反馈状态暂不可用"
            : `已反馈 ${feedbackCompletedCount}/${availableReports.length}`}
        </span>
      </div>

      {availableReports.length > 0 && feedbackRemainingCount !== null && feedbackRemainingCount > 0 ? (
        <section className="notice">
          <strong>还差 {feedbackRemainingCount} 个岗位需要你的真实判断</strong>
          <p>你的反馈会帮助 JobLens 判断推荐是否符合真实求职选择。即使系统当前不建议优先投，也可以记录“感兴趣 / 再看看 / 不考虑”。</p>
          {nextFeedbackReportId ? (
            <div className="actions">
              <Link className="button-secondary" href={`#feedback-${nextFeedbackReportId}`}>
                继续完成反馈 →
              </Link>
            </div>
          ) : null}
        </section>
      ) : null}

      {availableReports.length > 0 && feedbackRemainingCount === null ? (
        <section className="notice">
          <strong>暂时无法确认已保存的反馈进度</strong>
          <p>岗位推荐仍可正常查看；JobLens 不会把读取失败误报成“0 个已反馈”。</p>
        </section>
      ) : null}

      {availableReports.length === 0 ? (
        <section className="empty-state">
          <h2>还没有当前资料版本的完整匹配结果</h2>
          <p>如果你刚更新过职业背景，旧 MatchReport 会自动失效；可以直接重新计算当前输入已准备好的岗位，不需要逐个打开岗位。</p>
          <div className="actions">
            <Link className="button-secondary" href="/jobs">查看岗位</Link>
            <Link className="button-ghost" href="/profile?next=/recommendations#profile-evidence">检查我的背景</Link>
          </div>
        </section>
      ) : null}

      <RecommendationRefresh
        jobIds={recomputeJobIds}
        focusJobId={focusJobId}
        focusJobTitle={focusJobTitle}
        focusReportId={focusJobReport?.report.reportId ?? null}
      />

      {rankedItems.length > 0 ? (
        <section className="job-list" aria-label="优先投递岗位">
          {rankedDisplayItems.map(({report, job, rank}) => {
            if (!job) return null;
            return (
              <article
                className={job.id === focusJobId ? "job-card focus-job-card" : "job-card"}
                id={job.id === focusJobId ? `focus-job-${job.id}` : `feedback-${report.reportId}`}
                data-report-id={report.reportId}
                key={report.reportId}
              >
                <div className="job-card-header">
                  <div>
                    <p className="eyebrow">第 {rank} 优先</p>
                    <h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2>
                    <p className="company">{job.company}</p>
                  </div>
                  <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
                </div>

                <div className="tags">
                  <span className={`tag ${matchRecommendationClasses[report.recommendation]}`}>
                    {matchRecommendationLabels[report.recommendation]}
                  </span>
                  {job.area ? <span className="tag">{job.area}</span> : null}
                  <RemoteStatusPill status={job.remoteStatus} />
                  <span className="tag">有依据要求 {report.evidenceLinks.length} 条</span>
                  {feedbackStateAvailable ? (
                    <span className="tag">
                      {feedbackByReportId.get(report.reportId) ? "已反馈" : "待反馈"}
                    </span>
                  ) : null}
                </div>

                <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p>
                {job.id === focusJobId ? (
                  <p className="focus-job-note">
                    {focusJobNowBlocked
                      ? `你刚为这个岗位补充了证据，重算后仍有 ${report.missingRequirementIds.length} 条硬条件缺口。`
                      : "你刚为这个岗位补充的证据已生效，它现在进入优先候选。"}
                  </p>
                ) : null}
                {report.missingRequirementIds.length > 0 ? (
                  <p className="muted">仍有 {report.missingRequirementIds.length} 条要求缺少足够证据，需要投递前重点确认。</p>
                ) : null}

                <div className="actions">
                  <Link className="button-secondary" href={`/jobs/${job.id}`}>查看为什么 →</Link>
                </div>
                <RecommendationFeedback
                  matchReportId={report.reportId}
                  jobId={job.id}
                  initialDecision={feedbackByReportId.get(report.reportId)?.decision ?? null}
                  initialReasons={feedbackByReportId.get(report.reportId)?.reasons ?? []}
                  initialNote={feedbackByReportId.get(report.reportId)?.note ?? null}
                />
              </article>
            );
          })}
        </section>
      ) : availableReports.length > 0 ? (
        <section className="notice">
          <strong>当前没有值得优先投的已分析岗位</strong>
          <p>现有完整匹配结果都触发了明确硬条件缺口。下面仍会列出这些岗位和原因，避免把“没有优先候选”误解成系统没有结果。</p>
        </section>
      ) : null}

      {blockerSummary && blockerSummary.categories.length > 0 ? (
        <section className="detail-card">
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">先补事实，再重算</p>
              <h2>哪些资料最可能解锁更多岗位判断？</h2>
              <p className="muted">
                这里只表示“当前 Profile 没有足够证据支撑这些硬条件”，不等于断言你没有对应能力或经历。
              </p>
            </div>
            <Link className="button-secondary" href="/profile?next=/recommendations#profile-evidence">补充我的真实经历</Link>
          </div>
          {nextEvidencePriority ? (
            <div className="notice evidence-next-action">
              <strong>
                下一步最值得先核实：{nextEvidencePriority.normalizedCapability ?? `${blockerRequirementTypeLabel(nextEvidencePriority.requirementType)}类事实`}
              </strong>
              <p>
                这个具体要求目前影响 {nextEvidencePriority.affectedJobCount} 个已分析岗位，其中 {nextEvidenceConsideredJobCount} 个没有被你明确标记为“不考虑”，共对应 {nextEvidencePriority.missingRequirementCount} 条当前硬条件。
                下一步会先围绕仍在考虑的岗位收敛；只影响“不考虑”岗位的缺口不会继续驱动你补证据。范围相同时，再优先你明确标记为“感兴趣 / 再看看”的岗位。Match、Eligibility 和历史 blocker 事实不会因此被改写。
                如果你确实有对应经历，优先把真实证据补进 Profile，再回来重算；如果没有，就保留缺口，不要为了排名补造经历。
              </p>
              {deprioritizedEvidenceActionKeys.size > 0 ? (
                <p className="muted">
                  最近连续两次核实同类事实后都拿到了可比较但未改善的结果，所以本轮优先换一个仍有价值的 blocker；如果它仍是唯一真实缺口，系统不会永久隐藏它。读取不到可比较结果时不会记入这段历史。
                </p>
              ) : null}
              {nextEvidencePriority.examples.length > 0 ? (
                <ul>
                  {nextEvidencePriority.examples.slice(0, 2).map((example) => <li key={example}>{example}</li>)}
                </ul>
              ) : null}
              {nextEvidenceImpactTargets.length > 0 ? (
                <div className="focus-improvement-facts">
                  <strong>这一步会优先帮助你核实这些仍在考虑的岗位</strong>
                  <ul>
                    {nextEvidenceImpactTargets.slice(0, 3).map((target) => (
                      <li key={target.jobId}>
                        <Link href={`/jobs/${target.jobId}`}>
                          {recommendationJobTitleById.get(target.jobId) ?? target.jobId}
                        </Link>
                        {target.requirementTexts.length > 0
                          ? `：${target.requirementTexts.slice(0, 2).join("；")}`
                          : ""}
                      </li>
                    ))}
                  </ul>
                  {nextEvidenceImpactTargets.length > 3 ? (
                    <p className="muted">另有 {nextEvidenceImpactTargets.length - 3} 个仍在考虑的岗位受同一证据行动影响。</p>
                  ) : null}
                  <p className="muted">
                    这里只展示当前 Match blocker 的真实岗位和 Requirement。它表示“这项事实值得先核实”，不承诺补充后一定能解锁这些岗位；最终仍以真实 Evidence 保存后的 Re-match 为准。
                  </p>
                </div>
              ) : null}
              <div className="actions">
                <Link
                  className="button"
                  href={nextEvidenceProfileHref ?? "/profile?next=/recommendations#profile-evidence"}
                >
                  去核实并补真实证据 →
                </Link>
              </div>
            </div>
          ) : null}

          <div className="readiness-blocker-list">
            {blockerSummary.categories.slice(0, 3).map((category) => (
              <div className="readiness-blocker-item" key={category.requirementType}>
                <strong>
                  {category.requirementType === "education"
                    ? "教育经历证据"
                    : category.requirementType === "skill"
                      ? "技能证据"
                      : category.requirementType === "experience"
                        ? "专项经验依据"
                        : category.requirementType === "domain"
                          ? "行业领域依据"
                          : category.requirementType === "responsibility"
                            ? "职责经历依据"
                            : "其他硬条件依据"}
                </strong>
                <p>
                  影响 {category.affectedJobCount} 个已分析岗位，共 {category.missingRequirementCount} 条当前无法证实的硬条件。
                </p>
                {category.examples.length > 0 ? (
                  <ul>
                    {category.examples.map((example) => <li key={example}>{example}</li>)}
                  </ul>
                ) : null}
                {category.requirementType === "education" ? (
                  <div className="actions">
                    <Link
                      className="button-secondary"
                      href="/profile?next=/recommendations&focus=education#profile-evidence"
                    >
                      补教育经历 →
                    </Link>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          {blockerSummary.unresolvedMissingRequirementIds.length > 0 ? (
            <p className="inline-error">
              有 {blockerSummary.unresolvedMissingRequirementIds.length} 条历史缺口已无法和当前岗位要求对应，请重新生成这些岗位的完整匹配建议后再判断。
            </p>
          ) : null}
        </section>
      ) : null}

      {coverage ? (
        <section className="detail-card">
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">扩大比较范围</p>
              <h2>下一批先分析哪些岗位？</h2>
              <p className="muted">
                JobLens 先找出还没进入完整匹配、但和你明确求职方向更接近的岗位。这里仅使用岗位标题、城市、薪资等明确偏好信号排序，不用 AI 猜一个隐藏匹配分数。
              </p>
            </div>
          </div>

          <div className="summary-grid eval-summary-grid">
            <div className="summary-card">
              <span>已有完整匹配</span>
              <strong>{coverage.currentReportCount}</strong>
            </div>
            <div className="summary-card">
              <span>已准备好，可直接重算</span>
              <strong>{coverage.matchReadyWithoutReportCount}</strong>
            </div>
            <div className="summary-card">
              <span>还需要岗位要求分析</span>
              <strong>{coverage.requirementAnalysisNeededCount}</strong>
            </div>
          </div>

          {coverage.matchReadyWithoutReportCount > 0 ? (
            <p className="notice">
              有 {coverage.matchReadyWithoutReportCount} 个岗位的事实输入已经准备好但还没有当前 MatchReport，可以用上面的“重新计算”继续扩充排名。
            </p>
          ) : null}

          {coverage.nextAnalysisCandidates.length > 0 ? (
            <>
              <RecommendationRequirementAnalysis
                jobIds={coverage.nextAnalysisCandidates.map((candidate) => candidate.jobId)}
              />
              <div className="job-list" aria-label="下一批岗位要求分析候选">
              {coverage.nextAnalysisCandidates.map((candidate, index) => (
                <article className="job-card" key={candidate.jobId}>
                  <div className="job-card-header">
                    <div>
                      <p className="eyebrow">建议第 {index + 1} 个分析</p>
                      <h3><Link href={`/jobs/${candidate.jobId}`}>{candidate.title}</Link></h3>
                      <p className="company">{candidate.company}</p>
                    </div>
                    <span className="salary">
                      {formatSalary(candidate.salaryMinK, candidate.salaryMaxK)}
                    </span>
                  </div>
                  <div className="tags">
                    {candidate.intentSignals.map((signal) => (
                      <span className="tag" key={signal}>{signal}</span>
                    ))}
                    {candidate.area && !candidate.intentSignals.some((signal) => signal.startsWith("目标城市：")) ? (
                      <span className="tag">{candidate.area}</span>
                    ) : null}
                  </div>
                  <p className="muted">
                    这个岗位当前缺的是可信的 JobRequirement 输入；先完成岗位要求分析，再进入 Eligibility、Match 和 Ranking。
                  </p>
                  <div className="actions">
                    <Link className="button-secondary" href={`/jobs/${candidate.jobId}`}>
                      查看并分析岗位要求 →
                    </Link>
                  </div>
                </article>
              ))}
              </div>
            </>
          ) : coverage.requirementAnalysisNeededCount > 0 ? (
            <p className="muted">目前没有能依据明确求职偏好排出优先级的待分析岗位，可以从岗位列表继续选择。</p>
          ) : (
            <p className="muted">当前前 {coverage.consideredJobCount} 个岗位里，没有新的岗位要求分析任务需要优先处理。</p>
          )}

          <details className="technical-details">
            <summary>查看覆盖率技术详情</summary>
            <p className="code">
              considered={coverage.consideredJobCount}/{coverage.totalJobCount} · profileBlocked={coverage.profileBlockedCount} · otherBlocked={coverage.otherBlockedCount}
            </p>
            <p className="code">
              dbWrites={coverage.dbWrites} · providerCalls={coverage.providerCalls} · traces={coverage.traceRunsCreated}
            </p>
          </details>
        </section>
      ) : null}

      {blockedDisplayItems.length > 0 ? (
        <section>
          <div className="section-heading">
            <p className="eyebrow">暂不优先</p>
            <h2>这些岗位当前有明确硬条件缺口</h2>
            <p className="muted">
              同样属于暂不建议投递时，会先参考你的明确求职偏好，再把硬条件缺口较少的岗位排在前面，方便你先核实或补证据；这不是成功概率。
            </p>
          </div>
          <div className="job-list" aria-label="当前不建议投递岗位">
            {blockedDisplayItems.map(({report, job}) => {
              if (!job) return null;
              const jobBlocker = blockerSummary?.jobBlockers.find((item) => item.jobId === job.id);
              return (
                <article
                  className={job.id === focusJobId ? "job-card focus-job-card" : "job-card"}
                  id={job.id === focusJobId ? `focus-job-${job.id}` : `feedback-${report.reportId}`}
                  data-report-id={report.reportId}
                  key={report.reportId}
                >
                  <div className="job-card-header">
                    <div>
                      <h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2>
                      <p className="company">{job.company}</p>
                    </div>
                    <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
                  </div>
                  <div className="tags">
                    <span className={`tag ${matchRecommendationClasses.blocked}`}>
                      {matchRecommendationLabels.blocked}
                    </span>
                    {job.area ? <span className="tag">{job.area}</span> : null}
                    <span className="tag">明显缺失 {report.missingRequirementIds.length} 条</span>
                    {feedbackStateAvailable ? (
                      <span className="tag">
                        {feedbackByReportId.get(report.reportId) ? "已反馈" : "待反馈"}
                      </span>
                    ) : null}
                  </div>
                  <p>{report.summary || matchRecommendationDescriptions.blocked}</p>
                  {job.id === focusJobId ? (
                    <p className="focus-job-note">
                      {focusJobNowBlocked
                        ? `你刚为这个岗位补充了证据，重算后仍有 ${report.missingRequirementIds.length} 条硬条件缺口。`
                        : "你刚为这个岗位补充的证据已生效，它现在进入优先候选。"}
                    </p>
                  ) : null}
                  {jobBlocker && jobBlocker.requirements.length > 0 ? (
                    <div className="recommendation-blocker-facts">
                      <strong>当前缺少足够 Profile 证据的硬条件</strong>
                      <ul>
                        {jobBlocker.requirements.slice(0, 3).map((requirement) => (
                          <li key={requirement.requirementId}>
                            <span className="tag">{blockerRequirementTypeLabel(requirement.requirementType)}</span>
                            <span>{requirement.originalText}</span>
                            <Link
                              className="recommendation-blocker-action"
                              href={`/profile?next=/recommendations&focusRequirement=${requirement.requirementType}&focusJob=${job.id}#profile-evidence-focus`}
                            >
                              去补对应证据 →
                            </Link>
                          </li>
                        ))}
                      </ul>
                      {jobBlocker.requirements.length > 3 ? (
                        <p className="muted">还有 {jobBlocker.requirements.length - 3} 条已解析硬条件，可进入岗位详情继续核实。</p>
                      ) : null}
                    </div>
                  ) : null}
                  {jobBlocker && jobBlocker.unresolvedMissingRequirementIds.length > 0 ? (
                    <p className="muted">
                      另有 {jobBlocker.unresolvedMissingRequirementIds.length} 条历史缺口无法与当前岗位要求对应，需要重新生成完整匹配结果后再判断。
                    </p>
                  ) : null}
                  <div className="actions">
                    <Link className="button-secondary" href={`/jobs/${job.id}`}>查看硬条件缺口 →</Link>
                  </div>
                  <RecommendationFeedback
                    matchReportId={report.reportId}
                    jobId={job.id}
                    initialDecision={feedbackByReportId.get(report.reportId)?.decision ?? null}
                    initialReasons={feedbackByReportId.get(report.reportId)?.reasons ?? []}
                    initialNote={feedbackByReportId.get(report.reportId)?.note ?? null}
                  />
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="notice product-trust-note">
        <strong>排序依据是什么？</strong>
        <p>
          先看硬条件是否通过，再看已有经历对岗位要求的证据支撑，最后只在同一推荐等级里参考你的求职偏好；同为 blocked 时，再用明确硬缺口数量帮助安排核实顺序。没有完整 MatchReport 的岗位不会被偷偷猜一个名次。
        </p>
      </section>
    </>
  );
}
