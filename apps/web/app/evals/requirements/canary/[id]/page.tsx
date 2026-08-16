import Link from "next/link";
import {notFound} from "next/navigation";

import {RequirementCanaryReviewForm} from "@/components/requirement-canary-review-form";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobDetail,
  fetchJobRequirementExtraction,
  fetchRequirementAcceptanceRun,
} from "@/lib/backend";
import type {
  JobDetail,
  JobRequirementExtraction,
  RequirementAcceptanceRunCase,
} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";
import {
  requirementImportanceLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";
import {
  attemptedCanaryCases,
  requirementAcceptanceCaseIsProviderOutage,
  requirementAcceptanceCaseStatusClass,
  requirementAcceptanceCaseStatusLabels,
  requirementAcceptanceRunStatusClass,
  requirementAcceptanceRunStatusLabels,
} from "@/lib/requirement-acceptance-runs";

export const dynamic = "force-dynamic";

type CanaryEvidence = {
  runCase: RequirementAcceptanceRunCase;
  job: JobDetail | null;
  extraction: JobRequirementExtraction | null;
  jobReadError: string | null;
  extractionReadError: string | null;
};

function evidenceReadError(caught: unknown, fallback: string): string {
  return caught instanceof BackendApiError ? caught.message : fallback;
}

async function loadCanaryEvidence(
  runCase: RequirementAcceptanceRunCase,
): Promise<CanaryEvidence> {
  const [jobResult, extractionResult] = await Promise.allSettled([
    fetchJobDetail(runCase.jobId),
    runCase.extractionId
      ? fetchJobRequirementExtraction(runCase.jobId, runCase.extractionId)
      : Promise.resolve(null),
  ]);
  return {
    runCase,
    job: jobResult.status === "fulfilled" ? jobResult.value : null,
    extraction:
      extractionResult.status === "fulfilled" ? extractionResult.value : null,
    jobReadError:
      jobResult.status === "rejected"
        ? evidenceReadError(jobResult.reason, "读取当前 Job 证据失败。")
        : null,
    extractionReadError:
      extractionResult.status === "rejected"
        ? evidenceReadError(
            extractionResult.reason,
            "读取冻结的 Requirement Extraction 失败。",
          )
        : null,
  };
}

export default async function RequirementCanaryRunDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
  let run;
  try {
    run = await fetchRequirementAcceptanceRun(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) notFound();
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement Canary Run 时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const attemptedCases = attemptedCanaryCases(run.cases);
  const evidence = await Promise.all(attemptedCases.map(loadCanaryEvidence));

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">质量验收</p>
        <h1>Requirement 抽取结果人工抽查</h1>
        <p className="lede">
          请逐个对照岗位原文与抽取结果，重点判断是否有遗漏、误提取或重要程度判断错误。技术运行信息默认收起，只有排查问题时才需要查看。
        </p>
        <div className="actions">
          <Link className="button-ghost" href="/evals/requirements/canary">
            返回抽查列表
          </Link>
          {run.batchId ? (
            <Link
              className="button"
              href={`/evals/requirements/manual/${run.batchId}`}
            >
              打开完整 20 条验收
            </Link>
          ) : null}
        </div>
      </section>

      <div className="summary-grid">
        <div className="summary-card">
          <span>审核状态</span>
          <strong>{requirementAcceptanceRunStatusLabels[run.status]}</strong>
        </div>
        <div className="summary-card">
          <span>本次抽查</span>
          <strong>{attemptedCases.length} 个岗位</strong>
        </div>
        <div className="summary-card">
          <span>成功抽取</span>
          <strong>{run.completedCaseCount} 个</strong>
        </div>
        <div className="summary-card">
          <span>需要关注</span>
          <strong>{run.failedCount} 个</strong>
        </div>
      </div>

      <section className="detail-grid">
        <article className="detail-card">
          <div className="section-heading-row">
            <div>
              <h2>抽查结果</h2>
              <p className="muted">
                只需要判断两件事：岗位原文表达了什么，以及系统抽取出来的要求是否准确。内部运行记录不会影响你的质量判断。
              </p>
            </div>
            <span
              className={`status-chip ${requirementAcceptanceRunStatusClass(run.status)}`}
            >
              {requirementAcceptanceRunStatusLabels[run.status]}
            </span>
          </div>

          {evidence.length === 0 ? (
            <p className="notice">
              当前还没有可供人工抽查的岗位结果。
            </p>
          ) : (
            evidence.map(
              ({runCase, job, extraction, jobReadError, extractionReadError}) => {
              const requirements = extraction
                ? sortJobRequirements(extraction.requirements)
                : [];
              const providerOutage = requirementAcceptanceCaseIsProviderOutage(runCase);
              const exactDescription =
                runCase.descriptionSnapshot ??
                (runCase.descriptionIsCurrent ? job?.description ?? null : null);
              const descriptionEvidenceLabel = runCase.descriptionSnapshot
                ? "Run 创建时冻结的 JD 快照"
                : runCase.descriptionIsCurrent
                  ? "当前 JD 哈希仍匹配 Run，可作为兼容回退"
                  : "精确 JD 不可恢复；当前 Job 已变化";
              return (
                <section className="eval-case" key={runCase.id}>
                  <div className="eval-case-heading">
                    <div>
                      <span
                        className={`status-chip ${providerOutage ? "status-fixture" : requirementAcceptanceCaseStatusClass(runCase.status)}`}
                      >
                        {providerOutage
                          ? "服务暂不可用"
                          : runCase.status === "extracted" || runCase.status === "reused"
                            ? "抽取完成"
                            : requirementAcceptanceCaseStatusLabels[runCase.status]}
                      </span>
                      <strong>
                        #{runCase.caseIndex + 1} {runCase.title} · {runCase.company}
                      </strong>
                    </div>
                  </div>

                  {jobReadError ? (
                    <div className="inline-error">岗位原文读取失败：{jobReadError}</div>
                  ) : null}
                  {extractionReadError ? (
                    <div className="inline-error">
                      抽取结果读取失败：{extractionReadError}
                    </div>
                  ) : null}

                  <section className="detail-section">
                    <h3>岗位原文</h3>
                    <p className="muted">本次抽取实际使用的岗位描述。</p>
                    {!runCase.descriptionIsCurrent ? (
                      <p className="inline-error">
                        岗位原文在本次抽取后发生过变化。为避免把新内容误当成当时输入，本次审核必须以这里冻结的原文为准。
                      </p>
                    ) : null}
                    <p style={{whiteSpace: "pre-wrap"}}>
                      {exactDescription ??
                        "无法恢复本次抽取实际使用的岗位原文。请停止这次验收并重新开始。"}
                    </p>
                    <div className="actions">
                      <Link className="button-ghost" href={`/jobs/${runCase.jobId}`}>
                        打开岗位详情
                      </Link>
                      <a
                        className="button-ghost"
                        href={runCase.sourceUrl}
                        rel="noreferrer"
                        target="_blank"
                      >
                        打开来源页面
                      </a>
                    </div>
                  </section>

                  <section className="detail-section">
                    <h3>抽取结果（{requirements.length}）</h3>
                    <p className="muted">
                      重点检查是否漏掉关键要求、把非要求误当要求，或把“必须 / 优先 / 加分”判断错。
                    </p>
                    {requirements.length === 0 ? (
                      <p className="notice">
                        {providerOutage
                          ? "本岗位没有生成抽取结果，因为模型服务当时暂不可用。这不代表抽取质量不合格。"
                          : "本岗位没有生成可审核的抽取结果，请查看下方技术详情确认原因。"}
                      </p>
                    ) : (
                      <div className="eval-run-list">
                        {requirements.map((requirement) => (
                          <article className="eval-run-card" key={requirement.id}>
                            <div className="eval-run-card-heading">
                              <div>
                                <span
                                  className={`status-chip status-${requirement.importance === "must_have" ? "fail" : requirement.importance === "preferred" ? "live" : "fixture"}`}
                                >
                                  {requirementImportanceLabel(requirement.importance)}
                                </span>
                                <span className="status-chip status-fixture">
                                  {requirementTypeLabel(requirement.type)}
                                </span>
                              </div>
                            </div>
                            <strong>{requirement.originalText}</strong>
                            <p className="requirement-evidence">
                              <span>JD 原文依据</span>
                              {requirement.evidenceSpan}
                            </p>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <details className="canary-technical-details">
                    <summary>技术详情（开发调试）</summary>
                    <p className="muted">
                      这里保留模型调用、内部 ID、哈希和追踪信息，普通质量审核无需阅读。
                    </p>
                    <div className="meta-list compact-meta">
                      <div>
                        <span className="meta-label">Attempt</span>
                        <strong>{runCase.attemptCount}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Job ID</span>
                        <strong className="code">{runCase.jobId}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Extraction ID</span>
                        <strong className="code">{runCase.extractionId ?? "—"}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Trace ID</span>
                        <strong className="code">{runCase.traceRunId ?? "—"}</strong>
                      </div>
                      <div>
                        <span className="meta-label">JD 来源</span>
                        <strong>{descriptionEvidenceLabel}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Run JD SHA-256</span>
                        <strong className="code">{runCase.descriptionHash}</strong>
                      </div>
                      <div>
                        <span className="meta-label">当前 JD SHA-256</span>
                        <strong className="code">{runCase.currentDescriptionHash}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Capability</span>
                        <strong>{runCase.traceCapability ?? "—"}</strong>
                      </div>
                      <div>
                        <span className="meta-label">Model / Prompt</span>
                        <strong>
                          {runCase.traceModel ?? "—"} / {runCase.tracePromptVersion ?? "—"}
                        </strong>
                      </div>
                      <div>
                        <span className="meta-label">Latency</span>
                        <strong>
                          {runCase.traceLatencyMs === null
                            ? "—"
                            : `${runCase.traceLatencyMs} ms`}
                        </strong>
                      </div>
                      <div>
                        <span className="meta-label">Tokens</span>
                        <strong>
                          {runCase.traceInputTokens ?? "—"} in / {runCase.traceOutputTokens ?? "—"} out
                        </strong>
                      </div>
                      <div>
                        <span className="meta-label">Trace 时间</span>
                        <strong>
                          {runCase.traceCreatedAt
                            ? formatDateTime(runCase.traceCreatedAt)
                            : "—"}
                        </strong>
                      </div>
                    </div>
                    {requirements.length > 0 ? (
                      <div className="canary-requirement-debug-list">
                        <strong>Requirement 内部字段</strong>
                        {requirements.map((requirement) => (
                          <p className="code" key={requirement.id}>
                            {requirement.id} · normalized={requirement.normalizedCapability ?? "—"} · confidence={Math.round(requirement.confidence * 100)}%
                          </p>
                        ))}
                      </div>
                    ) : null}
                    {providerOutage ? (
                      <div className="notice">
                        <strong>Provider outage 证据（不计入 v6 质量判断）</strong>
                        <p className="code">Trace：{runCase.traceError ?? "—"}</p>
                        <p className="code">
                          Case：{runCase.errorCode ?? "unknown"} · {runCase.errorMessage ?? "—"}
                        </p>
                      </div>
                    ) : (
                      <>
                        {runCase.traceError ? (
                          <p className="inline-error">Trace error：{runCase.traceError}</p>
                        ) : (
                          <p className="notice">本次调用未记录技术错误。</p>
                        )}
                        {runCase.errorCode || runCase.errorMessage ? (
                          <p className="inline-error">
                            Case error：{runCase.errorCode ?? "unknown"} · {runCase.errorMessage ?? "—"}
                          </p>
                        ) : null}
                      </>
                    )}
                  </details>
                </section>
              );
            },
            )
          )}
        </article>

        <aside className="detail-card">
          <h2>人工判断</h2>
          <p className="muted">
            看完左侧抽查结果后，再决定是否允许继续扩大到剩余岗位。这里的决定只控制下一步，不代表最终质量验收已经通过。
          </p>
          <div className="meta-list">
            <div>
              <span className="meta-label">审核人</span>
              <strong>{run.reviewer}</strong>
            </div>
            <div>
              <span className="meta-label">最近更新</span>
              <strong>{formatDateTime(run.updatedAt)}</strong>
            </div>
          </div>

          <section className="detail-section">
            <h3>决策</h3>
            {run.canaryReview ? (
              <div
                className={`review-result review-${run.canaryReview.decision === "continue" ? "accepted" : "rejected"}`}
              >
                <strong>
                  {run.canaryReview.decision === "continue" ? "已允许继续" : "已停止这次验收"}
                </strong>
                <p>{run.canaryReview.notes}</p>
                <small>{formatDateTime(run.canaryReview.reviewedAt)}</small>
                <details className="canary-technical-details compact-technical-details">
                  <summary>查看审核记录 ID</summary>
                  <p className="code">
                    Cases：{run.canaryReview.reviewedCaseIds.join(", ")}
                  </p>
                  <p className="code">
                    Extractions：{run.canaryReview.reviewedExtractionIds.join(", ") || "—"}
                  </p>
                  <p className="code">
                    Traces：{run.canaryReview.reviewedTraceRunIds.join(", ")}
                  </p>
                </details>
              </div>
            ) : (
              <RequirementCanaryReviewForm
                runId={run.id}
                reviewer={run.reviewer}
                continueAllowed={run.canaryContinueAllowed}
                stopAllowed={run.canaryStopAllowed}
                blockReason={run.canaryReviewBlockReason}
              />
            )}
          </section>

          <section className="detail-section">
            <h3>这一步代表什么</h3>
            <p className="notice">
              选择“允许继续”只表示这 1～3 个抽查样本没有发现需要立即停止的问题。剩余岗位完成后仍要进行完整人工验收，不能直接进入匹配流程。
            </p>
          </section>

          <details className="canary-technical-details">
            <summary>技术详情（开发调试）</summary>
            <div className="meta-list compact-meta">
              <div>
                <span className="meta-label">Run title</span>
                <strong>{run.title}</strong>
              </div>
              <div>
                <span className="meta-label">Run ID</span>
                <strong className="code">{run.id}</strong>
              </div>
              <div>
                <span className="meta-label">Provider / Model</span>
                <strong>{run.provider} / {run.model}</strong>
              </div>
              <div>
                <span className="meta-label">Extractor / Prompt</span>
                <strong>{run.extractorVersion} / {run.promptVersion}</strong>
              </div>
              <div>
                <span className="meta-label">首次 / 最近 Import</span>
                <strong className="code">
                  {run.firstImportId} / {run.lastImportId}
                </strong>
              </div>
              <div>
                <span className="meta-label">Provider 调用数</span>
                <strong>{run.attemptedCalls}</strong>
              </div>
              <div>
                <span className="meta-label">Deferred</span>
                <strong>{run.deferredCount}</strong>
              </div>
            </div>
          </details>
        </aside>
      </section>
    </>
  );
}
