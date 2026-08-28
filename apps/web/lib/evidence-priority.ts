import type {MatchBlockerPriorityAction, UserFeedbackRecord} from "./contracts";

function feedbackWeight(decision: UserFeedbackRecord["decision"]): number {
  if (decision === "interested") return 2;
  if (decision === "maybe") return 1;
  return 0;
}

export function selectEvidenceFocusJobId(
  action: MatchBlockerPriorityAction | null,
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
): string | null {
  if (!action) return null;
  let bestJobId = action.affectedJobIds[0] ?? null;
  let bestWeight = bestJobId
    ? feedbackWeight(feedbackByJobId.get(bestJobId)?.decision ?? "rejected")
    : 0;

  for (const jobId of action.affectedJobIds.slice(1)) {
    const weight = feedbackWeight(feedbackByJobId.get(jobId)?.decision ?? "rejected");
    if (weight > bestWeight) {
      bestJobId = jobId;
      bestWeight = weight;
    }
  }
  return bestJobId;
}

export function selectNextEvidencePriority(
  actions: MatchBlockerPriorityAction[],
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
  excludedRequirementId: string | null,
): MatchBlockerPriorityAction | null {
  const eligible = actions.filter((action) =>
    !(
      excludedRequirementId
      && action.requirementIds.includes(excludedRequirementId)
    ),
  );
  const first = eligible[0];
  if (!first) return null;

  const tied = eligible.filter((action) =>
    action.affectedJobCount === first.affectedJobCount
    && action.missingRequirementCount === first.missingRequirementCount,
  );
  if (tied.length === 1 || feedbackByJobId.size === 0) return first;

  let best = first;
  let bestWeight = best.affectedJobIds.reduce(
    (total, jobId) => total + feedbackWeight(feedbackByJobId.get(jobId)?.decision ?? "rejected"),
    0,
  );

  for (const action of tied.slice(1)) {
    const weight = action.affectedJobIds.reduce(
      (total, jobId) => total + feedbackWeight(feedbackByJobId.get(jobId)?.decision ?? "rejected"),
      0,
    );
    if (weight > bestWeight) {
      best = action;
      bestWeight = weight;
    }
  }
  return best;
}
