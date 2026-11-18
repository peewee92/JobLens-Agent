import {matchReasonCopy} from "@/lib/match-report";

/** Keep model wording intact; do not invent a translation or another model call. */
export function MatchReason({reason}: {reason: string}) {
  const copy = matchReasonCopy(reason);
  if (/\p{Script=Han}/u.test(copy)) return <p>{copy}</p>;
  return <div>
    <p>请对照这项岗位要求和已确认经历核实。模型返回了英文说明，原文保留在下方；这不改变上方的匹配结论。</p>
    <details><summary>查看模型原始说明（英文）</summary><p lang="en">{copy}</p></details>
  </div>;
}
