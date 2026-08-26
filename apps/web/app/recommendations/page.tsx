import Link from "next/link";

import {RecommendationFeedback} from "@/components/recommendation-feedback";
import {RecommendationRefresh} from "@/components/recommendation-refresh";
import {RecommendationRequirementAnalysis} from "@/components/recommendation-requirement-analysis";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchJobPage,
  fetchMatchBlockerSummary,
  fetchMatchRanking,
  fetchMatchReviewReadiness,
  fetchRecommendationCoverage,
  fetchUserFeedbackHistory,
} from "@/lib/backend";
import {formatSalary} from "@/lib/format";
import {
  matchRecommendationClasses,
  matchRecommendationDescriptions,
  matchRecommendationLabels,
} from "@/lib/match-report";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function RecommendationsPage() {
  let jobs;
  try {
    jobs = await fetchJobPage(new URLSearchParams({limit: "50", offset: "0"}));
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位，请稍后重试。")
        : "暂时无法读取岗位，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
        </section>
        <ServiceError message={message} />
      </>
    );
  }

  if (jobs.items.length === 0) {
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
          <p className="lede">先加入真实岗位，JobLens 才能基于你的真实经历做有依据的选择。</p>
        </section>
        <section className="empty-state">
          <h2>还没有岗位可以比较</h2>
          <p>先从浏览器插件或导入页添加一批你真正考虑的岗位。</p>
          <Link className="button" href="/import">添加岗位</Link>
        </section>
      </>
    );
  }

  let ranking;
  try {
    ranking = await fetchMatchRanking(
      jobs.items.map((job) => job.id),
      {includeBlocked: true, topN: 50},
    );
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法生成岗位优先级，请稍后重试。")
        : "暂时无法生成岗位优先级，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">优先投递</p>
          <h1>哪些岗位最值得我先投？</h1>
          <p className="lede">这里只使用已经生成并保存的完整匹配结果，不会为了凑排名临时编造依据。</p>
        </section>
        <ServiceError message={message} />
        <div className="actions">
          <Link className="button-secondary" href="/jobs">查看岗位</Link>
        </div>
      </>
    );
  }

  const jobById = new Map(jobs.items.map((job) => [job.id, job]));
  const availableReports = ranking.items
    .map((report) => ({report, job: jobById.get(report.jobId)}))
    .filter((item) => item.job !== undefined);
  const rankedItems = availableReports
    .filter(({report}) => report.recommendation !== "blocked")
    .slice(0, 5)
    .map((item, index) => ({...item, rank: index + 1}));
  const blockedItems = availableReports
    .filter(({report}) => report.recommendation === "blocked")
    .slice(0, 5);
  let blockerSummary = null;
  try {
    blockerSummary = await fetchMatchBlockerSummary(jobs.items.map((job) => job.id));
  } catch {
    // Ranking remains usable even if this secondary explanation read model is unavailable.
  }

  let reviewableJobIds: string[] = [];
  try {
    const readiness = await fetchMatchReviewReadiness();
    reviewableJobIds = readiness.reviewableJobIds;
  } catch {
    // Existing ranking remains readable even when the refresh readiness check is unavailable.
  }

  let coverage = null;
  try {
    coverage = await fetchRecommendationCoverage();
  } catch {
    // Current recommendations remain usable when the read-only coverage planner is unavailable.
  }

  const feedbackEntries = await Promise.all(
    availableReports.map(async ({report}) => {
      try {
        const history = await fetchUserFeedbackHistory(report.reportId);
        const latest = history.feedback.at(-1) ?? null;
        return [report.reportId, latest?.decision ?? null] as const;
      } catch {
        return [report.reportId, null] as const;
      }
    }),
  );
  const feedbackByReportId = new Map(feedbackEntries);
  const feedbackCompletedCount = feedbackEntries.filter(([, decision]) => decision !== null).length;
  const feedbackRemainingCount = Math.max(availableReports.length - feedbackCompletedCount, 0);

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">优先投递</p>
        <h1>哪些岗位最值得我先投？</h1>
        <p className="lede">
          基于你确认过的经历、当前求职偏好和已经生成的完整匹配结果排序。这里只比较有可追溯依据的岗位，不把“匹配分数”当成功概率。
        </p>
      </section>

      <div className="result-bar">
        <span>岗位池 {jobs.total} 个 · 本轮比较前 {jobs.items.length} 个</span>
        <span>已有完整匹配 {availableReports.length} 个 · 当前优先候选 {rankedItems.length} 个</span>
        <span>已反馈 {feedbackCompletedCount}/{availableReports.length}</span>
      </div>

      {availableReports.length > 0 && feedbackRemainingCount > 0 ? (
        <section className="notice">
          <strong>还差 {feedbackRemainingCount} 个岗位需要你的真实判断</strong>
          <p>你的反馈会帮助 JobLens 判断推荐是否符合真实求职选择。即使系统当前不建议优先投，也可以记录“感兴趣 / 再看看 / 不考虑”。</p>
        </section>
      ) : null}

      {availableReports.length === 0 ? (
        <section className="empty-state">
          <h2>还没有当前资料版本的完整匹配结果</h2>
          <p>如果你刚更新过职业背景，旧 MatchReport 会自动失效；可以直接重新计算当前输入已准备好的岗位，不需要逐个打开岗位。</p>
          <div className="actions">
            <Link className="button-secondary" href="/jobs">查看岗位</Link>
            <Link className="button-ghost" href="/profile?next=/recommendations#profile-evidence">检查我的背景</Link>
          </div>
        </section>
      ) : null}

      <RecommendationRefresh jobIds={reviewableJobIds} />

      {rankedItems.length > 0 ? (
        <section className="job-list" aria-label="优先投递岗位">
          {rankedItems.map(({report, job, rank}) => {
            if (!job) return null;
            return (
              <article className="job-card" key={report.reportId}>
                <div className="job-card-header">
                  <div>
                    <p className="eyebrow">第 {rank} 优先</p>
                    <h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2>
                    <p className="company">{job.company}</p>
                  </div>
                  <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
                </div>

                <div className="tags">
                  <span className={`tag ${matchRecommendationClasses[report.recommendation]}`}>
                    {matchRecommendationLabels[report.recommendation]}
                  </span>
                  {job.area ? <span className="tag">{job.area}</span> : null}
                  <RemoteStatusPill status={job.remoteStatus} />
                  <span className="tag">有依据要求 {report.evidenceLinks.length} 条</span>
                </div>

                <p>{report.summary || matchRecommendationDescriptions[report.recommendation]}</p>
                {report.missingRequirementIds.length > 0 ? (
                  <p className="muted">仍有 {report.missingRequirementIds.length} 条要求缺少足够证据，需要投递前重点确认。</p>
                ) : null}

                <div className="actions">
                  <Link className="button-secondary" href={`/jobs/${job.id}`}>查看为什么 →</Link>
                </div>
                <RecommendationFeedback
                  matchReportId={report.reportId}
                  jobId={job.id}
                  initialDecision={feedbackByReportId.get(report.reportId) ?? null}
                />
              </article>
            );
          })}
        </section>
      ) : availableReports.length > 0 ? (
        <section className="notice">
          <strong>当前没有值得优先投的已分析岗位</strong>
          <p>现有完整匹配结果都触发了明确硬条件缺口。下面仍会列出这些岗位和原因，避免把“没有优先候选”误解成系统没有结果。</p>
        </section>
      ) : null}

      {blockerSummary && blockerSummary.categories.length > 0 ? (
        <section className="detail-card">
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">先补事实，再重算</p>
              <h2>哪些资料最可能解锁更多岗位判断？</h2>
              <p className="muted">
                这里只表示“当前 Profile 没有足够证据支撑这些硬条件”，不等于断言你没有对应能力或经历。
              </p>
            </div>
            <Link className="button-secondary" href="/profile?next=/recommendations#profile-evidence">补充我的真实经历</Link>
          </div>
          <div className="readiness-blocker-list">
            {blockerSummary.categories.slice(0, 3).map((category) => (
              <div className="readiness-blocker-item" key={category.requirementType}>
                <strong>
                  {category.requirementType === "education"
                    ? "教育经历证据"
                    : category.requirementType === "skill"
                      ? "技能证据"
                      : category.requirementType === "experience"
                        ? "专项经验依据"
                        : category.requirementType === "domain"
                          ? "行业领域依据"
                          : category.requirementType === "responsibility"
                            ? "职责经历依据"
                            : "其他硬条件依据"}
                </strong>
                <p>
                  影响 {category.affectedJobCount} 个已分析岗位，共 {category.missingRequirementCount} 条当前无法证实的硬条件。
                </p>
                {category.examples.length > 0 ? (
                  <ul>
                    {category.examples.map((example) => <li key={example}>{example}</li>)}
                  </ul>
                ) : null}
                {category.requirementType === "education" ? (
                  <div className="actions">
                    <Link
                      className="button-secondary"
                      href="/profile?next=/recommendations&focus=education#profile-evidence"
                    >
                      补教育经历 →
                    </Link>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          {blockerSummary.unresolvedMissingRequirementIds.length > 0 ? (
            <p className="inline-error">
              有 {blockerSummary.unresolvedMissingRequirementIds.length} 条历史缺口已无法和当前岗位要求对应，请重新生成这些岗位的完整匹配建议后再判断。
            </p>
          ) : null}
        </section>
      ) : null}

      {coverage ? (
        <section className="detail-card">
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">扩大比较范围</p>
              <h2>下一批先分析哪些岗位？</h2>
              <p className="muted">
                JobLens 先找出还没进入完整匹配、但和你明确求职方向更接近的岗位。这里仅使用岗位标题、城市、薪资等明确偏好信号排序，不用 AI 猜一个隐藏匹配分数。
              </p>
            </div>
          </div>

          <div className="summary-grid eval-summary-grid">
            <div className="summary-card">
              <span>已有完整匹配</span>
              <strong>{coverage.currentReportCount}</strong>
            </div>
            <div className="summary-card">
              <span>已准备好，可直接重算</span>
              <strong>{coverage.matchReadyWithoutReportCount}</strong>
            </div>
            <div className="summary-card">
              <span>还需要岗位要求分析</span>
              <strong>{coverage.requirementAnalysisNeededCount}</strong>
            </div>
          </div>

          {coverage.matchReadyWithoutReportCount > 0 ? (
            <p className="notice">
              有 {coverage.matchReadyWithoutReportCount} 个岗位的事实输入已经准备好但还没有当前 MatchReport，可以用上面的“重新计算”继续扩充排名。
            </p>
          ) : null}

          {coverage.nextAnalysisCandidates.length > 0 ? (
            <>
              <RecommendationRequirementAnalysis
                jobIds={coverage.nextAnalysisCandidates.map((candidate) => candidate.jobId)}
              />
              <div className="job-list" aria-label="下一批岗位要求分析候选">
              {coverage.nextAnalysisCandidates.map((candidate, index) => (
                <article className="job-card" key={candidate.jobId}>
                  <div className="job-card-header">
                    <div>
                      <p className="eyebrow">建议第 {index + 1} 个分析</p>
                      <h3><Link href={`/jobs/${candidate.jobId}`}>{candidate.title}</Link></h3>
                      <p className="company">{candidate.company}</p>
                    </div>
                    <span className="salary">
                      {formatSalary(candidate.salaryMinK, candidate.salaryMaxK)}
                    </span>
                  </div>
                  <div className="tags">
                    {candidate.intentSignals.map((signal) => (
                      <span className="tag" key={signal}>{signal}</span>
                    ))}
                    {candidate.area && !candidate.intentSignals.some((signal) => signal.startsWith("目标城市：")) ? (
                      <span className="tag">{candidate.area}</span>
                    ) : null}
                  </div>
                  <p className="muted">
                    这个岗位当前缺的是可信的 JobRequirement 输入；先完成岗位要求分析，再进入 Eligibility、Match 和 Ranking。
                  </p>
                  <div className="actions">
                    <Link className="button-secondary" href={`/jobs/${candidate.jobId}`}>
                      查看并分析岗位要求 →
                    </Link>
                  </div>
                </article>
              ))}
              </div>
            </>
          ) : coverage.requirementAnalysisNeededCount > 0 ? (
            <p className="muted">目前没有能依据明确求职偏好排出优先级的待分析岗位，可以从岗位列表继续选择。</p>
          ) : (
            <p className="muted">当前前 {coverage.consideredJobCount} 个岗位里，没有新的岗位要求分析任务需要优先处理。</p>
          )}

          <details className="technical-details">
            <summary>查看覆盖率技术详情</summary>
            <p className="code">
              considered={coverage.consideredJobCount}/{coverage.totalJobCount} · profileBlocked={coverage.profileBlockedCount} · otherBlocked={coverage.otherBlockedCount}
            </p>
            <p className="code">
              dbWrites={coverage.dbWrites} · providerCalls={coverage.providerCalls} · traces={coverage.traceRunsCreated}
            </p>
          </details>
        </section>
      ) : null}

      {blockedItems.length > 0 ? (
        <section>
          <div className="section-heading">
            <p className="eyebrow">暂不优先</p>
            <h2>这些岗位当前有明确硬条件缺口</h2>
          </div>
          <div className="job-list" aria-label="当前不建议投递岗位">
            {blockedItems.map(({report, job}) => {
              if (!job) return null;
              return (
                <article className="job-card" key={report.reportId}>
                  <div className="job-card-header">
                    <div>
                      <h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2>
                      <p className="company">{job.company}</p>
                    </div>
                    <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
                  </div>
                  <div className="tags">
                    <span className={`tag ${matchRecommendationClasses.blocked}`}>
                      {matchRecommendationLabels.blocked}
                    </span>
                    {job.area ? <span className="tag">{job.area}</span> : null}
                    <span className="tag">明显缺失 {report.missingRequirementIds.length} 条</span>
                  </div>
                  <p>{report.summary || matchRecommendationDescriptions.blocked}</p>
                  <div className="actions">
                    <Link className="button-secondary" href={`/jobs/${job.id}`}>查看硬条件缺口 →</Link>
                  </div>
                  <RecommendationFeedback
                    matchReportId={report.reportId}
                    jobId={job.id}
                    initialDecision={feedbackByReportId.get(report.reportId) ?? null}
                  />
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="notice product-trust-note">
        <strong>排序依据是什么？</strong>
        <p>
          先看硬条件是否通过，再看已有经历对岗位要求的证据支撑，最后只在同一推荐等级里参考你的求职偏好。没有完整 MatchReport 的岗位不会被偷偷猜一个名次。
        </p>
      </section>
    </>
  );
}
