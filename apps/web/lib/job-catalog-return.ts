import type {SearchParams} from "@/lib/contracts";
import {jobsHref, parseJobFilters} from "@/lib/query";

export function jobCatalogRowId(id: string) {
  return `saved-job-${encodeURIComponent(id)}`;
}

/** Only the catalog path and its existing filters may be used as a return destination. */
export function jobCatalogPath(value: unknown): string | null {
  if (typeof value !== "string" || !/^\/jobs(?:\?[^#]*)?$/.test(value)) return null;
  const params = new URLSearchParams(value.slice(6));
  const filters: SearchParams = {};
  for (const key of ["q", "city", "minSalaryK", "remoteStatus", "source", "sort", "limit", "offset"]) {
    const field = params.get(key);
    if (field !== null) filters[key] = field;
  }
  return jobsHref(parseJobFilters(filters));
}

export function withJobCatalogReturn(detailHref: string, catalogPath: string | null) {
  if (!catalogPath) return detailHref;
  return `${detailHref}${detailHref.includes("?") ? "&" : "?"}${new URLSearchParams({returnJobs: catalogPath})}`;
}
