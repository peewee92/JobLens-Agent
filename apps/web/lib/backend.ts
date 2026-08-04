import "server-only";

import type {
  ApiErrorBody,
  JobDetail,
  JobImportDetail,
  AcceptedProfileEvalBaseline,
  JobPage,
  JobRequirementExtraction,
  ProfileEvalRunDetail,
  ProfileEvalRunPage,
  AcceptedRequirementEvalBaseline,
  RequirementEvalRunDetail,
  RequirementEvalRunPage,
  RequirementReviewBatchDetail,
  RequirementReviewBatchPage,
  RequirementReviewCandidatePage,
  SearchIntent,
  UserProfile,
} from "@/lib/contracts";

export class BackendApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "BackendApiError";
  }
}

export function backendBaseUrl(): string {
  return (process.env.JOBLENS_BACKEND_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
}

async function publicError(response: Response): Promise<BackendApiError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    const code = body.error?.code ?? "backend_request_failed";
    const message = body.error?.message ?? `Backend request failed (${response.status}).`;
    return new BackendApiError(response.status, code, message);
  } catch {
    return new BackendApiError(
      response.status,
      "backend_request_failed",
      `Backend request failed (${response.status}).`,
    );
  }
}

export async function backendResponse(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(`${backendBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new BackendApiError(
      503,
      "backend_unavailable",
      "JobLens Backend 暂时不可用，请确认 FastAPI 已启动。",
    );
  }
}

export async function backendJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await backendResponse(path, init);
  if (!response.ok) {
    throw await publicError(response);
  }
  return (await response.json()) as T;
}

export function fetchJobPage(query: URLSearchParams): Promise<JobPage> {
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return backendJson<JobPage>(`/api/v1/jobs${suffix}`);
}

export function fetchJobDetail(jobId: string): Promise<JobDetail> {
  return backendJson<JobDetail>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchLatestJobRequirements(
  jobId: string,
): Promise<JobRequirementExtraction | null> {
  return optionalJson<JobRequirementExtraction>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/requirements`,
  );
}

export function fetchImportDetail(importId: string): Promise<JobImportDetail> {
  return backendJson<JobImportDetail>(
    `/api/v1/job-imports/${encodeURIComponent(importId)}`,
  );
}

async function optionalJson<T>(path: string): Promise<T | null> {
  try {
    return await backendJson<T>(path);
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function fetchCurrentProfile(): Promise<UserProfile | null> {
  return optionalJson<UserProfile>("/api/v1/profile");
}

export function fetchCurrentSearchIntent(): Promise<SearchIntent | null> {
  return optionalJson<SearchIntent>("/api/v1/search-intent");
}

export function fetchProfileEvalRuns(
  limit = 20,
  offset = 0,
): Promise<ProfileEvalRunPage> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return backendJson<ProfileEvalRunPage>(`/api/v1/profile-evals?${query}`);
}

export function fetchProfileEvalRun(
  evalRunId: string,
): Promise<ProfileEvalRunDetail> {
  return backendJson<ProfileEvalRunDetail>(
    `/api/v1/profile-evals/${encodeURIComponent(evalRunId)}`,
  );
}

export function fetchAcceptedProfileEvalBaseline(): Promise<AcceptedProfileEvalBaseline | null> {
  return optionalJson<AcceptedProfileEvalBaseline>(
    "/api/v1/profile-evals/baseline/accepted",
  );
}

export function fetchRequirementEvalRuns(
  limit = 20,
  offset = 0,
): Promise<RequirementEvalRunPage> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return backendJson<RequirementEvalRunPage>(
    `/api/v1/requirement-evals?${query}`,
  );
}

export function fetchRequirementEvalRun(
  evalRunId: string,
): Promise<RequirementEvalRunDetail> {
  return backendJson<RequirementEvalRunDetail>(
    `/api/v1/requirement-evals/${encodeURIComponent(evalRunId)}`,
  );
}

export function fetchAcceptedRequirementEvalBaseline(): Promise<AcceptedRequirementEvalBaseline | null> {
  return optionalJson<AcceptedRequirementEvalBaseline>(
    "/api/v1/requirement-evals/baseline/accepted",
  );
}

export function fetchRequirementReviewCandidates(
  limit = 100,
  offset = 0,
): Promise<RequirementReviewCandidatePage> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return backendJson<RequirementReviewCandidatePage>(
    `/api/v1/requirement-review-batches/candidates?${query}`,
  );
}

export function fetchRequirementReviewBatches(
  limit = 20,
  offset = 0,
): Promise<RequirementReviewBatchPage> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return backendJson<RequirementReviewBatchPage>(
    `/api/v1/requirement-review-batches?${query}`,
  );
}

export function fetchRequirementReviewBatch(
  batchId: string,
): Promise<RequirementReviewBatchDetail> {
  return backendJson<RequirementReviewBatchDetail>(
    `/api/v1/requirement-review-batches/${encodeURIComponent(batchId)}`,
  );
}
