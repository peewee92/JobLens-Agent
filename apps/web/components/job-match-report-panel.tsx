"use client";
import {matchCoverage} from "@/lib/match-coverage";

import {useState} from "react";
import {InsufficientEvidenceGuidance} from "@/components/insufficient-evidence-guidance";
import {PreferenceCheckList} from "@/components/preference-check-list";
import {useRouter, usePathname} from "next/navigation";
import {AuthorizedModelCall} from "@/components/authorized-model-call";
import {SavedMatchReportNotice} from "@/components/saved-match-report-notice";

import type {ApiErrorBody, JobMatchReport, MatchReportHistoryItem, SemanticCallPlan} from "@/lib/contracts";
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
  savedResult,
  returnHref,
  profileHref,
}: {
  jobId: string;
  enabled: boolean;
  disabledReason?: string;
  savedResult?: MatchReportHistoryItem | null;
  returnHref?: string;
  profileHref?: string;
}) {
  const [report, setReport] = useState<JobMatchReport | null>(savedResult?.report ?? null);
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [message, setMessage] = useState("");

  const router = useRouter();
  const pathname = usePathname();
  const [generated, setGenerated] = useState(false);
  const [semanticPlan, setSemanticPlan] = useState<SemanticCallPlan | null>(null);

  async function generateReport() {
    setStatus("submitting");
    setMessage("");
    try {
      const preview = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/semantic-call-plan`);
      if (!preview.ok) throw new Error("暂时无法核对匹配输入，请检查资料和岗位要求后重新操作；本次没有授权模型调用。");
      const plan = await preview.json() as SemanticCallPlan;
      if (plan.executionMode === "authorized" && plan.requirements.length > 0) {
        setSemanticPlan(plan);
        setStatus("idle");
        return;
      }
      setSemanticPlan(null);
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
      setGenerated(true);
      router.replace(returnHref ?? pathname, {scroll: false});
      router.refresh();
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "生成完整匹配建议时发生未知错误。");
    }
  }

  const busy = status === "submitting";
  const coverage = report ? matchCoverage(report) : null;

  return (
    <div className="match-report-panel" id="job-match-report">
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
      {enabled ? (
        <p className="muted-copy match-report-disclaimer">
          先检查当前输入：规则能判断时直接保存结果；需要模型时先展示要求与经历摘要，明确授权后才调用，不会替你投递岗位。
        </p>
      ) : null}
      {semanticPlan ? <AuthorizedModelCall key={semanticPlan.planDigest} jobId={jobId} plan={semanticPlan} disabled={!enabled || busy} kind="semantic" /> : null}
      {status === "error" ? <p className="inline-error">{message}</p> : null}

      {savedResult && !generated ? <SavedMatchReportNotice result={savedResult} /> : null}
      {report ? (
        <div className="match-report-content">
          <section
            className={`match-recommendation-card ${matchRecommendationClasses[report.recommendation]}`}
          >
            <span className="review-label">推荐结论</span>
            <h3>{matchRecommendationLabels[report.recommendation]}</h3>
            {!coverage!.noCandidates ? <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p> : null}
            {coverage!.noCandidates ? <p role="status" className="notice">已提取 {report.requirementResults.length} 条要求，但未找到可比较的经历证据，本次未进行语义判断。请核对已有资料与证据关联；不能据此断言你不具备能力。</p> : null}
            {coverage!.legacy ? <p className="muted-copy">历史报告未记录完整召回来源，无法追溯是否全部未召回。原结论仍保留，请按当前事实更新匹配；待核实不代表明确不满足。</p> : null}
            <div className="match-report-counts" aria-label="完整匹配建议统计">
              <span><strong>{coverage!.counts.supported}</strong> 已有支持</span>
              <span><strong>{coverage!.counts.partial}</strong> 部分支持</span>
              <span><strong>{coverage!.counts.uncovered}</strong> 证据未覆盖</span>
              <span><strong>{coverage!.counts.pending}</strong> 待核实</span>
              <span><strong>{coverage!.counts.conflict}</strong> 明确硬冲突</span>
            </div>
          </section>

          <PreferenceCheckList checks={report.preferenceChecks ?? []} version={report.searchIntentVersion} />
          {report.recommendation === "low" && <InsufficientEvidenceGuidance requirements={report.requirementResults} profileHref={profileHref} />}

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
                <p className="muted-copy">当前没有发现岗位要求方面的额外风险；求职偏好冲突见上方。</p>
              )}
            </section>
          </div>

          {(report.strengths.length > 3 || report.risks.length > 3) ? (
            <p className="muted-copy">
              下方“已匹配 / 待确认 / 明确不满足”仍保留全部逐条依据，可继续核对细节。
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
