import Link from "next/link";
import {agentScopeHref} from "@/lib/agent-job-scope";
import {splitAnalysisScopes} from "@/lib/import-match-batching";

/** Successful reports remain independently accessible even when another job fails. */
export function BatchMatchSuccesses({jobIds}: {jobIds: readonly string[]}) {
  if (!jobIds.length) return null;
  return <section aria-label="本次已完成的岗位">
    <h3>本次已完成的岗位（{jobIds.length}）</h3>
    <p>这些岗位的匹配已保存；尚未完成的岗位不代表不适合。离开本页前可继续核对成功结果。</p>
    {splitAnalysisScopes(jobIds).map((scope, index, scopes) => <p key={scope[0]}>
      <Link href={agentScopeHref(scope)}>{scopes.length === 1 ? "仅用已完成的岗位继续分析" : `分析已完成岗位第 ${index + 1} 组（${scope.length} 个）`}</Link>
    </p>)}
    <details><summary>逐项查看已完成岗位</summary><ul>{jobIds.map(id => <li key={id}>
      <Link href={`/jobs/${encodeURIComponent(id)}`}>查看岗位 {id} 的匹配</Link>
    </li>)}</ul></details>
  </section>;
}
