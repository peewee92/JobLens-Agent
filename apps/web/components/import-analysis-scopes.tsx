import Link from "next/link";
import {agentScopeHref} from "@/lib/agent-job-scope";
import {splitAnalysisScopes} from "@/lib/import-match-batching";

/** Saved ranking results, rather than browser session state, define the available scopes. */
export function ImportAnalysisScopes({jobIds}: {jobIds: readonly string[]}) {
  const ids = [...new Set(jobIds)];
  if (!ids.length) return null;
  const scopes = splitAnalysisScopes(ids);
  return <section aria-label="已保存匹配的分析入口">
    <h3>用已保存的匹配继续分析</h3>
    <p>当前有 {ids.length} 个岗位已保存匹配。每次分析最多选择 50 个岗位；进入后仍可调整，岗位或资料变化时需要重新核对。</p>
    {scopes.map((scope, index) => <p key={scope[0]}>
      <Link href={agentScopeHref(scope)}>{scopes.length === 1 ? `选择这 ${scope.length} 个岗位进行分析` : `选择第 ${index + 1} 组的 ${scope.length} 个岗位进行分析`}</Link>
    </p>)}
  </section>;
}
