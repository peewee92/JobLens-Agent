import Link from "next/link";
import {notFound} from "next/navigation";

import {ApplicationChecklistSummary} from "@/components/application-checklist-summary";
import {ImportBatchMatch} from "@/components/import-batch-match";
import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {ImportOutcomePill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchImportDetail,
  fetchJobDetail,
  fetchJobPreparation,
  fetchJobRequirementReleaseReadiness,
  fetchLatestUserFeedback,
  fetchMatchBlockerSummary,
  fetchMatchImprovement,
  fetchMatchRanking,
  fetchMatchReviewReadiness,
} from "@/lib/backend";
import {buildApplicationChecklistItems} from "@/lib/application-checklist";
import {
  consideredAffectedJobCount,
  listEvidencePriorityImpactTargets,
  selectEvidenceFocusJobId,
  selectNextEvidencePriority,
} from "@/lib/evidence-priority";
import {formatDateTime} from "@/lib/format";
import {
  matchRecommendationClasses,
  matchRecommendationDescriptions,
  matchRecommendationLabels,
} from "@/lib/match-report";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function ImportDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{id: string}>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const {id} = await params;
  const query = await searchParams;
  const showImprovement = query.showImprovement === "1";
  const requestedAfterPrepareEvidenceJobId = typeof query.afterPrepareEvidence === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(query.afterPrepareEvidence)
    ? query.afterPrepareEvidence
    : null;
  const requestedFocusRequirementId = typeof query.focusRequirementId === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(query.focusRequirementId)
    ? query.focusRequirementId
    : null;
  const requestedAfterFeedbackJobId = typeof query.afterFeedback === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(query.afterFeedback)
    ? query.afterFeedback
    : null;
  const requestedAfterPreparationJobId = typeof query.afterPreparation === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(query.afterPreparation)
    ? query.afterPreparation
    : null;
  const requestedPrepareEvidenceJobIds = typeof query.prepareEvidenceJobs === "string"
    ? Array.from(new Set(
        query.prepareEvidenceJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20)
    : [];
  const requestedPrepareAlternativeEvidenceJobIds = typeof query.prepareAlternativeEvidenceJobs === "string"
    ? Array.from(new Set(
        query.prepareAlternativeEvidenceJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20)
    : [];
  const requestedAfterMatchJobIds = typeof query.afterMatchJobs === "string"
    ? Array.from(new Set(
        query.afterMatchJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20)
    : [];
  const afterMatchPrepareQuery = requestedAfterMatchJobIds.length > 0
    ? `&afterMatchJobs=${encodeURIComponent(requestedAfterMatchJobIds.join(","))}`
    : "";
  const focusImpactJobIds = typeof query.focusImpactJobs === "string"
    ? query.focusImpactJobs.split(",").map((jobId) => jobId.trim().slice(0, 120)).filter(Boolean).slice(0, 3)
    : [];
  const focusImpactRequirementIds = typeof query.focusImpactRequirementIds === "string"
    ? Array.from(new Set(
        query.focusImpactRequirementIds
          .split(",")
          .map((requirementId) => requirementId.trim())
          .filter((requirementId) => /^[A-Za-z0-9_-]{1,120}$/.test(requirementId)),
      )).slice(0, 20)
    : [];
  const previousEvidenceAttributionQuery = `${focusImpactJobIds.length > 0 ? `&focusImpactJobs=${encodeURIComponent(focusImpactJobIds.join(","))}` : ""}${focusImpactRequirementIds.length > 0 ? `&focusImpactRequirementIds=${encodeURIComponent(focusImpactRequirementIds.join(","))}` : ""}`;
  let detail;
  try {
    detail = await fetchImportDetail(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) {
      notFound();
    }
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取这批岗位的处理结果，请稍后重试。")
        : "暂时无法读取这批岗位的处理结果，请稍后重试。";
    return <ServiceError message={message} />;
  }

  const importedJobIds = detail.items.flatMap((item) => (item.jobId ? [item.jobId] : []));
  const preparationProgressResult = requestedAfterPreparationJobId && importedJobIds.includes(requestedAfterPreparationJobId)
    ? await fetchJobPreparation(requestedAfterPreparationJobId)
        .then((value) => ({status: "fulfilled" as const, value}))
        .catch((reason) => ({status: "rejected" as const, reason}))
    : null;
  const preparationProgressItems = preparationProgressResult?.status === "fulfilled" && preparationProgressResult.value.factsUsable
    ? buildApplicationChecklistItems(preparationProgressResult.value)
    : null;
  const [rankingResult, matchReviewReadinessResult, jobDetailResults, readinessResults] = await Promise.all([
    importedJobIds.length > 0
      ? fetchMatchRanking(importedJobIds, {includeBlocked: true})
          .then((value) => ({status: "fulfilled" as const, value}))
          .catch((reason) => ({status: "rejected" as const, reason}))
      : Promise.resolve({
          status: "fulfilled" as const,
          value: {items: [], count: 0, dbWrites: 0, providerCalls: 0, traceRunsCreated: 0},
        }),
    fetchMatchReviewReadiness()
      .then((value) => ({status: "fulfilled" as const, value}))
      .catch((reason) => ({status: "rejected" as const, reason})),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobDetail(jobId))),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobRequirementReleaseReadiness(jobId))),
  ]);
  const rankingAvailable = rankingResult.status === "fulfilled";
  const rankedJobIds = new Set(
    rankingAvailable ? rankingResult.value.items.map((item) => item.jobId) : [],
  );
  const matchInputReadinessAvailable = matchReviewReadinessResult.status === "fulfilled";
  const matchInputReadyJobIds = new Set(
    matchInputReadinessAvailable ? matchReviewReadinessResult.value.reviewableJobIds : [],
  );
  const jobDetailById = new Map(
    jobDetailResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.id, result.value] as const] : [],
    ),
  );
  const readinessByJobId = new Map(
    readinessResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.jobId, result.value] as const] : [],
    ),
  );
  const matchedReports = rankingAvailable
    ? rankingResult.value.items.filter((item) => importedJobIds.includes(item.jobId))
    : [];
  const matchedCount = matchedReports.length;
  const latestFeedbackResult = matchedReports.length > 0
    ? await fetchLatestUserFeedback(matchedReports.map((report) => report.reportId))
        .then((value) => ({status: "fulfilled" as const, value}))
        .catch((reason) => ({status: "rejected" as const, reason}))
    : {status: "fulfilled" as const, value: {feedback: [], count: 0, dbWrites: 0, providerCalls: 0, traceRunsCreated: 0}};
  const feedbackAvailable = latestFeedbackResult.status === "fulfilled";
  const latestFeedbackByReportId = new Map(
    feedbackAvailable
      ? latestFeedbackResult.value.feedback.map((item) => [item.matchReportId, item] as const)
      : [],
  );
  const feedbackCoveredCount = feedbackAvailable ? latestFeedbackByReportId.size : 0;
  const feedbackDecisionCounts = feedbackAvailable
    ? matchedReports.reduce(
        (counts, report) => {
          const decision = latestFeedbackByReportId.get(report.reportId)?.decision;
          if (decision) counts[decision] += 1;
          else counts.pending += 1;
          return counts;
        },
        {interested: 0, maybe: 0, rejected: 0, pending: 0},
      )
    : null;
  const finalInterestedReports = feedbackAvailable
    ? matchedReports.filter((report) => latestFeedbackByReportId.get(report.reportId)?.decision === "interested")
    : [];
  const finalMaybeReports = feedbackAvailable
    ? matchedReports.filter((report) => latestFeedbackByReportId.get(report.reportId)?.decision === "maybe")
    : [];
  const finalRejectedReports = feedbackAvailable
    ? matchedReports.filter((report) => latestFeedbackByReportId.get(report.reportId)?.decision === "rejected")
    : [];
  const afterPreparationInterestedReports = requestedAfterPreparationJobId
    ? finalInterestedReports.filter((report) => report.jobId !== requestedAfterPreparationJobId)
    : [];
  const afterPreparationInterestedPreparationResults = requestedAfterPreparationJobId
    ? await Promise.allSettled(
        afterPreparationInterestedReports.map(async (report) => ({
          report,
          preparation: await fetchJobPreparation(report.jobId),
        })),
      )
    : [];
  const afterPreparationInterestedCandidates = afterPreparationInterestedPreparationResults.map((result, index) => {
    const report = afterPreparationInterestedReports[index];
    if (!report) return null;
    if (result.status !== "fulfilled" || !result.value.preparation.factsUsable) {
      return {report, items: null};
    }
    return {report, items: buildApplicationChecklistItems(result.value.preparation)};
  }).filter((candidate): candidate is {report: (typeof finalInterestedReports)[number]; items: ReturnType<typeof buildApplicationChecklistItems> | null} => candidate !== null);
  const pendingFeedbackReports = feedbackAvailable
    ? matchedReports.filter((report) => !latestFeedbackByReportId.has(report.reportId))
    : [];
  const improvementResults = showImprovement && matchedReports.length > 0
    ? await Promise.allSettled(
        matchedReports.map(async (report) => ({
          report,
          improvement: await fetchMatchImprovement(report.jobId, report.reportId),
        })),
      )
    : [];
  const improvementByJobId = new Map(
    improvementResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.report.jobId, result.value.improvement] as const] : [],
    ),
  );
  const improvedBatchJobs = improvementResults.flatMap((result) => {
    if (result.status !== "fulfilled") return [];
    const {report, improvement} = result.value;
    if (!improvement.comparable || improvement.previousProfileVersion === improvement.currentProfileVersion) return [];
    const improved = improvement.resolvedRequirementIds.length > 0
      || improvement.previousRecommendation !== improvement.currentRecommendation;
    return improved ? [{report, improvement}] : [];
  });
  const resolvedBatchRequirementIds = new Set(
    improvedBatchJobs.flatMap(({improvement}) => improvement.resolvedRequirementIds),
  );
  const prepareEvidenceSourceResult = requestedAfterPrepareEvidenceJobId && requestedFocusRequirementId
    ? improvedBatchJobs.find(({report, improvement}) =>
        report.jobId === requestedAfterPrepareEvidenceJobId
        && improvement.resolvedRequirementIds.includes(requestedFocusRequirementId),
      ) ?? null
    : null;
  const otherPrepareEvidenceImprovedJobs = prepareEvidenceSourceResult
    ? improvedBatchJobs.filter(({report}) => report.jobId !== prepareEvidenceSourceResult.report.jobId)
    : [];
  const feedbackByJobId = new Map(
    matchedReports.flatMap((report) => {
      const feedback = latestFeedbackByReportId.get(report.reportId);
      return feedback ? [[report.jobId, feedback] as const] : [];
    }),
  );
  const blockerSummaryResult = matchedReports.length > 0
    ? await fetchMatchBlockerSummary(importedJobIds)
        .then((value) => ({status: "fulfilled" as const, value}))
        .catch((reason) => ({status: "rejected" as const, reason}))
    : {status: "fulfilled" as const, value: null};
  const blockerByJobId = new Map(
    blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
      ? blockerSummaryResult.value.jobBlockers.map((item) => [item.jobId, item] as const)
      : [],
  );
  const feedbackQueueAvailable = feedbackAvailable
    && blockerSummaryResult.status === "fulfilled"
    && Boolean(blockerSummaryResult.value);
  const afterMatchTransitionResults = requestedAfterMatchJobIds
    .filter((jobId) => importedJobIds.includes(jobId))
    .map((jobId) => {
      const report = matchedReports.find((item) => item.jobId === jobId) ?? null;
      if (!report || !feedbackQueueAvailable) {
        return {jobId, status: "unverifiable" as const};
      }
      const feedback = latestFeedbackByReportId.get(report.reportId);
      const blocker = blockerByJobId.get(jobId) ?? null;
      if (feedback?.decision === "rejected" || (feedback && !blocker)) {
        return {jobId, status: "completed" as const};
      }
      if (blocker) {
        return {jobId, status: "evidence" as const, blocker};
      }
      return {jobId, status: "apply" as const};
    });
  const afterMatchApplyResults = afterMatchTransitionResults.filter((item) => item.status === "apply");
  const afterMatchEvidenceResults = afterMatchTransitionResults.filter((item) => item.status === "evidence");
  const afterMatchCompletedResults = afterMatchTransitionResults.filter((item) => item.status === "completed");
  const afterMatchUnverifiableResults = afterMatchTransitionResults.filter((item) => item.status === "unverifiable");
  const afterMatchApplyJobIds = new Set(afterMatchApplyResults.map((item) => item.jobId));
  const nextAfterMatchApplyReport = matchedReports.find((report) => afterMatchApplyJobIds.has(report.jobId)) ?? null;
  const pendingClearedReports = feedbackQueueAvailable
    ? pendingFeedbackReports.filter((report) => !blockerByJobId.has(report.jobId))
    : [];
  const pendingBlockedReports = feedbackQueueAvailable
    ? pendingFeedbackReports.filter((report) => blockerByJobId.has(report.jobId))
    : [];
  const consideredBlockedReports = feedbackQueueAvailable
    ? matchedReports.filter((report) => {
        const decision = latestFeedbackByReportId.get(report.reportId)?.decision;
        return decision !== "rejected" && blockerByJobId.has(report.jobId);
      })
    : [];
  const completedDecisionReports = feedbackQueueAvailable
    ? matchedReports.filter((report) => {
        const feedback = latestFeedbackByReportId.get(report.reportId);
        return Boolean(feedback) && (feedback?.decision === "rejected" || !blockerByJobId.has(report.jobId));
      })
    : [];
  const batchProcessingTotal = importedJobIds.length;
  const batchProcessedCount = feedbackQueueAvailable ? completedDecisionReports.length : null;
  const batchProcessingRemaining = batchProcessedCount === null
    ? null
    : Math.max(batchProcessingTotal - batchProcessedCount, 0);
  const batchProcessingComplete = feedbackQueueAvailable
    && matchedCount === batchProcessingTotal
    && completedDecisionReports.length === batchProcessingTotal;
  const unmatchedProcessingCount = feedbackQueueAvailable
    ? Math.max(batchProcessingTotal - matchedCount, 0)
    : null;
  const pendingApplyDecisionCount = feedbackQueueAvailable ? pendingClearedReports.length : null;
  const pendingEvidenceCount = feedbackQueueAvailable ? consideredBlockedReports.length : null;
  const nextApplyDecisionReport = pendingClearedReports[0] ?? null;
  const otherPrepareEvidenceResolvedJobIds = new Set(
    otherPrepareEvidenceImprovedJobs
      .filter(({improvement}) => improvement.resolvedRequirementIds.length > 0)
      .map(({report}) => report.jobId),
  );
  const prepareEvidenceUnlockedReports = prepareEvidenceSourceResult && feedbackQueueAvailable
    ? matchedReports.filter((report) =>
        otherPrepareEvidenceResolvedJobIds.has(report.jobId)
        && !blockerByJobId.has(report.jobId),
      )
    : [];
  const nextPrepareEvidenceUnlockedReport = prepareEvidenceUnlockedReports.find((report) => !latestFeedbackByReportId.has(report.reportId)) ?? null;
  const prepareEvidenceUnlockedJobQuery = prepareEvidenceUnlockedReports.length > 0
    ? `&prepareEvidenceJobs=${encodeURIComponent(prepareEvidenceUnlockedReports.map((report) => report.jobId).join(","))}`
    : "";
  const verifiedPrepareEvidenceDecisionReports = feedbackQueueAvailable
    ? matchedReports.filter((report) =>
        requestedPrepareEvidenceJobIds.includes(report.jobId)
        && !blockerByJobId.has(report.jobId)
        && otherPrepareEvidenceResolvedJobIds.has(report.jobId),
      )
    : [];
  const prepareEvidenceCompletedDecisionReports = verifiedPrepareEvidenceDecisionReports.filter((report) => latestFeedbackByReportId.has(report.reportId));
  const prepareEvidencePendingDecisionReports = verifiedPrepareEvidenceDecisionReports.filter((report) => !latestFeedbackByReportId.has(report.reportId));
  const prepareEvidenceDecisionSetFullyVerifiable = requestedPrepareEvidenceJobIds.length > 0
    && verifiedPrepareEvidenceDecisionReports.length === requestedPrepareEvidenceJobIds.length;
  const prepareEvidenceDecisionLoopComplete = prepareEvidenceDecisionSetFullyVerifiable
    && prepareEvidencePendingDecisionReports.length === 0;
  const prepareEvidenceInterestedCount = prepareEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "interested",
  ).length;
  const prepareEvidenceMaybeCount = prepareEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "maybe",
  ).length;
  const prepareEvidenceRejectedCount = prepareEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "rejected",
  ).length;
  const nextPrepareEvidencePendingDecisionReport = prepareEvidencePendingDecisionReports[0] ?? null;
  const prepareEvidenceDecisionQuery = verifiedPrepareEvidenceDecisionReports.length > 0
    ? `&prepareEvidenceJobs=${encodeURIComponent(verifiedPrepareEvidenceDecisionReports.map((report) => report.jobId).join(","))}`
    : "";
  const afterFeedbackReport = requestedAfterFeedbackJobId
    ? matchedReports.find((report) => report.jobId === requestedAfterFeedbackJobId) ?? null
    : null;
  const afterFeedbackDecision = feedbackAvailable && afterFeedbackReport
    ? latestFeedbackByReportId.get(afterFeedbackReport.reportId)?.decision ?? null
    : null;
  const afterFeedbackConfirmed = Boolean(afterFeedbackReport && afterFeedbackDecision);
  const rawBatchEvidenceAction = feedbackAvailable && blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? selectNextEvidencePriority(blockerSummaryResult.value.priorityActions, feedbackByJobId, null)
    : null;
  const batchEvidenceAction = rawBatchEvidenceAction
    && !rawBatchEvidenceAction.requirementIds.some((requirementId) => resolvedBatchRequirementIds.has(requirementId))
    ? rawBatchEvidenceAction
    : null;
  const batchEvidenceActionStaleAfterImprovement = Boolean(
    rawBatchEvidenceAction
    && rawBatchEvidenceAction.requirementIds.some((requirementId) => resolvedBatchRequirementIds.has(requirementId)),
  );
  const batchEvidenceFocusJobId = selectEvidenceFocusJobId(batchEvidenceAction, feedbackByJobId);
  const batchEvidenceRequirement = batchEvidenceAction && batchEvidenceFocusJobId && blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? blockerSummaryResult.value.jobBlockers
        .find((item) => item.jobId === batchEvidenceFocusJobId)
        ?.requirements.find((requirement) => batchEvidenceAction.requirementIds.includes(requirement.requirementId)) ?? null
    : null;
  const batchEvidenceImpactTargets = blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value
    ? listEvidencePriorityImpactTargets(batchEvidenceAction, blockerSummaryResult.value.jobBlockers, feedbackByJobId)
    : [];
  const consideredBlockedJobIds = new Set(consideredBlockedReports.map((report) => report.jobId));
  const batchEvidenceQueueTargets = batchEvidenceImpactTargets.filter((target) => consideredBlockedJobIds.has(target.jobId));
  const batchEvidenceQueueTargetJobIds = new Set(batchEvidenceQueueTargets.map((target) => target.jobId));
  const currentEvidenceQueuePriorityTargets = batchEvidenceQueueTargets.slice(0, 3);
  const previousEvidenceQueueResults = showImprovement && focusImpactJobIds.length > 0
    ? focusImpactJobIds.map((jobId) => {
        const report = matchedReports.find((item) => item.jobId === jobId) ?? null;
        const improvement = improvementByJobId.get(jobId) ?? null;
        if (!report || !improvement || !improvement.comparable || improvement.previousProfileVersion === improvement.currentProfileVersion) {
          return {jobId, report, status: "unverifiable" as const};
        }
        const resolvedPlannedRequirement = focusImpactRequirementIds.length > 0
          && improvement.resolvedRequirementIds.some((requirementId) => focusImpactRequirementIds.includes(requirementId));
        if (!resolvedPlannedRequirement) {
          const improvedWithoutPlannedRequirement = improvement.resolvedRequirementIds.length > 0
            || improvement.previousRecommendation !== improvement.currentRecommendation;
          const alternativeEvidenceProvenance = improvedWithoutPlannedRequirement
            ? improvement.newlySupportingEvidence.flatMap((evidence) => {
                const supportingRequirements = evidence.supportingRequirements.filter((requirement) =>
                  !focusImpactRequirementIds.includes(requirement.requirementId),
                );
                return supportingRequirements.length > 0 ? [{evidence, supportingRequirements}] : [];
              })
            : [];
          return {
            jobId,
            report,
            status: improvedWithoutPlannedRequirement ? "unattributed" as const : "unverifiable" as const,
            alternativeEvidenceProvenance,
          };
        }
        const blocker = blockerByJobId.get(jobId) ?? null;
        if (blocker) {
          const nextRequirement = blocker.requirements[0] ?? null;
          const coveredByCurrentAction = Boolean(
            nextRequirement
            && batchEvidenceAction
            && batchEvidenceAction.requirementIds.includes(nextRequirement.requirementId),
          );
          return {
            jobId,
            report,
            status: "blocked" as const,
            blocker,
            nextRequirement,
            coveredByCurrentAction,
          };
        }
        return {jobId, report, status: "cleared" as const};
      })
    : [];
  const clearedPreviousEvidenceQueueResults = previousEvidenceQueueResults.filter((item) => item.status === "cleared");
  const blockedPreviousEvidenceQueueResults = previousEvidenceQueueResults.filter((item) => item.status === "blocked");
  const unattributedPreviousEvidenceQueueResults = previousEvidenceQueueResults.filter((item) => item.status === "unattributed");
  const unverifiablePreviousEvidenceQueueResults = previousEvidenceQueueResults.filter((item) => item.status === "unverifiable");
  const alternativeEvidenceQualifiedJobIds = new Set(
    feedbackQueueAvailable
      ? unattributedPreviousEvidenceQueueResults.flatMap((item) => {
          if (!item.report || (item.alternativeEvidenceProvenance ?? []).length === 0) return [];
          if (blockerByJobId.has(item.jobId)) return [];
          return [item.jobId];
        })
      : [],
  );
  const unattributedEvidenceOpportunityJobIds = new Set(
    matchedReports.flatMap((report) =>
      alternativeEvidenceQualifiedJobIds.has(report.jobId) && !latestFeedbackByReportId.has(report.reportId)
        ? [report.jobId]
        : [],
    ),
  );
  const unattributedEvidenceOpportunityReports = matchedReports.filter((report) =>
    unattributedEvidenceOpportunityJobIds.has(report.jobId),
  );
  const nextUnattributedEvidenceApplyReport = unattributedEvidenceOpportunityReports[0] ?? null;
  const verifiedAlternativeEvidenceDecisionReports = feedbackQueueAvailable
    ? matchedReports.filter((report) =>
        requestedPrepareAlternativeEvidenceJobIds.includes(report.jobId)
        && alternativeEvidenceQualifiedJobIds.has(report.jobId),
      )
    : [];
  const alternativeEvidenceDecisionSetFullyVerifiable = requestedPrepareAlternativeEvidenceJobIds.length > 0
    && verifiedAlternativeEvidenceDecisionReports.length === requestedPrepareAlternativeEvidenceJobIds.length;
  const alternativeEvidenceCompletedDecisionReports = verifiedAlternativeEvidenceDecisionReports.filter((report) =>
    latestFeedbackByReportId.has(report.reportId),
  );
  const alternativeEvidencePendingDecisionReports = verifiedAlternativeEvidenceDecisionReports.filter((report) =>
    !latestFeedbackByReportId.has(report.reportId),
  );
  const alternativeEvidenceInterestedCount = alternativeEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "interested",
  ).length;
  const alternativeEvidenceMaybeCount = alternativeEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "maybe",
  ).length;
  const alternativeEvidenceRejectedCount = alternativeEvidenceCompletedDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "rejected",
  ).length;
  const nextAlternativeEvidencePendingDecisionReport = alternativeEvidencePendingDecisionReports[0] ?? null;
  const alternativeEvidenceDecisionQuery = verifiedAlternativeEvidenceDecisionReports.length > 0
    ? `&prepareAlternativeEvidenceJobs=${encodeURIComponent(verifiedAlternativeEvidenceDecisionReports.map((report) => report.jobId).join(","))}`
    : "";
  const evidenceUpdateDecisionReports = matchedReports.filter((report) =>
    verifiedPrepareEvidenceDecisionReports.some((item) => item.reportId === report.reportId)
    || verifiedAlternativeEvidenceDecisionReports.some((item) => item.reportId === report.reportId),
  );
  const evidenceUpdateDecisionSetFullyVerifiable = (requestedPrepareEvidenceJobIds.length > 0 || requestedPrepareAlternativeEvidenceJobIds.length > 0)
    && (requestedPrepareEvidenceJobIds.length === 0 || prepareEvidenceDecisionSetFullyVerifiable)
    && (requestedPrepareAlternativeEvidenceJobIds.length === 0 || alternativeEvidenceDecisionSetFullyVerifiable);
  const evidenceUpdatePendingDecisionReports = evidenceUpdateDecisionReports.filter((report) =>
    !latestFeedbackByReportId.has(report.reportId),
  );
  const evidenceUpdateDecisionLoopComplete = evidenceUpdateDecisionSetFullyVerifiable
    && evidenceUpdatePendingDecisionReports.length === 0;
  const evidenceUpdateInterestedReports = evidenceUpdateDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "interested",
  );
  const evidenceUpdateMaybeReports = evidenceUpdateDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "maybe",
  );
  const evidenceUpdateRejectedReports = evidenceUpdateDecisionReports.filter(
    (report) => latestFeedbackByReportId.get(report.reportId)?.decision === "rejected",
  );
  const evidenceUpdatePrimaryApplicationReport = evidenceUpdateInterestedReports[0] ?? evidenceUpdateMaybeReports[0] ?? null;
  const unattributedEvidenceOpportunityQuery = unattributedEvidenceOpportunityReports.length > 0
    ? `&prepareAlternativeEvidenceJobs=${encodeURIComponent(unattributedEvidenceOpportunityReports.map((report) => report.jobId).join(","))}`
    : "";
  const verifiedPreviousEvidenceQueueCount = clearedPreviousEvidenceQueueResults.length + blockedPreviousEvidenceQueueResults.length;
  const afterMatchJobIdSet = new Set(requestedAfterMatchJobIds);
  const postMatchEvidenceResults = previousEvidenceQueueResults.filter((item) => afterMatchJobIdSet.has(item.jobId));
  const postMatchEvidenceClearedResults = postMatchEvidenceResults.filter((item) => item.status === "cleared");
  const postMatchEvidenceBlockedResults = postMatchEvidenceResults.filter((item) => item.status === "blocked");
  const postMatchEvidenceUnattributedResults = postMatchEvidenceResults.filter((item) => item.status === "unattributed");
  const postMatchEvidenceUnverifiableResults = postMatchEvidenceResults.filter((item) => item.status === "unverifiable");
  const postMatchEvidenceBlockedJobIds = new Set(postMatchEvidenceBlockedResults.map((item) => item.jobId));
  const postMatchEvidenceClearedWithFeedbackCount = postMatchEvidenceClearedResults.filter((item) => {
    const report = item.report;
    return Boolean(report && latestFeedbackByReportId.has(report.reportId));
  }).length;
  const postMatchEvidenceClearedPendingFeedbackCount = postMatchEvidenceClearedResults.length - postMatchEvidenceClearedWithFeedbackCount;
  const postMatchEvidenceClearedJobIds = new Set(postMatchEvidenceClearedResults.map((item) => item.jobId));
  const nextPostMatchEvidenceFeedbackReport = matchedReports.find((report) =>
    postMatchEvidenceClearedJobIds.has(report.jobId) && !latestFeedbackByReportId.has(report.reportId),
  ) ?? null;
  const postMatchEvidenceConverged = postMatchEvidenceResults.length > 0
    && postMatchEvidenceBlockedResults.length === 0
    && postMatchEvidenceUnattributedResults.length === 0
    && postMatchEvidenceUnverifiableResults.length === 0;
  const nextEvidencePostMatchTargets = batchEvidenceImpactTargets.filter((target) => postMatchEvidenceBlockedJobIds.has(target.jobId));
  const clearedPreviousEvidenceQueueJobIds = new Set(clearedPreviousEvidenceQueueResults.map((item) => item.jobId));
  const clearedPendingDecisionReports = feedbackAvailable
    ? matchedReports.filter(
        (report) => clearedPreviousEvidenceQueueJobIds.has(report.jobId) && !latestFeedbackByReportId.has(report.reportId),
      )
    : [];
  const nextClearedApplyDecisionReport = clearedPendingDecisionReports[0] ?? null;
  const batchEvidenceConsideredJobCount = batchEvidenceAction
    ? consideredAffectedJobCount(batchEvidenceAction, feedbackByJobId)
    : 0;
  const batchEvidenceProfileHref = batchEvidenceAction
    ? `/profile?next=/recommendations&returnImport=${encodeURIComponent(id)}&focusRequirement=${encodeURIComponent(batchEvidenceAction.requirementType)}&focusJob=${encodeURIComponent(batchEvidenceFocusJobId ?? "")}${batchEvidenceRequirement ? `&focusRequirementId=${encodeURIComponent(batchEvidenceRequirement.requirementId)}` : ""}${batchEvidenceAction.normalizedCapability ? `&focusCapability=${encodeURIComponent(batchEvidenceAction.normalizedCapability)}` : ""}${batchEvidenceAction.examples[0] ? `&focusRequirementText=${encodeURIComponent(batchEvidenceAction.examples[0])}` : ""}${batchEvidenceImpactTargets.length > 0 ? `&focusImpactJobs=${encodeURIComponent(batchEvidenceImpactTargets.slice(0, 3).map((target) => target.jobId).join(","))}` : ""}${batchEvidenceAction.requirementIds.length > 0 ? `&focusImpactRequirementIds=${encodeURIComponent(batchEvidenceAction.requirementIds.slice(0, 20).join(","))}` : ""}${requestedAfterMatchJobIds.length > 0 ? `&afterMatchJobs=${encodeURIComponent(requestedAfterMatchJobIds.join(","))}` : ""}#profile-evidence-focus`
    : null;
  const matchReadyCount = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  ).length;
  const requirementBlockedCount = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  }).length;
  const unknownReadinessCount = importedJobIds.length - matchedCount - matchReadyCount - requirementBlockedCount;
  const matchReadyJobs = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  );
  const requirementBlockedJobs = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  });
  const unknownReadinessJobs = importedJobIds.filter((jobId) => {
    if (rankedJobIds.has(jobId)) {
      return false;
    }
    const readiness = readinessByJobId.get(jobId);
    return !readiness || (
      readiness.releaseEligible && (!rankingAvailable || !matchInputReadinessAvailable)
    );
  });
  const jobLabel = (jobId: string) => {
    const job = jobDetailById.get(jobId);
    return job ? `${job.title} · ${job.company}` : `岗位 ${jobId}`;
  };
  const afterPreparationFallbackAction = requestedAfterPreparationJobId
    ? nextApplyDecisionReport
      ? {
          href: `/jobs/${nextApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`,
          label: `回到批次：判断 ${jobLabel(nextApplyDecisionReport.jobId)}`,
          reason: `当前还有 ${pendingApplyDecisionCount ?? 0} 个岗位已经有 current MatchReport、没有 hard blocker，但尚未记录投递判断；先完成判断能直接把现有 Ranking 结果转成用户决策，不需要生成新的分析。`,
        }
      : matchReadyJobs.length > 0
        ? {
            href: "#batch-match",
            label: `回到批次：匹配 ${matchReadyJobs.length} 个已准备岗位`,
            reason: `当前有 ${matchReadyJobs.length} 个岗位的 Requirement 已达到 release / Match readiness，但还没有 current MatchReport；下一步需要用户显式 Match，才能进入 Ranking 与投递判断。`,
          }
        : requirementBlockedJobs.length > 0
          ? {
              href: `/jobs/${requirementBlockedJobs[0]}`,
              label: "回到批次：先处理一个岗位要求",
              reason: `当前还有 ${requirementBlockedJobs.length} 个岗位的 Requirement 尚未达到 release 条件；在这些事实准备好之前，不应提前运行 Match 或解释排序结果。`,
            }
          : batchEvidenceAction && batchEvidenceProfileHref
            ? {
                href: batchEvidenceProfileHref,
                label: "回到批次：继续下一项 Evidence",
                reason: batchEvidenceImpactTargets.length > 0
                  ? `当前 Evidence action 精确命中 ${batchEvidenceImpactTargets.length} 个仍在考虑岗位的 Requirement；这些 hard blocker 需要先用真实经历补证，再通过显式 Re-match 验证是否解除。`
                  : "当前仍有 Evidence blocker，但没有更早阶段的待判断、Match-ready 或 Requirement blocker；继续现有 Evidence action 是当前可验证的下一步。",
              }
            : finalMaybeReports[0]
              ? {
                  href: `/jobs/${finalMaybeReports[0].jobId}/prepare?returnImport=${encodeURIComponent(id)}`,
                  label: `复核保留观察岗位：${jobLabel(finalMaybeReports[0].jobId)}`,
                  reason: `当前没有更早阶段的待判断、Match-ready、Requirement 或 Evidence 工作；剩余 ${finalMaybeReports.length} 个“再看看”岗位，因此按 current Ranking 先复核最高的一项。`,
                }
              : {
                  href: "/import",
                  label: "当前批次没有其他可执行目标，导入下一批岗位",
                  reason: "当前批次没有可验证的待判断、Match-ready、Requirement blocker、Evidence blocker 或 maybe 复核项；继续制造新动作不会增加主闭环价值。",
                }
    : null;

  const feedbackDecisionLabel = (decision: "interested" | "maybe" | "rejected" | undefined) => {
    if (decision === "interested") return "你已标记为感兴趣";
    if (decision === "maybe") return "你已标记为再看看";
    if (decision === "rejected") return "你已标记为不考虑";
    return "你还没有记录投递判断";
  };
  const feedbackDecisionShortLabel = (decision: "interested" | "maybe" | "rejected" | undefined) => {
    if (decision === "interested") return "感兴趣";
    if (decision === "maybe") return "再看看";
    if (decision === "rejected") return "不考虑";
    return "尚未判断";
  };

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">添加结果</p>
        <h1>这批岗位处理得怎么样</h1>
        <p className="lede">
          这里告诉你哪些岗位已经添加、哪些更新了已有信息，以及哪些没有成功处理。
        </p>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>文件中的岗位</span><strong>{detail.received}</strong></div>
        <div className="summary-card"><span>新增</span><strong>{detail.created}</strong></div>
        <div className="summary-card"><span>信息已更新</span><strong>{detail.updated}</strong></div>
        <div className="summary-card"><span>未添加</span><strong>{detail.skipped}</strong></div>
      </div>

      {importedJobIds.length > 0 ? (
        <section className="detail-card" style={{marginBottom: "1rem"}}>
          <h2>这批岗位下一步怎么处理</h2>
          <p className="notice">
            这里只读取现有 Requirement / Match 事实，不会自动分析岗位、调用 Provider 或替你发起匹配。
          </p>
          <div className="summary-grid">
            <div className="summary-card"><span>已有当前匹配结果</span><strong>{matchedCount}</strong></div>
            <div className="summary-card"><span>要求已准备，可进入匹配</span><strong>{matchReadyCount}</strong></div>
            <div className="summary-card"><span>岗位要求还未准备好</span><strong>{requirementBlockedCount}</strong></div>
            {unknownReadinessCount > 0 ? (
              <div className="summary-card"><span>暂时无法确认</span><strong>{unknownReadinessCount}</strong></div>
            ) : null}
          </div>
          {requestedAfterPreparationJobId ? (
            preparationProgressItems ? (
              <ApplicationChecklistSummary
                jobId={requestedAfterPreparationJobId}
                jobLabel={jobLabel(requestedAfterPreparationJobId)}
                items={preparationProgressItems}
                prepareHref={`/jobs/${requestedAfterPreparationJobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceDecisionQuery}${alternativeEvidenceDecisionQuery}${previousEvidenceAttributionQuery}`}
                interestedCandidates={afterPreparationInterestedCandidates.map(({report, items}) => ({
                  jobId: report.jobId,
                  jobLabel: jobLabel(report.jobId),
                  prepareHref: `/jobs/${report.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceDecisionQuery}${alternativeEvidenceDecisionQuery}${previousEvidenceAttributionQuery}`,
                  items,
                }))}
                fallbackHref={afterPreparationFallbackAction?.href ?? "/import"}
                fallbackLabel={afterPreparationFallbackAction?.label ?? "回到批次继续下一步"}
                fallbackReason={afterPreparationFallbackAction?.reason ?? "继续使用当前批次已有事实选择下一步，不新增评分或状态。"}
                batchRemainder={{
                  pendingDecision: pendingApplyDecisionCount ?? 0,
                  matchReady: matchReadyJobs.length,
                  requirementBlocked: requirementBlockedJobs.length,
                  evidenceBlocked: pendingEvidenceCount ?? 0,
                  maybe: finalMaybeReports.length,
                  unknownReadiness: unknownReadinessCount,
                }}
              />
            ) : (
              <div className="notice">
                当前无法用这批岗位的最新 JobPreparationBundle 校验刚才的申请准备进度，因此这里不展示旧浏览器勾选，也不猜测准备是否完成。
              </div>
            )
          ) : null}
          {requestedAfterMatchJobIds.length > 0 ? (
            <div className="notice" id="batch-match-result">
              <strong>刚完成显式 Match 后，这些岗位进入了哪里：</strong>
              {afterMatchTransitionResults.length > 0 ? (
                <>
                  <div className="summary-grid">
                    <div className="summary-card"><span>等待投递判断</span><strong>{afterMatchApplyResults.length}</strong></div>
                    <div className="summary-card"><span>进入 Evidence Loop</span><strong>{afterMatchEvidenceResults.length}</strong></div>
                    {afterMatchCompletedResults.length > 0 ? (
                      <div className="summary-card"><span>当前已完成处理</span><strong>{afterMatchCompletedResults.length}</strong></div>
                    ) : null}
                    {afterMatchUnverifiableResults.length > 0 ? (
                      <div className="summary-card"><span>暂无法确认迁移</span><strong>{afterMatchUnverifiableResults.length}</strong></div>
                    ) : null}
                  </div>
                  {afterMatchApplyResults.length > 0 ? (
                    <p className="muted">{afterMatchApplyResults.map((item) => jobLabel(item.jobId)).join("、")} 已形成 current MatchReport，且当前没有 hard blocker；下一步是完成真实投递判断。</p>
                  ) : null}
                  {afterMatchEvidenceResults.length > 0 ? (
                    <p className="muted">{afterMatchEvidenceResults.map((item) => jobLabel(item.jobId)).join("、")} 已形成 current MatchReport，但仍有 hard blocker；它们已进入 Evidence Loop，不会被误报成可直接投递。</p>
                  ) : null}
                  {afterMatchUnverifiableResults.length > 0 ? (
                    <p className="muted">另有 {afterMatchUnverifiableResults.length} 个本轮目标当前还缺少可可靠读取的 current MatchReport / blocker facts，因此这里不猜测它们迁移到了哪个阶段。</p>
                  ) : null}
                  {nextAfterMatchApplyReport ? (
                    <div className="actions">
                      <Link className="button" href={`/jobs/${nextAfterMatchApplyReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}`}>
                        下一步：先判断 {jobLabel(nextAfterMatchApplyReport.jobId)}
                      </Link>
                      <span className="muted">这项在本轮新进入“等待投递判断”的岗位里 current Ranking 最高；没有新增评分。</span>
                    </div>
                  ) : afterMatchEvidenceResults.length > 0 && batchEvidenceAction && batchEvidenceProfileHref ? (
                    <div className="actions">
                      <Link className="button" href={batchEvidenceProfileHref}>下一步：处理当前最高价值 Evidence</Link>
                      <span className="muted">本轮没有新解锁到投递判断的岗位；这些成功 Match 岗位仍有 hard blocker，因此继续现有 Evidence Loop。</span>
                    </div>
                  ) : afterMatchUnverifiableResults.length > 0 ? (
                    <p className="muted">本轮迁移结果仍有不可验证项，当前不强行切换到投递判断或下一 Evidence。</p>
                  ) : null}
                  <p className="muted">这里只解释你刚才显式 Match 已产生的最新事实，不会再次运行 Match 或调用 Provider。</p>
                </>
              ) : (
                <p className="muted">返回参数没有命中这次导入中的岗位，因此这里不声称任何岗位已经完成 Match。</p>
              )}
            </div>
          ) : null}
          {feedbackQueueAvailable && batchProcessedCount !== null && batchProcessingRemaining !== null && unmatchedProcessingCount !== null && pendingApplyDecisionCount !== null && pendingEvidenceCount !== null ? (
            <div className="notice">
              <strong>本批处理进度：已处理 {batchProcessedCount}/{batchProcessingTotal}</strong>
              {batchProcessingComplete ? (
                <div className="detail-section">
                  <p className="muted">这批岗位已经全部形成 current MatchReport，并且每个岗位都完成了当前所需处理：无 hard blocker 的岗位已有投递判断，明确“不考虑”的岗位已退出后续 Evidence 待办。当前批次可以视为处理完成。</p>
                  <strong>这批岗位最终怎么处理</strong>
                  <div className="summary-grid">
                    <div className="summary-card"><span>优先继续关注</span><strong>{finalInterestedReports.length}</strong></div>
                    <div className="summary-card"><span>保留观察</span><strong>{finalMaybeReports.length}</strong></div>
                    <div className="summary-card"><span>明确不考虑</span><strong>{finalRejectedReports.length}</strong></div>
                    {showImprovement ? (
                      <div className="summary-card"><span>已验证 Evidence 改善</span><strong>{improvedBatchJobs.length}</strong></div>
                    ) : null}
                  </div>
                  {finalInterestedReports.length > 0 ? (
                    <div>
                      <strong>优先申请 / 继续跟进</strong>
                      <p className="muted">以下顺序直接沿用 current Ranking，不新增最终评分：</p>
                      <ol>
                        {finalInterestedReports.slice(0, 5).map((report) => (
                          <li key={`final-interested-${report.jobId}`}>
                            <Link href={`/jobs/${report.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>{jobLabel(report.jobId)}</Link>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                  <div className="notice">
                    <strong>整批完成后，下一步做什么</strong>
                    {finalInterestedReports[0] ? (
                      <>
                        <p className="muted">先把最高 Ranking 的“感兴趣”岗位转成真实投递准备；这里沿用你已经做出的 UserFeedback，不替你自动申请。</p>
                        <div className="actions">
                          <Link className="button" href={`/jobs/${finalInterestedReports[0].jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                            准备申请：{jobLabel(finalInterestedReports[0].jobId)}
                          </Link>
                        </div>
                      </>
                    ) : finalMaybeReports[0] ? (
                      <>
                        <p className="muted">这批没有你明确标记“感兴趣”的岗位。先复核最高 Ranking 的“再看看”岗位，决定是否升级为真实申请目标。</p>
                        <div className="actions">
                          <Link className="button" href={`/jobs/${finalMaybeReports[0].jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                            复核观察岗位：{jobLabel(finalMaybeReports[0].jobId)}
                          </Link>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="muted">这批岗位都已明确“不考虑”。不要继续为它们补 Evidence；更有价值的是调整求职偏好，或导入下一批真实岗位重新开始。</p>
                        <div className="actions">
                          <Link className="button" href="/profile#targetRoles">调整求职偏好</Link>
                          <Link className="button-secondary" href="/import">导入下一批岗位</Link>
                        </div>
                      </>
                    )}
                  </div>
                  {finalMaybeReports.length > 0 ? (
                    <p className="muted">保留观察：{finalMaybeReports.slice(0, 5).map((report) => jobLabel(report.jobId)).join("、")}{finalMaybeReports.length > 5 ? ` 等 ${finalMaybeReports.length} 个` : ""}。</p>
                  ) : null}
                  {finalRejectedReports.length > 0 ? (
                    <p className="muted">明确不考虑：{finalRejectedReports.slice(0, 5).map((report) => jobLabel(report.jobId)).join("、")}{finalRejectedReports.length > 5 ? ` 等 ${finalRejectedReports.length} 个` : ""}。这些岗位不会继续驱动 Evidence 待办。</p>
                  ) : null}
                  {showImprovement ? (
                    improvementResults.length > 0 ? (
                      <p className="muted">本页当前可比较的 Match 历史中，有 {improvedBatchJobs.length} 个岗位出现了可验证改善；这里只统计已读取到的 immutable MatchReport 对比，不把缺少历史的数据算成“没有改善”。</p>
                    ) : (
                      <p className="muted">当前没有可比较的 Match 历史，因此最终摘要不声称本轮 Evidence 带来了岗位改善。</p>
                    )
                  ) : null}
                </div>
              ) : (
                <>
                  <p className="muted">还剩 {batchProcessingRemaining} 个岗位没有完成当前处理。下面只按当前事实拆分剩余阶段，不把 unknown 状态塞进某个可执行队列。</p>
                  <div className="summary-grid">
                    <div className="summary-card"><span>还没形成 MatchReport</span><strong>{unmatchedProcessingCount}</strong></div>
                    <div className="summary-card"><span>等待投递判断</span><strong>{pendingApplyDecisionCount}</strong></div>
                    <div className="summary-card"><span>等待 Evidence 改善</span><strong>{pendingEvidenceCount}</strong></div>
                  </div>
                  <p className="muted">“等待投递判断”只包含当前无 hard blocker 且尚未反馈的岗位；“等待 Evidence 改善”保留感兴趣/再看看且仍有 blocker 的岗位，明确“不考虑”的岗位已经退出。</p>
                  {unmatchedProcessingCount > 0 ? (
                    <div className="detail-section">
                      <strong>还没形成 MatchReport 的岗位卡在哪里</strong>
                      <div className="summary-grid">
                        <div className="summary-card"><span>Requirement 已 ready，可显式 Match</span><strong>{matchReadyJobs.length}</strong></div>
                        <div className="summary-card"><span>Requirement 仍 blocked</span><strong>{requirementBlockedJobs.length}</strong></div>
                        {unknownReadinessJobs.length > 0 ? (
                          <div className="summary-card"><span>Readiness 暂无法确认</span><strong>{unknownReadinessJobs.length}</strong></div>
                        ) : null}
                      </div>
                      <p className="muted">这三个状态直接复用当前 Requirement Release / Match Readiness 事实：ready 只代表可以由你显式发起 Match，不会自动调用 Provider；blocked 需要先处理岗位要求；无法确认的岗位不会被猜成 ready 或 blocked。</p>
                    </div>
                  ) : null}
                  {nextApplyDecisionReport ? (
                    <div className="actions">
                      <Link className="button" href={`/jobs/${nextApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                        当前主行动：先判断 {jobLabel(nextApplyDecisionReport.jobId)}
                      </Link>
                    </div>
                  ) : matchReadyJobs.length > 0 ? (
                    <div className="actions">
                      <Link className="button" href="#batch-match">当前主行动：先匹配 {matchReadyJobs.length} 个已准备岗位</Link>
                    </div>
                  ) : requirementBlockedJobs.length > 0 ? (
                    <div className="actions">
                      <Link className="button" href={`/jobs/${requirementBlockedJobs[0]}`}>当前主行动：先处理一个岗位要求</Link>
                    </div>
                  ) : batchEvidenceAction && batchEvidenceProfileHref ? (
                    <div className="actions">
                      <Link className="button" href={batchEvidenceProfileHref}>当前主行动：继续下一项 Evidence</Link>
                    </div>
                  ) : (
                    <p className="muted">当前没有可以基于可靠事实给出的唯一主行动；不会用未知 readiness / blocker 状态替你猜。</p>
                  )}
                </>
              )}
            </div>
          ) : matchedReports.length > 0 ? (
            <div className="notice">当前无法可靠读取 latest UserFeedback 或 hard blocker，因此这里不计算批次完成进度，也不会把未知状态误报成“已处理”。</div>
          ) : null}
          {requestedAfterFeedbackJobId ? (
            afterFeedbackConfirmed ? (
              <div className="notice">
                <strong>刚完成一项投递判断：</strong>{jobLabel(requestedAfterFeedbackJobId)} 已记录为“{feedbackDecisionShortLabel(afterFeedbackDecision ?? undefined)}”。本页已经按更新后的 latest UserFeedback、当前 Ranking 与 hard blocker 重新计算下一步。
                {requestedPrepareEvidenceJobIds.length > 0 ? (
                  <div className="detail-section">
                    <strong>这次 Evidence 已转化出的真实投递判断：</strong>
                    <div className="summary-grid">
                      <div className="summary-card"><span>已完成判断</span><strong>{prepareEvidenceCompletedDecisionReports.length}</strong></div>
                      <div className="summary-card"><span>仍待判断</span><strong>{prepareEvidencePendingDecisionReports.length}</strong></div>
                    </div>
                    {prepareEvidencePendingDecisionReports.length > 0 ? (
                      <p className="muted">仍待判断：{prepareEvidencePendingDecisionReports.slice(0, 3).map((report) => jobLabel(report.jobId)).join("、")}。这里只统计 current facts 仍能验证为“本次 Evidence 真实解除 Requirement 且当前无 hard blocker”的岗位。</p>
                    ) : prepareEvidenceDecisionLoopComplete ? (
                      <>
                        <p className="muted">这次 Evidence 真实解锁且仍可验证的岗位都已经形成 UserFeedback；不会把 URL 中的观察集合本身当成完成证据。</p>
                        <div className="detail-section">
                          <strong>这次 Evidence 行动的小闭环已经完成</strong>
                          <div className="summary-grid">
                            <div className="summary-card"><span>感兴趣</span><strong>{prepareEvidenceInterestedCount}</strong></div>
                            <div className="summary-card"><span>再看看</span><strong>{prepareEvidenceMaybeCount}</strong></div>
                            <div className="summary-card"><span>不考虑</span><strong>{prepareEvidenceRejectedCount}</strong></div>
                          </div>
                          <p className="muted">这些结果只来自 current latest UserFeedback。下面继续复用当前批次已有的主行动顺序，不因为这组局部闭环完成就误报整批结束。</p>
                          {batchEvidenceAction && currentEvidenceQueuePriorityTargets.length > 0 ? (
                            <div className="detail-section">
                              <strong>为什么下一步仍值得继续补 Evidence</strong>
                              <p className="muted">
                                当前下一 Evidence action 仍精确命中 {batchEvidenceQueueTargets.length} 个你还在考虑、且仍有 hard blocker 的岗位；这里只展示 Requirement ID 的真实命中，不预测改善幅度。
                              </p>
                              <ul>
                                {currentEvidenceQueuePriorityTargets.map((target) => (
                                  <li key={`evidence-loop-next-target-${target.jobId}`}>
                                    <strong>{jobLabel(target.jobId)}</strong>
                                    {target.requirementTexts.length > 0 ? `：${target.requirementTexts.slice(0, 2).join("；")}` : ""}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : (
                            <p className="muted">这组判断已完成，但当前没有可靠的下一 Evidence impact target；这里不会为了保持连续感猜测下一项证据会帮助哪些岗位。</p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="muted">当前观察集合里有岗位已经无法由 current Match / blocker / improvement facts 完整验证，因此这里不声明这次 Evidence 决策闭环已经完成。</p>
                    )}
                  </div>
                ) : null}
                {requestedPrepareAlternativeEvidenceJobIds.length > 0 ? (
                  <div className="detail-section">
                    <strong>同次 Profile 更新带来的额外决策价值：</strong>
                    <p className="muted">这一组岗位不是原计划 Evidence 直接解除的目标；它们必须仍能由 alternative Evidence → Requirement provenance + 当前 blocker 清零重新验证，才会计入这里，避免把额外价值混成直接归因成果。</p>
                    <div className="summary-grid">
                      <div className="summary-card"><span>额外已完成判断</span><strong>{alternativeEvidenceCompletedDecisionReports.length}</strong></div>
                      <div className="summary-card"><span>额外仍待判断</span><strong>{alternativeEvidencePendingDecisionReports.length}</strong></div>
                      <div className="summary-card"><span>感兴趣</span><strong>{alternativeEvidenceInterestedCount}</strong></div>
                      <div className="summary-card"><span>再看看</span><strong>{alternativeEvidenceMaybeCount}</strong></div>
                      <div className="summary-card"><span>不考虑</span><strong>{alternativeEvidenceRejectedCount}</strong></div>
                    </div>
                    {alternativeEvidenceDecisionSetFullyVerifiable ? (
                      alternativeEvidencePendingDecisionReports.length > 0 ? (
                        <p className="muted">仍待判断：{alternativeEvidencePendingDecisionReports.slice(0, 3).map((report) => jobLabel(report.jobId)).join("、")}。这些只算“同次更新中的其他真实 Evidence 带来的额外解锁”，不会并入上面的原计划 Evidence 直接产出。</p>
                      ) : (
                        <p className="muted">这组额外解锁岗位都已完成 latest UserFeedback；结果单独保留为额外价值，不改写原计划 Evidence 的直接归因摘要。</p>
                      )
                    ) : (
                      <p className="muted">当前有岗位已经无法由 alternative provenance + current blocker facts 完整验证，因此这里不声明这组额外决策产出已收敛。</p>
                    )}
                  </div>
                ) : null}
                {evidenceUpdateDecisionLoopComplete ? (
                  <div className="detail-section">
                    <strong>这次 Profile Evidence 更新已经形成完整决策结果</strong>
                    <p className="muted">下面把原计划 Evidence 的直接产出与同次更新中其他 Evidence 的额外价值放在同一个结果出口里，但归因口径仍保持分离；顺序继续沿用 current Ranking。</p>
                    <div className="summary-grid">
                      <div className="summary-card"><span>直接解锁</span><strong>{verifiedPrepareEvidenceDecisionReports.length}</strong></div>
                      <div className="summary-card"><span>额外解锁</span><strong>{verifiedAlternativeEvidenceDecisionReports.length}</strong></div>
                      <div className="summary-card"><span>感兴趣</span><strong>{evidenceUpdateInterestedReports.length}</strong></div>
                      <div className="summary-card"><span>再看看</span><strong>{evidenceUpdateMaybeReports.length}</strong></div>
                      <div className="summary-card"><span>不考虑</span><strong>{evidenceUpdateRejectedReports.length}</strong></div>
                    </div>
                    {evidenceUpdatePrimaryApplicationReport ? (
                      <div className="actions">
                        <Link className="button" href={`/jobs/${evidenceUpdatePrimaryApplicationReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceDecisionQuery}${alternativeEvidenceDecisionQuery}${previousEvidenceAttributionQuery}`}>
                          {latestFeedbackByReportId.get(evidenceUpdatePrimaryApplicationReport.reportId)?.decision === "interested" ? "下一步：准备申请" : "下一步：复核观察岗位"} {jobLabel(evidenceUpdatePrimaryApplicationReport.jobId)}
                        </Link>
                        <span className="muted">优先选择 current Ranking 最高的“感兴趣”岗位；若没有感兴趣岗位，才复核最高 Ranking 的“再看看”。明确“不考虑”的岗位不会被继续推动。</span>
                      </div>
                    ) : (
                      <p className="muted">这次更新解锁的岗位都已明确“不考虑”；不再为这组岗位继续做申请准备，回到当前批次的剩余主行动。</p>
                    )}
                  </div>
                ) : nextPrepareEvidencePendingDecisionReport ? (
                  <div className="actions">
                    <Link className="button" href={`/jobs/${nextPrepareEvidencePendingDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceDecisionQuery}${alternativeEvidenceDecisionQuery}${previousEvidenceAttributionQuery}`}>
                      下一步：继续判断这次 Evidence 解锁的 {jobLabel(nextPrepareEvidencePendingDecisionReport.jobId)}
                    </Link>
                  </div>
                ) : nextAlternativeEvidencePendingDecisionReport ? (
                  <div className="actions">
                    <Link className="button" href={`/jobs/${nextAlternativeEvidencePendingDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceDecisionQuery}${alternativeEvidenceDecisionQuery}${previousEvidenceAttributionQuery}`}>
                      下一步：继续判断额外解锁的 {jobLabel(nextAlternativeEvidencePendingDecisionReport.jobId)}
                    </Link>
                  </div>
                ) : nextAfterMatchApplyReport ? (
                  <div className="actions">
                    <Link className="button" href={`/jobs/${nextAfterMatchApplyReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}`}>
                      下一步：继续判断本轮 Match 解锁的 {jobLabel(nextAfterMatchApplyReport.jobId)}
                    </Link>
                  </div>
                ) : requestedAfterMatchJobIds.length > 0 && afterMatchEvidenceResults.length > 0 && batchEvidenceAction && batchEvidenceProfileHref ? (
                  <div className="actions">
                    <Link className="button" href={batchEvidenceProfileHref}>下一步：本轮解锁岗位已判断完，继续处理真实 Evidence</Link>
                  </div>
                ) : nextApplyDecisionReport ? (
                  <div className="actions">
                    <Link className="button" href={`/jobs/${nextApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                      下一步：判断 {jobLabel(nextApplyDecisionReport.jobId)}
                    </Link>
                  </div>
                ) : batchEvidenceAction && batchEvidenceProfileHref ? (
                  <div className="actions">
                    <Link className="button" href={batchEvidenceProfileHref}>下一步：处理真实 Evidence</Link>
                  </div>
                ) : feedbackDecisionCounts?.pending === 0 ? (
                  <p className="muted">这批已有 MatchReport 的岗位都已记录投递判断；当前没有新的可靠主行动。</p>
                ) : (
                  <p className="muted">当前没有可以基于可靠事实自动推荐的下一主行动；不会用未知 blocker 状态替你猜。</p>
                )}
              </div>
            ) : (
              <div className="notice">返回批次时没有读到这次岗位判断对应的 current MatchReport + latest UserFeedback，因此这里不声称反馈已完成，也不据此改变下一步。</div>
            )
          ) : null}
          {showImprovement ? (
            <section className="detail-section" id="prepare-evidence-batch-result">
              {requestedAfterPrepareEvidenceJobId ? (
                prepareEvidenceSourceResult ? (
                  <div className="notice">
                    <strong>刚从申请准备回来：这次 Evidence 的批次影响已重新核验</strong>
                    <p className="muted">{jobLabel(prepareEvidenceSourceResult.report.jobId)} 的目标 Requirement 已在可比较 MatchImprovement 中真实解除；下面的跨岗位结果仍由本批 current MatchReport 重新计算，不信任返回链接本身。</p>
                    {otherPrepareEvidenceImprovedJobs.length > 0 ? (
                      <>
                        <p>同一次 Profile 更新还真实改善了 <strong>{otherPrepareEvidenceImprovedJobs.length}</strong> 个同批岗位：</p>
                        <ul>
                          {otherPrepareEvidenceImprovedJobs.slice(0, 3).map(({report, improvement}) => (
                            <li key={`prepare-evidence-batch-${report.reportId}`}>
                              <strong>{jobLabel(report.jobId)}</strong>：少了 {improvement.resolvedRequirementIds.length} 条硬条件缺口
                              {improvement.previousRecommendation !== improvement.currentRecommendation
                                ? `，推荐结果从 ${improvement.previousRecommendation ?? "无"} 变为 ${improvement.currentRecommendation ?? "无"}`
                                : ""}。
                            </li>
                          ))}
                        </ul>
                        {nextPrepareEvidenceUnlockedReport ? (
                          <div className="actions">
                            <Link className="button" href={`/jobs/${nextPrepareEvidenceUnlockedReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}${prepareEvidenceUnlockedJobQuery}`}>
                              下一步：判断刚被这次 Evidence 解锁的 {jobLabel(nextPrepareEvidenceUnlockedReport.jobId)}
                            </Link>
                          </div>
                        ) : (
                          <p className="muted">这些额外改善岗位里，当前没有同时满足“真实解除 Requirement、已无 hard blocker、且尚未反馈”的新投递判断；不会仅凭推荐文案变化强行推进。</p>
                        )}
                      </>
                    ) : (
                      <p className="muted">当前没有其他同批岗位满足“可比较且真实改善”的证据，因此这里不扩张这次 Evidence 的跨岗位价值。</p>
                    )}
                  </div>
                ) : (
                  <div className="notice">
                    <strong>暂时无法确认这次 Prepare Evidence 的批次影响</strong>
                    <p className="muted">返回参数不能证明改善；只有来源岗位的目标 Requirement 能在当前可比较 MatchImprovement 中再次确认 resolved 时，才会展示跨岗位影响。</p>
                  </div>
                )
              ) : null}
              {postMatchEvidenceResults.length > 0 ? (
                <div className="notice">
                  <strong>这轮 Match 里原本 blocked 的岗位，Re-match 后发生了什么：</strong>
                  <p className="muted">这里只统计同时属于本轮 Match 上下文、且确实被刚才 Evidence action 纳入观察的岗位；只有可比较的 MatchReport 和当前 blocker facts 才会被归类。</p>
                  <div className="summary-grid">
                    <div className="summary-card"><span>本次实际观察</span><strong>{postMatchEvidenceResults.length}</strong></div>
                    <div className="summary-card"><span>新增解锁</span><strong>{postMatchEvidenceClearedResults.length}</strong></div>
                    <div className="summary-card"><span>仍有 hard blocker</span><strong>{postMatchEvidenceBlockedResults.length}</strong></div>
                    {postMatchEvidenceUnverifiableResults.length > 0 ? (
                      <div className="summary-card"><span>暂无法验证</span><strong>{postMatchEvidenceUnverifiableResults.length}</strong></div>
                    ) : null}
                  </div>
                  <div className="notice">
                    <strong>这组岗位现在还剩多少要处理：</strong>
                    <div className="summary-grid">
                      <div className="summary-card"><span>已解锁并完成反馈</span><strong>{postMatchEvidenceClearedWithFeedbackCount}</strong></div>
                      <div className="summary-card"><span>已解锁、等待反馈</span><strong>{postMatchEvidenceClearedPendingFeedbackCount}</strong></div>
                      <div className="summary-card"><span>仍需 Evidence</span><strong>{postMatchEvidenceBlockedResults.length}</strong></div>
                      {postMatchEvidenceUnverifiableResults.length > 0 ? (
                        <div className="summary-card"><span>暂无法确认</span><strong>{postMatchEvidenceUnverifiableResults.length}</strong></div>
                      ) : null}
                    </div>
                    <p className="muted">这里的“已完成反馈”只统计已经真实存在 latest UserFeedback 的已解锁岗位；不会把单纯解除 blocker 当成用户已经做完投递判断。</p>
                  </div>
                  {postMatchEvidenceConverged ? (
                    <div className="notice">
                      <strong>这组 post-Match Evidence 已经收敛：</strong>
                      {nextPostMatchEvidenceFeedbackReport ? (
                        <>
                          <p className="muted">本次实际观察岗位已经全部解除 hard blocker，且没有不可验证项；现在剩下的不是继续补 Evidence，而是完成已解锁岗位的真实 UserFeedback。</p>
                          <div className="actions">
                            <Link className="button" href={`/jobs/${nextPostMatchEvidenceFeedbackReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${afterMatchPrepareQuery}`}>
                              下一步：判断 {jobLabel(nextPostMatchEvidenceFeedbackReport.jobId)}
                            </Link>
                          </div>
                        </>
                      ) : (
                        <>
                          <p className="muted">本次实际观察岗位已经全部解除 hard blocker，并且这些已解锁岗位都已有 latest UserFeedback。这组 Evidence 工作可以结束；这里只结束这组观察目标，不代表整个 Import Batch 已完成。</p>
                          {batchProcessingComplete ? (
                            <p className="muted">按当前 current MatchReport、latest UserFeedback 与 blocker facts，这批导入岗位也已经全部完成当前处理。</p>
                          ) : nextApplyDecisionReport ? (
                            <div className="actions">
                              <Link className="button" href={`/jobs/${nextApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                                回到批次剩余判断：{jobLabel(nextApplyDecisionReport.jobId)}
                              </Link>
                            </div>
                          ) : matchReadyJobs.length > 0 ? (
                            <div className="actions">
                              <Link className="button" href="#batch-match">回到批次：匹配 {matchReadyJobs.length} 个已准备岗位</Link>
                            </div>
                          ) : requirementBlockedJobs.length > 0 ? (
                            <div className="actions">
                              <Link className="button" href={`/jobs/${requirementBlockedJobs[0]}`}>回到批次：先处理一个岗位要求</Link>
                            </div>
                          ) : batchEvidenceAction && batchEvidenceProfileHref ? (
                            <div className="actions">
                              <Link className="button" href={batchEvidenceProfileHref}>回到批次剩余 Evidence</Link>
                            </div>
                          ) : (
                            <p className="muted">当前没有更强的批次级主行动；不会把这组 Evidence 的完成误报成整批岗位完成，也不会把未知 readiness 猜成可执行状态。</p>
                          )}
                        </>
                      )}
                    </div>
                  ) : postMatchEvidenceClearedResults.length > 0 ? (
                    <p className="muted">新增解锁岗位已经重新进入上面的 post-Match 投递判断队列，并继续按 current Ranking 选择下一项；不会因为 Evidence 回流另建一套排序。</p>
                  ) : postMatchEvidenceBlockedResults.length > 0 ? (
                    <>
                      <p className="muted">这组岗位当前还没有新增解锁；已验证仍 blocked 的岗位继续留在 Evidence Loop。</p>
                      {batchEvidenceAction && nextEvidencePostMatchTargets.length > 0 ? (
                        <div className="detail-section">
                          <strong>为什么下一 Evidence 仍值得继续：</strong>
                          <p className="muted">当前既有 Evidence Priority 仍精确命中这轮 Match 中 {nextEvidencePostMatchTargets.length} 个已验证 blocked 岗位；这里不新增评分，只展示它实际覆盖的剩余 Requirement。</p>
                          <ul>
                            {nextEvidencePostMatchTargets.slice(0, 3).map((target) => (
                              <li key={`post-match-next-evidence-${target.jobId}`}>
                                <strong>{jobLabel(target.jobId)}</strong>
                                <ul>
                                  {target.requirementTexts.map((requirementText) => (
                                    <li key={`post-match-next-evidence-${target.jobId}-${requirementText}`}>{requirementText}</li>
                                  ))}
                                </ul>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : batchEvidenceAction ? (
                        <p className="muted">当前下一 Evidence action 仍来自批次中未解决的真实 blocker，但它没有精确命中这轮 Match 里刚验证仍 blocked 的岗位；系统不会为了维持连续感而声称它会帮助这些岗位。</p>
                      ) : null}
                    </>
                  ) : (
                    <p className="muted">当前只有不可验证结果，因此这里不声称 Evidence 已经改善或没有改善这些岗位。</p>
                  )}
                </div>
              ) : null}
              {previousEvidenceQueueResults.length > 0 ? (
                <div className="notice">
                  <strong>刚才这项 Evidence 核实后，待办岗位发生了什么：</strong>
                  <p className="muted">
                    原计划观察 {focusImpactJobIds.length} 个待办岗位；Re-match 后已有 {verifiedPreviousEvidenceQueueCount} 个可以归因到本次计划 Requirement，{unattributedPreviousEvidenceQueueResults.length} 个虽然出现改善但不能归因给本次 Evidence，另有 {unverifiablePreviousEvidenceQueueResults.length} 个暂时无法验证。
                  </p>
                  <div className="summary-grid">
                    <div className="summary-card"><span>原计划观察</span><strong>{focusImpactJobIds.length}</strong></div>
                    <div className="summary-card"><span>已解除 hard blocker</span><strong>{clearedPreviousEvidenceQueueResults.length}</strong></div>
                    <div className="summary-card"><span>仍有 hard blocker</span><strong>{blockedPreviousEvidenceQueueResults.length}</strong></div>
                    <div className="summary-card"><span>改善但无法归因</span><strong>{unattributedPreviousEvidenceQueueResults.length}</strong></div>
                    <div className="summary-card"><span>暂无法验证</span><strong>{unverifiablePreviousEvidenceQueueResults.length}</strong></div>
                  </div>
                  {nextClearedApplyDecisionReport ? (
                    <div className="notice">
                      <strong>现在最值得做：</strong>先完成已解除 hard blocker、且还没有记录投递判断的岗位。按当前 Ranking 顺序，<strong>{jobLabel(nextClearedApplyDecisionReport.jobId)}</strong> 是这组岗位里排位最高的一项；这里不新增评分，只把已经产生的 Evidence 价值先转成真实 UserFeedback。
                      <div className="actions">
                        <Link className="button" href={`/jobs/${nextClearedApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                          先判断这个最高排名的已解锁岗位
                        </Link>
                      </div>
                    </div>
                  ) : verifiedPreviousEvidenceQueueCount > 0 && blockedPreviousEvidenceQueueResults.length > 0 && batchEvidenceAction && batchEvidenceProfileHref ? (
                    <div className="notice">
                      <strong>现在最值得做：</strong>这次还没有原计划岗位解除 hard blocker，但已有可验证结果，且当前仍存在可靠的下一 Evidence action。继续核实下一项真实证据，再 Re-match 看是否能解锁岗位。
                      <div className="actions">
                        <Link className="button" href={batchEvidenceProfileHref}>继续下一项 Evidence</Link>
                      </div>
                    </div>
                  ) : unverifiablePreviousEvidenceQueueResults.length > 0 ? (
                    <div className="notice">
                      <strong>现在先不自动改节奏：</strong>本轮仍有岗位缺少可比较结果或当前事实不完整。先保留现有处理路径，不把未知当成“补证据无效”，也不因为未知结果强行切换到投递判断或下一 Evidence。
                    </div>
                  ) : null}
                  {clearedPreviousEvidenceQueueResults.length > 0 ? (
                    <div className="detail-section">
                      <strong>可以转入投递判断</strong>
                      <ul>
                        {clearedPreviousEvidenceQueueResults.map(({jobId, report}) => {
                          const latestFeedback = report ? latestFeedbackByReportId.get(report.reportId) : undefined;
                          return (
                            <li key={`cleared-${jobId}`}>
                              {jobLabel(jobId)}
                              {latestFeedback ? (
                                <div className="muted">当前投递判断：{feedbackDecisionShortLabel(latestFeedback.decision)}；这项已完成 UserFeedback，不再占用本轮主下一步。</div>
                              ) : (
                                <div className="actions">
                                  <Link className="button" href={`/jobs/${jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>查看完整依据并做投递判断</Link>
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                  {blockedPreviousEvidenceQueueResults.length > 0 ? (
                    <div className="detail-section">
                      <strong>仍需继续 Evidence Loop</strong>
                      <ul>
                        {blockedPreviousEvidenceQueueResults.map((item) => (
                          <li key={`blocked-${item.jobId}`}>
                            <strong>{jobLabel(item.jobId)}</strong>：当前仍有 {item.blocker.missingRequirementCount} 条 hard blocker。
                            {item.nextRequirement ? (
                              <>
                                <div>下一条剩余 Requirement：{item.nextRequirement.originalText}</div>
                                <div className="muted">
                                  {batchEvidenceAction
                                    ? item.coveredByCurrentAction
                                      ? "当前下一 Evidence action 会覆盖这条 Requirement；完成真实资料核实后，再用 Re-match 验证它是否解除。"
                                      : "当前下一 Evidence action 不覆盖这条 Requirement；它会先处理当前批次中价值更高的其他真实 blocker。"
                                    : "当前没有可可靠生成的下一 Evidence action，因此这里只展示剩余 Requirement，不猜测该先补什么。"}
                                </div>
                                {batchEvidenceAction && !item.coveredByCurrentAction ? (
                                  currentEvidenceQueuePriorityTargets.length > 0 ? (
                                    <div className="notice">
                                      <strong>当前 action 会先帮助这些待办岗位：</strong>
                                      <ul>
                                        {currentEvidenceQueuePriorityTargets.map((target) => (
                                          <li key={`priority-target-${item.jobId}-${target.jobId}`}>
                                            <strong>{jobLabel(target.jobId)}</strong>
                                            {target.requirementTexts.length > 0 ? (
                                              <ul>
                                                {target.requirementTexts.slice(0, 2).map((requirementText) => (
                                                  <li key={`${item.jobId}-${target.jobId}-${requirementText}`}>{requirementText}</li>
                                                ))}
                                              </ul>
                                            ) : null}
                                          </li>
                                        ))}
                                      </ul>
                                      <p className="muted">这些目标来自当前 Evidence action 对真实 Requirement ID 的命中，不代表它们一定会改善；最终仍以保存真实 Evidence 后的 Re-match 为准。</p>
                                    </div>
                                  ) : (
                                    <div className="muted">当前 action 没有可可靠列出的其他 queue target，因此这里不猜测它会先帮助哪个岗位。</div>
                                  )
                                ) : null}
                              </>
                            ) : (
                              <div className="muted">当前 blocker 事实无法解析出 Requirement 原文，因此这里不猜测具体缺口。</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {unattributedPreviousEvidenceQueueResults.length > 0 ? (
                    <div className="detail-section">
                      <strong>岗位改善了，但不能归功于这次 Evidence</strong>
                      <ul>
                        {unattributedPreviousEvidenceQueueResults.map((item) => (
                          <li key={`unattributed-${item.jobId}`}>
                            <strong>{jobLabel(item.jobId)}</strong>：前后 MatchReport 可比较且确实出现改善，但本次行动前记录的 Requirement ID 没有进入 resolvedRequirementIds。系统不会把同一次 Profile 更新中的其他 Evidence 改动误算到这次行动上。
                            {(item.alternativeEvidenceProvenance ?? []).length > 0 ? (
                              <div className="notice">
                                <strong>现有 provenance 指向的其他新增匹配依据：</strong>
                                <ul>
                                  {(item.alternativeEvidenceProvenance ?? []).slice(0, 3).map(({evidence, supportingRequirements}) => (
                                    <li key={`${item.jobId}-${evidence.evidenceId}`}>
                                      <strong>{evidence.summary}</strong>
                                      <ul>
                                        {supportingRequirements.slice(0, 3).map((requirement) => (
                                          <li key={`${evidence.evidenceId}-${requirement.requirementId}`}>
                                            新支撑岗位要求：{requirement.originalText}
                                          </li>
                                        ))}
                                      </ul>
                                    </li>
                                  ))}
                                </ul>
                                <p className="muted">这些只说明同一次 Profile 更新中真实新增了哪些 Requirement → Evidence 支撑关系，可以解释岗位为何出现其他改善；它们不会被改写成本次原计划 Evidence 的成果。</p>
                                {feedbackQueueAvailable && item.report ? (
                                  blockerByJobId.has(item.jobId) ? (
                                    <p className="muted">这个岗位当前仍有 hard blocker，所以这些其他新增 Evidence 还不足以把它放行到投递判断；继续留在 Evidence Loop。</p>
                                  ) : latestFeedbackByReportId.has(item.report.reportId) ? (
                                    <p className="muted">这个岗位当前已经没有 hard blocker，但你已经完成最新 UserFeedback，因此不重复占用下一投递判断。</p>
                                  ) : (
                                    <p className="muted">这个岗位当前已经没有 hard blocker，并且还没有最新 UserFeedback；它已经形成一个新的投递判断机会。</p>
                                  )
                                ) : (
                                  <p className="muted">当前 blocker / feedback 事实不完整，因此这里不把 provenance 直接升级成投递判断机会。</p>
                                )}
                              </div>
                            ) : (
                              <p className="muted">现有 MatchImprovement 没有提供足够精确的其他新增 Evidence → Requirement provenance，因此这里保持 unknown，不猜测是哪条改动带来了改善。</p>
                            )}
                          </li>
                        ))}
                      </ul>
                      {nextUnattributedEvidenceApplyReport ? (
                        <div className="actions">
                          <Link className="button" href={`/jobs/${nextUnattributedEvidenceApplyReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}${unattributedEvidenceOpportunityQuery}${previousEvidenceAttributionQuery}`}>
                            下一步：判断 {jobLabel(nextUnattributedEvidenceApplyReport.jobId)}
                          </Link>
                          <span className="muted">按 current Ranking 顺序选择第一个由其他真实 Evidence 解锁、且尚未完成 UserFeedback 的岗位。</span>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {unverifiablePreviousEvidenceQueueResults.length > 0 ? (
                    <p className="muted">“暂无法验证”只表示缺少可比较的前后 MatchReport 或当前事实读取不完整；它与“改善但无法归因”是不同状态，这里不会把未知结果当成未改善。</p>
                  ) : null}
                </div>
              ) : null}
              <h3>这次补证据后，本批哪些岗位改善了</h3>
              {improvedBatchJobs.length > 0 ? (
                <ul>
                  {improvedBatchJobs.map(({report, improvement}) => {
                    const resolvedRequirementIds = new Set(improvement.resolvedRequirementIds);
                    const resolvingEvidence = improvement.newlySupportingEvidence.flatMap((evidence) => {
                      const supportingRequirements = evidence.supportingRequirements.filter((requirement) =>
                        resolvedRequirementIds.has(requirement.requirementId),
                      );
                      return supportingRequirements.length > 0 ? [{evidence, supportingRequirements}] : [];
                    });
                    return (
                      <li key={report.reportId}>
                        <strong>{jobLabel(report.jobId)}</strong>：
                        {improvement.resolvedRequirementIds.length > 0
                          ? `少了 ${improvement.resolvedRequirementIds.length} 条硬条件缺口`
                          : "硬条件缺口数量未减少"}
                        {improvement.previousRecommendation !== improvement.currentRecommendation
                          ? `，推荐结果从 ${improvement.previousRecommendation ?? "无"} 变为 ${improvement.currentRecommendation ?? "无"}`
                          : ""}。
                        {blockerSummaryResult.status === "fulfilled" && blockerSummaryResult.value ? (() => {
                          const currentBlocker = blockerByJobId.get(report.jobId);
                          const nextRequirement = currentBlocker?.requirements[0] ?? null;
                          const latestFeedback = latestFeedbackByReportId.get(report.reportId);
                          return currentBlocker ? (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>
                              {nextRequirement
                                ? `虽然已经改善，但当前仍有 ${currentBlocker.missingRequirementCount} 条硬条件缺口；下一条先看“${nextRequirement.originalText}”。`
                                : `虽然已经改善，但仍有 ${currentBlocker.missingRequirementCount} 条硬条件缺口；当前 Requirement 事实无法解析出具体原文，因此这里不猜测下一项。`}
                            </div>
                          ) : latestFeedback?.decision === "rejected" ? (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>当前 Match blocker 事实里已没有硬条件缺口，但你已经明确标记为“不考虑”，因此这里不会继续推动投递，也不会再要求为它补证据。
                            </div>
                          ) : (
                            <div className="notice">
                              <strong>这个岗位现在还差什么：</strong>当前 Match blocker 事实里已没有硬条件缺口，可以停止机械补证据，转向投递判断。
                              <div className="detail-section">
                                <strong>现在为什么值得进入投递判断：</strong>
                                <ul>
                                  <li>当前 Ranking 建议：{matchRecommendationLabels[report.recommendation]}。</li>
                                  <li>当前 MatchReport 依据：{report.summary || matchRecommendationDescriptions[report.recommendation]}</li>
                                  <li>可追溯到 {report.evidenceLinks.length} 条 Requirement → Evidence 关联。</li>
                                  <li>你的当前判断：{feedbackDecisionLabel(latestFeedback?.decision)}。</li>
                                </ul>
                                <p className="muted">这只是基于当前 MatchReport、hard blocker 与你的反馈做的决策摘要，不代表系统替你决定投递。</p>
                              </div>
                              <div className="actions">
                                <Link className="button" href={`/jobs/${report.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>查看完整依据并进入投递判断</Link>
                              </div>
                            </div>
                          );
                        })() : (
                          <p className="muted">当前无法可靠读取这个岗位最新的 hard blocker，因此这里不判断它是否已经没有硬缺口。</p>
                        )}
                        {resolvingEvidence.length > 0 ? (
                          <ul>
                            {resolvingEvidence.slice(0, 3).map(({evidence, supportingRequirements}) => (
                              <li key={`${report.reportId}-${evidence.evidenceId}`}>
                                新进入匹配依据的真实经历：<strong>{evidence.summary}</strong>
                                <ul>
                                  {supportingRequirements.slice(0, 3).map((requirement) => (
                                    <li key={`${evidence.evidenceId}-${requirement.requirementId}`}>
                                      已支撑岗位要求：{requirement.originalText}
                                    </li>
                                  ))}
                                </ul>
                              </li>
                            ))}
                          </ul>
                        ) : improvement.resolvedRequirementIds.length > 0 ? (
                          <p className="muted">这次能确认硬缺口减少，但现有 provenance 没有精确指出是哪条新增 Evidence 直接支撑了这些已解决要求，因此这里不做猜测。</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="notice">当前还没有可确认的批次改善。只有存在同一岗位、同一 Requirement 事实集且 Profile 版本不同的前后 MatchReport 时，系统才会把变化归因给这次资料更新。</p>
              )}
              {resolvedBatchRequirementIds.size > 0 ? (
                batchEvidenceAction ? (
                  <p className="notice">
                    这次补充的 Evidence 已经解决 {resolvedBatchRequirementIds.size} 条硬要求；这些已解决 Requirement 不会继续驱动下一证据行动。下面的下一步只来自当前仍未解决的 blocker。
                  </p>
                ) : batchEvidenceActionStaleAfterImprovement ? (
                  <p className="notice">
                    这次已经有硬要求被解决，但当前 blocker 汇总仍包含已解决 Requirement。为避免重复让你补同一项证据，本页暂不生成下一证据行动，请刷新后再看最新事实。
                  </p>
                ) : (
                  <p className="notice">
                    这次补充的 Evidence 已经解决 {resolvedBatchRequirementIds.size} 条硬要求；当前这批岗位没有新的、可可靠确认的下一证据行动。
                  </p>
                )
              ) : null}
              <p className="muted">这里只比较已经存在的 immutable MatchReport，不会在打开页面时重新匹配或调用 Provider。</p>
            </section>
          ) : null}

          {matchedReports.length > 0 ? (
            <section className="detail-section">
              <h3>这批岗位当前的匹配结果</h3>
              <p className="muted">按当前 Ranking 顺序展示，只读取已经存在的 MatchReport；这里不会重新匹配。</p>
              {feedbackAvailable && feedbackDecisionCounts ? (
                <>
                  <p className="muted">已反馈 {feedbackCoveredCount}/{matchedCount}。你可以直接在这批结果里记录真实判断。</p>
                  <div className="summary-grid">
                    <div className="summary-card"><span>感兴趣</span><strong>{feedbackDecisionCounts.interested}</strong></div>
                    <div className="summary-card"><span>再看看</span><strong>{feedbackDecisionCounts.maybe}</strong></div>
                    <div className="summary-card"><span>不考虑</span><strong>{feedbackDecisionCounts.rejected}</strong></div>
                    <div className="summary-card"><span>尚未判断</span><strong>{feedbackDecisionCounts.pending}</strong></div>
                  </div>
                  {feedbackQueueAvailable ? (
                    <>
                      <h4>这批岗位现在还剩哪些待办</h4>
                      <div className="summary-grid">
                        <div className="summary-card"><span>可直接做投递判断</span><strong>{pendingClearedReports.length}</strong></div>
                        <div className="summary-card"><span>仍需补真实证据</span><strong>{consideredBlockedReports.length}</strong></div>
                        <div className="summary-card"><span>当前已完成处理</span><strong>{completedDecisionReports.length}</strong></div>
                      </div>
                      <p className="muted">“仍需补真实证据”会保留已标记为感兴趣/再看看的岗位；只有明确“不考虑”的岗位才退出后续 Evidence 待办。</p>
                    </>
                  ) : null}
                  {feedbackDecisionCounts.pending === 0 ? (
                    <p className="notice">这批已有 MatchReport 的岗位都已经记录了投递判断；你可以继续处理 Evidence、投递准备或下一批岗位。</p>
                  ) : !feedbackQueueAvailable ? (
                    <p className="notice">还有 {feedbackDecisionCounts.pending} 个岗位尚未判断，但当前 hard blocker 状态暂时无法可靠读取，因此这里不猜测哪个岗位应该先投、哪个应该先补证据。</p>
                  ) : nextApplyDecisionReport ? (
                    <div className="notice">
                      <strong>下一岗位：</strong>{jobLabel(nextApplyDecisionReport.jobId)} 当前没有 hard blocker，先完成它的投递判断最省步骤。
                      <div className="actions">
                        <Link className="button" href={`/jobs/${nextApplyDecisionReport.jobId}/prepare?returnImport=${encodeURIComponent(id)}`}>
                          先完成这个岗位的投递判断
                        </Link>
                      </div>
                      {pendingBlockedReports.length > 0 ? (
                        <p className="muted">另外还有 {pendingBlockedReports.length} 个尚未判断岗位仍有 hard blocker；它们继续留在 Evidence Loop，不会被误报成可直接投递。</p>
                      ) : null}
                    </div>
                  ) : batchEvidenceAction && batchEvidenceProfileHref ? (
                    <div className="notice">
                      还差 {feedbackDecisionCounts.pending} 个岗位完成投递判断，但这些岗位当前都有 hard blocker。先处理本批最高价值的 Evidence 行动，再 Re-match 后继续判断。
                      <div className="actions">
                        <Link className="button" href={batchEvidenceProfileHref}>先处理下一项真实证据</Link>
                      </div>
                    </div>
                  ) : (
                    <p className="notice">还有 {feedbackDecisionCounts.pending} 个岗位尚未判断，且当前仍有 hard blocker；但本页暂时无法可靠生成下一 Evidence 行动，因此先不替你猜下一步。</p>
                  )}
                </>
              ) : (
                <p className="notice">当前反馈状态暂时读取失败。匹配结果仍可查看，但这里暂不开放反馈，避免覆盖未知状态。</p>
              )}
              <div className="recommendation-grid">
                {matchedReports.map((report, index) => (
                  <article
                    className={`match-recommendation-card ${matchRecommendationClasses[report.recommendation]}`}
                    id={`feedback-${report.reportId}`}
                    key={report.reportId}
                  >
                    <p className="eyebrow">第 {index + 1} 位</p>
                    <h3><Link href={`/jobs/${report.jobId}`}>{jobLabel(report.jobId)}</Link></h3>
                    <div className="actions">
                      <span className={`tag ${matchRecommendationClasses[report.recommendation]}`}>
                        {matchRecommendationLabels[report.recommendation]}
                      </span>
                      <span className="tag">有依据要求 {report.evidenceLinks.length} 条</span>
                      {feedbackAvailable ? (
                        <span className="tag">投递判断：{feedbackDecisionShortLabel(latestFeedbackByReportId.get(report.reportId)?.decision)}</span>
                      ) : null}
                      {feedbackQueueAvailable ? (() => {
                        const decision = latestFeedbackByReportId.get(report.reportId)?.decision;
                        const blocked = blockerByJobId.has(report.jobId);
                        const nextStep = decision === "rejected"
                          ? "已退出待办"
                          : blocked
                            ? "先补真实证据"
                            : decision
                              ? "当前判断已记录"
                              : "做投递判断";
                        return (
                          <>
                            <span className="tag">下一步：{nextStep}</span>
                            {batchEvidenceQueueTargetJobIds.has(report.jobId) ? (
                              <span className="tag">当前证据行动会影响</span>
                            ) : null}
                          </>
                        );
                      })() : null}
                    </div>
                    <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p>
                    {feedbackAvailable ? (() => {
                      const latestFeedback = latestFeedbackByReportId.get(report.reportId);
                      return (
                        <RecommendationFeedback
                          matchReportId={report.reportId}
                          jobId={report.jobId}
                          initialDecision={latestFeedback?.decision ?? null}
                          initialReasons={latestFeedback?.reasons ?? []}
                          initialNote={latestFeedback?.note ?? null}
                        />
                      );
                    })() : null}
                  </article>
                ))}
              </div>
              {batchEvidenceAction && batchEvidenceProfileHref ? (
                <section className="detail-section">
                  <h3>这批岗位下一项最值得核实的证据</h3>
                  {showImprovement && resolvedBatchRequirementIds.size > 0 ? (
                    <div className="notice">
                      <strong>为什么下一步是这一项：</strong>
                      刚补的真实 Evidence 已解决 {resolvedBatchRequirementIds.size} 条硬要求
                      {improvedBatchJobs.length > 0
                        ? `，并让 ${improvedBatchJobs.slice(0, 3).map(({report}) => jobLabel(report.jobId)).join("、")}${improvedBatchJobs.length > 3 ? ` 等 ${improvedBatchJobs.length} 个岗位` : ""} 出现可验证改善`
                        : ""}。
                      这些要求已经从候选行动中排除；当前仍未解决、且影响仍在考虑岗位最多的是下面这一项，所以继续优先核实它。
                    </div>
                  ) : null}
                  <p>
                    {batchEvidenceAction.normalizedCapability
                      ? `先核实“${batchEvidenceAction.normalizedCapability}”相关的真实经历。`
                      : `先核实一项 ${batchEvidenceAction.requirementType} 类型的真实经历。`}
                    当前仍影响这批中 {batchEvidenceConsideredJobCount} 个你没有明确标记为“不考虑”的岗位，共对应 {batchEvidenceAction.missingRequirementCount} 条硬条件缺口。
                  </p>
                  {batchEvidenceQueueTargets.length > 0 ? (
                    <div className="notice">
                      <strong>这项证据对应当前待办队列中的 {batchEvidenceQueueTargets.length} 个岗位。</strong>
                      <p className="muted">这些岗位都仍有 hard blocker，且没有被你明确标记为“不考虑”；完成真实 Evidence 核实后，优先回看它们的 Re-match 结果。</p>
                    </div>
                  ) : null}
                  {batchEvidenceImpactTargets.length > 0 ? (
                    <ul>
                      {batchEvidenceImpactTargets.slice(0, 3).map((target) => (
                        <li key={target.jobId}>
                          <strong>{jobLabel(target.jobId)}</strong>
                          <ul>
                            {target.requirementTexts.map((requirementText) => (
                              <li key={`${target.jobId}-${requirementText}`}>{requirementText}</li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="muted">
                    这里只按当前 blocker 与你的真实反馈排序；明确 rejected 的岗位不会继续驱动补证据。核实并保存真实经历后，最终是否改善仍以 Re-match 为准。
                  </p>
                  <div className="actions">
                    <Link className="button" href={batchEvidenceProfileHref}>去核实这项真实经历</Link>
                  </div>
                </section>
              ) : feedbackAvailable && blockerSummaryResult.status === "fulfilled" ? null : (
                <p className="notice">
                  当前无法可靠读取反馈或硬条件缺口，因此这里不生成下一证据建议，避免把未知状态当成事实。
                </p>
              )}
              <div className="actions">
                <Link className="button" href="/recommendations">查看全部优先投递</Link>
              </div>
            </section>
          ) : null}

          {requirementBlockedJobs.length > 0 ? (
            <section className="detail-section">
              <h3>还需处理岗位要求</h3>
              <p className="muted">先看具体阻塞原因，再决定是否进入该岗位处理；这里不会自动发起分析。</p>
              <ul>
                {requirementBlockedJobs.map((jobId) => {
                  const readiness = readinessByJobId.get(jobId);
                  return (
                    <li key={jobId} style={{marginBottom: "0.85rem"}}>
                      <Link href={`/jobs/${jobId}`}><strong>{jobLabel(jobId)}</strong></Link>
                      {readiness && readiness.blockers.length > 0 ? (
                        <ul>
                          {readiness.blockers.slice(0, 2).map((blocker) => (
                            <li key={`${jobId}-${blocker.code}`}>{blocker.message}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">当前没有可展示的具体阻塞原因，请进入岗位查看最新状态。</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {matchReadyJobs.length > 0 ? (
            <section className="detail-section" id="batch-match">
              <h3>Requirement 已准备、等待匹配</h3>
              <ul>
                {matchReadyJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
              <ImportBatchMatch jobIds={matchReadyJobs} importId={id} />
            </section>
          ) : null}

          {unknownReadinessJobs.length > 0 ? (
            <section className="detail-section">
              <h3>暂时无法确认的岗位</h3>
              <p className="muted">这些岗位的 Requirement 状态读取失败，因此不会被误报为“尚未准备”。</p>
              <ul>
                {unknownReadinessJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="actions">
            {matchedCount > 0 || matchReadyCount > 0 ? (
              <Link className="button" href="/recommendations">查看优先投递与继续匹配</Link>
            ) : null}
            {requirementBlockedCount > 0 ? (
              <Link className="button-ghost" href="/jobs">查看全部岗位</Link>
            ) : null}
          </div>
          <p className="muted">
            “要求已准备，可进入匹配”表示这批岗位已经通过当前 Match Input Readiness，不代表已经生成 MatchReport；真正的匹配仍必须由你显式点击发起。
          </p>
        </section>
      ) : null}

      <section className="detail-grid">
        <article className="detail-card">
          <h2>逐条处理结果</h2>
          {detail.items.length === 0 ? (
            <p className="notice">本批次没有最终 Job 输入项，可能只包含候选诊断数据。</p>
          ) : (
            <div style={{overflowX: "auto"}}>
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>结果</th>
                    <th>岗位</th>
                    <th>错误</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((item) => (
                    <tr key={item.inputIndex}>
                      <td>{item.inputIndex}</td>
                      <td><ImportOutcomePill outcome={item.outcome} /></td>
                      <td>
                        {item.jobId ? (
                          <Link href={`/jobs/${item.jobId}`}>查看岗位</Link>
                        ) : "—"}
                      </td>
                      <td>{item.errorMessage || item.errorCode || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {detail.errors.length > 0 ? (
            <section className="detail-section">
              <h2>没有成功添加的原因</h2>
              {detail.errors.map((error) => (
                <div className="inline-error" key={`${error.index}-${error.code}`}>
                  <strong>第 {error.index} 条 · {error.code}</strong>
                  <p>{error.message}</p>
                </div>
              ))}
            </section>
          ) : null}
        </article>

        <aside className="detail-card">
          <h2>这批数据</h2>
          <div className="meta-list">
            <div><span className="meta-label">插件版本</span><strong>{detail.collectorVersion || detail.sourceVersion}</strong></div>
            <div><span className="meta-label">采集时间</span><strong>{formatDateTime(detail.collectedAt)}</strong></div>
            <div><span className="meta-label">添加时间</span><strong>{formatDateTime(detail.createdAt)}</strong></div>
          </div>

          <details className="technical-details">
            <summary>查看技术详情</summary>
            <p className="code">Import ID：{detail.importId}</p>
            <h3>候选数据统计</h3>
            <pre className="code notice">{JSON.stringify(detail.candidateSummary, null, 2)}</pre>
            <h3>采集时的筛选信息</h3>
            <pre className="code notice">{JSON.stringify(detail.searchIntentSnapshot, null, 2)}</pre>
          </details>

          <div className="actions">
            <Link className="button" href="/jobs">查看我的岗位</Link>
            <Link className="button-ghost" href="/import">继续添加岗位</Link>
          </div>
        </aside>
      </section>
    </>
  );
}
