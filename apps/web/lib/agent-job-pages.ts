import type {JobListItem, JobPage} from "./contracts";

/** Offset follows the returned page, never the merged list with a pinned job. */
export function appendAgentJobPage(current: readonly JobListItem[], page: JobPage, requestedOffset: number) {
  if (page.offset !== requestedOffset || page.limit !== 20 || !Array.isArray(page.items) || page.items.length > 20 || !Number.isInteger(page.total) || page.total < 0 || page.items.some(job => !job || typeof job.id !== "string")) {
    throw new Error("岗位列表发生变化或返回格式错误，请重试。");
  }
  if (page.items.length === 0 && requestedOffset < page.total) throw new Error("岗位列表已变化，请重新读取后重试。");
  const seen = new Set(current.map(job => job.id));
  const jobs = [...current];
  for (const job of page.items) if (!seen.has(job.id)) { jobs.push(job); seen.add(job.id); }
  const offset = requestedOffset + page.items.length;
  return {jobs, offset, hasMore: page.items.length > 0 && offset < page.total};
}
