import {TargetCohortGapPanel} from "@/components/target-cohort-gap-panel";

export default function GapPage() {
  return (
    <section>
      <h1>目标岗位能力差距</h1>
      <p>基于你明确选择的真实岗位与已确认职业证据，查看最值得优先补齐的能力。</p>
      <TargetCohortGapPanel />
    </section>
  );
}
