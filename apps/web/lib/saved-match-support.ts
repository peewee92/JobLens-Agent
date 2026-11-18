import type {MatchReportHistory, SavedCareerAnalysis} from "./contracts";

/** Join the exact historical report, not the latest report or the current profile. */
export function savedMatchSupport(
  saved: SavedCareerAnalysis,
  binding: SavedCareerAnalysis["bindings"][number],
  history: MatchReportHistory,
): {partial: readonly string[]; matched: readonly string[]} {
  const empty = {partial: [], matched: []};
  if (!saved.selectedJobIds.includes(binding.jobId)) return empty;
  const report = history.items.find(item => item.reportId === binding.matchReportId)?.report;
  if (!report || report.jobId !== binding.jobId || report.extractionId !== binding.extractionId ||
    report.profileId !== saved.profileId || report.profileVersion !== saved.profileVersion ||
    report.searchIntentId !== saved.searchIntentId || report.searchIntentVersion !== saved.searchIntentVersion ||
    report.policyVersion !== binding.policyVersion) return empty;
  const cited = report.requirementResults.filter(item => item.assessmentSource === "provider" && item.evidenceIds.length > 0);
  return {
    partial: cited.filter(item => item.semanticVerdict === "partial").map(item => item.requirementId),
    matched: cited.filter(item => item.semanticVerdict === "matched").map(item => item.requirementId),
  };
}
