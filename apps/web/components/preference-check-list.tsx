import * as React from "react";
import Link from "next/link";
import type {PreferenceCheck} from "@/lib/contracts";

const labels = {matched: "已有支持", conditional: "待核实", missing: "明确冲突"};

export function PreferenceCheckList({checks, version}: {
  checks: PreferenceCheck[];
  version?: number | null;
}) {
  if (checks.length === 0) return null;
  const conflicts = checks.filter((check) => check.status === "missing").length;
  const unknowns = checks.filter((check) => check.status === "conditional").length;
  return (
    <details className="notice" open={conflicts > 0}>
      <summary>
        求职偏好依据：{conflicts} 项明确冲突，{unknowns} 项待核实
        {version != null ? `（意向版本 ${version}）` : ""}
      </summary>
      <p>待核实不会被当成不满足，也不会被包装成已经满足。</p>
      <ul>
        {checks.map((check) => (
          <li key={check.key}>
            <strong>{labels[check.status]}：</strong>{check.reason}
          </li>
        ))}
      </ul>
      <Link href="/profile#search-intent">检查或修改已确认求职意向</Link>
    </details>
  );
}
