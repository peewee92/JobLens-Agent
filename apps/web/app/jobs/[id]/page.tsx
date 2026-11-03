import type {CareerContextReleaseReadiness} from "@/lib/contracts";
import {careerContextReleaseBlockerCopy} from "@/lib/career-context";
import {JobReportComparison} from "@/components/job-report-comparison";
import {JobDescriptionObservationsView} from "@/components/job-description-observations";
import {JobAvailabilityControl} from "@/components/job-availability-control";
import {validImportMatchInputs} from "@/lib/import-match-readiness";
import {PreferenceCheckList} from "@/components/preference-check-list";
import Link from "next/link";
import {agentScopeHref, jobDetailWithAgentScope, parseAgentScope, profileWithAgentScope} from "@/lib/agent-job-scope";
import {runHref, validThreadReference} from "@/lib/career-agent-commands";
import {notFound} from "next/navigation";

import {JobMatchReportPanel} from "@/components/job-match-report-panel";
import {JobRequirementExtractButton} from "@/components/job-requirement-extract-button";
import {JobRequirementConfirmation} from "@/components/job-requirement-confirmation";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchJobDescriptionObservations,
  fetchMatchReportHistory,
  fetchJobEligibility,
  fetchJobMatchInputReadiness,
  fetchLatestJobRequirements,
} from "@/lib/backend";
import {
  eligibilityDescriptions,
  eligibilityLabels,
  groupEligibilityRequirements,
  requirementFitLabels,
} from "@/lib/eligibility";
import {formatDateTime, formatSalary} from "@/lib/format";
import {userFacingErrorCode} from "@/lib/user-facing-errors";
import {
  requirementImportanceLabel,
  hasEnoughJobDescription,
  jobDescriptionIssue,
  requirementReleaseBlockerCopy,
  requirementReleaseLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";

export const dynamic = "force-dynamic";

export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{id: string}>;
  searchParams: Promise<{requirementExtractionError?: string; reportId?: string; scopeJobId?: string | string[]; returnThreadId?: string | string[]}>;
}) {
  const {id} = await params;
  const {requirementExtractionError, reportId, scopeJobId, returnThreadId} = await searchParams;
  const agentScope = parseAgentScope(scopeJobId);
  const retainedScope = agentScope?.includes(id) ? agentScope : null;
  const detailPath = retainedScope ? jobDetailWithAgentScope(id, retainedScope) : `/jobs/${encodeURIComponent(id)}`;
  const detailHref = validThreadReference(returnThreadId) ? `${detailPath}${detailPath.includes("?") ? "&" : "?"}${new URLSearchParams({returnThreadId})}` : detailPath;
  function reportHref(report: string) {
    return `${detailHref}${detailHref.includes("?") ? "&" : "?"}${new URLSearchParams({reportId: report})}`;
  }
  let job;
  try {
    job = await fetchJobDetail(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) {
      notFound();
    }
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位详情，请稍后重试。")
        : "暂时无法读取岗位详情，请稍后重试。";
    return <ServiceError message={message} />;
  }

  let descriptions = null;
  try {
    const result = await fetchJobDescriptionObservations(id);
    if (result.jobId === id && Array.isArray(result.items)) descriptions = result;
  } catch { /* A failed history read must not hide the current job. */ }
  let history = null;
  let historyError = "";
  try {
    history = await fetchMatchReportHistory(id);
  } catch {
    historyError = "暂时无法读取保存的匹配结果，请刷新重试；这不表示历史结果已丢失。";
  }
  const savedResult = reportId
    ? history?.items.find((item) => item.reportId === reportId) ?? null
    : history?.items[0] ?? null;
  const selectedReportMissing = Boolean(reportId && history && !savedResult);
  let extraction = null;
  let releaseReadiness = null;
  let careerReadiness: CareerContextReleaseReadiness | null = null;
  let eligibility = null;
  let requirementError = "";
  let releaseReadinessError = "";
  let eligibilityError = "";
  try {
    extraction = await fetchLatestJobRequirements(id);
  } catch (caught) {
    requirementError =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位要求分析结果，请稍后重试。")
        : "暂时无法读取岗位要求分析结果，请稍后重试。";
  }
  try {
    const inputReadiness = await fetchJobMatchInputReadiness(id);
    if (!validImportMatchInputs(id, inputReadiness)) {
      throw new Error("invalid match input readiness");
    }
    releaseReadiness = inputReadiness.jobRequirements;
    careerReadiness = inputReadiness.careerContext;
  } catch (caught) {
    releaseReadinessError =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法检查岗位匹配准备状态，请稍后重试。")
        : "暂时无法检查岗位匹配准备状态，请稍后重试。";
  }
  try {
    eligibility = await fetchJobEligibility(id);
  } catch (caught) {
    if (!(caught instanceof BackendApiError && caught.code === "eligibility_inputs_not_ready")) {
      eligibilityError =
        caught instanceof BackendApiError
          ? userFacingErrorCode(caught.code, "暂时无法判断这个岗位与你的职业背景是否匹配。")
          : "暂时无法判断这个岗位与你的职业背景是否匹配。";
    }
  }
  const groupedEligibility = eligibility
    ? groupEligibilityRequirements(eligibility.requirements)
    : null;
  const requirementBlockerCodes = new Set(
    releaseReadiness?.blockers.map((item) => item.code) ?? [],
  );
  const requirementExtractionMissing = requirementBlockerCodes.has(
    "requirement_extraction_missing",
  );
  const hasEnoughDescription = hasEnoughJobDescription(job.description);
  const descriptionIssue = jobDescriptionIssue(job.description);
  const acceptedBaselineMissing = requirementBlockerCodes.has(
    "accepted_baseline_missing",
  );
  const canConfirmRequirements = !!(extraction?.factsDigest && releaseReadiness
    && extraction.extractionId === releaseReadiness.extractionId
    && extraction.factsDigest === releaseReadiness.requirementFactsDigest
    && !job.userMarkedInactive
    && releaseReadiness.blockers.every(blocker => ["accepted_baseline_missing", "extraction_cohort_mismatch"].includes(blocker.code)));
  const matchDisabledReason = job.userMarkedInactive
    ? "你已标记此岗位失效；如需再次分析，请先恢复为待核实。"
    : job.userMarkedInactive !== false
      ? "暂时无法确认岗位标记，请刷新页面或检查服务版本。"
    : requirementExtractionMissing
      ? descriptionIssue ?? "请先完成下方的岗位要求分析，再检查匹配准备情况。"
      : canConfirmRequirements && !releaseReadiness?.userConfirmationId
        ? "请先对照原文核对下方全部岗位要求，再确认这一版用于匹配。"
      : acceptedBaselineMissing
        ? "岗位要求尚未核对或未满足输入检查，请先处理下方具体准备项。"
      : "当前职业背景或岗位要求仍未通过匹配输入检查，请先处理下方准备项。";

  return (
    <>
      <div className="actions" style={{marginBottom: 18}}>
        <Link className="button-ghost" href="/jobs">← 返回我的岗位</Link>
        {retainedScope && <Link className="button-ghost" href={agentScopeHref(retainedScope)}>← 返回所选岗位分析</Link>}
        {validThreadReference(returnThreadId) && <Link className="button-ghost" href={runHref(returnThreadId)}>← 返回本次分析</Link>}
        <Link className="button-ghost" href={`/jobs/${encodeURIComponent(job.id)}/prepare`}>
          查看投递与面试准备
        </Link>
      </div>
      <section className="detail-grid">
        <article className="detail-card">
          <header className="detail-header">
            <div>
              <p className="eyebrow">岗位详情</p>
              <h1>{job.title}</h1>
              <p className="company">{job.company}</p>
            </div>
            <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
          </header>

          <div className="tags">
            {job.area ? <span className="tag">{job.area}</span> : null}
            <RemoteStatusPill status={job.remoteStatus} />
            {job.remoteConfidence === "high" ? <span className="tag">远程信息较明确</span> : null}
          </div>

          <section className="detail-section">
            <h2>岗位描述</h2>
            <p className="description">{job.description || "该来源暂未提供完整岗位描述。"}</p>
            <JobDescriptionObservationsView history={descriptions} />
          </section>

          <section className="detail-section">
            <h2>技能标签</h2>
            <div className="tags">
              {job.skills.length > 0
                ? job.skills.map((skill) => <span className="tag" key={skill}>{skill}</span>)
                : <span className="tag">尚未提取技能</span>}
            </div>
          </section>

          <section className="detail-section eligibility-section">
            <div className="section-title-row">
              <div>
                <p className="eyebrow">结合我的职业背景</p>
                <h2>这个岗位适合我吗？</h2>
                <p className="lede requirement-lede">
                  这里只判断当前已确认资料能不能支撑岗位硬条件，不使用模糊的百分制匹配分数。
                </p>
              </div>
            </div>

            {historyError ? <p className="inline-error">{historyError}</p> : null}
            {selectedReportMissing ? <p className="inline-error">找不到指定结果，或它不属于此岗位。未自动替换为其他结果。<Link href={detailHref}>查看此岗位最新保存结果</Link></p> : null}
            {history && history.items.length > 0 ? (
              <details>
                <summary>查看保存的匹配历史（{history.count} 份）</summary>
                <ul>{history.items.map((item) => (
                  <li key={item.reportId}>
                    <Link href={reportHref(item.reportId)}>
                      {formatDateTime(item.createdAt)} · {item.isCurrent ? "当前" : "历史"}
                      {savedResult?.reportId === item.reportId ? " · 正在查看" : ""}
                    </Link>
                  </li>
                ))}</ul>
              </details>
            ) : null}
            {savedResult && history && (() => {
              const index = history.items.findIndex(item => item.reportId === savedResult.reportId);
              const previous = index >= 0 ? history.items[index + 1] : undefined;
              return previous ? <JobReportComparison previous={previous} current={savedResult} /> : null;
            })()}
            {careerReadiness && !careerReadiness.releaseEligible ? <section className="notice" aria-label="个人匹配输入准备">
              <h3>下一步：确认职业资料和求职偏好</h3>
              <p>仍可查看岗位。个性化结论只使用你确认保存的事实，不需要先完成模型整体质量评审。</p>
              <ul>{careerReadiness.blockers.map(blocker => <li key={blocker.code}>
                {careerContextReleaseBlockerCopy(blocker.code)?.title ?? "请核对职业资料和偏好"}
              </li>)}</ul>
              <Link className="button" href={profileWithAgentScope(id, retainedScope ?? [id])}>确认资料和偏好，返回这个岗位</Link>
            </section> : null}
            <JobMatchReportPanel
              key={savedResult?.reportId ?? "no-saved-result"}
              savedResult={savedResult}
              disabledReason={matchDisabledReason}
              enabled={eligibility !== null && job.userMarkedInactive === false}
              jobId={job.id}
              returnHref={detailHref}
              profileHref={profileWithAgentScope(id, retainedScope ?? [id])}
            />

            {eligibilityError ? <p className="inline-error">{eligibilityError}</p> : null}
            {eligibility && groupedEligibility ? (
              <div className={`eligibility-summary eligibility-${eligibility.eligibility}`}>
                <div className="eligibility-summary-header">
                  <div>
                    <span className="review-label">当前判断</span>
                    <h3>{eligibilityLabels[eligibility.eligibility]}</h3>
                    <p>{eligibilityDescriptions[eligibility.eligibility]}</p>
                  </div>
                  <div className="eligibility-counts" aria-label="岗位要求判断统计">
                    <span>岗位要求：</span>
                    <span><strong>{eligibility.matchedCount}</strong> 已匹配</span>
                    <span><strong>{eligibility.conditionalCount}</strong> 待确认</span>
                    <span><strong>{eligibility.missingCount}</strong> 明确不满足</span>
                  </div>
                </div>

                <PreferenceCheckList checks={eligibility.preferenceChecks ?? []} version={eligibility.searchIntentVersion} />
                <p className="notice">
                  缺少技能、学历或专项年限证据只表示待核实，不代表你不具备这些条件，也不代表已经满足。
                <Link href={profileWithAgentScope(id, retainedScope ?? [id])}>补充或确认职业资料</Link>
                </p>
                <div className="eligibility-groups">
                  {(["missing", "conditional", "matched"] as const).map((status) => {
                    const items = groupedEligibility[status];
                    if (items.length === 0) return null;
                    return (
                      <section className="eligibility-group" key={status}>
                        <div className="eligibility-group-heading">
                          <h3>{requirementFitLabels[status]}</h3>
                          <span>{items.length} 项</span>
                        </div>
                        <div className="eligibility-result-list">
                          {items.map((item) => (
                            <article className={`eligibility-result-card fit-${status}`} key={item.requirementIndex}>
                              <div className="tags">
                                <span className={`tag importance-${item.importance}`}>
                                  {requirementImportanceLabel(item.importance)}
                                </span>
                                <span className="tag">{requirementTypeLabel(item.type)}</span>
                                {item.normalizedCapability ? (
                                  <span className="tag">{item.normalizedCapability}</span>
                                ) : null}
                              </div>
                              <strong>{item.originalText}</strong>
                              <p>{item.reason}</p>
                              {item.evidenceIds.length > 0 ? (
                                <small className="muted-copy">
                                  有 {item.evidenceIds.length} 条已确认经历作为依据
                                </small>
                              ) : null}
                              {item.profileFactRefs.includes("yearsOfExperience") ? (
                                <small className="muted-copy">依据包含你已确认的总工作年限</small>
                              ) : null}
                            </article>
                          ))}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </div>
            ) : !eligibilityError ? (
              <div className="review-result review-pending">
                <strong>匹配判断还没有开始</strong>
                <p>{matchDisabledReason}</p>
              </div>
            ) : null}
          </section>

          <section className="detail-section requirement-section">
            <div className="section-title-row">
              <div>
                <h2>岗位要求分析</h2>
                <p className="lede requirement-lede">
                  系统会先把原始岗位描述整理成可核对的学历、经验、技能和职责。符合当前匹配规则的结果才会用于后续匹配。
                </p>
              </div>
              <JobRequirementExtractButton
                disabled={job.userMarkedInactive || !hasEnoughDescription}
                disabledReason={job.userMarkedInactive ? "你已标记此岗位失效；请先恢复为待核实，再分析岗位要求。" : descriptionIssue ?? undefined}
                hasExisting={extraction !== null}
                jobId={job.id}
              />
            </div>

            {requirementError ? <p className="inline-error">{requirementError}</p> : null}
            {requirementExtractionError ? (
              <p className="inline-error">
                {userFacingErrorCode(
                  requirementExtractionError,
                  "岗位要求分析失败，请稍后重试。",
                )}
              </p>
            ) : null}
            {!extraction && !requirementError && hasEnoughDescription ? (
              <p className="notice">
                <strong>你现在可以做第 1 步：</strong> 在上方检查分析方式与调用范围，然后提取当前岗位要求。提取完成后，对照原文核对这一版要求，即可继续个人匹配。
              </p>
            ) : null}
            {acceptedBaselineMissing ? (
              <details className="muted-copy"><summary>模型整体质量评审（高级）</summary><p>
                <Link href="/evals/requirements/manual">查看岗位要求人工审核状态 →</Link>
              </p><p>模型整体评审与单岗位核对不同；下方提供单岗位确认时，你可以先核对本岗位，不需要替维护者完成整批评审。</p></details>
            ) : null}
            {releaseReadinessError ? (
              <p className="inline-error">岗位匹配准备状态暂时不可用：{releaseReadinessError}</p>
            ) : null}
            {releaseReadiness ? (
              <div className={`review-result ${releaseReadiness.releaseEligible ? "review-accepted" : "review-pending"}`}>
                <strong>{requirementReleaseLabel(releaseReadiness)}</strong>
                {releaseReadiness.releaseEligible ? (
                  <p>
                    这份岗位要求符合当前匹配规则，可以用于后续匹配；这不代表已完成正式模型质量验收。
                  </p>
                ) : (
                  <>
                    <p>
                      还有 {releaseReadiness.blockers.length} 项准备工作未完成。完成后，系统才会把这份岗位要求用于匹配，避免因为未校验的数据给出误导性的推荐。
                    </p>
                    <div className="readiness-blocker-list">
                      {releaseReadiness.blockers.map((blocker, index) => {
                        const copy = (canConfirmRequirements || !extraction) && ["accepted_baseline_missing", "extraction_cohort_mismatch"].includes(blocker.code)
                          ? {title: extraction ? "请核对当前岗位要求" : "先提取，再核对当前岗位要求", description: "提取后对照原文检查全部要求，再确认这一版用于当前岗位匹配；不需要先替维护者完成整批模型质量评审。"}
                          : requirementReleaseBlockerCopy(blocker.code, job.description);
                        return (
                          <div className="readiness-blocker-item" key={`${copy.title}-${index}`}>
                            <strong>{copy.title}</strong>
                            <p>{copy.description}</p>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            ) : null}
            {extraction ? (
              <>
                <div className="requirement-run-meta">
                  <span>分析时间：{formatDateTime(extraction.createdAt)}</span>
                </div>
                {extraction.provider === "fixture" ? (
                  <p className="notice">
                    当前要求由离线演示分析产生，不代表真实模型质量。核对确认后可用于当前岗位的个人匹配验证，不代表模型整体质量评审通过。
                  </p>
                ) : null}
                <div className="requirement-list">
                  {sortJobRequirements(extraction.requirements).map((requirement) => (
                    <article className="requirement-card" key={requirement.requirementIndex}>
                      <div className="tags">
                        <span className={`tag importance-${requirement.importance}`}>
                          {requirementImportanceLabel(requirement.importance)}
                        </span>
                        <span className="tag">{requirementTypeLabel(requirement.type)}</span>
                        {requirement.normalizedCapability ? (
                          <span className="tag">{requirement.normalizedCapability}</span>
                        ) : null}
                      </div>
                      <p>{requirement.originalText}</p>
                      <small className="muted-copy">岗位原文依据</small>
                      <blockquote>{requirement.evidenceSpan}</blockquote>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="notice">
                {hasEnoughDescription ? "这个岗位还没有做要求分析。点击上方“分析岗位要求”后，系统会整理岗位描述中的学历、经验、技能和职责。" : descriptionIssue}
              </p>
            )}
            {canConfirmRequirements && extraction?.factsDigest && releaseReadiness ? (
                <JobRequirementConfirmation key={extraction.factsDigest}
                  jobId={job.id} extractionId={extraction.extractionId} inputHash={extraction.inputHash}
                  factsDigest={extraction.factsDigest} confirmed={!!releaseReadiness.userConfirmationId} />
              ) : null}
          </section>
        </article>

        <aside className="detail-card">
          <h2>岗位信息</h2>
          <div className="meta-list">
            <div><span className="meta-label">经验</span><strong>{job.experience || "未说明"}</strong></div>
            <div><span className="meta-label">学历</span><strong>{job.education || "未说明"}</strong></div>
            <div><span className="meta-label">来源</span><strong>{job.source === "manual" ? "手动粘贴" : job.source}</strong></div>
            <div><span className="meta-label">{job.source === "manual" ? "保存时间" : "采集时间"}</span><strong>{formatDateTime(job.collectedAt)}</strong></div>
            {job.source !== "manual" ? <div><span className="meta-label">该来源记录时间</span><strong>{formatDateTime(job.lastSeenAt ?? null)}</strong></div> : null}
          </div>
          <p className="muted-copy">{job.source === "manual" ? "此内容由用户手动粘贴，保存时间不代表岗位发布时间或仍在招聘，请自行核实岗位有效性。" : "该时间来自来源记录，缺失时可能使用报告时间或系统记录时间；不代表岗位仍在招聘，请打开原始岗位核实。"}</p>
          <JobAvailabilityControl jobId={job.id} inactive={job.userMarkedInactive} revision={job.availabilityRevision} />
          <div className="actions" style={{marginTop: 24}}>
            {job.sourceUrl ? <a className="button" href={job.sourceUrl} target="_blank" rel="noreferrer">
              打开原始岗位 ↗
            </a> : <p className="muted-copy">未提供原始岗位链接。</p>}
          </div>
        </aside>
      </section>
    </>
  );
}
