import type {MatchImprovement} from "@/lib/contracts";

export type MatchImprovementOutcome = "improved" | "unchanged" | "unverifiable";

export function classifyMatchImprovementOutcome(
  improvement: MatchImprovement | null,
): MatchImprovementOutcome {
  if (
    !improvement
    || !improvement.comparable
    || improvement.previousProfileVersion === null
    || improvement.previousProfileVersion === improvement.currentProfileVersion
  ) {
    return "unverifiable";
  }

  if (
    improvement.resolvedRequirementIds.length > 0
    || improvement.previousRecommendation !== improvement.currentRecommendation
  ) {
    return "improved";
  }

  return "unchanged";
}

export function shouldDeferImmediateEvidenceRepeat(
  improvement: MatchImprovement | null,
  requirementId: string | null,
  stillMissing: boolean,
): boolean {
  if (!requirementId || !stillMissing) return false;
  return classifyMatchImprovementOutcome(improvement) === "unchanged";
}
