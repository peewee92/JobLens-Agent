import Link from "next/link";

import {ApplicationChecklistProgress} from "@/components/application-checklist-progress";
import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchJobPreparation,
  fetchLatestUserFeedback,
  fetchMatchImprovement,
  fetchMatchRanking,
} from "@/lib/backend";
import {listNewlySupportedRequirements} from "@/lib/match-improvement-outcome";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function JobPreparationPage({
  params,
  searchParams,
}: {
  params: Promise<{id: string}>;
  searchParams?: Promise<{
    returnImport?: string | string[];
    afterMatchJobs?: string | string[];
    afterEvidence?: string | string[];
    focusRequirementId?: string | string[];
    prepareEvidenceJobs?: string | string[];
  }>;
}) {
  const {id} = await params;
  const query = searchParams ? await searchParams : {};
  const requestedReturnImport = Array.isArray(query.returnImport) ? query.returnImport[0] : query.returnImport;
  const returnImportId = typeof requestedReturnImport === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedReturnImport)
    ? requestedReturnImport
    : null;
  const requestedAfterMatchJobs = Array.isArray(query.afterMatchJobs) ? query.afterMatchJobs[0] : query.afterMatchJobs;
  const requestedAfterEvidence = Array.isArray(query.afterEvidence) ? query.afterEvidence[0] : query.afterEvidence;
  const requestedFocusRequirementId = Array.isArray(query.focusRequirementId) ? query.focusRequirementId[0] : query.focusRequirementId;
  const requestedPrepareEvidenceJobs = Array.isArray(query.prepareEvidenceJobs) ? query.prepareEvidenceJobs[0] : query.prepareEvidenceJobs;
  const afterEvidence = requestedAfterEvidence === "1";
  const focusRequirementId = typeof requestedFocusRequirementId === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedFocusRequirementId)
    ? requestedFocusRequirementId
    : null;
  const afterMatchJobIds = typeof requestedAfterMatchJobs === "string"
    ? Array.from(new Set(
        requestedAfterMatchJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20)
    : [];
  const afterMatchQuery = afterMatchJobIds.length > 0
    ? `&afterMatchJobs=${encodeURIComponent(afterMatchJobIds.join(","))}`
    : "";
  const prepareEvidenceJobIds = typeof requestedPrepareEvidenceJobs === "string"
    ? Array.from(new Set(
        requestedPrepareEvidenceJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20)
    : [];
  const prepareEvidenceQuery = prepareEvidenceJobIds.length > 0
    ? `&prepareEvidenceJobs=${encodeURIComponent(prepareEvidenceJobIds.join(","))}`
    : "";

  try {
    const [job, preparation] = await Promise.all([
      fetchJobDetail(id),
      fetchJobPreparation(id),
    ]);
    const rankingResult = await fetchMatchRanking([id], {includeBlocked: true}).catch(() => null);
    const currentReport = rankingResult?.items.find((item) => item.jobId === id) ?? null;
    const feedbackResult = currentReport
      ? await fetchLatestUserFeedback([currentReport.reportId]).catch(() => null)
      : null;
    const latestFeedback = feedbackResult?.feedback[0] ?? null;
    const evidenceImprovement = afterEvidence && currentReport && focusRequirementId
      ? await fetchMatchImprovement(id, currentReport.reportId).catch(() => null)
      : null;
    const focusedEvidenceOutcome = afterEvidence && focusRequirementId
      ? evidenceImprovement?.comparable
        ? evidenceImprovement.resolvedRequirementIds.includes(focusRequirementId)
          ? "resolved"
          : currentReport?.missingRequirementIds.includes(focusRequirementId)
            ? "remaining"
            : "unverifiable"
        : "unverifiable"
      : null;
    const otherRequirementsReachedByEvidence = focusedEvidenceOutcome === "resolved"
      ? listNewlySupportedRequirements(evidenceImprovement, focusRequirementId)
      : [];
    const preparationHighlights = preparation.resumeDelta?.highlights ?? [];
    const preparationEvidenceGaps = preparation.resumeDelta?.evidenceGaps ?? [];
    const preparationStudyItems = preparation.studyChecklist?.items ?? [];
    const preparationInterviewItems = preparation.interviewFacts?.items ?? [];
    const topPreparationHighlight = preparationHighlights[0] ?? null;
    const topPreparationEvidenceGap = preparationEvidenceGaps[0] ?? null;
    const topPreparationStudyItem = preparationStudyItems[0] ?? null;
    const topInterviewFocus = preparationInterviewItems[0] ?? null;
    const preparationHighlightText = topPreparationHighlight
      ? `${topPreparationHighlight.capability}（Evidence：${topPreparationHighlight.evidenceIds.join("、") || "已确认"}）`
      : "当前没有可安全突出为岗位优势的已确认 Evidence。";
    const preparationGapText = topPreparationEvidenceGap
      ? `${topPreparationEvidenceGap.capability}（${topPreparationEvidenceGap.status === "missing" ? "Profile 中缺少该能力事实" : "已有技能事实，但缺少已确认 Evidence"}）`
      : topPreparationStudyItem
        ? `${topPreparationStudyItem.capability}（${topPreparationStudyItem.requirementText}）`
        : "当前没有已识别的 Evidence 缺口或面试前补习项。";
    const topPreparationEvidenceGapRequirementText = topPreparationEvidenceGap
      ? preparationInterviewItems.find((item) => item.requirementId === topPreparationEvidenceGap.requirementId)?.requirementText
        ?? preparationStudyItems.find((item) => item.requirementId === topPreparationEvidenceGap.requirementId)?.requirementText
        ?? null
      : null;
    const preparationGapProfileHref = topPreparationEvidenceGap
      ? `/profile?next=/recommendations&focusJob=${encodeURIComponent(id)}&focusRequirementId=${encodeURIComponent(topPreparationEvidenceGap.requirementId)}&focusCapability=${encodeURIComponent(topPreparationEvidenceGap.capability)}${topPreparationEvidenceGapRequirementText ? `&focusRequirementText=${encodeURIComponent(topPreparationEvidenceGapRequirementText)}` : ""}&returnPrepare=${encodeURIComponent(id)}${returnImportId ? `&returnImport=${encodeURIComponent(returnImportId)}` : ""}${afterMatchJobIds.length > 0 ? `&afterMatchJobs=${encodeURIComponent(afterMatchJobIds.join(","))}` : ""}#profile-evidence-focus`
      : null;
    const interviewFocusText = topInterviewFocus
      ? `${topInterviewFocus.requirementText}（优先级：${topInterviewFocus.preparationPriority}）`
      : "当前没有可可靠生成的面试 Requirement 重点。";

    return (
      <>
        <div className="actions" style={{marginBottom: 18}}>
          {returnImportId ? (
            <Link className="button-ghost" href={`/imports/${encodeURIComponent(returnImportId)}?showImprovement=1${afterMatchQuery}`}>
              ← 返回本次导入
            </Link>
          ) : null}
          <Link className="button-ghost" href={`/jobs/${encodeURIComponent(id)}`}>
            ← 返回岗位详情
          </Link>
        </div>

        <section className="detail-card">
          <p className="eyebrow">投递与面试准备</p>
          <h1>{job.title}</h1>
          <p className="company">{job.company}</p>
          <p className="lede">
            这里只展示已确认职业事实与已放行岗位要求之间的确定性准备依据，不补写不存在的经历、成绩或指标。
          </p>

          {currentReport ? (
            <section className="detail-section">
              <h2>记录你的投递判断</h2>
              <p className="muted">看完完整依据后，在这里记录“感兴趣 / 再看看 / 不考虑”。反馈只更新你的判断，不会改写 MatchReport 或自动投递。</p>
              {feedbackResult ? (
                <RecommendationFeedback
                  matchReportId={currentReport.reportId}
                  jobId={currentReport.jobId}
                  initialDecision={latestFeedback?.decision ?? null}
                  initialReasons={latestFeedback?.reasons ?? []}
                  initialNote={latestFeedback?.note ?? null}
                  successHref={returnImportId
                    ? `/imports/${encodeURIComponent(returnImportId)}?showImprovement=1&afterFeedback=${encodeURIComponent(id)}${afterMatchQuery}${prepareEvidenceQuery}`
                    : undefined}
                  successLabel="返回本次导入继续下一步"
                />
              ) : (
                <p className="notice">当前无法可靠读取最新反馈状态，因此这里暂不开放反馈，避免覆盖未知历史判断。</p>
              )}
              {returnImportId ? (
                <div className="actions">
                  <Link className="button" href={`/imports/${encodeURIComponent(returnImportId)}?showImprovement=1${afterMatchQuery}${prepareEvidenceQuery}`}>
                    返回本次导入查看反馈进度
                  </Link>
                </div>
              ) : null}
            </section>
          ) : (
            <p className="notice">当前没有可用的最新 MatchReport，因此这里不能记录投递判断；请先完成该岗位的显式匹配。</p>
          )}

          {focusedEvidenceOutcome ? (
            <div className="notice">
              <strong>刚才这项 Evidence 更新后的准备结果：</strong>
              {focusedEvidenceOutcome === "resolved" ? (
                <>
                  <p className="muted">这条岗位 Requirement 已在可比较的 Re-match 中从 hard missing 移除。下面的准备清单已按最新 JobPreparationBundle 刷新，可以继续处理新的最高优先级准备项。</p>
                  {otherRequirementsReachedByEvidence.length > 0 ? (
                    <div className="detail-section">
                      <strong>这次新增 Evidence 还命中了其他真实 Requirement：</strong>
                      <ul>
                        {otherRequirementsReachedByEvidence.slice(0, 3).map((requirement) => (
                          <li key={`prepare-evidence-impact-${requirement.requirementId}`}>{requirement.originalText}</li>
                        ))}
                      </ul>
                      <p className="muted">这里只展示本次可比较 MatchImprovement 中真实记录的 supportingRequirements，不把“可能有帮助”当成已经改善。</p>
                    </div>
                  ) : (
                    <p className="muted">当前没有可验证的其他 Requirement 命中，因此这里不扩张这次 Evidence 的影响范围。</p>
                  )}
                  <div className="actions">
                    <Link className="button-secondary" href="#application-checklist">继续最新准备清单 ↓</Link>
                    {returnImportId ? (
                      <Link className="button-ghost" href={`/imports/${encodeURIComponent(returnImportId)}?showImprovement=1&afterPrepareEvidence=${encodeURIComponent(id)}${focusRequirementId ? `&focusRequirementId=${encodeURIComponent(focusRequirementId)}` : ""}${afterMatchQuery}#prepare-evidence-batch-result`}>
                        返回本次导入查看最新批次结果
                      </Link>
                    ) : null}
                  </div>
                </>
              ) : focusedEvidenceOutcome === "remaining" ? (
                <p className="muted">这条 Requirement 在可比较的 Re-match 后仍是 hard missing。下面会继续显示当前真实缺口；不要为了勾完清单补写不存在的经历。</p>
              ) : (
                <p className="muted">当前无法基于可比较 Match 历史确认这条 Requirement 是否改善，因此这里只展示最新准备事实，不把返回链接本身当成成功证据。</p>
              )}
            </div>
          ) : null}

          {preparation.factsUsable ? (
            <>
              <ApplicationChecklistProgress
              jobId={id}
              items={[
                {id: "highlight", label: "先突出最有把握的真实经历：", text: preparationHighlightText},
                {id: "gap", label: "再补最关键的准备缺口：", text: preparationGapText},
                {id: "interview", label: "最后准备最高优先级面试问题：", text: interviewFocusText},
              ]}
              />
              {preparationGapProfileHref ? (
                <div className="notice">
                  <strong>这项缺口可以回到真实 Evidence 闭环处理</strong>
                  <p className="muted">只在你确实有相关经历时补充 Profile；保存后仍需要你显式重新计算这个岗位，系统不会因为打开链接就声称缺口已改善。</p>
                  <div className="actions">
                    <Link className="button-secondary" href={preparationGapProfileHref}>补充这项真实 Evidence →</Link>
                  </div>
                </div>
              ) : null}
            </>
          ) : null}

          {!preparation.factsUsable ? (
            <div className="review-result review-pending">
              <strong>当前还不能生成可信的岗位准备依据</strong>
              <p>前置事实门禁尚未全部通过。完成这些门禁后，本页才会展示简历、项目和面试准备事实。</p>
              {preparation.blockers.length > 0 ? (
                <ul>
                  {preparation.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                </ul>
              ) : null}
            </div>
          ) : (
            <div className="eligibility-groups">
              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>简历调整依据</h2>
                  <span>{preparation.resumeDelta?.highlights.length ?? 0} 项可突出</span>
                </div>
                {(preparation.resumeDelta?.highlights ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>已确认 Evidence：{item.evidenceIds.join("、")}</p>
                    <small className="muted-copy">Requirement：{item.requirementId}</small>
                  </article>
                ))}
                {(preparation.resumeDelta?.evidenceGaps ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>{item.status === "missing" ? "当前 Profile 中缺少该能力事实。" : "已有技能事实，但缺少已确认 Evidence。"}</p>
                    <small className="muted-copy">Requirement：{item.requirementId}</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>项目 / 经历排序</h2>
                  <span>{preparation.experiencePriority?.items.length ?? 0} 项</span>
                </div>
                {(preparation.experiencePriority?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.evidenceId}>
                    <strong>{item.evidenceId}</strong>
                    <p>匹配能力：{item.matchedCapabilities.join("、") || "无"}</p>
                    <small className="muted-copy">支撑 {item.requirementCount} 条 Requirement，其中 must-have {item.mustHaveCount} 条</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>项目讲述事实</h2>
                  <span>{preparation.storyFacts?.items.length ?? 0} 项</span>
                </div>
                {(preparation.storyFacts?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.evidenceId}>
                    <strong>{item.evidenceSummary}</strong>
                    <p>岗位要求：{item.supportingRequirementTexts.join("；")}</p>
                    <small className="muted-copy">这里只选择真实事实，不生成 STAR 成绩或指标。</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>面试重点</h2>
                  <span>{preparation.interviewFacts?.items.length ?? 0} 项</span>
                </div>
                {(preparation.interviewFacts?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.requirementText}</strong>
                    <p>准备优先级：{item.preparationPriority} · Evidence 状态：{item.evidenceStatus}</p>
                    {item.evidenceSummaries.length > 0 ? <p>可用事实：{item.evidenceSummaries.join("；")}</p> : null}
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>面试前补习清单</h2>
                  <span>{preparation.studyChecklist?.items.length ?? 0} 项</span>
                </div>
                {(preparation.studyChecklist?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>{item.requirementText}</p>
                    <p>补齐标准：{item.completionCriteria.join("；")}</p>
                  </article>
                ))}
              </section>
            </div>
          )}
        </section>
      </>
    );
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位准备信息，请稍后重试。")
        : "暂时无法读取岗位准备信息，请稍后重试。";
    return <ServiceError message={message} />;
  }
}
