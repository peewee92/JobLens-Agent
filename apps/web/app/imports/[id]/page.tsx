import Link from "next/link";
import {notFound} from "next/navigation";

import {ImportBatchMatch} from "@/components/import-batch-match";
import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {ImportOutcomePill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchImportDetail,
  fetchJobDetail,
  fetchJobRequirementReleaseReadiness,
  fetchLatestUserFeedback,
  fetchMatchBlockerSummary,
  fetchMatchImprovement,
  fetchMatchRanking,
  fetchMatchReviewReadiness,
} from "@/lib/backend";
import {
  consideredAffectedJobCount,
  listEvidencePriorityImpactTargets,
  selectEvidenceFocusJobId,
  selectNextEvidencePriority,
} from "@/lib/evidence-priority";
import {formatDateTime} from "@/lib/format";
import {
  matchRecommendationClasses,
  matchRecommendationDescriptions,
  matchRecommendationLabels,
} from "@/lib/match-report";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function ImportDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{id: string}>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const {id} = await params;
  const query = await searchParams;
  const showImprovement = query.showImprovement === "1";
  let detail;
  try {
    detail = await fetchImportDetail(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) {
      notFound();
    }
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取这批岗位的处理结果，请稍后重试。")
        : "暂时无法读取这批岗位的处理结果，请稍后重试。";
    return <ServiceError message={message} />;
  }

  const importedJobIds = detail.items.flatMap((item) => (item.jobId ? [item.jobId] : []));
  const [rankingResult, matchReviewReadinessResult, jobDetailResults, readinessResults] = await Promise.all([
    importedJobIds.length > 0
      ? fetchMatchRanking(importedJobIds, {includeBlocked: true})
          .then((value) => ({status: "fulfilled" as const, value}))
          .catch((reason) => ({status: "rejected" as const, reason}))
      : Promise.resolve({
          status: "fulfilled" as const,
          value: {items: [], count: 0, dbWrites: 0, providerCalls: 0, traceRunsCreated: 0},
        }),
    fetchMatchReviewReadiness()
      .then((value) => ({status: "fulfilled" as const, value}))
      .catch((reason) => ({status: "rejected" as const, reason})),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobDetail(jobId))),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobRequirementReleaseReadiness(jobId))),
  ]);
  const rankingAvailable = rankingResult.status === "fulfilled";
  const rankedJobIds = new Set(
    rankingAvailable ? rankingResult.value.items.map((item) => item.jobId) : [],
  );
  const matchInputReadinessAvailable = matchReviewReadinessResult.status === "fulfilled";
  const matchInputReadyJobIds = new Set(
    matchInputReadinessAvailable ? matchReviewReadinessResult.value.reviewableJobIds : [],
  );
  const jobDetailById = new Map(
    jobDetailResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.id, result.value] as const] : [],
    ),
  );
  const readinessByJobId = new Map(
    readinessResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.jobId, result.value] as const] : [],
    ),
  );
  const matchedReports = rankingAvailable
    ? rankingResult.value.items.filter((item) => importedJobIds.includes(item.jobId))
    : [];
  const matchedCount = matchedReports.length;
  const latestFeedbackResult = matchedReports.length > 0
    ? await fetchLatestUserFeedback(matchedReports.map((report) => report.reportId))
        .then((value) => ({status: "fulfilled" as const, value}))
        .catch((reason) => ({status: "rejected" as const, reason}))
    : {status: "fulfilled" as const, value: {feedback: [], count: 0, dbWrites: 0, providerCalls: 0, traceRunsCreated: 0}};
  const feedbackAvailable = latestFeedbackResult.status === "fulfilled";
  const latestFeedbackByReportId = new Map(
    feedbackAvailable
      ? latestFeedbackResult.value.feedback.map((item) => [item.matchReportId, item] as const)
      : [],
  );
  const feedbackCoveredCount = feedbackAvailable ? latestFeedbackByReportId.size : 0;
  const improvementResults = showImprovement && matchedReports.length > 0
    ? await Promise.allSettled(
        matchedReports.map(async (report) => ({
          report,
          improvement: await fetchMatchImprovement(report.jobId, report.reportId),
        })),
      )
    : [];
  const improvedBatchJobs = improvementResults.flatMap((result) => {
    if (result.status !== "fulfilled") return [];
    const {report, improvement} = result.value;
    if (!improvement.comparable || improvement.previousProfileVersion === improvement.currentProfileVersion) return [];
    const improved = improvement.resolvedRequirementIds.length > 0
      || improvement.previousRecommendation !== improvement.currentRecommendation;
    return improved ? [{report, improvement}] : [];
  });
  const resolvedBatchRequirementIds = new Set(
    improvedBatchJobs.flatMap(({improvement}) => improvement.resolvedRequirementIds),
  );
  const feedbackByJobId = new Map(
    matchedReports.flatMap((report) => {
      const feedback = latestFeedbackByReportId.get(report.reportId);
      return feedback ? [[report.jobId, feedback] as const] : [];
    }),
  );
  const blockerSummaryResult = matchedReports.length > 0
    ? await fetchMatchBlockerSummary(importedJobIds)
        .then((value) => ({status: "fulfilled" as const, value}))
        .catch((reason) => ({status: "rejected" as const, reason}))
    : {status: "fulfilled" as const, value: null};
  const blockerByJobId = new Map(
    blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
      ? blockerSummaryResult.value.jobBlockers.map((item) => [item.jobId, item] as const)
      : [],
  );
  const rawBatchEvidenceAction = feedbackAvailable && blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? selectNextEvidencePriority(blockerSummaryResult.value.priorityActions, feedbackByJobId, null)
    : null;
  const batchEvidenceAction = rawBatchEvidenceAction
    && !rawBatchEvidenceAction.requirementIds.some((requirementId) => resolvedBatchRequirementIds.has(requirementId))
    ? rawBatchEvidenceAction
    : null;
  const batchEvidenceActionStaleAfterImprovement = Boolean(
    rawBatchEvidenceAction
    && rawBatchEvidenceAction.requirementIds.some((requirementId) => resolvedBatchRequirementIds.has(requirementId)),
  );
  const batchEvidenceFocusJobId = selectEvidenceFocusJobId(batchEvidenceAction, feedbackByJobId);
  const batchEvidenceRequirement = batchEvidenceAction && batchEvidenceFocusJobId && blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? blockerSummaryResult.value.jobBlockers
        .find((item) => item.jobId === batchEvidenceFocusJobId)
        ?.requirements.find((requirement) => batchEvidenceAction.requirementIds.includes(requirement.requirementId)) ?? null
    : null;
  const batchEvidenceImpactTargets = blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? listEvidencePriorityImpactTargets(batchEvidenceAction, blockerSummaryResult.value.jobBlockers, feedbackByJobId)
    : [];
  const batchEvidenceConsideredJobCount = batchEvidenceAction
    ? consideredAffectedJobCount(batchEvidenceAction, feedbackByJobId)
    : 0;
  const batchEvidenceProfileHref = batchEvidenceAction
    ? `/profile?next=/recommendations&returnImport=${encodeURIComponent(id)}&focusRequirement=${encodeURIComponent(batchEvidenceAction.requirementType)}&focusJob=${encodeURIComponent(batchEvidenceFocusJobId ?? "")}${batchEvidenceRequirement ? `&focusRequirementId=${encodeURIComponent(batchEvidenceRequirement.requirementId)}` : ""}${batchEvidenceAction.normalizedCapability ? `&focusCapability=${encodeURIComponent(batchEvidenceAction.normalizedCapability)}` : ""}${batchEvidenceAction.examples[0] ? `&focusRequirementText=${encodeURIComponent(batchEvidenceAction.examples[0])}` : ""}${batchEvidenceImpactTargets.length > 0 ? `&focusImpactJobs=${encodeURIComponent(batchEvidenceImpactTargets.slice(0, 3).map((target) => target.jobId).join(","))}` : ""}#profile-evidence-focus`
    : null;
  const matchReadyCount = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  ).length;
  const requirementBlockedCount = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  }).length;
  const unknownReadinessCount = importedJobIds.length - matchedCount - matchReadyCount - requirementBlockedCount;
  const matchReadyJobs = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  );
  const requirementBlockedJobs = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  });
  const unknownReadinessJobs = importedJobIds.filter((jobId) => {
    if (rankedJobIds.has(jobId)) {
      return false;
    }
    const readiness = readinessByJobId.get(jobId);
    return !readiness || (
      readiness.releaseEligible && (!rankingAvailable || !matchInputReadinessAvailable)
    );
  });
  const jobLabel = (jobId: string) => {
    const job = jobDetailById.get(jobId);
    return job ? `${job.title} · ${job.company}` : `岗位 ${jobId}`;
  };
  const feedbackDecisionLabel = (decision: "interested" | "maybe" | "rejected" | undefined) => {
    if (decision === "interested") return "你已标记为感兴趣";
    if (decision === "maybe") return "你已标记为再看看";
    if (decision === "rejected") return "你已标记为不考虑";
    return "你还没有记录投递判断";
  };

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">添加结果</p>
        <h1>这批岗位处理得怎么样</h1>
        <p className="lede">
          这里告诉你哪些岗位已经添加、哪些更新了已有信息，以及哪些没有成功处理。
        </p>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>文件中的岗位</span><strong>{detail.received}</strong></div>
        <div className="summary-card"><span>新增</span><strong>{detail.created}</strong></div>
        <div className="summary-card"><span>信息已更新</span><strong>{detail.updated}</strong></div>
        <div className="summary-card"><span>未添加</span><strong>{detail.skipped}</strong></div>
      </div>

      {importedJobIds.length > 0 ? (
        <section className="detail-card" style={{marginBottom: "1rem"}}>
          <h2>这批岗位下一步怎么处理</h2>
          <p className="notice">
            这里只读取现有 Requirement / Match 事实，不会自动分析岗位、调用 Provider 或替你发起匹配。
          </p>
          <div className="summary-grid">
            <div className="summary-card"><span>已有当前匹配结果</span><strong>{matchedCount}</strong></div>
            <div className="summary-card"><span>要求已准备，可进入匹配</span><strong>{matchReadyCount}</strong></div>
            <div className="summary-card"><span>岗位要求还未准备好</span><strong>{requirementBlockedCount}</strong></div>
            {unknownReadinessCount > 0 ? (
              <div className="summary-card"><span>暂时无法确认</span><strong>{unknownReadinessCount}</strong></div>
            ) : null}
          </div>
          {showImprovement ? (
            <section className="detail-section">
              <h3>这次补证据后，本批哪些岗位改善了</h3>
              {improvedBatchJobs.length > 0 ? (
                <ul>
                  {improvedBatchJobs.map(({report, improvement}) => {
                    const resolvedRequirementIds = new Set(improvement.resolvedRequirementIds);
                    const resolvingEvidence = improvement.newlySupportingEvidence.flatMap((evidence) => {
                      const supportingRequirements = evidence.supportingRequirements.filter((requirement) =>
                        resolvedRequirementIds.has(requirement.requirementId),
                      );
                      return supportingRequirements.length > 0 ? [{evidence, supportingRequirements}] : [];
                    });
                    return (
                      <li key={report.reportId}>
                        <strong>{jobLabel(report.jobId)}</strong>：
                        {improvement.resolvedRequirementIds.length > 0
                          ? `少了 ${improvement.resolvedRequirementIds.length} 条硬条件缺口`
                          : "硬条件缺口数量未减少"}
                        {improvement.previousRecommendation !== improvement.currentRecommendation
                          ? `，推荐结果从 ${improvement.previousRecommendation ?? "无"} 变为 ${improvement.currentRecommendation ?? "无"}`
                          : ""}。
                        {blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value ? (() => {
                          const currentBlocker = blockerByJobId.get(report.jobId);
                          const nextRequirement = currentBlocker?.requirements[0] ?? null;
                          const latestFeedback = latestFeedbackByReportId.get(report.reportId);
                          return currentBlocker ? (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>
                              {nextRequirement
                                ? `虽然已经改善，但当前仍有 ${currentBlocker.missingRequirementCount} 条硬条件缺口；下一条先看“${nextRequirement.originalText}”。`
                                : `虽然已经改善，但仍有 ${currentBlocker.missingRequirementCount} 条硬条件缺口；当前 Requirement 事实无法解析出具体原文，因此这里不猜测下一项。`}
                            </div>
                          ) : latestFeedback?.decision === "rejected" ? (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>当前 Match blocker 事实里已没有硬条件缺口，但你已经明确标记为“不考虑”，因此这里不会继续推动投递，也不会再要求为它补证据。
                            </div>
                          ) : (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>当前 Match blocker 事实里已没有硬条件缺口，可以停止机械补证据，转向投递判断。
                              <div className="detail-section">
                                <strong>现在为什么值得进入投递判断：</strong>
                                <ul>
                                  <li>当前 Ranking 建议：{matchRecommendationLabels[report.recommendation]}。</li>
                                  <li>当前 MatchReport 依据：{report.summary || matchRecommendationDescriptions[report.recommendation]}</li>
                                  <li>可追溯到 {report.evidenceLinks.length} 条 Requirement → Evidence 关联。</li>
                                  <li>你的当前判断：{feedbackDecisionLabel(latestFeedback?.decision)}。</li>
                                </ul>
                                <p className="muted">这只是基于当前 MatchReport、hard blocker 与你的反馈做的决策摘要，不代表系统替你决定投递。</p>
                              </div>
                              <div className="actions">
                                <Link className="button" href={`/jobs/${report.jobId}/prepare`}>查看完整依据并进入投递判断</Link>
                              </div>
                            </div>
                          );
                        })() : (
                          <p className="muted">当前无法可靠读取这个岗位最新的 hard blocker，因此这里不判断它是否已经没有硬缺口。</p>
                        )}
                        {resolvingEvidence.length > 0 ? (
                          <ul>
                            {resolvingEvidence.slice(0, 3).map(({evidence, supportingRequirements}) => (
                              <li key={`${report.reportId}-${evidence.evidenceId}`}>
                                新进入匹配依据的真实经历：<strong>{evidence.summary}</strong>
                                <ul>
                                  {supportingRequirements.slice(0, 3).map((requirement) => (
                                    <li key={`${evidence.evidenceId}-${requirement.requirementId}`}>
                                      已支撑岗位要求：{requirement.originalText}
                                    </li>
                                  ))}
                                </ul>
                              </li>
                            ))}
                          </ul>
                        ) : improvement.resolvedRequirementIds.length > 0 ? (
                          <p className="muted">这次能确认硬缺口减少，但现有 provenance 没有精确指出是哪条新增 Evidence 直接支撑了这些已解决要求，因此这里不做猜测。</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="notice">当前还没有可确认的批次改善。只有存在同一岗位、同一 Requirement 事实集且 Profile 版本不同的前后 MatchReport 时，系统才会把变化归因给这次资料更新。</p>
              )}
              {resolvedBatchRequirementIds.size > 0 ? (
                batchEvidenceAction ? (
                  <p className="notice">
                    这次补充的 Evidence 已经解决 {resolvedBatchRequirementIds.size} 条硬要求；这些已解决 Requirement 不会继续驱动下一证据行动。下面的下一步只来自当前仍未解决的 blocker。
                  </p>
                ) : batchEvidenceActionStaleAfterImprovement ? (
                  <p className="notice">
                    这次已经有硬要求被解决，但当前 blocker 汇总仍包含已解决 Requirement。为避免重复让你补同一项证据，本页暂不生成下一证据行动，请刷新后再看最新事实。
                  </p>
                ) : (
                  <p className="notice">
                    这次补充的 Evidence 已经解决 {resolvedBatchRequirementIds.size} 条硬要求；当前这批岗位没有新的、可可靠确认的下一证据行动。
                  </p>
                )
              ) : null}
              <p className="muted">这里只比较已经存在的 immutable MatchReport，不会在打开页面时重新匹配或调用 Provider。</p>
            </section>
          ) : null}

          {matchedReports.length > 0 ? (
            <section className="detail-section">
              <h3>这批岗位当前的匹配结果</h3>
              <p className="muted">按当前 Ranking 顺序展示，只读取已经存在的 MatchReport；这里不会重新匹配。</p>
              {feedbackAvailable ? (
                <p className="muted">已反馈 {feedbackCoveredCount}/{matchedCount}。你可以直接在这批结果里记录真实判断。</p>
              ) : (
                <p className="notice">当前反馈状态暂时读取失败。匹配结果仍可查看，但这里暂不开放反馈，避免覆盖未知状态。</p>
              )}
              <div className="recommendation-grid">
                {matchedReports.map((report, index) => (
                  <article className={`match-recommendation-card ${matchRecommendationClasses[report.recommendation]}`} key={report.reportId}>
                    <p className="eyebrow">第 {index + 1} 位</p>
                    <h3><Link href={`/jobs/${report.jobId}`}>{jobLabel(report.jobId)}</Link></h3>
                    <div className="actions">
                      <span className={`tag ${matchRecommendationClasses[report.recommendation]}`}>
                        {matchRecommendationLabels[report.recommendation]}
                      </span>
                      <span className="tag">有依据要求 {report.evidenceLinks.length} 条</span>
                    </div>
                    <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p>
                    {feedbackAvailable ? (() => {
                      const latestFeedback = latestFeedbackByReportId.get(report.reportId);
                      return (
                        <RecommendationFeedback
                          matchReportId={report.reportId}
                          jobId={report.jobId}
                          initialDecision={latestFeedback?.decision ?? null}
                          initialReasons={latestFeedback?.reasons ?? []}
                          initialNote={latestFeedback?.note ?? null}
                        />
                      );
                    })() : null}
                  </article>
                ))}
              </div>
              {batchEvidenceAction && batchEvidenceProfileHref ? (
                <section className="detail-section">
                  <h3>这批岗位下一项最值得核实的证据</h3>
                  {showImprovement && resolvedBatchRequirementIds.size > 0 ? (
                    <div className="notice">
                      <strong>为什么下一步是这一项：</strong>
                      刚补的真实 Evidence 已解决 {resolvedBatchRequirementIds.size} 条硬要求
                      {improvedBatchJobs.length > 0
                        ? `，并让 ${improvedBatchJobs.slice(0, 3).map(({report}) => jobLabel(report.jobId)).join("、")}${improvedBatchJobs.length > 3 ? ` 等 ${improvedBatchJobs.length} 个岗位` : ""} 出现可验证改善`
                        : ""}。
                      这些要求已经从候选行动中排除；当前仍未解决、且影响仍在考虑岗位最多的是下面这一项，所以继续优先核实它。
                    </div>
                  ) : null}
                  <p>
                    {batchEvidenceAction.normalizedCapability
                      ? `先核实“${batchEvidenceAction.normalizedCapability}”相关的真实经历。`
                      : `先核实一项 ${batchEvidenceAction.requirementType} 类型的真实经历。`}
                    当前仍影响这批中 {batchEvidenceConsideredJobCount} 个你没有明确标记为“不考虑”的岗位，共对应 {batchEvidenceAction.missingRequirementCount} 条硬条件缺口。
                  </p>
                  {batchEvidenceImpactTargets.length > 0 ? (
                    <ul>
                      {batchEvidenceImpactTargets.slice(0, 3).map((target) => (
                        <li key={target.jobId}>
                          <strong>{jobLabel(target.jobId)}</strong>
                          <ul>
                            {target.requirementTexts.map((requirementText) => (
                              <li key={`${target.jobId}-${requirementText}`}>{requirementText}</li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="muted">
                    这里只按当前 blocker 与你的真实反馈排序；明确 rejected 的岗位不会继续驱动补证据。核实并保存真实经历后，最终是否改善仍以 Re-match 为准。
                  </p>
                  <div className="actions">
                    <Link className="button" href={batchEvidenceProfileHref}>去核实这项真实经历</Link>
                  </div>
                </section>
              ) : feedbackAvailable && blockerSummaryResult.status === "fulfilled" ? null : (
                <p className="notice">
                  当前无法可靠读取反馈或硬条件缺口，因此这里不生成下一证据建议，避免把未知状态当成事实。
                </p>
              )}
              <div className="actions">
                <Link className="button" href="/recommendations">查看全部优先投递</Link>
              </div>
            </section>
          ) : null}

          {requirementBlockedJobs.length > 0 ? (
            <section className="detail-section">
              <h3>还需处理岗位要求</h3>
              <p className="muted">先看具体阻塞原因，再决定是否进入该岗位处理；这里不会自动发起分析。</p>
              <ul>
                {requirementBlockedJobs.map((jobId) => {
                  const readiness = readinessByJobId.get(jobId);
                  return (
                    <li key={jobId} style={{marginBottom: "0.85rem"}}>
                      <Link href={`/jobs/${jobId}`}><strong>{jobLabel(jobId)}</strong></Link>
                      {readiness && readiness.blockers.length > 0 ? (
                        <ul>
                          {readiness.blockers.slice(0, 2).map((blocker) => (
                            <li key={`${jobId}-${blocker.code}`}>{blocker.message}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">当前没有可展示的具体阻塞原因，请进入岗位查看最新状态。</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {matchReadyJobs.length > 0 ? (
            <section className="detail-section">
              <h3>Requirement 已准备、等待匹配</h3>
              <ul>
                {matchReadyJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
              <ImportBatchMatch jobIds={matchReadyJobs} />
            </section>
          ) : null}

          {unknownReadinessJobs.length > 0 ? (
            <section className="detail-section">
              <h3>暂时无法确认的岗位</h3>
              <p className="muted">这些岗位的 Requirement 状态读取失败，因此不会被误报为“尚未准备”。</p>
              <ul>
                {unknownReadinessJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="actions">
            {matchedCount > 0 || matchReadyCount > 0 ? (
              <Link className="button" href="/recommendations">查看优先投递与继续匹配</Link>
            ) : null}
            {requirementBlockedCount > 0 ? (
              <Link className="button-ghost" href="/jobs">查看全部岗位</Link>
            ) : null}
          </div>
          <p className="muted">
            “要求已准备，可进入匹配”表示这批岗位已经通过当前 Match Input Readiness，不代表已经生成 MatchReport；真正的匹配仍必须由你显式点击发起。
          </p>
        </section>
      ) : null}

      <section className="detail-grid">
        <article className="detail-card">
          <h2>逐条处理结果</h2>
          {detail.items.length === 0 ? (
            <p className="notice">本批次没有最终 Job 输入项，可能只包含候选诊断数据。</p>
          ) : (
            <div style={{overflowX: "auto"}}>
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>结果</th>
                    <th>岗位</th>
                    <th>错误</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((item) => (
                    <tr key={item.inputIndex}>
                      <td>{item.inputIndex}</td>
                      <td><ImportOutcomePill outcome={item.outcome} /></td>
                      <td>
                        {item.jobId ? (
                          <Link href={`/jobs/${item.jobId}`}>查看岗位</Link>
                        ) : "—"}
                      </td>
                      <td>{item.errorMessage || item.errorCode || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {detail.errors.length > 0 ? (
            <section className="detail-section">
              <h2>没有成功添加的原因</h2>
              {detail.errors.map((error) => (
                <div className="inline-error" key={`${error.index}-${error.code}`}>
                  <strong>第 {error.index} 条 · {error.code}</strong>
                  <p>{error.message}</p>
                </div>
              ))}
            </section>
          ) : null}
        </article>

        <aside className="detail-card">
          <h2>这批数据</h2>
          <div className="meta-list">
            <div><span className="meta-label">插件版本</span><strong>{detail.collectorVersion || detail.sourceVersion}</strong></div>
            <div><span className="meta-label">采集时间</span><strong>{formatDateTime(detail.collectedAt)}</strong></div>
            <div><span className="meta-label">添加时间</span><strong>{formatDateTime(detail.createdAt)}</strong></div>
          </div>

          <details className="technical-details">
            <summary>查看技术详情</summary>
            <p className="code">Import ID：{detail.importId}</p>
            <h3>候选数据统计</h3>
            <pre className="code notice">{JSON.stringify(detail.candidateSummary, null, 2)}</pre>
            <h3>采集时的筛选信息</h3>
            <pre className="code notice">{JSON.stringify(detail.searchIntentSnapshot, null, 2)}</pre>
          </details>

          <div className="actions">
            <Link className="button" href="/jobs">查看我的岗位</Link>
            <Link className="button-ghost" href="/import">继续添加岗位</Link>
          </div>
        </aside>
      </section>
    </>
  );
}
