import Link from "next/link";

import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchJobPreparation,
  fetchLatestUserFeedback,
  fetchMatchRanking,
} from "@/lib/backend";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function JobPreparationPage({
  params,
  searchParams,
}: {
  params: Promise<{id: string}>;
  searchParams?: Promise<{returnImport?: string | string[]; afterMatchJobs?: string | string[]}>;
}) {
  const {id} = await params;
  const query = searchParams ? await searchParams : {};
  const requestedReturnImport = Array.isArray(query.returnImport) ? query.returnImport[0] : query.returnImport;
  const returnImportId = typeof requestedReturnImport === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedReturnImport)
    ? requestedReturnImport
    : null;
  const requestedAfterMatchJobs = Array.isArray(query.afterMatchJobs) ? query.afterMatchJobs[0] : query.afterMatchJobs;
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
                    ? `/imports/${encodeURIComponent(returnImportId)}?showImprovement=1&afterFeedback=${encodeURIComponent(id)}${afterMatchQuery}`
                    : undefined}
                  successLabel="返回本次导入继续下一步"
                />
              ) : (
                <p className="notice">当前无法可靠读取最新反馈状态，因此这里暂不开放反馈，避免覆盖未知历史判断。</p>
              )}
              {returnImportId ? (
                <div className="actions">
                  <Link className="button" href={`/imports/${encodeURIComponent(returnImportId)}?showImprovement=1${afterMatchQuery}`}>
                    返回本次导入查看反馈进度
                  </Link>
                </div>
              ) : null}
            </section>
          ) : (
            <p className="notice">当前没有可用的最新 MatchReport，因此这里不能记录投递判断；请先完成该岗位的显式匹配。</p>
          )}

          {preparation.factsUsable ? (
            <section className="detail-section">
              <h2>申请准备清单</h2>
              <p className="muted">先按这三步准备，再看下面的完整依据。这里只整理 Backend 已返回的 Requirement / Evidence 事实，不生成新的经历、成绩或指标。</p>
              <ol>
                <li><strong>先突出最有把握的真实经历：</strong> {preparationHighlightText}</li>
                <li><strong>再补最关键的准备缺口：</strong> {preparationGapText}</li>
                <li><strong>最后准备最高优先级面试问题：</strong> {interviewFocusText}</li>
              </ol>
            </section>
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
