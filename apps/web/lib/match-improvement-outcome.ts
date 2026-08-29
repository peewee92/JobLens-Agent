import type {MatchImprovement} from "@/lib/contracts";

export type MatchImprovementOutcome = "improved" | "unchanged" | "unverifiable";

export type FocusedRequirementOutcomeReason =
  | "unverifiable"
  | "resolved"
  | "resolved_with_other_hard_gaps"
  | "evidence_reached_requirement_but_still_missing"
  | "evidence_added_elsewhere"
  | "no_new_matching_evidence";

export function listNewlySupportedRequirements(
  improvement: MatchImprovement | null,
  excludedRequirementId: string | null = null,
): MatchImprovement["resolvedRequirements"] {
  if (!improvement || classifyMatchImprovementOutcome(improvement) === "unverifiable") return [];

  const byRequirementId = new Map<string, MatchImprovement["resolvedRequirements"][number]>();
  for (const evidence of improvement.newlySupportingEvidence) {
    for (const requirement of evidence.supportingRequirements) {
      if (requirement.requirementId === excludedRequirementId) continue;
      byRequirementId.set(requirement.requirementId, requirement);
    }
  }
  return [...byRequirementId.values()];
}

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

export function diagnoseFocusedRequirementOutcome(
  improvement: MatchImprovement | null,
  requirementId: string | null,
  stillMissing: boolean,
): FocusedRequirementOutcomeReason {
  if (!requirementId || classifyMatchImprovementOutcome(improvement) === "unverifiable" || !improvement) {
    return "unverifiable";
  }

  if (improvement.resolvedRequirementIds.includes(requirementId)) {
    return improvement.currentMissingRequirementCount > 0
      ? "resolved_with_other_hard_gaps"
      : "resolved";
  }

  if (!stillMissing) return "unverifiable";

  const focusedRequirementReceivedNewEvidence = improvement.newlySupportingEvidence.some((evidence) =>
    evidence.supportingRequirements.some((requirement) => requirement.requirementId === requirementId),
  );
  if (focusedRequirementReceivedNewEvidence) return "evidence_reached_requirement_but_still_missing";
  if (improvement.newlySupportingEvidence.length > 0) return "evidence_added_elsewhere";
  return "no_new_matching_evidence";
}

export function shouldDeferImmediateEvidenceRepeat(
  improvement: MatchImprovement | null,
  requirementId: string | null,
  stillMissing: boolean,
): boolean {
  if (!requirementId || !stillMissing) return false;
  return classifyMatchImprovementOutcome(improvement) === "unchanged";
}
