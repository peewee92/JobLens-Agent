/** Preserve the requested cohort, never an arbitrary external return URL. */
export function gapScope(value: string | string[] | undefined): string[] {
  const ids = typeof value === "string" ? [value] : value ?? [];
  if (!ids.length || ids.length > 50 || ids.some(id => !/^[A-Za-z0-9_-]{1,120}$/.test(id))) return [];
  return [...new Set(ids)];
}

export function gapScopeHref(ids: readonly string[]): string {
  const params = new URLSearchParams({from: "agent"});
  ids.forEach(id => params.append("jobId", id));
  return `/gaps?${params}`;
}

export function withGapReturn(href: string, ids: readonly string[]): string {
  const url = new URL(href, "http://joblens.local");
  ids.forEach(id => url.searchParams.append("gapJobId", id));
  return `${url.pathname}${url.search}${url.hash}`;
}
