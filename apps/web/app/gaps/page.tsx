import {TargetCohortGapPanel} from "@/components/target-cohort-gap-panel";

const SAFE_FACT_ID = /^[A-Za-z0-9_-]{1,120}$/;

type SearchParams = {
  jobId?: string | string[];
  from?: string;
};

export default async function GapPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const requestedJobIds = Array.isArray(params.jobId)
    ? params.jobId
    : params.jobId
      ? [params.jobId]
      : [];
  const initialJobIds = Array.from(new Set(requestedJobIds.filter((jobId) => SAFE_FACT_ID.test(jobId)))).slice(0, 10);

  return (
    <>
      <section className="gap-page-hero">
        <span className="eyebrow">能力规划</span>
        <h1>别按感觉补技能，先看目标岗位共同缺什么</h1>
        <p>
          从你真正感兴趣的岗位里选出一组目标，JobLens 会把这些岗位反复出现的能力要求与你已经确认的职业证据对照，帮你找到最值得优先投入时间的 P0 / P1 补强项。
        </p>
      </section>
      <TargetCohortGapPanel initialJobIds={params.from === "agent" ? initialJobIds : []} />
    </>
  );
}
