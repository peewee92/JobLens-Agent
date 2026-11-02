import type {MatchReportHistory, MatchReportHistoryItem} from "./contracts";

/** An old runtime reference must never fall back to the latest report. */
export function rankedReportSnapshot(history: MatchReportHistory, jobId: string, reportId: string): MatchReportHistoryItem | null {
  return history.items.find(item => item.reportId === reportId && item.report.jobId === jobId) ?? null;
}
