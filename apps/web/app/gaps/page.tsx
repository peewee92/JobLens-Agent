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
  const initialJobIds = Array.from(new Set(requestedJobIds.filter((jobId) => SAFE_FACT_ID.test(jobId)))).slice(0, 50);

  return (
    <>
      <section className="gap-page-hero">
        <span className="eyebrow">能力规划</span>
        <h1>对照目标岗位，找出下一步该核对什么</h1>
        <p>
          选一个岗位或一组目标。这里对照已核对的岗位要求与已确认的经历：区分必需条件和加分项，不把证据不足当成不会，也不替你决定能否投递。
        </p>
      </section>
      <TargetCohortGapPanel initialJobIds={params.from === "agent" ? initialJobIds : []} />
    </>
  );
}
