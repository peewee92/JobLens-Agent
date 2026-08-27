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
  const afterProfileSaveHref = requestedNext === "/recommendations" ? "/recommendations" : null;
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

      <ProfileEditor
        initialProfile={profile}
        initialIntent={intent}
        afterProfileSaveHref={afterProfileSaveHref}
        focusEvidenceType={focusEvidenceType}
        focusRequirementType={focusRequirementType}
      />
    </>
  );
}
