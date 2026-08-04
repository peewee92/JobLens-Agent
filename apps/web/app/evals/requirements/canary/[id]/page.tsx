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
        <p className="eyebrow">Requirement Canary Evidence Workbench</p>
        <h1>{run.title}</h1>
        <p className="lede">
          这里展示后端冻结的 Run、Case、Extraction 和 Trace 事实。请亲自比较完整 JD 与抽取结果，再提交一次性 Continue 或 Stop；页面不会启动或续跑 Provider。
        </p>
        <p className="code">{run.id}</p>
        <div className="actions">
          <Link className="button-ghost" href="/evals/requirements/canary">
            返回 Canary Run 列表
          </Link>
          {run.batchId ? (
            <Link
              className="button"
              href={`/evals/requirements/manual/${run.batchId}`}
            >
              打开 20 条人工验收批次
            </Link>
          ) : null}
        </div>
      </section>

      <div className="summary-grid">
        <div className="summary-card">
          <span>Run 状态</span>
          <strong>{requirementAcceptanceRunStatusLabels[run.status]}</strong>
        </div>
        <div className="summary-card">
          <span>累计 Provider 调用</span>
          <strong>{run.attemptedCalls}</strong>
        </div>
        <div className="summary-card">
          <span>完成 Case</span>
          <strong>{run.completedCaseCount}/20</strong>
        </div>
        <div className="summary-card">
          <span>失败 / Deferred</span>
          <strong>{run.failedCount} / {run.deferredCount}</strong>
        </div>
      </div>

      <section className="detail-grid">
        <article className="detail-card">
          <div className="section-heading-row">
            <div>
              <h2>Canary 证据</h2>
              <p className="muted">
                决策前展示当前已尝试的 Canary 候选；决策后只展示不可变 Review 冻结的 Case。安全复用、未调用和 Continue 后的后续调用不会混入原始放行证据。
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
              当前没有已尝试的 Canary Case。先通过 CLI 对正式数据集执行 1～3 次真实调用。
            </p>
          ) : (
            evidence.map(
              ({runCase, job, extraction, jobReadError, extractionReadError}) => {
              const requirements = extraction
                ? sortJobRequirements(extraction.requirements)
                : [];
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
                        className={`status-chip ${requirementAcceptanceCaseStatusClass(runCase.status)}`}
                      >
                        {requirementAcceptanceCaseStatusLabels[runCase.status]}
                      </span>
                      <strong>
                        #{runCase.caseIndex + 1} {runCase.title} · {runCase.company}
                      </strong>
                    </div>
                    <span className="code">attempts={runCase.attemptCount}</span>
                  </div>

                  <div className="meta-list compact-meta">
                    <div>
                      <span className="meta-label">Job</span>
                      <strong className="code">{runCase.jobId}</strong>
                    </div>
                    <div>
                      <span className="meta-label">Extraction</span>
                      <strong className="code">{runCase.extractionId ?? "—"}</strong>
                    </div>
                    <div>
                      <span className="meta-label">Trace</span>
                      <strong className="code">{runCase.traceRunId ?? "—"}</strong>
                    </div>
                    <div>
                      <span className="meta-label">Run JD SHA-256</span>
                      <strong className="code">{runCase.descriptionHash}</strong>
                    </div>
                    <div>
                      <span className="meta-label">当前 JD SHA-256</span>
                      <strong className="code">
                        {runCase.currentDescriptionHash}
                      </strong>
                    </div>
                  </div>

                  {jobReadError ? (
                    <div className="inline-error">Job read：{jobReadError}</div>
                  ) : null}
                  {extractionReadError ? (
                    <div className="inline-error">
                      Extraction read：{extractionReadError}
                    </div>
                  ) : null}

                  <section className="detail-section">
                    <h3>Canary 当时的完整 JD</h3>
                    <p className="notice">证据来源：{descriptionEvidenceLabel}</p>
                    {!runCase.descriptionIsCurrent ? (
                      <p className="inline-error">
                        当前 Job.description 的 SHA-256 已与 Run 不同。人工判断必须使用冻结快照，不能把当前 JD 当作原始输入。
                      </p>
                    ) : null}
                    <p style={{whiteSpace: "pre-wrap"}}>
                      {exactDescription ??
                        "该旧 Run 没有可信 JD 快照，且当前 JD 哈希不匹配。请停止该 Run 或重新创建正式数据集。"}
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
                    <h3>抽取出的 Requirements（{requirements.length}）</h3>
                    {requirements.length === 0 ? (
                      <p className="notice">
                        没有成功 Extraction。请重点检查 Trace 错误，并倾向 Stop，而不是把失败样本忽略掉。
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
                              <span>{Math.round(requirement.confidence * 100)}%</span>
                            </div>
                            <strong>{requirement.originalText}</strong>
                            <p>
                              归一化能力：{requirement.normalizedCapability ?? "—"}
                            </p>
                            <p className="notice">
                              Evidence：{requirement.evidenceSpan}
                            </p>
                            <p className="code">{requirement.id}</p>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className="detail-section">
                    <h3>Trace 摘要</h3>
                    <div className="meta-list compact-meta">
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
                    {runCase.traceError ? (
                      <p className="inline-error">Trace error：{runCase.traceError}</p>
                    ) : (
                      <p className="notice">Trace 未记录错误。</p>
                    )}
                    {runCase.errorCode || runCase.errorMessage ? (
                      <p className="inline-error">
                        Case error：{runCase.errorCode ?? "unknown"} · {runCase.errorMessage ?? "—"}
                      </p>
                    ) : null}
                  </section>
                </section>
              );
            },
            )
          )}
        </article>

        <aside className="detail-card">
          <h2>人工门禁</h2>
          <div className="meta-list">
            <div>
              <span className="meta-label">Reviewer</span>
              <strong>{run.reviewer}</strong>
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
              <span className="meta-label">更新时间</span>
              <strong>{formatDateTime(run.updatedAt)}</strong>
            </div>
          </div>

          <section className="detail-section">
            <h3>决策</h3>
            {run.canaryReview ? (
              <div
                className={`review-result review-${run.canaryReview.decision === "continue" ? "accepted" : "rejected"}`}
              >
                <strong>{run.canaryReview.decision}</strong>
                <p>{run.canaryReview.notes}</p>
                <p className="code">
                  Cases：{run.canaryReview.reviewedCaseIds.join(", ")}
                </p>
                <p className="code">
                  Extractions：{run.canaryReview.reviewedExtractionIds.join(", ") || "—"}
                </p>
                <p className="code">
                  Traces：{run.canaryReview.reviewedTraceRunIds.join(", ")}
                </p>
                <small>{formatDateTime(run.canaryReview.reviewedAt)}</small>
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
            <h3>范围边界</h3>
            <p className="notice">
              Continue 只解除该 Run 的 Canary 门禁。后续 Provider 调用仍由 CLI 显式预算控制；20 条完成后还必须进入逐岗位人工验收，不能直接进入 Match。
            </p>
          </section>
        </aside>
      </section>
    </>
  );
}
