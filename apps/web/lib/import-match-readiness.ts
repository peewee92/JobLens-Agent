import type {JobRequirementReleaseReadiness} from "./contracts";

export type ImportMatchReadiness = "matched" | "ready" | "requirements_blocked" | "inactive" | "unknown";
export type ImportMatchInputs = {jobId: string; inputsReleaseEligible: boolean; jobRequirements: JobRequirementReleaseReadiness};

/** Match uses the embedded MVP-compatible gate, not the stricter formal-review endpoint. */
export function validImportMatchInputs(jobId: string, value: ImportMatchInputs | null | undefined): value is ImportMatchInputs {
  return value?.jobId === jobId && typeof value.inputsReleaseEligible === "boolean"
    && value.jobRequirements?.jobId === jobId && typeof value.jobRequirements.releaseEligible === "boolean"
    && Array.isArray(value.jobRequirements.blockers);
}

/** A failed read or a blocked career context must never be treated as ready. */
export function classifyImportMatchReadiness(input: {
  rankingAvailable: boolean; ranked: boolean; matchInputsReady: boolean | null; requirementsReady: boolean | null;
  userMarkedInactive?: boolean | null;
}): ImportMatchReadiness {
  if (input.userMarkedInactive === true) return "inactive";
  if (input.userMarkedInactive === null) return "unknown";
  if (!input.rankingAvailable) return "unknown";
  // These are separate reads, not a transactional snapshot. Never use a
  // report or a positive input check to override a conflicting later read.
  if (input.ranked && (input.matchInputsReady !== true || input.requirementsReady !== true)) return "unknown";
  if (input.matchInputsReady === true && input.requirementsReady === false) return "unknown";
  if (input.requirementsReady === false) return "requirements_blocked";
  if (input.matchInputsReady !== true || input.requirementsReady !== true) return "unknown";
  if (input.ranked) return "matched";
  return "ready";
}

/** Import audit entries are observations; processing scope is distinct job identity. */
export function importedUniqueJobIds(items: ReadonlyArray<{jobId: string | null}>): string[] {
  return [...new Set(items.flatMap(item => item.jobId ? [item.jobId] : []))];
}
