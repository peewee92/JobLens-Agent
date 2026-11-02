import type {JobMatchReport, MatchReportRequirementResult} from "./contracts";

export function matchCoverage(report: JobMatchReport) {
  const counts = {supported: 0, partial: 0, uncovered: 0, pending: 0, conflict: 0};
  for (const item of report.requirementResults) {
    counts[requirementCoverage(item)]++;
  }
  const noCandidates = report.eligibility !== "blocked" && report.requirementResults.length > 0 &&
    report.requirementResults.every(item => item.candidateCount === 0 &&
      item.assessmentSource === "deterministic" && item.eligibilityStatus === "conditional");
  const legacy = !report.retrievalVersion || report.requirementResults.some(
    item => item.candidateCount == null || item.assessmentSource == null);
  return {counts, noCandidates, legacy};
}


export function requirementCoverage(item: MatchReportRequirementResult) {
  if (item.eligibilityStatus === "missing") return "conflict";
  if (item.semanticVerdict === "matched") return "supported";
  if (item.semanticVerdict === "partial") return "partial";
  if (item.assessmentSource === "provider" && (item.candidateCount ?? 0) > 0) return "uncovered";
  return "pending";
}

export const coverageLabels = {
  conflict: "明确硬冲突", supported: "已有支持", partial: "部分支持",
  uncovered: "证据未覆盖", pending: "待核实",
};
