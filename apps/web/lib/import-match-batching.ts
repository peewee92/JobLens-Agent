/** Import batches may exceed the analysis scope limit; never discard the remainder. */
export function splitImportMatchBatch(pending: readonly string[]) {
  return {requestJobIds: pending.slice(0, 50), untouchedJobIds: pending.slice(50)};
}

export function mergeImportMatchRemainder(resumeJobIds: readonly string[], untouchedJobIds: readonly string[]) {
  return Array.from(new Set([...resumeJobIds, ...untouchedJobIds]));
}

export function splitAnalysisScopes(jobIds: readonly string[]): string[][] {
  const scopes: string[][] = [];
  for (let i = 0; i < jobIds.length; i += 50) scopes.push(jobIds.slice(i, i + 50));
  return scopes;
}

export function importMatchButtonLabel(pendingCount: number, hasProcessed: boolean, running: boolean): string {
  if (running) return "正在匹配…";
  return hasProcessed ? `继续匹配剩余 ${pendingCount} 个` : `匹配这批已准备岗位（${Math.min(pendingCount, 5)} 个）`;
}

/** A timeout or server failure does not prove that prior writes were rolled back. */
export function isUncertainMatchResponse(status: number): boolean {
  return status === 408 || status >= 500;
}
