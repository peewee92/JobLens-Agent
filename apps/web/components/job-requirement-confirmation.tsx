"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";

export function JobRequirementConfirmation({jobId, extractionId, inputHash, factsDigest, confirmed}: {
  jobId: string; extractionId: string; inputHash: string; factsDigest: string; confirmed: boolean;
}) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState("");
  if (confirmed || saved) return <div className="success-box" role="status">
    <strong>你已核对这份岗位要求</strong>
    <p>这次确认只适用于当前岗位原文和这一版要求，不代表抽取模型已通过整体质量评审。个人匹配仍以已确认的职业资料和求职意向为依据。</p>
    <a className="button-secondary" href="#job-match-report">查看匹配与下一步</a>
  </div>;

  async function confirm() {
    if (busy || !checked) return;
    setBusy(true);
    setMessage("");
    try {
      const key = `joblens:requirement-confirmation:${jobId}:${extractionId}:${factsDigest}`;
      let actionId = window.localStorage.getItem(key);
      if (!actionId) {
        actionId = crypto.randomUUID();
        window.localStorage.setItem(key, actionId);
      }
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/requirement-confirmations`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({actionId, extractionId, inputHash, factsDigest, confirmed: true}),
      });
      if (!response.ok) {
        setMessage(response.status === 409
          ? "岗位原文、提取要求或请求已经变化。请刷新核对后再确认；这次没有放行新的分析。"
          : "暂时无法确认保存结果。可先刷新核对；重试会使用同一个请求，不会自动调用模型。");
        return;
      }
      setSaved(true);
      router.refresh();
    } catch {
      setMessage("连接或浏览器存储不可用。请先刷新查看是否已确认；页面不会自动重发，重试仍使用原请求。");
    } finally { setBusy(false); }
  }

  return <section className="detail-card">
    <h3>核对这一个岗位的要求</h3>
    <p>请对照上方岗位原文，检查全部要求是否准确、是否遗漏关键条件，以及哪些是必需、优先或加分项。不准确时不要确认，应先重新分析或核实原文。</p>
    <label><input type="checkbox" checked={checked} disabled={busy} onChange={event => setChecked(event.target.checked)} />我已逐项核对，愿意用这一版要求分析当前岗位。</label>
    <p className="muted-copy">只记录你的核对，不改写要求、不替维护者签署模型质量评审，也不调用模型。</p>
    <button type="button" className="button" disabled={busy || !checked} onClick={confirm}>{busy ? "正在保存确认…" : "确认这份要求，继续匹配"}</button>
    {message ? <p role="alert" className="inline-error">{message}</p> : null}
  </section>;
}
