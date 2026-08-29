export type EvidenceActionStage = "pending" | "evidence_saved" | "rematch_verified" | "completed";

export interface EvidenceActionSnapshot {
  requirementId: string;
  jobId: string | null;
  capability: string | null;
  requirementText: string | null;
  stage: EvidenceActionStage;
  updatedAt: number;
}

export interface EvidenceActionState {
  current: EvidenceActionSnapshot | null;
  recentCompleted: EvidenceActionSnapshot[];
}

export const EVIDENCE_ACTION_STORAGE_KEY = "joblens:evidence-action:v1";
export const EVIDENCE_ACTION_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
export const EVIDENCE_ACTION_COMPLETED_LIMIT = 3;

export function parseEvidenceActionSnapshot(
  raw: string | null,
  now = Date.now(),
): EvidenceActionSnapshot | null {
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<EvidenceActionSnapshot>;
    if (
      typeof parsed.requirementId !== "string"
      || !parsed.requirementId.trim()
      || !["pending", "evidence_saved", "rematch_verified", "completed"].includes(parsed.stage ?? "")
      || typeof parsed.updatedAt !== "number"
      || !Number.isFinite(parsed.updatedAt)
      || now - parsed.updatedAt > EVIDENCE_ACTION_MAX_AGE_MS
      || parsed.updatedAt - now > 60_000
    ) {
      return null;
    }

    return {
      requirementId: parsed.requirementId.trim().slice(0, 120),
      jobId: typeof parsed.jobId === "string" ? parsed.jobId.trim().slice(0, 120) || null : null,
      capability: typeof parsed.capability === "string" ? parsed.capability.trim().slice(0, 120) || null : null,
      requirementText: typeof parsed.requirementText === "string"
        ? parsed.requirementText.trim().slice(0, 300) || null
        : null,
      stage: parsed.stage as EvidenceActionStage,
      updatedAt: parsed.updatedAt,
    };
  } catch {
    return null;
  }
}

export function parseEvidenceActionState(raw: string | null, now = Date.now()): EvidenceActionState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<EvidenceActionState & EvidenceActionSnapshot>;
    const legacyCurrent = typeof parsed.requirementId === "string"
      ? parseEvidenceActionSnapshot(raw, now)
      : null;
    const current = parsed.current ? parseEvidenceActionSnapshot(JSON.stringify(parsed.current), now) : legacyCurrent;
    const recentCompleted = Array.isArray(parsed.recentCompleted)
      ? parsed.recentCompleted
        .map((item) => parseEvidenceActionSnapshot(JSON.stringify(item), now))
        .filter((item): item is EvidenceActionSnapshot => item?.stage === "completed")
        .slice(0, EVIDENCE_ACTION_COMPLETED_LIMIT)
      : [];
    if (!current && recentCompleted.length === 0) return null;
    return {current, recentCompleted};
  } catch {
    return null;
  }
}

export function transitionEvidenceActionState(
  previous: EvidenceActionState | null,
  nextCurrent: EvidenceActionSnapshot | null,
  completeCurrent = false,
): EvidenceActionState {
  const completed = completeCurrent && previous?.current
    ? [{...previous.current, stage: "completed" as const, updatedAt: nextCurrent?.updatedAt ?? Date.now()}]
    : [];
  return {
    current: nextCurrent,
    recentCompleted: [...completed, ...(previous?.recentCompleted ?? [])].slice(0, EVIDENCE_ACTION_COMPLETED_LIMIT),
  };
}

export function evidenceActionStageLabel(stage: EvidenceActionStage): string {
  switch (stage) {
    case "pending":
      return "待核实";
    case "evidence_saved":
      return "已核实，等待可比较的 Re-match";
    case "rematch_verified":
      return "Re-match 已验证";
    case "completed":
      return "已完成";
  }
}
