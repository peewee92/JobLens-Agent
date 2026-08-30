import {EvidenceActionProgress} from "@/components/evidence-action-progress";
import {ProfileEditor} from "@/components/profile-editor";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchCareerContextReleaseReadiness,
  fetchCurrentProfile,
  fetchCurrentSearchIntent,
} from "@/lib/backend";
import {
  careerContextReleaseBlockerCopy,
  careerContextReleaseLabel,
} from "@/lib/career-context";
import type {RequirementType, SearchParams} from "@/lib/contracts";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

function buildRecommendationReturnHref({
  focusJob,
  focusRequirement,
  focusRequirementId,
  focusCapability,
  focusRequirementText,
  focusImpactJobs,
  evidenceActionHistory,
  returnImport,
}: {
  focusJob: string | null;
  focusRequirement: string | null;
  focusRequirementId: string | null;
  focusCapability: string | null;
  focusRequirementText: string | null;
  focusImpactJobs: string | null;
  evidenceActionHistory: string | null;
  returnImport: string | null;
}): string {
  const query = new URLSearchParams();
  if (focusJob) query.set("focusJob", focusJob);
  if (focusRequirement) query.set("focusRequirement", focusRequirement);
  if (focusRequirementId) query.set("focusRequirementId", focusRequirementId);
  if (focusCapability) query.set("focusCapability", focusCapability);
  if (focusRequirementText) query.set("focusRequirementText", focusRequirementText);
  if (focusImpactJobs) query.set("focusImpactJobs", focusImpactJobs);
  if (evidenceActionHistory) query.set("evidenceActionHistory", evidenceActionHistory);
  if (returnImport) query.set("returnImport", returnImport);
  const queryString = query.toString();
  return queryString ? `/recommendations?${queryString}` : "/recommendations";
}

export default async function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const requestedNext = Array.isArray(params.next) ? params.next[0] : params.next;
  const requestedFocus = Array.isArray(params.focus) ? params.focus[0] : params.focus;
  const requestedRequirementFocus = Array.isArray(params.focusRequirement)
    ? params.focusRequirement[0]
    : params.focusRequirement;
  const requestedFocusJob = Array.isArray(params.focusJob) ? params.focusJob[0] : params.focusJob ?? null;
  const requestedFocusRequirementId = Array.isArray(params.focusRequirementId)
    ? params.focusRequirementId[0]
    : params.focusRequirementId;
  const requestedFocusCapability = Array.isArray(params.focusCapability)
    ? params.focusCapability[0]
    : params.focusCapability;
  const requestedFocusRequirementText = Array.isArray(params.focusRequirementText)
    ? params.focusRequirementText[0]
    : params.focusRequirementText;
  const requestedFocusImpactJobs = Array.isArray(params.focusImpactJobs)
    ? params.focusImpactJobs[0]
    : params.focusImpactJobs;
  const requestedEvidenceActionHistory = Array.isArray(params.evidenceActionHistory)
    ? params.evidenceActionHistory[0]
    : params.evidenceActionHistory;
  const requestedReturnImport = Array.isArray(params.returnImport) ? params.returnImport[0] : params.returnImport;
  const focusRequirementId = typeof requestedFocusRequirementId === "string"
    ? requestedFocusRequirementId.trim().slice(0, 120) || null
    : null;
  const focusCapability = typeof requestedFocusCapability === "string"
    ? requestedFocusCapability.trim().slice(0, 120) || null
    : null;
  const focusRequirementText = typeof requestedFocusRequirementText === "string"
    ? requestedFocusRequirementText.trim().slice(0, 300) || null
    : null;
  const focusImpactJobs = typeof requestedFocusImpactJobs === "string"
    ? requestedFocusImpactJobs.split(",").map((jobId) => jobId.trim().slice(0, 120)).filter(Boolean).slice(0, 3).join(",") || null
    : null;
  const evidenceActionHistory = typeof requestedEvidenceActionHistory === "string"
    ? requestedEvidenceActionHistory.split(",").map((item) => item.trim().slice(0, 160)).filter(Boolean).slice(-4).join(",") || null
    : null;
  const returnImport = typeof requestedReturnImport === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedReturnImport)
    ? requestedReturnImport
    : null;
  // Return to recommendations carrying the same focus so the recompute can prioritize that job.
  const afterProfileSaveHref = requestedNext === "/recommendations"
    ? buildRecommendationReturnHref({
        focusJob: requestedFocusJob,
        focusRequirement: typeof requestedRequirementFocus === "string" ? requestedRequirementFocus : null,
        focusRequirementId,
        focusCapability,
        focusRequirementText,
        focusImpactJobs,
        evidenceActionHistory,
        returnImport,
      })
    : null;
  // The specific job the user is supplementing evidence for; it should be recomputed first on return.
  const recomputeJobId = requestedFocusJob;
  const focusEvidenceType = requestedFocus === "education" || requestedRequirementFocus === "education"
    ? "education"
    : null;
  const focusRequirementType: RequirementType | null = [
    "skill",
    "experience",
    "education",
    "responsibility",
    "domain",
    "constraint",
  ].includes(requestedRequirementFocus ?? "")
    ? requestedRequirementFocus as RequirementType
    : null;
  let profile;
  let intent;
  try {
    [profile, intent] = await Promise.all([
      fetchCurrentProfile(),
      fetchCurrentSearchIntent(),
    ]);
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取你的背景信息，请稍后重试。")
        : "暂时无法读取你的背景信息，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">我的背景</p>
          <h1>我的背景和求职偏好</h1>
        </section>
        <ServiceError message={message} />
      </>
    );
  }

  let releaseReadiness = null;
  let releaseReadinessError = "";
  try {
    releaseReadiness = await fetchCareerContextReleaseReadiness();
  } catch (caught) {
    releaseReadinessError =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法检查你的信息是否完整，请稍后重试。")
        : "暂时无法检查你的信息是否完整，请稍后重试。";
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">我的背景</p>
        <h1>我的背景和求职偏好</h1>
        <p className="lede">
          告诉 JobLens 你真实做过什么、会什么，以及你想找什么样的工作。AI 可以帮你从简历生成草稿，但只有你确认保存的信息才会用于岗位匹配。
        </p>
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>匹配准备情况</h2>
            <p className="muted">这里会告诉你还缺什么，不需要理解系统内部的版本或验证流程。</p>
          </div>
        </div>

        {releaseReadinessError ? (
          <p className="inline-error">{releaseReadinessError}</p>
        ) : null}

        {releaseReadiness ? (
          <div
            className={`review-result ${
              releaseReadiness.releaseEligible ? "review-accepted" : "review-pending"
            }`}
          >
            <strong>{careerContextReleaseLabel(releaseReadiness)}</strong>
            {releaseReadiness.releaseEligible ? (
              <>
                <p>职业背景和求职偏好都已确认。后续匹配只会使用这些你亲自确认过的信息。</p>
                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card">
                    <span>真实经历</span>
                    <strong>{releaseReadiness.profileEvidenceCount}</strong>
                  </div>
                  <div className="summary-card">
                    <span>已确认技能</span>
                    <strong>{releaseReadiness.profileSkillCount}</strong>
                  </div>
                  <div className="summary-card">
                    <span>目标岗位</span>
                    <strong>{releaseReadiness.searchIntentTargetRoleCount}</strong>
                  </div>
                </div>
              </>
            ) : (
              <>
                <p>把下面这些信息补齐后，后续岗位匹配才能使用这些内容。系统不会擅自猜测你的经历或偏好。</p>
                <div className="readiness-blocker-list">
                  {releaseReadiness.blockers.map((blocker) => {
                    const copy = careerContextReleaseBlockerCopy(blocker.code);
                    return (
                      <div className="readiness-blocker-item" key={blocker.code}>
                        <strong>{copy.title}</strong>
                        <p>{copy.description}</p>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            <details className="technical-details">
              <summary>查看技术详情</summary>
              <p className="code">
                Background：{releaseReadiness.profileId ?? "—"} v{releaseReadiness.profileVersion ?? "—"} · Preferences：{releaseReadiness.searchIntentId ?? "—"} v{releaseReadiness.searchIntentVersion ?? "—"}
              </p>
              <p className="code">
                dbWrites={releaseReadiness.dbWrites} · providerCalls={releaseReadiness.providerCalls} · traces={releaseReadiness.traceRunsCreated}
              </p>
              {releaseReadiness.blockers.length > 0 ? (
                <ul>
                  {releaseReadiness.blockers.map((blocker) => (
                    <li key={blocker.code} className="code">{blocker.code}</li>
                  ))}
                </ul>
              ) : null}
            </details>
          </div>
        ) : null}
      </section>

      {focusRequirementId ? (
        <EvidenceActionProgress
          requirementId={focusRequirementId}
          jobId={requestedFocusJob}
          capability={focusCapability}
          requirementText={focusRequirementText}
          stage="pending"
        />
      ) : null}

      <ProfileEditor
        initialProfile={profile}
        initialIntent={intent}
        afterProfileSaveHref={afterProfileSaveHref}
        focusEvidenceType={focusEvidenceType}
        focusRequirementType={focusRequirementType}
        focusJobId={requestedFocusJob}
        focusCapability={focusCapability}
        focusRequirementText={focusRequirementText}
      />
    </>
  );
}
