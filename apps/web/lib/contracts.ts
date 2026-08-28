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

export type CareerContextReleaseBlockerCode =
  | "profile_missing"
  | "profile_headline_missing"
  | "profile_years_invalid"
  | "profile_evidence_missing"
  | "profile_evidence_invalid"
  | "profile_evidence_keys_duplicated"
  | "profile_skills_missing"
  | "profile_skill_names_duplicated"
  | "profile_skill_evidence_missing"
  | "profile_skill_evidence_reference_invalid"
  | "search_intent_missing"
  | "search_intent_target_roles_missing"
  | "search_intent_target_roles_duplicated"
  | "search_intent_minimum_salary_invalid";

export interface CareerContextReleaseReadiness {
  releaseEligible: boolean;
  confirmationBoundary: "explicit_versioned_user_confirmation";
  profileId: string | null;
  profileVersion: number | null;
  profileCreatedAt: string | null;
  profileEvidenceCount: number;
  profileSkillCount: number;
  searchIntentId: string | null;
  searchIntentVersion: number | null;
  searchIntentCreatedAt: string | null;
  searchIntentTargetRoleCount: number;
  blockers: Array<{
    code: CareerContextReleaseBlockerCode;
    message: string;
  }>;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
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

export type RequirementFitStatus = "matched" | "conditional" | "missing";
export type EligibilityDecision = "eligible" | "conditional" | "blocked";

export interface RequirementEligibilityResult {
  requirementId: string;
  requirementIndex: number;
  type: RequirementType;
  importance: RequirementImportance;
  originalText: string;
  normalizedCapability: string | null;
  status: RequirementFitStatus;
  evidenceIds: string[];
  profileFactRefs: string[];
  reason: string;
}

export interface JobEligibilityResult {
  jobId: string;
  profileId: string;
  profileVersion: number;
  extractionId: string;
  eligibility: EligibilityDecision;
  requirements: RequirementEligibilityResult[];
  matchedCount: number;
  conditionalCount: number;
  missingCount: number;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export type SemanticMatchVerdict = "matched" | "partial" | "not_matched";
export type MatchRecommendation = "strong" | "good" | "stretch" | "low" | "blocked";

export interface MatchReportInsight {
  requirementId: string;
  requirementText: string;
  reason: string;
  evidenceIds: string[];
}

export interface MatchReportRequirementResult {
  requirementId: string;
  requirementIndex: number;
  type: RequirementType;
  importance: RequirementImportance;
  originalText: string;
  normalizedCapability: string | null;
  eligibilityStatus: RequirementFitStatus;
  semanticVerdict: SemanticMatchVerdict;
  evidenceIds: string[];
  profileFactRefs: string[];
  reason: string;
}

export interface MatchEvidenceLink {
  requirementId: string;
  evidenceIds: string[];
}

export interface RankedMatchReportItem {
  reportId: string;
  createdAt: string;
  jobId: string;
  profileId: string;
  profileVersion: number;
  extractionId: string;
  eligibility: EligibilityDecision;
  recommendation: MatchRecommendation;
  summary: string;
  matchedRequirementIds: string[];
  partialRequirementIds: string[];
  missingRequirementIds: string[];
  evidenceLinks: MatchEvidenceLink[];
}

export interface BatchMatchRanking {
  items: RankedMatchReportItem[];
  count: number;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export interface MatchReviewReadiness {
  requiredJobCount: number;
  availableJobCount: number;
  inputReadyJobCount: number;
  persistenceReady: boolean;
  readyForHumanReview: boolean;
  reviewableJobIds: string[];
  blockers: Array<{code: string; message: string}>;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export type BatchMatchExecutionStatus =
  | "succeeded"
  | "failed"
  | "input_blocked"
  | "persistence_blocked"
  | "deferred_limit";

export interface BatchMatchExecutionResponse {
  total: number;
  succeededCount: number;
  failedCount: number;
  deferredCount: number;
  inputBlockedCount: number;
  persistenceBlockedCount: number;
  items: Array<{
    jobId: string;
    status: BatchMatchExecutionStatus;
    blockerCodes: string[];
    errorCode: string | null;
  }>;
  resumeJobIds: string[];
  executionComplete: boolean;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
  sideEffectCountsComplete: boolean;
}

export interface MatchBlockerRequirement {
  requirementId: string;
  requirementType: RequirementType;
  originalText: string;
}

export interface MatchBlockerJob {
  jobId: string;
  missingRequirementCount: number;
  requirements: MatchBlockerRequirement[];
  unresolvedMissingRequirementIds: string[];
}

export interface MatchBlockerCategory {
  requirementType: RequirementType;
  missingRequirementCount: number;
  affectedJobCount: number;
  affectedJobIds: string[];
  examples: string[];
}

export interface MatchBlockerSummary {
  analyzedReportCount: number;
  blockedReportCount: number;
  missingRequirementCount: number;
  resolvedMissingRequirementCount: number;
  unresolvedMissingRequirementIds: string[];
  categories: MatchBlockerCategory[];
  jobBlockers: MatchBlockerJob[];
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export interface MatchImprovementRequirement {
  requirementId: string;
  originalText: string;
}

export interface MatchImprovement {
  jobId: string;
  currentReportId: string;
  previousReportId: string | null;
  previousRecommendation: MatchRecommendation | null;
  currentRecommendation: MatchRecommendation;
  previousMissingRequirementCount: number | null;
  currentMissingRequirementCount: number;
  resolvedRequirementIds: string[];
  newlyMissingRequirementIds: string[];
  resolvedRequirements: MatchImprovementRequirement[];
  newlyMissingRequirements: MatchImprovementRequirement[];
  comparable: boolean;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export type RecommendationCoverageStatus =
  | "current_report"
  | "match_ready"
  | "requirement_analysis_needed"
  | "profile_blocked"
  | "other_blocked";

export interface RecommendationCoverageCandidate {
  jobId: string;
  title: string;
  company: string;
  area: string | null;
  salaryMinK: number | null;
  salaryMaxK: number | null;
  status: RecommendationCoverageStatus;
  blockerCodes: string[];
  intentSignals: string[];
}

export interface RecommendationCoverage {
  totalJobCount: number;
  consideredJobCount: number;
  currentReportCount: number;
  matchReadyWithoutReportCount: number;
  requirementAnalysisNeededCount: number;
  profileBlockedCount: number;
  otherBlockedCount: number;
  nextAnalysisCandidates: RecommendationCoverageCandidate[];
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export type RequirementBatchExecutionStatus =
  | "succeeded"
  | "failed"
  | "provider_unavailable"
  | "deferred_provider_unavailable"
  | "deferred_limit"
  | "not_selected";

export interface RequirementBatchExecutionResponse {
  total: number;
  succeededCount: number;
  failedCount: number;
  deferredCount: number;
  providerUnavailableCount: number;
  notSelectedCount: number;
  items: Array<{
    jobId: string;
    status: RequirementBatchExecutionStatus;
    errorCode: string | null;
    providerCalls: number;
    traceRunsCreated: number;
  }>;
  resumeJobIds: string[];
  executionComplete: boolean;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
  sideEffectCountsComplete: boolean;
}

export type FeedbackDecision = "interested" | "maybe" | "rejected";
export type FeedbackReason =
  | "role_fit"
  | "skill_gap"
  | "compensation"
  | "location"
  | "seniority"
  | "company"
  | "work_mode"
  | "other";

export interface UserFeedbackRecord {
  feedbackId: string;
  matchReportId: string;
  jobId: string;
  decision: FeedbackDecision;
  reasons: FeedbackReason[];
  note: string | null;
  createdAt: string;
}

export interface UserFeedbackHistory {
  feedback: UserFeedbackRecord[];
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export interface JobMatchReport {
  jobId: string;
  profileId: string;
  profileVersion: number;
  extractionId: string;
  eligibility: EligibilityDecision;
  recommendation: MatchRecommendation;
  summary: string;
  strengths: MatchReportInsight[];
  risks: MatchReportInsight[];
  requirementResults: MatchReportRequirementResult[];
  matchedRequirementIds: string[];
  partialRequirementIds: string[];
  missingRequirementIds: string[];
  evidenceLinks: MatchEvidenceLink[];
  matcherVersion: string;
  promptVersion: string;
  model: string | null;
  traceRunId: string | null;
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
}

export interface ResumeDeltaHighlight {
  requirementId: string;
  capability: string;
  profileSkillIds: string[];
  evidenceIds: string[];
}

export interface ResumeDeltaGap {
  requirementId: string;
  capability: string;
  status: "unevidenced" | "missing";
  profileSkillIds: string[];
}

export interface JobPreparationBundle {
  jobId: string;
  factsUsable: boolean;
  profileId: string | null;
  profileVersion: number | null;
  extractionId: string | null;
  resumeDelta: {
    highlights: ResumeDeltaHighlight[];
    evidenceGaps: ResumeDeltaGap[];
  } | null;
  experiencePriority: {
    items: Array<{
      evidenceId: string;
      evidenceType: string;
      supportingRequirementIds: string[];
      matchedCapabilities: string[];
      mustHaveCount: number;
      requirementCount: number;
    }>;
  } | null;
  storyFacts: {
    items: Array<{
      evidenceId: string;
      evidenceType: string;
      evidenceSummary: string;
      supportingRequirementIds: string[];
      supportingRequirementTexts: string[];
      matchedCapabilities: string[];
      mustHaveCount: number;
      requirementCount: number;
    }>;
  } | null;
  interviewFacts: {
    items: Array<{
      requirementId: string;
      requirementType: string;
      requirementText: string;
      importance: string;
      normalizedCapability: string | null;
      preparationPriority: string;
      evidenceStatus: string;
      profileSkillIds: string[];
      evidenceIds: string[];
      evidenceSummaries: string[];
    }>;
  } | null;
  studyChecklist: {
    items: Array<{
      requirementId: string;
      requirementText: string;
      capability: string;
      importance: string;
      evidenceStatus: string;
      need: string;
      profileSkillIds: string[];
      completionCriteria: string[];
    }>;
  } | null;
  blockers: string[];
  dbWrites: number;
  providerCalls: number;
  traceRunsCreated: number;
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

export interface MvpQualityStatus {
  gatePassed: boolean;
  replayPassed: boolean;
  replayPassedCases: number;
  replayTotalCases: number;
  matchDemoPassed: boolean;
  matchDemoPersistedReports: number;
  matchDemoTopJobs: number;
  matchDemoEvidenceComplete: boolean;
  providerSmokeState: string;
  providerSmokeReady: boolean | null;
  providerSmokeBlocking: boolean;
  providerSmokeBlocker: string | null;
  providerSmokeCheckedAt: string | null;
  providerSmokePlainStatusCode: number | null;
  providerSmokeStructuredStatusCode: number | null;
  providerCalls: number;
}

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
