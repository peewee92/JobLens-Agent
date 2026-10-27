import React from "react";
import Link from "next/link";
import {inputIssueLabel, runStatusLabels, workspaceStatusLabels, workbenchChangeLabel, type Workbench} from "@/lib/workbench";

export function WorkbenchView({data}: {data: Workbench}) {
  const {snapshot: view, nextAction: action} = data;
  const run = view.currentRun;
  return <>
    <section className="hero product-hero">
      <p className="eyebrow">JobLens · 求职任务工作台</p>
      <h1>把有依据的选择，变成下一步行动</h1>
      <p className="lede">先确认真实资料，再比较岗位、准备材料并记录结果。不会编造经历，也不会自动投递。</p>
      <h2>下一步：{action.label}</h2><p>{action.reason}</p>
      <div className="actions"><Link className="button" href={action.href}>{action.label}</Link></div>
    </section>
    <section className="detail-card" aria-label="当前准备情况">
      <h2>当前准备情况</h2>
      <p>职业资料：{view.profileVersion ? `已确认 v${view.profileVersion}` : "尚未确认"} · 求职意向：{view.searchIntentVersion ? `已确认 v${view.searchIntentVersion}` : "尚未确认"}</p>
      <p>{view.evidenceCount} 项已确认经历证据 · {view.jobCount} 个已导入岗位{run ? ` · 最近分析范围 ${run.jobCount} 个岗位` : ""}</p>
      {view.inputIssueCodes.length ? <ul>{view.inputIssueCodes.map(code => <li key={code}>{inputIssueLabel(code)}</li>)}</ul> : <p>资料与意向已确认；具体岗位的数据质量、要求和证据覆盖仍需逐项核对。</p>}
      <div className="actions"><Link href="/profile">核对我的资料与意向</Link><Link href="/import">添加岗位</Link><Link href="/jobs">检查岗位描述、要求和输入问题</Link></div>
      <p className="muted-copy">导入数量不代表要求已提取或岗位仍在招聘；来源观察时间过旧需要核实，不会据此自动判定关闭。</p>
    </section>
    <section className="detail-card" aria-label="当前分析">
      <h2>当前分析</h2>
      {run ? <>
        <p>{run.partial && run.resultId ? "部分范围已保存" : runStatusLabels[run.status] ?? "状态待核实"} · 请求范围 {run.jobCount} 个岗位 · 已确认 {run.targetCount} 个目标</p>
        <div className="actions"><Link href={`/agent?threadId=${encodeURIComponent(run.threadId)}`}>查看本次运行与阻断原因</Link>
          {run.resultId && <Link href={`/agent/results/${encodeURIComponent(run.threadId)}`}>打开本次保存的完整分析</Link>}
          {run.resultId && <Link href={`/agent/results/${encodeURIComponent(run.threadId)}/update`}>核对范围并更新分析</Link>}</div>
        {run.partial && <p className="notice">只完成或复用了 {run.completedReportCount ?? 0} 个岗位的匹配；其余岗位没有在本次完成，不代表已淘汰。请查看保存结果中的范围说明。</p>}
        {run.resultIsCurrent === false && <p className="notice">资料或岗位事实已变化。旧分析仍可查看，不会自动重算或覆盖。</p>}
        {run.status === "completed" && !run.resultId && <p>此历史运行没有保存完整材料，不能用当前计算冒充原始结果；需要新建分析。</p>}
      </> : <p>还没有分析。可以先浏览岗位；个人化结论只使用已确认资料和有效报告。</p>}
      <p>打开工作台只查看状态，不会启动分析或调用模型。</p>
      <div className="actions"><Link href="/agent">选择岗位或找回其他运行</Link><Link href="/recommendations">查看同一匹配报告的优先级与分组</Link></div>
    </section>
    <section className="detail-card" aria-label="目标岗位">
      <h2>目标岗位与执行</h2>
      {view.workspaces.length ? <ul>{view.workspaces.map(workspace => <li key={workspace.workspaceId}>
        <Link href={`/applications/${encodeURIComponent(workspace.workspaceId)}`}>{workspace.title}</Link>
        <p>{workspaceStatusLabels[workspace.status] ?? "状态待核实"} · {workspace.openActionCount} 项待完成行动</p>
        {workspace.currentAnalysisThreadId && <Link href={`/agent/results/${encodeURIComponent(workspace.currentAnalysisThreadId)}`}>查看关联分析、差距与准备材料</Link>}
        {workspace.currentAnalysisThreadId && <p><Link href={`/agent/results/${encodeURIComponent(workspace.currentAnalysisThreadId)}/update`}>从该工作区关联分析更新</Link></p>}
      </li>)}</ul> : <p>还没有建立工作区。确认目标并保存分析后，即可一键开始执行。</p>}
      <p className="muted-copy">最多显示 5 个最近工作区。行动完成只记录进度，不会自动增加职业事实。</p>
    </section>
    <section className="detail-card" aria-label="最近变化">
      <h2>最近变化</h2>
      {view.changes.length ? <ul>{view.changes.map((change, i) => <li key={`${change.kind}-${change.occurredAt}-${i}`}>
        <Link href={change.href}>{workbenchChangeLabel(change.kind)}</Link><small> · {change.occurredAt.replace("T", " ").slice(0, 16)}（协调世界时）</small>
      </li>)}</ul> : <p>暂无已保存的变化。</p>}
      <p>这里汇总实际保存的事实和事件，不把点击按钮当成业务完成。</p>
    </section>
  </>;
}
