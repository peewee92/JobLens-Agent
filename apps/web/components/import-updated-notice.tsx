import Link from "next/link";
import type {JobImportAuditItem} from "@/lib/contracts";

export function ImportUpdatedNotice({items, labels}: {
  items: JobImportAuditItem[];
  labels: Record<string, string>;
}) {
  const ids = Array.from(new Set(items.filter(item => item.outcome === "updated" && item.jobId).map(item => item.jobId as string)));
  if (!ids.length) return null;
  return <section className="notice" aria-label="更新岗位提示">
    <strong>有 {ids.length} 个已有岗位收到新的采集记录</strong>
    <p>当前岗位信息可能已被新的采集内容替换，较短的内容不一定更准确。请打开岗位核对描述和原始链接；之前的分析可能已过期，不会自动重算。列表显示的是现在的岗位名称，并非当时的历史快照。</p>
    <details><summary>查看这些岗位</summary><ul>{ids.map(id => <li key={id}>
      <Link href={`/jobs/${encodeURIComponent(id)}`}>{labels[id] ?? `岗位 ${id}`}</Link>
    </li>)}</ul></details>
  </section>;
}
