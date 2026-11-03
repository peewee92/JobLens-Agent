import Link from "next/link";

/** Absence from ranking is not evidence that a candidate is unqualified. */
export function UnrankedJobs({ids, labels = {}}: {ids: readonly string[]; labels?: Readonly<Record<string, string>>}) {
  if (!ids.length) return null;
  return <aside className="notice" aria-label="未参与本次排序的岗位">
    <strong>{ids.length} 个所选岗位未出现在本次排序中</strong>
    <p>可能缺少可用匹配报告、事实版本已变化，或因明确硬冲突未进入默认排序；这不等于系统确认你不具备能力。请逐项核对岗位详情，不要将本次结果当作完整批次比较。</p>
    <ul>{ids.map(id => <li key={id}><Link href={`/jobs/${encodeURIComponent(id)}`}>{labels[id] ?? id}：核对岗位与匹配报告</Link></li>)}</ul>
  </aside>;
}
