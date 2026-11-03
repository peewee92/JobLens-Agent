"use client";
import Link from "next/link";
import {useEffect, useState, type FormEvent} from "react";

type Connection = {enableThinking?: boolean | null; name: string; baseUrl: string; model: string; apiStyle: string; profileModel?: string; requirementModel?: string; semanticModel?: string};
type Status = {recentCalls: {actionId:string; kind:string; status:string; model:string; attempts:number; inputTokens:number | null; outputTokens:number | null}[]; connected: boolean; version: number; connection: Connection | null; seed: string};
export function ModelConnection() {
  const [status, setStatus] = useState<Status | null>(null);
  const [seed, setSeed] = useState("blank");
  const [key, setKey] = useState("");
  const [config, setConfig] = useState<Connection>({name:"我的模型", baseUrl:"", model:"", apiStyle:"chat_completions"});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [plan, setPlan] = useState<{planDigest: string; model: string; maxOutputTokens: number} | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  async function read() {
    const r = await fetch("/api/byok/model-connection", {cache:"no-store"});
    if (r.ok) {const data: Status = await r.json(); setStatus(data); if (data.connection) setConfig(data.connection);}
  }
  useEffect(() => {void read().catch(() => {});}, []);
  async function perform(fn: () => Promise<void>) {
    if (busy) return; setBusy(true); setMessage("");
    try {await fn();} catch {setMessage("网络暂时不可用，请检查状态；不会自动重新调用模型。");} finally {setBusy(false);}
  }
  async function check(r: Response) {
    const data = await r.json();
    if (!r.ok) {setMessage(data.error?.message ?? "操作失败，请检查会话与输入。"); return null;}
    return data;
  }
  function save(e: FormEvent) {
    e.preventDefault();
    const apiKey = key; setKey(""); setPlan(null); setAction(null);
    void perform(async () => {
      const data = await check(await fetch("/api/byok/model-connection", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...config, apiKey})}));
      if (data) {setStatus(data); setMessage("连接已保存，尚未调用模型。可测试连接，或继续填写背景。");}
    });
  }
  return <div className="stack">
    <h1>连接我的模型</h1>
    <p>API Key 用于服务器代你请求所选模型服务，调用费用由你的模型账户承担。密钥仅保存在当前后端会话内存，不提供长期保存。</p>
    <p>背景和岗位文本会发送给你选择的服务。闲置 30 分钟、最长两小时或服务重启后，会话、密钥和进度失效；完成后请导出资料。</p>
    {!status ? <section className="card"><h2>创建独立真实使用会话</h2>
      <p>这会清除当前样本或旧会话的进度；不调用模型。公开功能未开启时会明确拒绝。</p>
      <label>初始资料 <select value={seed} onChange={e => setSeed(e.target.value)}><option value="blank">空白：填写自己的资料</option><option value="sample">样本：合成资料＋我的真实模型</option></select></label>
      <button disabled={busy} onClick={() => void perform(async () => {
        const d = await check(await fetch("/api/demo/session", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({mode:"byok", seed})}));
        if (d) window.location.assign("/connect");
      })}>确认清除旧进度并创建会话</button></section> : <>
      <p>资料来源：{status.seed === "sample" ? "合成样本" : "用户填写"}；模型方式：用户自带模型；连接版本：{status.version}。</p>
      <form className="panel stack-sm" onSubmit={save} autoComplete="off">
        <label>连接名称<input required maxLength={80} value={config.name} onChange={e => setConfig({...config, name:e.target.value})}/></label>
        <label>服务地址（Base URL）<input required type="url" placeholder="https://服务地址/v1" value={config.baseUrl} onChange={e => setConfig({...config, baseUrl:e.target.value})}/></label>
        <label>API Key<input required type="password" autoComplete="new-password" maxLength={4096} value={key} onChange={e => setKey(e.target.value)}/></label>
        <label>默认模型名称<input required maxLength={160} value={config.model} onChange={e => setConfig({...config, model:e.target.value})}/></label>
        <details><summary>高级设置</summary>
          <label>思考模式<select value={config.enableThinking == null ? "default" : String(config.enableThinking)} onChange={e => setConfig({...config, enableThinking:e.target.value === 'default' ? null : e.target.value === 'true'})}><option value="default">沿用服务默认（不发送参数）</option><option value="false">关闭（服务需支持 enable_thinking）</option><option value="true">开启（服务需支持 enable_thinking）</option></select></label>
          <label>接口类型<select value={config.apiStyle} onChange={e => setConfig({...config, apiStyle:e.target.value})}><option value="chat_completions">chat_completions</option><option value="responses">responses</option></select></label>
          {([['profileModel','背景提取'],['requirementModel','岗位提取'],['semanticModel','语义匹配']] as const).map(([field,label]) => <label key={field}>{label}模型（留空沿用默认）<input maxLength={160} value={config[field] ?? ""} onChange={e => setConfig({...config, [field]:e.target.value || undefined})}/></label>)}
        </details>
        <button disabled={busy} type="submit">保存连接（不调用模型）</button>
      </form>
      {status.connected && <section className="card">
        <button disabled={busy} onClick={() => void perform(async () => {const d = await check(await fetch('/api/byok/model-connection/test-plan')); if (d) {setPlan(d); setAction(null); setConsent(false);}})}>查看连接测试计划</button>
        {plan && <div><p>使用 {plan.model} 发送一次短结构化请求，最多输出 {plan.maxOutputTokens} Token，超时 60 秒。费用未知，不自动重试。</p>
          <label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>我确认使用自己的模型账户支付本次测试费用</label>
          <button disabled={busy || !consent} onClick={() => void perform(async () => {
            const id = action ?? crypto.randomUUID(); setAction(id);
            const d = await check(await fetch('/api/byok/model-connection/test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({actionId:id, planDigest:plan.planDigest, confirmed:true, maxProviderCalls:1})}));
            if (d) setMessage(`测试状态：${d.status}；请求 ${d.attempts} 次；输入 Token ${d.inputTokens ?? '未知'}，输出 Token ${d.outputTokens ?? '未知'}；${d.errorCode ?? '仅证明本次接口请求可用，不代表所有任务效果合格。'}`);
          })}>{action ? '检查同一测试请求' : '确认并测试连接'}</button></div>}
        <p><Link className="button" href="/my-analysis">继续：填写背景与添加岗位</Link></p>
        <p><a href="/api/byok/session-export" download>导出当前资料与结果（不含密钥）</a></p>
        <button disabled={busy} onClick={() => void perform(async () => {const d = await check(await fetch('/api/byok/model-connection', {method:'DELETE'})); if (d) {setStatus(d); setPlan(null); setMessage('已断开连接，后续不会发送请求；此前已发送的请求无法撤回。');}})}>断开连接</button>
      </section>}
      {status.recentCalls?.length > 0 && <section className="card"><h2>最近调用记录</h2><p>查看记录不会调用模型。结果未知时先检查原请求，不要另发新的付费请求。</p><ul>{status.recentCalls.map(r => <li key={r.actionId}>{r.kind === 'profile' ? '背景提取' : '连接测试'} · {r.model} · {r.status} · 请求 {r.attempts} 次 · 输入 {r.inputTokens ?? '未知'} / 输出 {r.outputTokens ?? '未知'} Token · <a href={`/api/byok/profile-calls/${encodeURIComponent(r.actionId)}`}>查看原请求</a></li>)}</ul></section>}
    </>}
    {busy && <p role="status">正在处理，请勿重复提交。免费后端唤醒可能需要约一分钟。</p>}
    {message && <p role="status">{message}</p>}
    <Link href="/demo">返回免配置样本体验</Link>
  </div>;
}
