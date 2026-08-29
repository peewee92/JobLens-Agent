import type {MatchBlockerJob, MatchBlockerPriorityAction, UserFeedbackRecord} from "./contracts";

export interface EvidencePriorityImpactTarget {
  jobId: string;
  requirementTexts: string[];
}

function feedbackWeight(decision: UserFeedbackRecord["decision"]): number {
  if (decision === "interested") return 2;
  if (decision === "maybe") return 1;
  return 0;
}

function isStillConsidered(
  jobId: string,
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
): boolean {
  return feedbackByJobId.get(jobId)?.decision !== "rejected";
}

export function consideredAffectedJobCount(
  action: MatchBlockerPriorityAction,
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
): number {
  return action.affectedJobIds.filter((jobId) => isStillConsidered(jobId, feedbackByJobId)).length;
}

export function selectEvidenceFocusJobId(
  action: MatchBlockerPriorityAction | null,
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
): string | null {
  if (!action) return null;
  const consideredJobIds = action.affectedJobIds.filter((jobId) => isStillConsidered(jobId, feedbackByJobId));
  const candidates = consideredJobIds.length > 0 ? consideredJobIds : action.affectedJobIds;
  let bestJobId = candidates[0] ?? null;
  let bestWeight = bestJobId
    ? feedbackWeight(feedbackByJobId.get(bestJobId)?.decision ?? "rejected")
    : 0;

  for (const jobId of candidates.slice(1)) {
    const weight = feedbackWeight(feedbackByJobId.get(jobId)?.decision ?? "rejected");
    if (weight > bestWeight) {
      bestJobId = jobId;
      bestWeight = weight;
    }
  }
  return bestJobId;
}

export function listEvidencePriorityImpactTargets(
  action: MatchBlockerPriorityAction | null,
  jobBlockers: MatchBlockerJob[],
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
): EvidencePriorityImpactTarget[] {
  if (!action) return [];

  const affectedJobOrder = new Map(action.affectedJobIds.map((jobId, index) => [jobId, index]));
  return jobBlockers
    .filter((job) => affectedJobOrder.has(job.jobId) && isStillConsidered(job.jobId, feedbackByJobId))
    .map((job) => ({
      jobId: job.jobId,
      requirementTexts: job.requirements
        .filter((requirement) => action.requirementIds.includes(requirement.requirementId))
        .map((requirement) => requirement.originalText),
    }))
    .filter((target) => target.requirementTexts.length > 0)
    .sort((left, right) => {
      const feedbackDelta = feedbackWeight(feedbackByJobId.get(right.jobId)?.decision ?? "rejected")
        - feedbackWeight(feedbackByJobId.get(left.jobId)?.decision ?? "rejected");
      if (feedbackDelta !== 0) return feedbackDelta;
      return (affectedJobOrder.get(left.jobId) ?? 0) - (affectedJobOrder.get(right.jobId) ?? 0);
    });
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
  if (feedbackByJobId.size === 0) return first;

  const stillRelevant = eligible.filter((action) => consideredAffectedJobCount(action, feedbackByJobId) > 0);
  if (stillRelevant.length === 0) return null;

  const maxConsideredJobs = Math.max(
    ...stillRelevant.map((action) => consideredAffectedJobCount(action, feedbackByJobId)),
  );
  const highestReach = stillRelevant.filter(
    (action) => consideredAffectedJobCount(action, feedbackByJobId) === maxConsideredJobs,
  );
  const maxMissingRequirements = Math.max(...highestReach.map((action) => action.missingRequirementCount));
  const tied = highestReach.filter((action) => action.missingRequirementCount === maxMissingRequirements);
  if (tied.length === 1) return tied[0];

  let best = tied[0];
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
