import type {MatchReportHistory, SavedCareerAnalysis} from "./contracts";

/** Join the exact historical report, not the latest report or the current profile. */
export function savedMatchSupport(
  saved: SavedCareerAnalysis,
  binding: SavedCareerAnalysis["bindings"][number],
  history: MatchReportHistory,
): string[] {
  if (!saved.selectedJobIds.includes(binding.jobId)) return [];
  const report = history.items.find(item => item.reportId === binding.matchReportId)?.report;
  if (!report || report.jobId !== binding.jobId || report.extractionId !== binding.extractionId ||
    report.profileId !== saved.profileId || report.profileVersion !== saved.profileVersion ||
    report.searchIntentId !== saved.searchIntentId || report.searchIntentVersion !== saved.searchIntentVersion ||
    report.policyVersion !== binding.policyVersion) return [];
  return report.requirementResults
    .filter(item => item.assessmentSource === "provider" && item.semanticVerdict === "partial" && item.evidenceIds.length > 0)
    .map(item => item.requirementId);
}
