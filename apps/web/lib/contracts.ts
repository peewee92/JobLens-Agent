export type RemoteStatus = "confirmed" | "rejected" | "unknown";
export type RemoteConfidence = "high" | "medium" | "low";
export type JobSort = "latest" | "salaryDesc" | "salaryAsc";
export type ImportOutcome = "created" | "updated" | "skipped" | "error";
export type RequirementType =
  | "skill"
  | "experience"
  | "education"
  | "responsibility"
  | "domain"
  | "constraint";
export type RequirementImportance = "must_have" | "preferred" | "bonus";
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
  descriptionQuality: string | null;
  requirementReviewEligible: boolean | null;
  requirementReviewIneligibilityReasons: string[];
}

export interface JobPage {
  total: number;
  limit: number;
  offset: number;
  items: JobListItem[];
}

export interface JobRequirement {
  id: string;
  jobId: string;
  extractionId: string;
  requirementIndex: number;
  type: RequirementType;
  originalText: string;
  normalizedCapability: string | null;
  importance: RequirementImportance;
  evidenceSpan: string;
  confidence: number;
  extractorVersion: string;
}

export interface JobRequirementReleaseBlocker {
  code: string;
  message: string;
}

export interface JobRequirementReleaseReadiness {
  jobId: string;
  releaseEligible: boolean;
  currentDescriptionSha256: string;
  extractionId: string | null;
  extractionInputHash: string | null;
  provider: string | null;
  model: string | null;
  extractorVersion: string | null;
  promptVersion: string | null;
  traceRunId: string | null;
  requirementCount: number;
  acceptedBaselineBatchId: string | null;
  acceptedBaselineDecisionId: string | null;
  acceptedBaselineEvidenceFingerprint: string | null;
  blockers: JobRequirementReleaseBlocker[];
}

export interface JobRequirementExtraction {
  extractionId: string;
  jobId: string;
  inputHash: string;
  extractorVersion: string;
  provider: string;
  model: string;
  promptVersion: string;
  traceRunId: string;
  requirementCount: number;
  createdAt: string;
  requirements: JobRequirement[];
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

export type RequirementEvalMode = "fixture" | "live";
export type RequirementEvalReviewDecision = "accepted" | "rejected";

export interface RequirementEvalRunSummary {
  id: string;
  datasetVersion: string;
  mode: RequirementEvalMode;
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
  capabilityRecall: number;
  importanceAccuracy: number;
  forbiddenCapabilityRate: number;
  gatePassed: boolean;
  releaseEligible: boolean;
  createdAt: string;
}

export interface RequirementEvalReview {
  id: string;
  evalRunId: string;
  decision: RequirementEvalReviewDecision;
  reviewer: string;
  notes: string;
  reviewedAt: string;
}

export interface RequirementEvalCaseResult {
  caseId: string;
  traceRunId: string | null;
  workflowSucceeded: boolean;
  passed: boolean;
  missingRequirements: string[];
  wrongImportance: string[];
  observedForbiddenCapabilities: string[];
  actualRequirements: string[];
  error: string | null;
}

export interface RequirementEvalComparison {
  baselineRunId: string;
  casePassRateDelta: number;
  workflowSuccessRateDelta: number;
  capabilityRecallDelta: number;
  importanceAccuracyDelta: number;
  forbiddenCapabilityRateDelta: number;
}

export interface RequirementEvalRunDetail {
  summary: RequirementEvalRunSummary;
  cases: RequirementEvalCaseResult[];
  comparison: RequirementEvalComparison | null;
  review: RequirementEvalReview | null;
}

export interface RequirementEvalRunPage {
  total: number;
  limit: number;
  offset: number;
  items: RequirementEvalRunSummary[];
}

export interface AcceptedRequirementEvalBaseline {
  review: RequirementEvalReview;
  run: RequirementEvalRunSummary;
}

export interface RequirementEvalReviewPayload {
  decision: RequirementEvalReviewDecision;
  reviewer: string;
  notes: string;
}

export type RequirementReviewDecision = "accepted" | "rejected";
export type RequirementReviewIssueCode =
  | "missing_requirement"
  | "unsupported_requirement"
  | "wrong_importance"
  | "wrong_type"
  | "wrong_normalization"
  | "evidence_mismatch"
  | "duplicate_requirement"
  | "other";

export interface RequirementReviewCandidate {
  extractionId: string;
  jobId: string;
  title: string;
  company: string;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  traceRunId: string;
  requirementCount: number;
  createdAt: string;
}

export interface RequirementReviewCandidatePage {
  total: number;
  limit: number;
  offset: number;
  items: RequirementReviewCandidate[];
}

export type RequirementReviewBatchFinalDecisionValue =
  | "accept_for_match"
  | "reject_for_match";

export interface RequirementCaseReview {
  id: string;
  batchCaseId: string;
  decision: RequirementReviewDecision;
  issueCodes: RequirementReviewIssueCode[];
  notes: string;
  reviewedAt: string;
}

export interface RequirementReviewBatchSummary {
  id: string;
  title: string;
  reviewer: string;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  sampleSize: number;
  reviewedCount: number;
  acceptedCount: number;
  rejectedCount: number;
  staleCaseCount: number;
  completed: boolean;
  formalEvidenceEligible: boolean;
  finalDecision: RequirementReviewBatchFinalDecisionValue | null;
  matchReleaseEligible: boolean;
  createdAt: string;
}

export interface RequirementReviewBatchCase {
  id: string;
  caseIndex: number;
  jobId: string;
  extractionId: string;
  title: string;
  company: string;
  description: string | null;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  traceRunId: string;
  createdAt: string;
  isCurrent: boolean;
  requirements: JobRequirement[];
  review: RequirementCaseReview | null;
}

export interface RequirementReviewBatchFinalDecision {
  id: string;
  batchId: string;
  decision: RequirementReviewBatchFinalDecisionValue;
  reviewer: string;
  notes: string;
  sampleSize: number;
  reviewedCount: number;
  acceptedCount: number;
  rejectedCount: number;
  staleCaseCount: number;
  issueCodeCounts: Record<string, number>;
  evidenceFingerprint: string;
  decidedAt: string;
}

export interface RequirementReviewBatchDetail {
  summary: RequirementReviewBatchSummary;
  issueCodeCounts: Record<string, number>;
  cases: RequirementReviewBatchCase[];
  finalDecision: RequirementReviewBatchFinalDecision | null;
}

export interface AcceptedRequirementReviewBaseline {
  decision: RequirementReviewBatchFinalDecision;
  batch: RequirementReviewBatchSummary;
  issueCodeCounts: Record<string, number>;
}

export interface RequirementReviewBatchPage {
  total: number;
  limit: number;
  offset: number;
  items: RequirementReviewBatchSummary[];
}

export type RequirementAcceptanceDatasetState =
  | "missing"
  | "selection_required"
  | "invalid"
  | "ready";
export type RequirementAcceptanceReadinessBlockerScope =
  | "workflow"
  | "provider_execution";
export type RequirementAcceptanceReadinessNextAction =
  | "fix_blockers"
  | "run_canary"
  | "review_canary"
  | "resume_run"
  | "open_manual_review"
  | "stopped";

export interface RequirementAcceptanceReadinessBlocker {
  scope: RequirementAcceptanceReadinessBlockerScope;
  code: string;
  message: string;
}

export interface RequirementAcceptanceReadiness {
  datasetState: RequirementAcceptanceDatasetState;
  datasetCandidateCount: number;
  datasetFileName: string | null;
  datasetFingerprint: string | null;
  sourceVersion: string | null;
  selectedCount: number;
  provider: string;
  model: string;
  apiKeyConfigured: boolean;
  reviewer: string;
  title: string;
  requestedMaxNewExtractions: number | null;
  databaseReachable: boolean;
  databaseRevision: string | null;
  migrationHead: string;
  workflowReady: boolean;
  providerExecutionAllowed: boolean;
  readyForNextAction: boolean;
  nextAction: RequirementAcceptanceReadinessNextAction;
  runId: string | null;
  runStatus: string | null;
  attemptedCalls: number;
  canaryDecision: RequirementAcceptanceCanaryDecision | null;
  batchId: string | null;
  workbenchUrl: string | null;
  manualReviewUrl: string | null;
  blockers: RequirementAcceptanceReadinessBlocker[];
  dbWrites: number;
  providerCalls: number;
}

export type RequirementAcceptanceRunCaseStatus =
  | "pending"
  | "reused"
  | "extracted"
  | "failed"
  | "deferred";
export type RequirementAcceptanceRunStatus =
  | "pending"
  | "partial"
  | "awaiting_canary_review"
  | "stopped"
  | "ready";
export type RequirementAcceptanceCanaryDecision = "continue" | "stop";

export interface RequirementAcceptanceCanaryReview {
  id: string;
  runId: string;
  reviewer: string;
  decision: RequirementAcceptanceCanaryDecision;
  notes: string;
  reviewedCaseIds: string[];
  reviewedExtractionIds: string[];
  reviewedTraceRunIds: string[];
  reviewedAt: string;
}

export interface RequirementAcceptanceRunCase {
  id: string;
  caseIndex: number;
  sourceUrl: string;
  title: string;
  company: string;
  descriptionHash: string;
  descriptionSnapshot: string | null;
  currentDescriptionHash: string;
  descriptionIsCurrent: boolean;
  isCanaryEvidence: boolean;
  jobId: string;
  status: RequirementAcceptanceRunCaseStatus;
  attemptCount: number;
  extractionId: string | null;
  traceRunId: string | null;
  traceCapability: string | null;
  traceModel: string | null;
  tracePromptVersion: string | null;
  traceLatencyMs: number | null;
  traceInputTokens: number | null;
  traceOutputTokens: number | null;
  traceError: string | null;
  traceCreatedAt: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RequirementAcceptanceRunSummary {
  id: string;
  title: string;
  reviewer: string;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  status: RequirementAcceptanceRunStatus;
  attemptedCalls: number;
  completedCaseCount: number;
  failedCount: number;
  deferredCount: number;
  canaryReviewRequired: boolean;
  canaryDecision: RequirementAcceptanceCanaryDecision | null;
  batchId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RequirementAcceptanceRunPage {
  total: number;
  limit: number;
  offset: number;
  items: RequirementAcceptanceRunSummary[];
}

export interface RequirementAcceptanceRunDetail {
  id: string;
  datasetFingerprint: string;
  sourceVersion: string;
  datasetGeneratedAt: string | null;
  title: string;
  reviewer: string;
  provider: string;
  model: string;
  extractorVersion: string;
  promptVersion: string;
  firstImportId: string;
  lastImportId: string;
  batchId: string | null;
  status: RequirementAcceptanceRunStatus;
  canaryReviewRequired: boolean;
  canaryContinueAllowed: boolean;
  canaryStopAllowed: boolean;
  canaryReviewBlockReason: string | null;
  canaryReview: RequirementAcceptanceCanaryReview | null;
  pendingCount: number;
  reusedCount: number;
  extractedCount: number;
  failedCount: number;
  deferredCount: number;
  attemptedCalls: number;
  completedCaseCount: number;
  createdAt: string;
  updatedAt: string;
  cases: RequirementAcceptanceRunCase[];
}

export interface RequirementAcceptanceCanaryReviewPayload {
  reviewer: string;
  decision: RequirementAcceptanceCanaryDecision;
  notes: string;
}

export interface CreateRequirementReviewBatchPayload {
  title: string;
  reviewer: string;
  extractionIds: string[];
}

export interface RequirementCaseReviewPayload {
  decision: RequirementReviewDecision;
  issueCodes: RequirementReviewIssueCode[];
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
