import "server-only";
import {isSystemReadiness, type SystemReadiness} from "@/lib/system-readiness";

import type {
  ApiErrorBody,
  ApplicationExecutionAction,
  ApplicationEvidenceProposal,
  ApplicationTimelineEvent,
  ApplicationResumeVariant,
  ApplicationResumeVariantProposal,
  ApplicationInterviewQuestionSet,
  ApplicationWorkspaceOverview,
  BatchMatchRanking,
  CareerContextReleaseReadiness,
  MatchBlockerSummary,
  MatchImprovement,
  MatchReviewReadiness,
  RecommendationCoverage,
  JobDetail,
  MatchReportHistory,
  JobEligibilityResult,
  JobImportDetail,
  JobPreparationBundle,
  AcceptedProfileEvalBaseline,
  JobPage,
  JobRequirementExtraction,
  JobRequirementReleaseReadiness,
  ProfileEvalRunDetail,
  ProfileEvalRunPage,
  AcceptedRequirementEvalBaseline,
  AcceptedRequirementReviewBaseline,
  MvpQualityStatus,
  RequirementEvalRunDetail,
  RequirementEvalRunPage,
  RequirementAcceptanceReadiness,
  RequirementAcceptanceRunDetail,
  RequirementAcceptanceRunPage,
  RequirementReviewBatchDetail,
  RequirementReviewBatchPage,
  RequirementReviewCandidatePage,
  SearchIntent,
  UserFeedbackHistory,
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

/** Preserve actionable transport errors at same-origin recovery endpoints. */
export async function backendProxyResponse(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await backendResponse(path, init);
  } catch (error) {
    if (!(error instanceof BackendApiError)) throw error;
    return new Response(JSON.stringify({error: {code: error.code, message: error.message}}), {
      status: error.status, headers: {"Content-Type": "application/json"},
    });
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

export async function fetchSystemReadiness(): Promise<SystemReadiness> {
  const response = await backendResponse("/api/v1/readiness", {signal: AbortSignal.timeout(5000)});
  if (response.status !== 200 && response.status !== 503) throw await publicError(response);
  let body: unknown;
  try { body = await response.json(); } catch { body = null; }
  if (!isSystemReadiness(body) || body.ready !== response.ok) {
    throw new BackendApiError(503, "readiness_unavailable", "暂时无法确认运行环境，请检查后端版本。");
  }
  return body;
}

export function fetchJobPage(query: URLSearchParams): Promise<JobPage> {
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return backendJson<JobPage>(`/api/v1/jobs${suffix}`);
}

export function fetchJobDetail(jobId: string): Promise<JobDetail> {
  return backendJson<JobDetail>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchMatchRanking(
  jobIds: readonly string[],
  options: {includeBlocked?: boolean; topN?: number} = {},
): Promise<BatchMatchRanking> {
  const query = new URLSearchParams();
  for (const jobId of jobIds) {
    query.append("jobId", jobId);
  }
  if (options.includeBlocked !== undefined) {
    query.set("includeBlocked", String(options.includeBlocked));
  }
  if (options.topN !== undefined) {
    query.set("topN", String(options.topN));
  }
  return backendJson<BatchMatchRanking>(`/api/v1/match-ranking?${query.toString()}`);
}

export function fetchMatchBlockerSummary(
  jobIds: readonly string[],
): Promise<MatchBlockerSummary> {
  const query = new URLSearchParams();
  for (const jobId of jobIds) {
    query.append("jobId", jobId);
  }
  return backendJson<MatchBlockerSummary>(`/api/v1/match-blockers?${query.toString()}`);
}

export function fetchMatchImprovement(
  jobId: string,
  currentReportId: string,
): Promise<MatchImprovement> {
  const query = new URLSearchParams({jobId, currentReportId});
  return backendJson<MatchImprovement>(`/api/v1/match-improvement?${query.toString()}`);
}

export function fetchMatchReviewReadiness(): Promise<MatchReviewReadiness> {
  return backendJson<MatchReviewReadiness>("/api/v1/match-review/readiness");
}

export function fetchRecommendationCoverage(): Promise<RecommendationCoverage> {
  return backendJson<RecommendationCoverage>("/api/v1/recommendation-coverage");
}

export function fetchJobEligibility(jobId: string): Promise<JobEligibilityResult> {
  return backendJson<JobEligibilityResult>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/eligibility`,
  );
}

export function fetchLatestUserFeedback(matchReportIds: string[]): Promise<UserFeedbackHistory> {
  const query = new URLSearchParams();
  for (const matchReportId of matchReportIds) query.append("matchReportId", matchReportId);
  return backendJson<UserFeedbackHistory>(`/api/v1/user-feedback/latest?${query.toString()}`);
}

export function fetchUserFeedbackHistory(matchReportId: string): Promise<UserFeedbackHistory> {
  const query = new URLSearchParams({matchReportId});
  return backendJson<UserFeedbackHistory>(`/api/v1/user-feedback?${query.toString()}`);
}

export function fetchApplicationWorkspaceOverview(workspaceId: string): Promise<ApplicationWorkspaceOverview> {
  return backendJson<ApplicationWorkspaceOverview>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/overview`);
}

export function fetchApplicationInterviewQuestions(workspaceId: string): Promise<ApplicationInterviewQuestionSet> {
  return backendJson<ApplicationInterviewQuestionSet>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/interview/questions`);
}

export function fetchApplicationResumeVariantProposal(workspaceId: string): Promise<ApplicationResumeVariantProposal> {
  return backendJson<ApplicationResumeVariantProposal>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variant/proposal`);
}

export async function fetchApplicationResumeVariants(workspaceId: string): Promise<ApplicationResumeVariant[]> {
  return backendJson<ApplicationResumeVariant[]>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variants`);
}

export function fetchApplicationActions(workspaceId: string): Promise<ApplicationExecutionAction[]> {
  return backendJson<ApplicationExecutionAction[]>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/actions`);
}

export function fetchApplicationEvidenceProposals(workspaceId: string): Promise<ApplicationEvidenceProposal[]> {
  return backendJson<ApplicationEvidenceProposal[]>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals`);
}

export function fetchApplicationTimeline(workspaceId: string): Promise<ApplicationTimelineEvent[]> {
  return backendJson<ApplicationTimelineEvent[]>(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/timeline`);
}

export function fetchJobPreparation(jobId: string): Promise<JobPreparationBundle> {
  return backendJson<JobPreparationBundle>(
    `/api/v1/job-preparation/${encodeURIComponent(jobId)}`,
  );
}

export function fetchLatestJobRequirements(
  jobId: string,
): Promise<JobRequirementExtraction | null> {
  return optionalJson<JobRequirementExtraction>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/requirements`,
  );
}

export function fetchJobRequirementReleaseReadiness(
  jobId: string,
): Promise<JobRequirementReleaseReadiness> {
  return backendJson<JobRequirementReleaseReadiness>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/requirement-release-readiness`,
  );
}

export function fetchJobRequirementExtraction(
  jobId: string,
  extractionId: string,
): Promise<JobRequirementExtraction> {
  return backendJson<JobRequirementExtraction>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/requirement-extractions/${encodeURIComponent(extractionId)}`,
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

export function fetchCareerContextReleaseReadiness(): Promise<CareerContextReleaseReadiness> {
  return backendJson<CareerContextReleaseReadiness>(
    "/api/v1/career-context/release-readiness",
  );
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

export function fetchMvpQualityStatus(): Promise<MvpQualityStatus> {
  return backendJson<MvpQualityStatus>("/api/v1/requirement-evals/mvp-quality-status");
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

export function fetchRequirementAcceptanceReadiness(
  query: URLSearchParams,
): Promise<RequirementAcceptanceReadiness> {
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return backendJson<RequirementAcceptanceReadiness>(
    `/api/v1/requirement-acceptance-runs/readiness${suffix}`,
  );
}

export function fetchRequirementAcceptanceRuns(
  limit = 20,
  offset = 0,
): Promise<RequirementAcceptanceRunPage> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return backendJson<RequirementAcceptanceRunPage>(
    `/api/v1/requirement-acceptance-runs?${query}`,
  );
}

export function fetchRequirementAcceptanceRun(
  runId: string,
): Promise<RequirementAcceptanceRunDetail> {
  return backendJson<RequirementAcceptanceRunDetail>(
    `/api/v1/requirement-acceptance-runs/${encodeURIComponent(runId)}`,
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

export function fetchAcceptedRequirementReviewBaseline(): Promise<AcceptedRequirementReviewBaseline> {
  return backendJson<AcceptedRequirementReviewBaseline>(
    "/api/v1/requirement-review-batches/accepted-baseline",
  );
}


export function fetchMatchReportHistory(jobId: string): Promise<MatchReportHistory> {
  return backendJson<MatchReportHistory>(`/api/v1/jobs/${encodeURIComponent(jobId)}/match-reports`);
}

export function fetchWorkspaceSavedPreparation(workspaceId: string): Promise<import("./contracts").WorkspaceSavedPreparation> {
  return backendJson(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/preparation`);
}

export async function fetchWorkbench(): Promise<import("@/lib/workbench").Workbench> {
  return backendJson("/api/v1/workbench");
}


export function fetchApplicationEvidenceContext(workspaceId: string): Promise<import("@/lib/contracts").ApplicationEvidenceContext> {
  return backendJson(`/api/v1/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-context`);
}
