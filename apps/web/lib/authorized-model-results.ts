function withSavedResult(detailHref: string, param: string, id: string, anchor: string): string {
  const [pathAndQuery] = detailHref.split("#", 1);
  const [pathname, query] = pathAndQuery.split("?", 2);
  const params = new URLSearchParams(query);
  params.set(param, id);
  return `${pathname}?${params}#${anchor}`;
}

/** Select the exact saved match report, preserving the comparison/return context. */
export function savedModelReportHref(detailHref: string, reportId: string): string {
  return withSavedResult(detailHref, "reportId", reportId, "job-match-report");
}

/** Distinguish the post-save document from the pre-save navigation cache. */
export function savedModelExtractionHref(detailHref: string, extractionId: string): string {
  return withSavedResult(detailHref, "reviewExtraction", extractionId, "job-requirements");
}

export function requirementsConfirmedHref(detailHref: string, extractionId: string): string {
  return withSavedResult(detailHref, "confirmedRequirements", extractionId, "job-match-report");
}

export function jobDocumentRoute(location: Pick<Location, "pathname" | "search">): string {
  return location.pathname + location.search;
}

export function openSavedJobDocument(
  location: Pick<Location, "pathname" | "search" | "hash" | "reload" | "replace">,
  href: string,
  startedOn: string,
) {
  const current = jobDocumentRoute(location);
  // A response may arrive after the user moves to another job or changes comparison scope.
  if (current !== startedOn) return;
  // A client-router refresh alone can leave the pre-save job content visible.
  if (current + location.hash === href) location.reload();
  else location.replace(href);
}
