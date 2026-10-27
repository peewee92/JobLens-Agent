import React from "react";
import {AnalysisUpdateStart} from "./analysis-update-start";
import Link from "next/link";
import type {AnalysisUpdatePlan} from "@/lib/contracts";

const statusLabels: Record<AnalysisUpdatePlan["items"][number]["status"], string> = {
  reuse: "可复用当前报告", ready: "可由规则重算（尚未执行）", deferred: "留待下一小批",
  requires_model: "需要单独授权模型", input_blocked: "先修复输入",
};
const reasonLabels: Record<string, string> = {
  profile_changed: "职业资料已更新", search_intent_changed: "求职意向已更新", policy_changed: "匹配规则已更新",
  requirements_changed: "岗位要求已有新版本", requirements_missing: "缺少岗位要求", job_missing: "原岗位记录缺失",
  preference_inputs_changed: "岗位偏好相关信息已变化", match_report_missing: "尚无保存的匹配报告",
  profile_missing: "尚未确认职业资料", search_intent_missing: "尚未确认求职意向",
  model_authorization_required: "需要语义判断，当前未授权模型调用", update_inputs_changed: "资料在预检期间变化，请重新预检",
};

export function AnalysisUpdatePlanView({plan}: {plan: AnalysisUpdatePlan}) {
  const base = `/agent/results/${encodeURIComponent(plan.sourceThreadId)}`;
  return <>
    <section className="page-heading"><p className="eyebrow">更新分析 · 输入预检</p><h1>先核对更新范围和所需输入</h1>
      <p>原分析使用职业资料 v{plan.previousProfileVersion}；当前资料 {plan.profileVersion ? `v${plan.profileVersion}` : "尚未确认"}、意向 {plan.searchIntentVersion ? `v${plan.searchIntentVersion}` : "尚未确认"}。</p>
      <Link href={base}>返回原始保存结果</Link>
    </section>
    <section className="card stack-md"><h2>这次覆盖哪些岗位</h2>
      <form className="form-grid" action={`${base}/update`} method="GET">
        <div className="field"><label htmlFor="analysis-update-scope">更新范围</label><select id="analysis-update-scope" name="scope" defaultValue={plan.scope}>
          <option value="targets">原确认目标岗位</option><option value="batch">原分析整批岗位</option>
        </select></div><div className="actions"><button className="button" type="submit">重新预检所选范围</button></div>
      </form>
      <p>{plan.items.length} 个岗位：{plan.reusableJobIds.length} 个可复用，{plan.nextJobIds.length} 个进入首批重算候选；每次最多新增分析 {plan.maxNewAnalyses} 个岗位。</p>
      <p className="notice">当前仅预检，没有重算、保存新结果或调用模型。执行时必须重新检查事实；预检通过不是模型授权，也不承诺排名提高。</p>
    </section>
    <section className="card stack-md"><h2>逐项检查</h2>
      {plan.items.map(item => <article className="eligibility-result-card" key={item.jobId}>
        <h3>{item.title}</h3><p>{statusLabels[item.status]}</p>
        {item.requiredOperations.includes("semantic_match") && <p>现有证据需要语义匹配；未授权时停在这里，不自动调用或切换模型。</p>}
        {item.requiredOperations.includes("extract_requirements") && <p>需要先补充并检查岗位要求；本页不会重新提取。</p>}
        <ul>{[...new Set([...item.staleReasons, ...item.blockerCodes])].map(code => <li key={code}>{reasonLabels[code] ?? "有一项输入需要核对，请查看岗位或资料详情"}</li>)}</ul>
        {item.status !== "reuse" && <Link href={item.repairHref}>核对该项输入与依据</Link>}
        <details><summary>查看版本与原因码</summary><p>岗位：{item.jobId}；要求：{item.extractionId ?? "缺失"}；复用报告：{item.reusableReportId ?? "无"}</p>
          <p>{[...item.staleReasons, ...item.blockerCodes].join("、") || "报告版本兼容"}</p></details>
      </article>)}
    </section>
    <AnalysisUpdateStart key={plan.scope} plan={plan} />
  </>;
}
