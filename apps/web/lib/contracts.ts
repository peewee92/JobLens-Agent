export type RemoteStatus = "confirmed" | "rejected" | "unknown";
export type RemoteConfidence = "high" | "medium" | "low";
export type JobSort = "latest" | "salaryDesc" | "salaryAsc";
export type ImportOutcome = "created" | "updated" | "skipped" | "error";
export type EvidenceType =
  | "work"
  | "project"
  | "education"
  | "achievement"
  | "self_report";
export type SkillLevel = "strong" | "working" | "basic" | "unknown";
export type Seniority =
  | "intern"
  | "junior"
  | "mid"
  | "senior"
  | "staff"
  | "lead"
  | "principal";

export interface ProfileEvidence {
  id: string;
  key: string;
  type: EvidenceType;
  summary: string;
  source: string;
}

export interface ProfileSkill {
  id: string;
  name: string;
  level: SkillLevel;
  evidenceIds: string[];
}

export interface UserProfile {
  id: string;
  version: number;
  headline: string;
  yearsOfExperience: number | null;
  evidence: ProfileEvidence[];
  skills: ProfileSkill[];
  createdAt: string;
}

export interface SaveProfilePayload {
  expectedVersion: number;
  headline: string;
  yearsOfExperience: number | null;
  evidence: Array<{
    key: string;
    type: EvidenceType;
    summary: string;
    source: string;
  }>;
  skills: Array<{
    name: string;
    level: SkillLevel;
    evidenceKeys: string[];
  }>;
}

export interface SearchIntent {
  id: string;
  version: number;
  targetRoles: string[];
  cities: string[];
  remoteAccepted: boolean | null;
  minimumSalaryK: number | null;
  seniority: Seniority | null;
  employmentTypes: string[];
  excludeKeywords: string[];
  hardConstraints: string[];
  softPreferences: string[];
  createdAt: string;
}

export interface ProposedProfileEvidence {
  key: string;
  type: EvidenceType;
  summary: string;
  source: string;
  evidenceSpan: string;
}

export interface ProposedProfileSkill {
  name: string;
  level: SkillLevel;
  evidenceKeys: string[];
}

export interface ProfileExtractionProposal {
  runId: string;
  extractorVersion: string;
  model: string;
  promptVersion: string;
  headline: string;
  yearsOfExperience: number | null;
  evidence: ProposedProfileEvidence[];
  skills: ProposedProfileSkill[];
  warnings: string[];
}

export interface SaveSearchIntentPayload {
  expectedVersion: number;
  targetRoles: string[];
  cities: string[];
  remoteAccepted: boolean | null;
  minimumSalaryK: number | null;
  seniority: Seniority | null;
  employmentTypes: string[];
  excludeKeywords: string[];
  hardConstraints: string[];
  softPreferences: string[];
}

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

export type ProfileEvalMode = "fixture" | "live";
export type ProfileEvalReviewDecision = "accepted" | "rejected";

export interface ProfileEvalRunSummary {
  id: string;
  datasetVersion: string;
  mode: ProfileEvalMode;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  gateVersion: string;
  baselineRunId: string | null;
  totalCases: number;
  passedCases: number;
  casePassRate: number;
  workflowSuccessRate: number;
  skillRecall: number;
  yearsAccuracy: number | null;
  forbiddenFactRate: number;
  gatePassed: boolean;
  releaseEligible: boolean;
  createdAt: string;
}

export interface ProfileEvalReview {
  id: string;
  evalRunId: string;
  decision: ProfileEvalReviewDecision;
  reviewer: string;
  notes: string;
  reviewedAt: string;
}

export interface ProfileEvalCaseResult {
  caseId: string;
  traceRunId: string | null;
  workflowSucceeded: boolean;
  passed: boolean;
  failureCodes: string[];
  failureReasons: string[];
  expectedSkills: string[];
  actualSkills: string[];
  missingSkills: string[];
  expectedYears: number | null;
  actualYears: number | null;
  forbiddenTerms: string[];
  observedForbiddenTerms: string[];
  diagnostics: Record<string, unknown>;
}

export interface ProfileEvalComparison {
  baselineRunId: string;
  casePassRateDelta: number;
  workflowSuccessRateDelta: number;
  skillRecallDelta: number;
  yearsAccuracyDelta: number | null;
  forbiddenFactRateDelta: number;
}

export interface ProfileEvalRunDetail {
  summary: ProfileEvalRunSummary;
  cases: ProfileEvalCaseResult[];
  comparison: ProfileEvalComparison | null;
  review: ProfileEvalReview | null;
}

export interface ProfileEvalRunPage {
  total: number;
  limit: number;
  offset: number;
  items: ProfileEvalRunSummary[];
}

export interface AcceptedProfileEvalBaseline {
  review: ProfileEvalReview;
  run: ProfileEvalRunSummary;
}

export interface ProfileEvalReviewPayload {
  decision: ProfileEvalReviewDecision;
  reviewer: string;
  notes: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export type SearchParamValue = string | string[] | undefined;
export type SearchParams = Record<string, SearchParamValue>;
