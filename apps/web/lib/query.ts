import type { JobSort, RemoteStatus, SearchParams } from "@/lib/contracts";

const REMOTE_STATUSES = new Set<RemoteStatus>([
  "confirmed",
  "rejected",
  "unknown",
]);
const SORTS = new Set<JobSort>(["latest", "salaryDesc", "salaryAsc"]);

export interface JobFilters {
  q: string;
  city: string;
  minSalaryK: string;
  remoteStatus: "" | RemoteStatus;
  source: string;
  sort: JobSort;
  limit: number;
  offset: number;
}

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function boundedInteger(
  value: string | string[] | undefined,
  fallback: number,
  min: number,
  max?: number,
): number {
  const parsed = Number.parseInt(first(value), 10);
  if (!Number.isFinite(parsed) || parsed < min) {
    return fallback;
  }
  return max === undefined ? parsed : Math.min(parsed, max);
}

export function parseJobFilters(searchParams: SearchParams): JobFilters {
  const remote = first(searchParams.remoteStatus);
  const sort = first(searchParams.sort);
  const minSalary = first(searchParams.minSalaryK).trim();
  const parsedMinSalary = minSalary === "" ? NaN : Number(minSalary);

  return {
    q: first(searchParams.q).trim(),
    city: first(searchParams.city).trim(),
    minSalaryK:
      Number.isFinite(parsedMinSalary) && parsedMinSalary >= 0
        ? String(parsedMinSalary)
        : "",
    remoteStatus: REMOTE_STATUSES.has(remote as RemoteStatus)
      ? (remote as RemoteStatus)
      : "",
    source: first(searchParams.source).trim().toLowerCase(),
    sort: SORTS.has(sort as JobSort) ? (sort as JobSort) : "latest",
    limit: boundedInteger(searchParams.limit, 20, 1, 100),
    offset: boundedInteger(searchParams.offset, 0, 0),
  };
}

export function buildJobQuery(filters: JobFilters): URLSearchParams {
  const query = new URLSearchParams();
  if (filters.q) query.set("q", filters.q);
  if (filters.city) query.set("city", filters.city);
  if (filters.minSalaryK) query.set("minSalaryK", filters.minSalaryK);
  if (filters.remoteStatus) query.set("remoteStatus", filters.remoteStatus);
  if (filters.source) query.set("source", filters.source);
  if (filters.sort !== "latest") query.set("sort", filters.sort);
  if (filters.limit !== 20) query.set("limit", String(filters.limit));
  if (filters.offset > 0) query.set("offset", String(filters.offset));
  return query;
}

export function jobsHref(filters: JobFilters, offset = filters.offset): string {
  const query = buildJobQuery({...filters, offset});
  const serialized = query.toString();
  return serialized ? `/jobs?${serialized}` : "/jobs";
}
