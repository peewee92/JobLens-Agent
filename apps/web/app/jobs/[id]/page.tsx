import Link from "next/link";
import {notFound} from "next/navigation";

import {JobRequirementExtractButton} from "@/components/job-requirement-extract-button";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchLatestJobRequirements,
} from "@/lib/backend";
import {formatDateTime, formatSalary} from "@/lib/format";
import {
  requirementImportanceLabel,
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
      caught instanceof BackendApiError ? caught.message : "读取岗位详情时发生未知错误。";
    return <ServiceError message={message} />;
  }

  let extraction = null;
  let requirementError = "";
  try {
    extraction = await fetchLatestJobRequirements(id);
  } catch (caught) {
    requirementError =
      caught instanceof BackendApiError
        ? caught.message
        : "读取结构化岗位要求时发生未知错误。";
  }

  return (
    <>
      <div className="actions" style={{marginBottom: 18}}>
        <Link className="button-ghost" href="/jobs">← 返回岗位池</Link>
      </div>
      <section className="detail-grid">
        <article className="detail-card">
          <header className="detail-header">
            <div>
              <p className="eyebrow">Job Detail</p>
              <h1>{job.title}</h1>
              <p className="company">{job.company}</p>
            </div>
            <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
          </header>

          <div className="tags">
            {job.area ? <span className="tag">{job.area}</span> : null}
            <RemoteStatusPill status={job.remoteStatus} />
            <span className="tag">置信等级：{job.remoteConfidence}</span>
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

          <section className="detail-section requirement-section">
            <div className="section-title-row">
              <div>
                <h2>结构化岗位要求</h2>
                <p className="lede requirement-lede">
                  后续 Eligibility、Match 和 Gap 只应引用这里的 Requirement ID 与 JD 证据片段。
                </p>
              </div>
              <JobRequirementExtractButton
                disabled={!job.description || job.description.trim().length < 40}
                hasExisting={extraction !== null}
                jobId={job.id}
              />
            </div>

            {requirementError ? <p className="inline-error">{requirementError}</p> : null}
            {extraction ? (
              <>
                <div className="requirement-run-meta">
                  <span className="version-badge">{extraction.extractorVersion}</span>
                  <span>Provider：{extraction.provider}</span>
                  <span>Model：{extraction.model}</span>
                  <span>抽取时间：{formatDateTime(extraction.createdAt)}</span>
                  <span className="code">Trace：{extraction.traceRunId}</span>
                </div>
                {extraction.provider === "fixture" ? (
                  <p className="notice">
                    当前为 Fixture 抽取结果，只证明工程链路可运行，不代表真实模型质量。
                  </p>
                ) : null}
                <div className="requirement-list">
                  {sortJobRequirements(extraction.requirements).map((requirement) => (
                    <article className="requirement-card" key={requirement.id}>
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
                      <blockquote>{requirement.evidenceSpan}</blockquote>
                      <small className="code">
                        {requirement.id} · confidence {requirement.confidence.toFixed(2)}
                      </small>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="notice">
                尚未生成 JobRequirement。原始 JD 仍可查看，但不能作为后续 Match 的隐式事实源。
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
            <div><span className="meta-label">JobLens ID</span><strong className="code">{job.id}</strong></div>
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
