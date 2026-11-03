import Link from "next/link";
import type {MatchReportRequirementResult} from "@/lib/contracts";

/** Explain the saved report, without inferring skills the person does or does not have. */
export function InsufficientEvidenceGuidance({requirements, profileHref = "/profile"}: {requirements: readonly MatchReportRequirementResult[]; profileHref?: string}) {
  const review = requirements.filter(item => item.semanticVerdict !== "matched");
  return <section className="match-insight-section" aria-label="证据不足时的准备方向">
    <h3>先核实哪些要求</h3>
    <p>下面来自这份已保存的匹配报告。证据未覆盖不等于你不会，也不代表要求已满足；请核对真实经历和岗位要求。</p>
    {review.length ? <ul>{review.map(item => <li key={item.requirementId}>
      <strong>{item.originalText}</strong><p>{item.reason}</p>
      <p>{item.semanticVerdict === "partial" ? "已有相关依据，但仍需核实是否足以支持该要求。" : "当前报告没有足够依据支持这项要求，请检查是否有可确认的真实经历。"}</p>
    </li>)}</ul> : <p>这份报告没有保存可逐项展示的待核实要求；请查看下方岗位要求和职业资料，不推测缺失内容。</p>}
    <p>如有遗漏的真实经历，请先核对并确认资料；否则可把岗位要求作为学习或准备方向，行动完成不会自动成为职业经历。</p>
    <Link href={profileHref}>核对职业资料与已确认经历</Link>
  </section>;
}
