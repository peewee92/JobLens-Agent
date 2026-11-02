import type {UserFeedbackHistory} from "@/lib/contracts";

/** The feedback endpoint accepts at most 50 reports. A failed batch invalidates the whole view. */
export async function fetchImportFeedbackBatches(
  reportIds: readonly string[],
  fetchBatch: (ids: string[]) => Promise<UserFeedbackHistory>,
): Promise<UserFeedbackHistory> {
  const ids = [...new Set(reportIds)];
  const batches: string[][] = [];
  for (let offset = 0; offset < ids.length; offset += 50) batches.push(ids.slice(offset, offset + 50));
  const results = await Promise.all(batches.map(fetchBatch));
  return {
    feedback: results.flatMap(result => result.feedback),
    dbWrites: results.reduce((sum, result) => sum + result.dbWrites, 0),
    providerCalls: results.reduce((sum, result) => sum + result.providerCalls, 0),
    traceRunsCreated: results.reduce((sum, result) => sum + result.traceRunsCreated, 0),
  };
}
