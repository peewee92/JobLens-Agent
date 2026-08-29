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

export function evidencePriorityActionKey(action: Pick<MatchBlockerPriorityAction, "requirementType" | "normalizedCapability">): string {
  return `${action.requirementType}:${action.normalizedCapability?.trim().toLowerCase() || "_"}`;
}

export function parseEvidenceActionHistory(value: string | null | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((item) => item.trim().slice(0, 160))
    .filter(Boolean)
    .slice(-4);
}

export function appendEvidenceActionHistory(history: string[], actionKey: string | null): string[] {
  if (!actionKey) return [];
  return [...history.slice(-3), actionKey].slice(-4);
}

export function repeatedEvidenceActionKeys(history: string[]): Set<string> {
  const counts = new Map<string, number>();
  for (const key of history) counts.set(key, (counts.get(key) ?? 0) + 1);
  return new Set([...counts.entries()].filter(([, count]) => count >= 2).map(([key]) => key));
}

export function selectNextEvidencePriority(
  actions: MatchBlockerPriorityAction[],
  feedbackByJobId: ReadonlyMap<string, UserFeedbackRecord>,
  excludedRequirementId: string | null,
  deprioritizedActionKeys: ReadonlySet<string> = new Set(),
): MatchBlockerPriorityAction | null {
  const eligible = actions.filter((action) =>
    !(
      excludedRequirementId
      && action.requirementIds.includes(excludedRequirementId)
    ),
  );
  const fresh = eligible.filter((action) => !deprioritizedActionKeys.has(evidencePriorityActionKey(action)));
  const first = (fresh.length > 0 ? fresh : eligible)[0];
  if (!first) return null;
  if (feedbackByJobId.size === 0) return first;

  const stillRelevantEligible = eligible.filter((action) => consideredAffectedJobCount(action, feedbackByJobId) > 0);
  if (stillRelevantEligible.length === 0) return null;
  const freshRelevant = stillRelevantEligible.filter(
    (action) => !deprioritizedActionKeys.has(evidencePriorityActionKey(action)),
  );
  const stillRelevant = freshRelevant.length > 0 ? freshRelevant : stillRelevantEligible;

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
