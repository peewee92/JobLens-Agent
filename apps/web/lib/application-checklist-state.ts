export const APPLICATION_CHECKLIST_STORAGE_PREFIX = "joblens:application-checklist:v1";

export type ApplicationChecklistStepId = "highlight" | "gap" | "interview";

export interface ApplicationChecklistState {
  fingerprint: string;
  completed: ApplicationChecklistStepId[];
}

const VALID_STEP_IDS: ApplicationChecklistStepId[] = ["highlight", "gap", "interview"];

export function applicationChecklistStorageKey(jobId: string): string {
  return `${APPLICATION_CHECKLIST_STORAGE_PREFIX}:${jobId}`;
}

export function applicationChecklistFingerprint(items: Array<{id: ApplicationChecklistStepId; text: string}>): string {
  return items.map((item) => `${item.id}:${item.text.trim()}`).join("|");
}

export function parseApplicationChecklistState(raw: string | null, fingerprint: string): ApplicationChecklistState {
  if (!raw) return {fingerprint, completed: []};
  try {
    const parsed = JSON.parse(raw) as Partial<ApplicationChecklistState>;
    if (parsed.fingerprint !== fingerprint || !Array.isArray(parsed.completed)) {
      return {fingerprint, completed: []};
    }
    const completed = Array.from(new Set(parsed.completed.filter(
      (item): item is ApplicationChecklistStepId => VALID_STEP_IDS.includes(item as ApplicationChecklistStepId),
    )));
    return {fingerprint, completed};
  } catch {
    return {fingerprint, completed: []};
  }
}

export function isApplicationChecklistComplete(
  raw: string | null,
  items: Array<{id: ApplicationChecklistStepId; text: string}>,
): boolean {
  if (items.length === 0) return false;
  const fingerprint = applicationChecklistFingerprint(items);
  const state = parseApplicationChecklistState(raw, fingerprint);
  return items.every((item) => state.completed.includes(item.id));
}

export function toggleApplicationChecklistStep(
  state: ApplicationChecklistState,
  stepId: ApplicationChecklistStepId,
): ApplicationChecklistState {
  const completed = state.completed.includes(stepId)
    ? state.completed.filter((item) => item !== stepId)
    : [...state.completed, stepId];
  return {...state, completed};
}
