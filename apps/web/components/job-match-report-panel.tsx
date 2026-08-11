"use client";

import {useState} from "react";

import type {ApiErrorBody, JobMatchReport} from "@/lib/contracts";
import {
  matchRecommendationClasses,
  matchRecommendationDescriptions,
  matchRecommendationLabels,
} from "@/lib/match-report";
import {userFacingApiError} from "@/lib/user-facing-errors";

export function JobMatchReportPanel({
  jobId,
  enabled,
  disabledReason,
}: {
  jobId: string;
  enabled: boolean;
  disabledReason?: string;
}) {
  const [report, setReport] = useState<JobMatchReport | null>(null);
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [message, setMessage] = useState("");

  async function generateReport() {
    setStatus("submitting");
    setMessage("");
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/match-report`,
        {method: "POST"},
      );
      const body = (await response.json()) as JobMatchReport | ApiErrorBody;
      if (!response.ok) {
        throw new Error(
          userFacingApiError(
            "error" in body ? body : null,
            `完整匹配建议生成失败（${response.status}），请稍后重试。`,
          ),
        );
      }
      setReport(body as JobMatchReport);
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "生成完整匹配建议时发生未知错误。");
    }
  }

  const busy = status === "submitting";

  return (
    <div className="match-report-panel">
      <div className="match-report-panel-header">
        <div>
          <span className="review-label">完整匹配建议</span>
          <h3>从“能不能投”进一步看“值不值得投”</h3>
          <p>
            AI 只会判断已确认经历与岗位要求之间的语义关系；它不能改写硬条件结论，也不会生成百分制匹配概率。
          </p>
        </div>
        <button
          className="button-secondary match-report-action"
          disabled={!enabled || busy}
          onClick={generateReport}
          type="button"
        >
          {busy ? "正在生成…" : report ? "重新生成完整匹配建议" : "生成完整匹配建议"}
        </button>
      </div>

      {!enabled ? (
        <p className="notice">
          {disabledReason ?? "先完成职业背景确认和岗位要求质量检查，之后才能生成完整匹配建议。"}
        </p>
      ) : null}
      {enabled && !report ? (
        <p className="muted-copy match-report-disclaimer">
          点击后会运行一次 AI 匹配分析；结果不会自动保存，也不会替你投递岗位。
        </p>
      ) : null}
      {status === "error" ? <p className="inline-error">{message}</p> : null}

      {report ? (
        <div className="match-report-content">
          <section
            className={`match-recommendation-card ${matchRecommendationClasses[report.recommendation]}`}
          >
            <span className="review-label">推荐结论</span>
            <h3>{matchRecommendationLabels[report.recommendation]}</h3>
            <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p>
            <div className="match-report-counts" aria-label="完整匹配建议统计">
              <span><strong>{report.matchedRequirementIds.length}</strong> 明确匹配</span>
              <span><strong>{report.partialRequirementIds.length}</strong> 有相关证据</span>
              <span><strong>{report.missingRequirementIds.length}</strong> 硬条件缺口</span>
            </div>
          </section>

          <div className="match-insight-grid">
            <section className="match-insight-section">
              <div className="match-insight-heading">
                <h3>核心优势</h3>
                <span>{report.strengths.length} 项</span>
              </div>
              {report.strengths.length > 0 ? (
                <div className="match-insight-list">
                  {report.strengths.slice(0, 3).map((item) => (
                    <article className="match-insight-card match-insight-positive" key={item.requirementId}>
                      <strong>{item.requirementText}</strong>
                      <p>{item.reason}</p>
                      {item.evidenceIds.length > 0 ? (
                        <small className="muted-copy">有 {item.evidenceIds.length} 条已确认经历作为依据</small>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">当前还没有识别到足够明确的优势证据。</p>
              )}
            </section>

            <section className="match-insight-section">
              <div className="match-insight-heading">
                <h3>主要风险</h3>
                <span>{report.risks.length} 项</span>
              </div>
              {report.risks.length > 0 ? (
                <div className="match-insight-list">
                  {report.risks.slice(0, 3).map((item) => (
                    <article className="match-insight-card match-insight-risk" key={item.requirementId}>
                      <strong>{item.requirementText}</strong>
                      <p>{item.reason}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">当前没有发现需要优先提醒的明显风险。</p>
              )}
            </section>
          </div>

          {(report.strengths.length > 3 || report.risks.length > 3) ? (
            <p className="muted-copy">
              下方“已匹配 / 待确认 / 明显缺失”仍保留全部逐条依据，可继续核对细节。
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
