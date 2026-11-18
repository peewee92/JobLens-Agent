import {parseAgentScope} from "./agent-job-scope";
import {maxPastedJobs} from "./manual-job-import";

const key = "joblens:pasted-job-scope:v1";
type ScopeStorage = Pick<Storage, "getItem" | "setItem">;

export function lastPastedJobScope(storage: ScopeStorage): string[] {
  try {
    const ids: unknown = JSON.parse(storage.getItem(key) ?? "null");
    if (!Array.isArray(ids) || ids.length > maxPastedJobs || !ids.every(id => typeof id === "string")) return [];
    return parseAgentScope(ids) ?? [];
  } catch { return []; }
}

/** Only confirmed job identifiers, never raw pasted text or ambiguous results. */
export function savePastedJobScope(storage: ScopeStorage, ids: string[]) {
  if (ids.length === 0) return;
  try { storage.setItem(key, JSON.stringify(ids)); } catch { /* Saving jobs does not depend on browser storage. */ }
}
