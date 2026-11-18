import {publicSession} from "@/lib/model-session";
import {redirect} from "next/navigation";
import {publicDemoEnabled} from "@/lib/public-demo";
import {EvidenceActionProgress} from "@/components/evidence-action-progress";
import {PageHeading} from "@/components/ui/patterns";
import {ProfileEditor} from "@/components/profile-editor";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  backendResponse,
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
import Link from "next/link";
import {gapScope, gapScopeHref} from "@/lib/gap-scope";
import {agentScopeFromProfile, agentScopeHref, jobDetailWithAgentScope} from "@/lib/agent-job-scope";

export const dynamic = "force-dynamic";

function AgentScopeReturn({scope}: {scope: {jobId: string; ids: string[]} | null}) {
  if (!scope) return null;
  return <section className="card stack-sm" aria-label="返回原分析范围">
    <p>你从岗位核对进入这里。保存资料或偏好后，原匹配报告可能不再适用；请返回岗位核对，再重新检查所选岗位。</p>
    <div className="button-row">
      <Link className="button-secondary" href={jobDetailWithAgentScope(scope.jobId, scope.ids)}>返回刚才的岗位</Link>
      <Link className="button-secondary" href={agentScopeHref(scope.ids)}>返回所选岗位分析</Link>
    </div>
  </section>;
}

function buildRecommendationReturnHref({
  focusJob,
  focusRequirement,
  focusRequirementId,
  focusCapability,
  focusRequirementText,
  focusImpactJobs,
  focusImpactRequirementIds,
  evidenceActionHistory,
  returnImport,
  returnPrepare,
  afterMatchJobs,
}: {
  focusJob: string | null;
  focusRequirement: string | null;
  focusRequirementId: string | null;
  focusCapability: string | null;
  focusRequirementText: string | null;
  focusImpactJobs: string | null;
  focusImpactRequirementIds: string | null;
  evidenceActionHistory: string | null;
  returnImport: string | null;
  returnPrepare: string | null;
  afterMatchJobs: string | null;
}): string {
  const query = new URLSearchParams();
  if (focusJob) query.set("focusJob", focusJob);
  if (focusRequirement) query.set("focusRequirement", focusRequirement);
  if (focusRequirementId) query.set("focusRequirementId", focusRequirementId);
  if (focusCapability) query.set("focusCapability", focusCapability);
  if (focusRequirementText) query.set("focusRequirementText", focusRequirementText);
  if (focusImpactJobs) query.set("focusImpactJobs", focusImpactJobs);
  if (focusImpactRequirementIds) query.set("focusImpactRequirementIds", focusImpactRequirementIds);
  if (evidenceActionHistory) query.set("evidenceActionHistory", evidenceActionHistory);
  if (returnImport) query.set("returnImport", returnImport);
  if (returnPrepare) query.set("returnPrepare", returnPrepare);
  if (afterMatchJobs) query.set("afterMatchJobs", afterMatchJobs);
  const queryString = query.toString();
  return queryString ? `/recommendations?${queryString}` : "/recommendations";
}

export default async function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  if ((await publicSession())?.mode === "byok") redirect("/my-analysis");
  if (publicDemoEnabled()) {
    try {
      const profile = await fetchCurrentProfile();
      return <section className="detail-card"><h1>合成样本背景</h1><p>这是两年工作经验、掌握 Python 的合成资料，不是真实职业经历。公开演示不接收私人简历或资料修改。</p>
        <ul>{profile?.evidence.map(item => <li key={item.id}>{item.summary}</li>)}</ul>
        <Link className="button" href="/agent">比较三个样本岗位</Link></section>;
    } catch {return <section className="error-panel"><h1>演示会话暂时不可用</h1><Link href="/demo">重新开始样本体验</Link></section>;}
  }
  const [params, localProfileModel] = await Promise.all([
    searchParams,
    process.env.JOBLENS_LOCAL_PRODUCT !== "1" ? null :
      backendResponse("/api/v1/local/profile-model/status")
        .then(async (response) => response.ok && (await response.json()).available === true)
        .catch(() => false),
  ]);
  const agentScope = agentScopeFromProfile(params.scopeFocusJobId, params.scopeJobId);
  const gapIds = gapScope(params.gapJobId);
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
  const requestedFocusImpactRequirementIds = Array.isArray(params.focusImpactRequirementIds)
    ? params.focusImpactRequirementIds[0]
    : params.focusImpactRequirementIds;
  const requestedEvidenceActionHistory = Array.isArray(params.evidenceActionHistory)
    ? params.evidenceActionHistory[0]
    : params.evidenceActionHistory;
  const requestedReturnImport = Array.isArray(params.returnImport) ? params.returnImport[0] : params.returnImport;
  const requestedReturnPrepare = Array.isArray(params.returnPrepare) ? params.returnPrepare[0] : params.returnPrepare;
  const requestedAfterMatchJobs = Array.isArray(params.afterMatchJobs) ? params.afterMatchJobs[0] : params.afterMatchJobs;
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
  const focusImpactRequirementIds = typeof requestedFocusImpactRequirementIds === "string"
    ? Array.from(new Set(
        requestedFocusImpactRequirementIds
          .split(",")
          .map((requirementId) => requirementId.trim())
          .filter((requirementId) => /^[A-Za-z0-9_-]{1,120}$/.test(requirementId)),
      )).slice(0, 20).join(",") || null
    : null;
  const evidenceActionHistory = typeof requestedEvidenceActionHistory === "string"
    ? requestedEvidenceActionHistory.split(",").map((item) => item.trim().slice(0, 160)).filter(Boolean).slice(-4).join(",") || null
    : null;
  const returnImport = typeof requestedReturnImport === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedReturnImport)
    ? requestedReturnImport
    : null;
  const returnPrepare = typeof requestedReturnPrepare === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(requestedReturnPrepare)
    ? requestedReturnPrepare
    : null;
  const afterMatchJobs = typeof requestedAfterMatchJobs === "string"
    ? Array.from(new Set(
        requestedAfterMatchJobs
          .split(",")
          .map((jobId) => jobId.trim())
          .filter((jobId) => /^[A-Za-z0-9_-]{1,120}$/.test(jobId)),
      )).slice(0, 20).join(",") || null
    : null;
  // Return to recommendations carrying the same focus so the recompute can prioritize that job.
  const afterProfileSaveHref = requestedNext === "/gaps" && gapIds.length ? gapScopeHref(gapIds) : requestedNext === "/recommendations"
    ? buildRecommendationReturnHref({
        focusJob: requestedFocusJob,
        focusRequirement: typeof requestedRequirementFocus === "string" ? requestedRequirementFocus : null,
        focusRequirementId,
        focusCapability,
        focusRequirementText,
        focusImpactJobs,
        focusImpactRequirementIds,
        evidenceActionHistory,
        returnImport,
        returnPrepare,
        afterMatchJobs,
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
        <AgentScopeReturn scope={agentScope} />
      {gapIds.length > 0 && <Link className="button-secondary" href={gapScopeHref(gapIds)}>返回原目标岗位差距</Link>}
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
      <PageHeading kicker="第 1 步 · 确认资料" title="我的背景和求职偏好"
        description="先写下你做过什么、想找什么岗位。只有你核对并保存的资料才会用于匹配。" />

      <AgentScopeReturn scope={agentScope} />
      {gapIds.length > 0 && <Link className="button-secondary" href={gapScopeHref(gapIds)}>返回原目标岗位差距</Link>}

      <details className="detail-card">
        <summary>查看匹配准备情况</summary>
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
      </details>

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
        localProfileModel={localProfileModel}
        initialProfile={profile}
        initialIntent={intent}
        readyNextHref={agentScope ? `${jobDetailWithAgentScope(agentScope.jobId, agentScope.ids)}#job-match` : "/import"}
        readyNextLabel={agentScope ? "继续分析刚才的岗位" : "去添加岗位"}
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
