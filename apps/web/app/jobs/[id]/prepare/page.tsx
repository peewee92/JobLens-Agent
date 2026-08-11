import Link from "next/link";

import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchJobDetail, fetchJobPreparation} from "@/lib/backend";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function JobPreparationPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;

  try {
    const [job, preparation] = await Promise.all([
      fetchJobDetail(id),
      fetchJobPreparation(id),
    ]);

    return (
      <>
        <div className="actions" style={{marginBottom: 18}}>
          <Link className="button-ghost" href={`/jobs/${encodeURIComponent(id)}`}>
            ← 返回岗位详情
          </Link>
        </div>

        <section className="detail-card">
          <p className="eyebrow">投递与面试准备</p>
          <h1>{job.title}</h1>
          <p className="company">{job.company}</p>
          <p className="lede">
            这里只展示已确认职业事实与已放行岗位要求之间的确定性准备依据，不补写不存在的经历、成绩或指标。
          </p>

          {!preparation.factsUsable ? (
            <div className="review-result review-pending">
              <strong>当前还不能生成可信的岗位准备依据</strong>
              <p>前置事实门禁尚未全部通过。完成这些门禁后，本页才会展示简历、项目和面试准备事实。</p>
              {preparation.blockers.length > 0 ? (
                <ul>
                  {preparation.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                </ul>
              ) : null}
            </div>
          ) : (
            <div className="eligibility-groups">
              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>简历调整依据</h2>
                  <span>{preparation.resumeDelta?.highlights.length ?? 0} 项可突出</span>
                </div>
                {(preparation.resumeDelta?.highlights ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>已确认 Evidence：{item.evidenceIds.join("、")}</p>
                    <small className="muted-copy">Requirement：{item.requirementId}</small>
                  </article>
                ))}
                {(preparation.resumeDelta?.evidenceGaps ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>{item.status === "missing" ? "当前 Profile 中缺少该能力事实。" : "已有技能事实，但缺少已确认 Evidence。"}</p>
                    <small className="muted-copy">Requirement：{item.requirementId}</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>项目 / 经历排序</h2>
                  <span>{preparation.experiencePriority?.items.length ?? 0} 项</span>
                </div>
                {(preparation.experiencePriority?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.evidenceId}>
                    <strong>{item.evidenceId}</strong>
                    <p>匹配能力：{item.matchedCapabilities.join("、") || "无"}</p>
                    <small className="muted-copy">支撑 {item.requirementCount} 条 Requirement，其中 must-have {item.mustHaveCount} 条</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>项目讲述事实</h2>
                  <span>{preparation.storyFacts?.items.length ?? 0} 项</span>
                </div>
                {(preparation.storyFacts?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.evidenceId}>
                    <strong>{item.evidenceSummary}</strong>
                    <p>岗位要求：{item.supportingRequirementTexts.join("；")}</p>
                    <small className="muted-copy">这里只选择真实事实，不生成 STAR 成绩或指标。</small>
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>面试重点</h2>
                  <span>{preparation.interviewFacts?.items.length ?? 0} 项</span>
                </div>
                {(preparation.interviewFacts?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.requirementText}</strong>
                    <p>准备优先级：{item.preparationPriority} · Evidence 状态：{item.evidenceStatus}</p>
                    {item.evidenceSummaries.length > 0 ? <p>可用事实：{item.evidenceSummaries.join("；")}</p> : null}
                  </article>
                ))}
              </section>

              <section className="eligibility-group">
                <div className="eligibility-group-heading">
                  <h2>面试前补习清单</h2>
                  <span>{preparation.studyChecklist?.items.length ?? 0} 项</span>
                </div>
                {(preparation.studyChecklist?.items ?? []).map((item) => (
                  <article className="eligibility-result-card" key={item.requirementId}>
                    <strong>{item.capability}</strong>
                    <p>{item.requirementText}</p>
                    <p>补齐标准：{item.completionCriteria.join("；")}</p>
                  </article>
                ))}
              </section>
            </div>
          )}
        </section>
      </>
    );
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位准备信息，请稍后重试。")
        : "暂时无法读取岗位准备信息，请稍后重试。";
    return <ServiceError message={message} />;
  }
}
