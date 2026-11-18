import Link from "next/link";
import {rankingOmissionMessage, rankingRecoveryAnchor, type RankingOmission} from "@/lib/agent-ranking-preflight";
import {jobDetailWithAgentScope} from "@/lib/agent-job-scope";
import {LinkFeedback} from "@/components/link-feedback";

/** Absence from ranking is not evidence that a candidate is unqualified. */
export function UnrankedJobs({ids, labels = {}, scope, currentOmissions = []}: {ids: readonly string[]; labels?: Readonly<Record<string, string>>; scope?: readonly string[]; currentOmissions?: readonly RankingOmission[]}) {
  if (!ids.length) return null;
  return <aside className="notice ranking-omissions" aria-label="未参与本次排序的岗位">
    <strong>{ids.length} 个所选岗位未出现在本次排序中</strong>
    <p>可能缺少可用匹配报告、事实版本已变化，或因明确硬冲突未进入默认排序；这不等于系统确认你不具备能力。请逐项核对岗位详情，不要将本次结果当作完整批次比较。</p>
    {currentOmissions.length > 0 && <p>下方原因来自当前检查，不会替换本次保存的比较结果。</p>}
    <ul>{ids.map(id => {
      const check = currentOmissions.find(item => item.jobId === id);
      const href = scope?.includes(id) ? jobDetailWithAgentScope(id, scope) : `/jobs/${encodeURIComponent(id)}`;
      return <li key={id}><Link href={check ? `${href}#${rankingRecoveryAnchor(check)}` : href}>{labels[id] ?? "名称暂不可读取的岗位"}<LinkFeedback /></Link>：{check ? rankingOmissionMessage(check) : "查看岗位及当前进度"}</li>;
    })}</ul>
  </aside>;
}
