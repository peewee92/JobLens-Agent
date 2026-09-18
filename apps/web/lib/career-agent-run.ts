export class CareerAgentRunHttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "CareerAgentRunHttpError";
  }
}

const SAFE_FACT_ID = /^[A-Za-z0-9_-]{1,120}$/;

export function shouldForgetPendingThread(error: unknown): boolean {
  return error instanceof CareerAgentRunHttpError && error.status === 404;
}

export function buildGapHandoffHref(jobIds: readonly string[]): string | null {
  const safeJobIds = Array.from(new Set(jobIds.filter((jobId) => SAFE_FACT_ID.test(jobId)))).slice(0, 10);
  if (safeJobIds.length === 0) return null;

  const query = new URLSearchParams();
  for (const jobId of safeJobIds) query.append("jobId", jobId);
  query.set("from", "agent");
  return `/gaps?${query.toString()}`;
}
