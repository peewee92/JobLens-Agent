"use client";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import type {RequirementCallPlan, RequirementCallRecord, SemanticCallPlan, SemanticCallRecord} from "@/lib/contracts";

export function AuthorizedModelCall({jobId, plan: initialPlan, disabled, kind}: {
  jobId: string; plan: RequirementCallPlan | SemanticCallPlan; disabled: boolean; kind: "requirement" | "semantic";
}) {
  const semantic = kind === "semantic";
  const endpoint = semantic ? "semantic" : "requirement";
  const router = useRouter();
  const [plan, setPlan] = useState(initialPlan);
  const [record, setRecord] = useState<RequirementCallRecord | SemanticCallRecord | null>(plan.latestRequest);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState("");
  const key = `joblens:${endpoint}-call:${jobId}`;
  const running = record?.status === "running";
  const uncertain = record?.status === "uncertain";
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored && stored !== plan.latestRequest?.actionId) setUnknown(true);
    } catch { /* A fresh request will fail closed before sending if storage is unavailable. */ }
  }, [key, plan.latestRequest?.actionId]);

  async function reloadPlan() {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/${endpoint}-call-plan`);
    if (response.ok) {
      const current = await response.json() as RequirementCallPlan | SemanticCallPlan;
      setPlan(current);
      setRecord(current.latestRequest);
    }
  }

  async function replay() {
    setBusy(true);
    try {
      const body = window.localStorage.getItem(`${key}:command`);
      if (!body) { setMessage("原授权内容不可用，请保留请求标识并检查服务端记录。"); return; }
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/${endpoint}-calls`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body,
      });
      if (!response.ok) {
        if (response.status === 409) {
          window.localStorage.removeItem(key);
          window.localStorage.removeItem(`${key}:command`);
          setUnknown(false);
          await reloadPlan();
        }
        setMessage("原请求未执行或暂时无法恢复。请核对当前授权范围，不会自动发起新调用。"); return;
      }
      const saved = await response.json() as RequirementCallRecord | SemanticCallRecord;
      setRecord(saved);
      setUnknown(false);
      if (saved.status === "completed") { await reloadPlan(); router.refresh(); }
    } catch { setMessage("重发结果仍不确定。保留原请求，不生成新授权。"); }
    finally { setBusy(false); }
  }

  async function check() {
    setBusy(true);
    setMessage("");
    try {
      const actionId = window.localStorage.getItem(key) ?? record?.actionId;
      if (!actionId) { setMessage("未找到已发送的请求标识，请刷新查看最近记录。"); return; }
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/${endpoint}-calls/${encodeURIComponent(actionId)}`);
      if (!response.ok) {
        setMessage("暂未查询到原请求。可稍后查询，或重发相同授权；不会生成新的请求标识。");
        return;
      }
      const saved = await response.json() as RequirementCallRecord | SemanticCallRecord;
      setRecord(saved);
      setUnknown(false);
      if (saved.status === "completed") { await reloadPlan(); router.refresh(); }
    } catch { setMessage("连接失败；查询不会发起新的模型调用。"); }
    finally { setBusy(false); }
  }

  async function start() {
    if (!checked || busy || running || unknown) return;
    setBusy(true);
    setMessage("");
    setChecked(false);
    let sent = false;
    try {
      const actionId = crypto.randomUUID();
      // Save before sending: browser failure must never turn into a new paid attempt.
      const command = {actionId, planDigest: plan.planDigest, confirmed: true, maxProviderCalls: 1,
        acknowledgedPriorRequestId: uncertain ? record?.actionId : null};
      window.localStorage.setItem(`${key}:command`, JSON.stringify(command));
      window.localStorage.setItem(key, actionId);
      sent = true;
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/${endpoint}-calls`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(command),
      });
      if (!response.ok) {
        setUnknown(response.status !== 409);
        if (response.status === 409) {
          window.localStorage.removeItem(key);
          window.localStorage.removeItem(`${key}:command`);
          await reloadPlan();
        }
        setMessage(response.status === 409 ? "本次授权未执行。范围或上次请求状态已变化，请重新核对后操作。"
          : "暂时无法确认请求结果，请查询原请求，不要重复授权。");
        return;
      }
      const saved = await response.json() as RequirementCallRecord | SemanticCallRecord;
      setRecord(saved);
      if (saved.status === "completed") { await reloadPlan(); router.refresh(); }
    } catch {
      setUnknown(sent);
      setMessage(sent ? "连接中断，调用可能已经发出。请只查询原请求。" : "浏览器无法保存请求标识，本次没有发送模型请求。");
    } finally { setBusy(false); }
  }

  return <section className="detail-card">
    <h3>{semantic ? "授权本次经历语义匹配" : "授权本次岗位要求提取"}</h3>
    <p>{semantic ? "只发送下方岗位要求和候选经历摘要，不发送完整简历或原始岗位描述。" : "只发送当前岗位描述，不发送职业资料。"}模型：{plan.model}；
      {"descriptionCharacters" in plan ? `原文 ${plan.descriptionCharacters} 字符；` : `资料第 ${plan.profileVersion} 版；意向第 ${plan.searchIntentVersion} 版；`}
      最多 1 次请求，最多输出 {plan.maxOutputTokens} token，网络超时 {plan.timeoutSeconds} 秒。不自动重试或切换模型。</p>
    {"requirements" in plan ? <details><summary>查看本次将发送的要求与经历（{plan.requirements.length} 项）</summary>
      {plan.requirements.map(item => <article key={item.requirementId}><strong>{item.requirementText}</strong>
        {item.candidates.map(candidate => <p key={candidate.evidenceId}>{candidate.summary}</p>)}</article>)}
    </details> : null}
    {!plan.available ? <p className="notice">{plan.blockerCode === "live_provider_not_configured" ? "尚未配置可用模型，本次不会发送请求。可先核对已确认资料，或完成模型配置后重新检查。" : "当前输入超出本次调用范围或不再需要模型，请重新检查匹配准备情况。"}</p> : null}
    <p className="muted-copy">这不是固定金额报价。实际费用取决于服务商；未知用量不会显示成零。</p>
    {record ? <div role="status">
      <p>最近请求：{record.status === "completed" ? (semantic ? "匹配结果已保存" : "结果已保存，请核对下方提取要求") : record.status === "running" ? "正在执行；超过两分钟未完成时请重新查询" : record.status === "uncertain" ? "调用结果不确定，可能已产生费用" : "未保存可用结果，不会自动重试"}。</p>
      <p>请求尝试：{record.attempts}；输入用量：{record.inputTokens ?? "未知"}；输出用量：{record.outputTokens ?? "未知"}。</p>
      {record.responseStatus === 402 ? <p role="alert" className="notice">模型服务返回 HTTP 402，账户或计费条件未满足，尚未获得可用分析结果。请先到已配置的模型服务商核对余额、额度或账户状态，再回来明确授权新的一次调用。修改岗位描述不能解决此问题；系统不会自动充值、重试或切换模型。当前用量未知，不代表费用为零。</p> : null}
    </div> : null}
    {running || unknown ? <div><button type="button" disabled={busy} onClick={check}>查询原请求状态（不调用模型）</button>
      {unknown ? <button type="button" disabled={busy} onClick={replay}>重发相同授权（不增加授权次数）</button> : null}</div> : <>
      {uncertain ? <p className="notice">上次结果无法确认。重新授权可能产生第二次费用，不会撤销已经发出的请求。</p> : null}
      <label><input type="checkbox" checked={checked} disabled={disabled || busy || !plan.available}
        onChange={event => setChecked(event.target.checked)} />
        {uncertain ? "我了解上次调用结果不确定，仍授权新的一次分析。" : semantic ? "我同意发送上述要求与经历摘要，并承担这一次匹配的模型费用。" : "我同意按上述范围发送一次岗位描述并承担本次模型费用。"}</label>
      <p><button type="button" className="button" disabled={disabled || busy || !checked || !plan.available} onClick={start}>
        {busy ? "正在分析…" : semantic ? "授权并匹配一次" : record ? "授权重新提取一次" : "授权并提取一次"}</button></p>
    </>}
    {message ? <p role="alert" className="inline-error">{message}</p> : null}
  </section>;
}
