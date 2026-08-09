import Link from "next/link";
import {notFound} from "next/navigation";

import {JobMatchReportPanel} from "@/components/job-match-report-panel";
import {JobRequirementExtractButton} from "@/components/job-requirement-extract-button";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchJobEligibility,
  fetchJobRequirementReleaseReadiness,
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
  requirementReleaseBlockerCopy,
  requirementReleaseLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";

export const dynamic = "force-dynamic";

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
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

  let extraction = null;
  let releaseReadiness = null;
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
    releaseReadiness = await fetchJobRequirementReleaseReadiness(id);
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

  return (
    <>
      <div className="actions" style={{marginBottom: 18}}>
        <Link className="button-ghost" href="/jobs">← 返回我的岗位</Link>
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

            <JobMatchReportPanel enabled={eligibility !== null} jobId={job.id} />

            {eligibilityError ? <p className="inline-error">{eligibilityError}</p> : null}
            {eligibility && groupedEligibility ? (
              <div className={`eligibility-summary eligibility-${eligibility.eligibility}`}>
                <div className="eligibility-summary-header">
                  <div>
                    <span className="review-label">当前判断</span>
                    <h3>{eligibilityLabels[eligibility.eligibility]}</h3>
                    <p>{eligibilityDescriptions[eligibility.eligibility]}</p>
                  </div>
                  <div className="eligibility-counts" aria-label="匹配结果统计">
                    <span><strong>{eligibility.matchedCount}</strong> 已匹配</span>
                    <span><strong>{eligibility.conditionalCount}</strong> 待确认</span>
                    <span><strong>{eligibility.missingCount}</strong> 明显缺失</span>
                  </div>
                </div>

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
                <p>
                  需要先确认你的职业背景，并让这份岗位要求通过质量检查。准备完成后，这里会显示“已匹配 / 待确认 / 明显缺失”。
                </p>
              </div>
            ) : null}
          </section>

          <section className="detail-section requirement-section">
            <div className="section-title-row">
              <div>
                <h2>岗位要求分析</h2>
                <p className="lede requirement-lede">
                  系统会先把原始岗位描述整理成可核对的学历、经验、技能和职责。只有完成质量检查的结果，才会用于后续岗位匹配。
                </p>
              </div>
              <JobRequirementExtractButton
                disabled={!job.description || job.description.trim().length < 40}
                hasExisting={extraction !== null}
                jobId={job.id}
              />
            </div>

            {requirementError ? <p className="inline-error">{requirementError}</p> : null}
            {releaseReadinessError ? (
              <p className="inline-error">岗位匹配准备状态暂时不可用：{releaseReadinessError}</p>
            ) : null}
            {releaseReadiness ? (
              <div className={`review-result ${releaseReadiness.releaseEligible ? "review-accepted" : "review-pending"}`}>
                <strong>{requirementReleaseLabel(releaseReadiness)}</strong>
                {releaseReadiness.releaseEligible ? (
                  <p>
                    这份岗位已经完成要求分析，并且当前分析方式已通过质量检查，可以作为后续岗位匹配的数据依据。
                  </p>
                ) : (
                  <>
                    <p>
                      还有 {releaseReadiness.blockers.length} 项准备工作未完成。完成后，系统才会把这份岗位要求用于匹配，避免因为未校验的数据给出误导性的推荐。
                    </p>
                    <div className="readiness-blocker-list">
                      {releaseReadiness.blockers.map((blocker, index) => {
                        const copy = requirementReleaseBlockerCopy(blocker.code);
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
                    当前是演示分析结果，仅用于验证功能，不会作为正式岗位匹配依据。
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
                这个岗位还没有做要求分析。点击上方“分析岗位要求”后，系统会把长篇岗位描述整理成更容易核对的学历、经验、技能和职责。
              </p>
            )}
          </section>
        </article>

        <aside className="detail-card">
          <h2>岗位信息</h2>
          <div className="meta-list">
            <div><span className="meta-label">经验</span><strong>{job.experience || "未说明"}</strong></div>
            <div><span className="meta-label">学历</span><strong>{job.education || "未说明"}</strong></div>
            <div><span className="meta-label">来源</span><strong>{job.source}</strong></div>
            <div><span className="meta-label">采集时间</span><strong>{formatDateTime(job.collectedAt)}</strong></div>
          </div>
          <div className="actions" style={{marginTop: 24}}>
            <a className="button" href={job.sourceUrl} target="_blank" rel="noreferrer">
              打开原始岗位 ↗
            </a>
          </div>
        </aside>
      </section>
    </>
  );
}
