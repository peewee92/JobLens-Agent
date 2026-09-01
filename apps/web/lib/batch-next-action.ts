export type BatchNextAction =
  | {kind: "feedback"; jobId: string}
  | {kind: "match"; count: number}
  | {kind: "requirement"; jobId: string; count: number}
  | {kind: "evidence"; impactCount: number}
  | {kind: "maybe"; jobId: string; count: number}
  | {kind: "unverifiable"; count: number}
  | {kind: "next-batch"};

export function selectBatchNextAction({
  pendingFeedbackJobIds,
  matchReadyJobIds,
  requirementBlockedJobIds,
  evidenceAvailable,
  evidenceImpactCount,
  maybeJobIds,
  unverifiableCount,
}: {
  pendingFeedbackJobIds: string[];
  matchReadyJobIds: string[];
  requirementBlockedJobIds: string[];
  evidenceAvailable: boolean;
  evidenceImpactCount: number;
  maybeJobIds: string[];
  unverifiableCount: number;
}): BatchNextAction {
  if (pendingFeedbackJobIds[0]) {
    return {kind: "feedback", jobId: pendingFeedbackJobIds[0]};
  }
  if (matchReadyJobIds.length > 0) {
    return {kind: "match", count: matchReadyJobIds.length};
  }
  if (requirementBlockedJobIds[0]) {
    return {
      kind: "requirement",
      jobId: requirementBlockedJobIds[0],
      count: requirementBlockedJobIds.length,
    };
  }
  if (evidenceAvailable) {
    return {kind: "evidence", impactCount: evidenceImpactCount};
  }
  if (maybeJobIds[0]) {
    return {kind: "maybe", jobId: maybeJobIds[0], count: maybeJobIds.length};
  }
  if (unverifiableCount > 0) {
    return {kind: "unverifiable", count: unverifiableCount};
  }
  return {kind: "next-batch"};
}
