export type RemoteStatus = "confirmed" | "rejected" | "unknown";
export type RemoteConfidence = "high" | "medium" | "low";
export type JobSort = "latest" | "salaryDesc" | "salaryAsc";
export type ImportOutcome = "created" | "updated" | "skipped" | "error";

export interface JobListItem {
  id: string;
  title: string;
  company: string;
  area: string | null;
  salaryMinK: number | null;
  salaryMaxK: number | null;
  remoteStatus: RemoteStatus;
  remoteConfidence: RemoteConfidence;
  source: string;
  sourceUrl: string;
  sourceVersion: string | null;
  collectedAt: string | null;
}

export interface JobDetail extends JobListItem {
  experience: string | null;
  education: string | null;
  description: string | null;
  skills: string[];
}

export interface JobPage {
  total: number;
  limit: number;
  offset: number;
  items: JobListItem[];
}

export interface ImportResultError {
  index: number;
  stage: string;
  code: string;
  message: string;
}

export interface JobImportResult {
  importId: string;
  sourceVersion: string;
  received: number;
  created: number;
  updated: number;
  skipped: number;
  errors: ImportResultError[];
}

export interface JobImportCandidateSummary {
  total: number;
  kept: number;
  rejected: number;
  unknown: number;
}

export interface JobImportAuditItem {
  inputIndex: number;
  outcome: ImportOutcome;
  jobId: string | null;
  jobSourceId: string | null;
  errorCode: string | null;
  errorMessage: string | null;
}

export interface JobImportDetail {
  importId: string;
  sourceVersion: string;
  collectorVersion: string | null;
  received: number;
  created: number;
  updated: number;
  skipped: number;
  errors: ImportResultError[];
  searchIntentSnapshot: Record<string, unknown>;
  sourceSnapshot: Record<string, unknown>;
  candidateSummary: JobImportCandidateSummary;
  collectedAt: string | null;
  createdAt: string;
  items: JobImportAuditItem[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export type SearchParamValue = string | string[] | undefined;
export type SearchParams = Record<string, SearchParamValue>;
