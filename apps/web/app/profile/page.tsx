import {ProfileEditor} from "@/components/profile-editor";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchCareerContextReleaseReadiness,
  fetchCurrentProfile,
  fetchCurrentSearchIntent,
} from "@/lib/backend";
import {
  careerContextReleaseBlockerLabels,
  careerContextReleaseLabel,
} from "@/lib/career-context";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
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
        ? caught.message
        : "读取职业画像时发生未知错误。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">Career Context</p>
          <h1>职业画像与求职意向</h1>
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
        ? caught.message
        : "读取个人侧 Match 输入门禁时发生未知错误。";
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Career Context</p>
        <h1>确认事实，再定义你想找什么</h1>
        <p className="lede">
          Profile 只保存你确认过的事实。每个技能必须引用 Evidence；SearchIntent
          独立记录硬约束与软偏好。每次保存都会生成新版本，不覆盖历史。
        </p>
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>未来 Match 的个人侧事实门禁</h2>
            <p className="muted">
              这里只验证你显式确认的最新 Profile 与 SearchIntent，不把简历提案或
              Profile Eval 结果自动写成用户事实。
            </p>
          </div>
        </div>

        {releaseReadinessError ? (
          <p className="inline-error">{releaseReadinessError}</p>
        ) : null}

        {releaseReadiness ? (
          <div
            className={`review-result ${
              releaseReadiness.releaseEligible
                ? "review-accepted"
                : "review-rejected"
            }`}
          >
            <strong>{careerContextReleaseLabel(releaseReadiness)}</strong>
            {releaseReadiness.releaseEligible ? (
              <>
                <p>
                  当前两个版本均由用户显式确认，且 Profile 的 Skill→Evidence
                  引用和 SearchIntent 目标岗位完整。未来 Match 必须记录实际使用的版本号。
                </p>
                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card">
                    <span>Profile 版本</span>
                    <strong>{releaseReadiness.profileVersion}</strong>
                  </div>
                  <div className="summary-card">
                    <span>Evidence / Skills</span>
                    <strong>
                      {releaseReadiness.profileEvidenceCount} / {releaseReadiness.profileSkillCount}
                    </strong>
                  </div>
                  <div className="summary-card">
                    <span>SearchIntent 版本</span>
                    <strong>{releaseReadiness.searchIntentVersion}</strong>
                  </div>
                  <div className="summary-card">
                    <span>目标岗位</span>
                    <strong>{releaseReadiness.searchIntentTargetRoleCount}</strong>
                  </div>
                </div>
                <p className="code">
                  Profile：{releaseReadiness.profileId} · SearchIntent：
                  {releaseReadiness.searchIntentId}
                </p>
              </>
            ) : (
              <>
                <p>
                  先修复以下确认态事实，再允许未来 Match 消费；页面不会替你生成或猜测缺失数据。
                </p>
                <ul>
                  {releaseReadiness.blockers.map((blocker) => (
                    <li key={blocker.code}>
                      {careerContextReleaseBlockerLabels[blocker.code] ?? blocker.message}
                      <span className="code"> · {blocker.code}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="muted">
              本查询副作用：DB writes {releaseReadiness.dbWrites} · Provider calls{" "}
              {releaseReadiness.providerCalls} · Trace runs {releaseReadiness.traceRunsCreated}
            </p>
          </div>
        ) : null}
      </section>

      <ProfileEditor initialProfile={profile} initialIntent={intent} />
    </>
  );
}
