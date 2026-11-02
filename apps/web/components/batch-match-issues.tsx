import Link from "next/link";
import {batchIssueDescription, type BatchMatchIssue} from "@/lib/batch-match-issues";

export function BatchMatchIssues({issues}: {issues: readonly BatchMatchIssue[]}) {
  if (!issues.length) return null;
  return <section aria-label="本次未完成的岗位">
    <h3>本次未完成的岗位</h3>
    <p>以下记录仅在当前页面保留；刷新后请重新核对岗位和已保存结果。</p>
    <ul>{issues.map(item => <li key={item.jobId}>
      <Link href={`/jobs/${encodeURIComponent(item.jobId)}`}>查看岗位 {item.jobId}</Link>：{batchIssueDescription(item)}
    </li>)}</ul>
  </section>;
}
