/** A requested scope must never silently fall back to unrelated jobs. */
export function initialAgentJobScope(jobIds: string[], requested?: string | readonly string[]): string[] {
  if (requested !== undefined) {
    const scope = typeof requested === "string" ? [requested] : [...requested];
    return scope.every(id => jobIds.includes(id)) ? scope : [];
  }
  return jobIds.slice(0, 5);
}

export function parseAgentScope(value: string | string[] | undefined): string[] | null {
  if (value === undefined) return null;
  const ids = typeof value === "string" ? [value] : value;
  if (!ids.length || ids.length > 50 || ids.some(id => !id.trim() || id.length > 100) || new Set(ids).size !== ids.length) return null;
  return [...ids];
}

/** Construct only local routes; callers must never accept an arbitrary return URL. */
export function agentScopeHref(ids: readonly string[]): string {
  const params = new URLSearchParams();
  ids.forEach(id => params.append("scopeJobId", id));
  return `/agent?${params}`;
}

export function jobDetailWithAgentScope(jobId: string, ids: readonly string[]): string {
  const params = new URLSearchParams();
  ids.forEach(id => params.append("scopeJobId", id));
  return `/jobs/${encodeURIComponent(jobId)}?${params}`;
}

export function initialScopeAnalysisHref(ids: readonly string[]): string {
  const params = new URLSearchParams();
  ids.forEach(id => params.append('scopeJobId', id));
  return `/agent/analyze?${params}`;
}

export function profileWithAgentScope(jobId: string, ids: readonly string[]): string {
  const params = new URLSearchParams({scopeFocusJobId: jobId});
  ids.forEach(id => params.append("scopeJobId", id));
  return `/profile?${params}`;
}

export function agentScopeFromProfile(focus: string | string[] | undefined, scope: string | string[] | undefined): {jobId: string; ids: string[]} | null {
  const ids = parseAgentScope(scope);
  if (typeof focus !== "string" || !ids || !ids.includes(focus)) return null;
  return {jobId: focus, ids};
}
