"use client";
import {useState} from "react";

export function DemoStart() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function start() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/demo/session", {method: "POST"});
      const data = await response.json();
      if (!response.ok) {setError(data.error?.message ?? "暂时无法开始，请稍后重试。"); return;}
      window.location.assign("/agent");
    } catch {setError("网络暂时不可用，请稍后重试；不会自动重复提交。");}
    finally {setBusy(false);}
  }
  return <><button className="button" onClick={start} disabled={busy}>{busy ? "正在准备独立样本……" : "开始／重新开始样本体验"}</button>
    {busy && <p role="status">免费后端闲置后需要唤醒，可能等待约一分钟。这里只准备合成样本，不调用在线模型。</p>}
    {error && <p role="alert">{error}</p>}</>;
}
