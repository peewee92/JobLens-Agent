"use client";
import * as Select from "@radix-ui/react-select";
import Link from "next/link";
import {useCallback, useEffect, useId, useRef, useState, type FormEvent} from "react";
import {readModelConnection, type ModelConnectionConfig, type ModelConnectionStatus} from "@/lib/model-connection-read";
import {Button} from "./ui/button";
import {PendingIndicator} from "./ui/pending-indicator";
import {ActionFeedback} from "./ui/patterns";
import {Field, Panel} from "./ui/primitives";

function ModelSelect({label, value, onValueChange, options, disabled}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: ReadonlyArray<readonly [value: string, label: string]>;
  disabled?: boolean;
}) {
  const id = useId();
  return <Field id={id} label={label}>
    <Select.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <Select.Trigger id={id} className="jl-model-select-trigger">
        <Select.Value />
        <Select.Icon asChild><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg></Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content position="popper" align="start" sideOffset={4} collisionPadding={12} className="jl-model-select-menu">
          <Select.Viewport>
            {options.map(([optionValue, text]) => <Select.Item key={optionValue} value={optionValue} className="jl-model-select-option">
              <Select.ItemText>{text}</Select.ItemText>
              <Select.ItemIndicator asChild><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m3 8 3 3 7-7" /></svg></Select.ItemIndicator>
            </Select.Item>)}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  </Field>;
}

export function ModelConnection() {
  const [status, setStatus] = useState<ModelConnectionStatus | null>(null);
  const [reading, setReading] = useState(true);
  const [readError, setReadError] = useState(false);
  const statusCheck = useRef<AbortController | null>(null);
  const requestLock = useRef(false);
  const [priorTest, setPriorTest] = useState<string | null>(null);
  const [testDone, setTestDone] = useState(false);
  const [seed, setSeed] = useState("blank");
  const [key, setKey] = useState("");
  const [config, setConfig] = useState<ModelConnectionConfig>({name:"我的模型", baseUrl:"", model:"", apiStyle:"chat_completions"});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [plan, setPlan] = useState<{planDigest: string; model: string; maxOutputTokens: number} | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const read = useCallback(async () => {
    statusCheck.current?.abort();
    const controller = new AbortController();
    statusCheck.current = controller;
    setReading(true); setReadError(false);
    const result = await readModelConnection(controller.signal);
    if (controller.signal.aborted) return;
    if (result.kind === "ready") {
      setStatus(result.status);
      if (result.status?.connection) setConfig(result.status.connection);
    } else {
      setReadError(true);
    }
    setReading(false);
  }, []);
  useEffect(() => {
    void read();
    return () => statusCheck.current?.abort();
  }, [read]);
  async function perform(fn: () => Promise<void>) {
    if (requestLock.current) return;
    requestLock.current = true; setBusy(true); setMessage("");
    try {await fn();} catch {setMessage("未收到处理结果。请先查看已保存状态；不会自动重新调用模型。");}
    finally {requestLock.current = false; setBusy(false);}
  }
  function describeTest(data: {status: string; attempts: number; inputTokens?: number | null; outputTokens?: number | null}) {
    const completed = data.status === "completed" || data.status === "failed";
    setTestDone(completed);
    setMessage(`测试${data.status === "completed" ? "已完成" : data.status === "failed" ? "未成功" : "结果未确认"} · 请求 ${data.attempts} 次 · 输入 ${data.inputTokens ?? "未知"} / 输出 ${data.outputTokens ?? "未知"} 个模型计量单位。${completed ? "这不代表所有任务的效果。" : "请先查看处理结果；不会重新发送。"}`);
  }
  async function check(r: Response) {
    const data = await r.json();
    if (!r.ok) {setMessage(data.error?.message ?? "操作失败，请检查会话与输入。"); return null;}
    return data;
  }
  async function createSession() {
    const response = await fetch("/api/public-session", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mode: "byok", seed}),
    });
    if (response.status === 503) {
      const data = await response.json().catch(() => null);
      if (statusCheck.current?.signal.aborted) return;
      setMessage(data?.error?.code !== "demo_backend_waking" && data?.error?.message
        ? data.error.message
        : "未能确认会话是否已创建。将重新检查连接状态，不会自动重试创建。");
      await read();
      return;
    }
    if (await check(response)) window.location.assign("/connect");
  }
  function save(e: FormEvent) {
    e.preventDefault();
    if (action && !testDone) return;
    const apiKey = key; setKey(""); setPlan(null); setAction(null);
    void perform(async () => {
      const data = await check(await fetch("/api/byok/model-connection", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...config, apiKey})}));
      if (data) {setStatus(data); setMessage("连接已保存，尚未调用模型。可测试连接，或继续填写背景。");}
    });
  }
  return <div className="byok-shell stack">
    <h1>连接我的模型</h1>
    <p>API Key 用于服务器代你请求所选模型服务，调用费用由你的模型账户承担。密钥仅保存在当前后端会话内存，不提供长期保存。</p>
    <p>背景和岗位文本会发送给你选择的服务。闲置 30 分钟、最长两小时或服务重启后，会话、密钥和进度失效；完成后请导出资料。</p>
    {reading && <PendingIndicator label={status ? "正在刷新模型设置，保留已有连接信息。" : "正在读取模型设置…"}
      slowLabel="免费演示服务可能正在启动，当前检查不会创建会话或调用模型。" skeleton={!status} />}
    {readError && <div className="stack-sm">
      <ActionFeedback tone="danger">暂时无法读取连接状态。尚不能确认是否已有会话；不会新建或清除资料。</ActionFeedback>
      <div><Button variant="secondary" onClick={() => void read()}>重新检查</Button></div>
    </div>}
    {reading || readError ? null : !status ? <Panel><h2>创建独立真实使用会话</h2>
      <p>这会清除当前样本或旧会话的进度；不调用模型。公开功能未开启时会明确拒绝。</p>
      <div className="jl-model-session-setup">
        <ModelSelect label="初始资料" value={seed} onValueChange={setSeed} disabled={busy}
          options={[["blank", "空白：填写自己的资料"], ["sample", "样本：合成资料＋我的真实模型"]]} />
        <Button variant="secondary" disabled={busy}
          onClick={() => void perform(createSession)}>确认清除旧进度并创建会话</Button>
      </div>
    </Panel> : <>
      <p>资料来源：{status.seed === "sample" ? "合成样本" : "用户填写"}；模型方式：用户自带模型；连接版本：{status.version}。</p>
      <form className="panel stack-sm" onSubmit={save} autoComplete="off">
        <label className="field">连接名称<input required maxLength={80} value={config.name} onChange={e => setConfig({...config, name:e.target.value})}/></label>
        <label className="field">服务地址（Base URL）<input required type="url" placeholder="https://服务地址/v1" value={config.baseUrl} onChange={e => setConfig({...config, baseUrl:e.target.value})}/></label>
        <label className="field">API Key<input required type="password" autoComplete="new-password" maxLength={4096} value={key} onChange={e => setKey(e.target.value)}/></label>
        <label className="field">默认模型名称<input required maxLength={160} value={config.model} onChange={e => setConfig({...config, model:e.target.value})}/></label>
        <details><summary>高级设置</summary>
          <ModelSelect label="思考模式" value={config.enableThinking == null ? "default" : String(config.enableThinking)}
            onValueChange={value => setConfig(current => ({...current, enableThinking: value === "default" ? null : value === "true"}))}
            options={[["default", "沿用服务默认（不发送参数）"], ["false", "关闭（服务需支持 enable_thinking）"], ["true", "开启（服务需支持 enable_thinking）"]]} />
          <ModelSelect label="接口类型" value={config.apiStyle}
            onValueChange={apiStyle => setConfig(current => ({...current, apiStyle}))}
            options={[["chat_completions", "chat_completions"], ["responses", "responses"]]} />
          {([['profileModel','背景提取'],['requirementModel','岗位提取'],['semanticModel','语义匹配']] as const).map(([field,label]) => <label className="field" key={field}>{label}模型（留空沿用默认）<input maxLength={160} value={config[field] ?? ""} onChange={e => setConfig({...config, [field]:e.target.value || undefined})}/></label>)}
        </details>
        <button className="button-secondary" disabled={busy || (!!action && !testDone)} type="submit">保存连接（不调用模型）</button>
      </form>
      {status.connected && <section className="detail-card">
        {!action && !plan && <Button variant="secondary" disabled={busy} onClick={() => void perform(async () => {
          const d = await check(await fetch('/api/byok/model-connection/test-plan'));
          if (d) {setPlan(d); setConsent(false); setTestDone(false);}
        })}>查看连接测试计划</Button>}
        {plan && <div><p>使用 {plan.model} 发送一次短结构化请求，最多输出 {plan.maxOutputTokens} Token，超时 60 秒。费用未知，不自动重试。</p>
          {!action ? <>
            {priorTest && <p className="notice">上一次测试可能已产生费用。以下确认只授权一次新的测试。</p>}
            <label className="check-row"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)}/>我确认使用自己的模型账户支付本次测试费用</label>
            <div className="jl-inline">
              <Button disabled={busy || !consent} onClick={() => void perform(async () => {
                const id = crypto.randomUUID(); setAction(id); setConsent(false);
                const d = await check(await fetch('/api/byok/model-connection/test', {method:'POST', headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({actionId:id, planDigest:plan.planDigest, confirmed:true, maxProviderCalls:1,
                    ...(priorTest ? {acknowledgedPriorRequestId: priorTest} : {})})}));
                if (d) describeTest(d);
              })}>确认并测试连接</Button>
              <Button variant="secondary" disabled={busy} onClick={() => {setPlan(null); setConsent(false); setMessage("已取消授权，没有发送测试请求。");}}>取消授权</Button>
            </div>
          </> : <div className="stack-sm">
            <div><Button variant="secondary" disabled={busy} onClick={() => void perform(async () => {
              const response = await fetch(`/api/byok/profile-calls/${encodeURIComponent(action)}`, {cache: "no-store"});
              if (response.status === 404) {setMessage("未查到该测试回执，仍无法确认是否计费；没有重新发送。"); return;}
              const data = await check(response);
              if (data) describeTest(data);
            })}>查看处理结果</Button></div>
            {testDone ? <div><Button variant="subtle" disabled={busy} onClick={() => {setAction(null); setPlan(null); setTestDone(false);}}>返回，制定新计划</Button></div>
              : <details><summary>准备重新测试</summary>
                  <p>上次请求可能已产生费用。先确认这一点，再查看新的发送范围和次数。</p>
                  <Button variant="secondary" disabled={busy} onClick={() => {
                    setPriorTest(action); setAction(null); setPlan(null); setConsent(false);
                  }}>了解，返回制定新计划</Button>
                </details>}
          </div>}</div>}
        <p><Link className="button" href="/my-analysis">继续：填写背景与添加岗位</Link></p>
        <p><a href="/api/byok/session-export" download>导出当前资料与结果（不含密钥）</a></p>
        <button className="button-secondary" disabled={busy || (!!action && !testDone)} onClick={() => void perform(async () => {const d = await check(await fetch('/api/byok/model-connection', {method:'DELETE'})); if (d) {setStatus(d); setPlan(null); setMessage('已断开连接，后续不会发送请求；此前已发送的请求无法撤回。');}})}>断开连接</button>
      </section>}
      {status.recentCalls?.length > 0 && <section className="detail-card"><h2>最近调用记录</h2><p>查看记录不会调用模型。结果未知时先检查原请求，不要另发新的付费请求。</p><ul>{status.recentCalls.map(r => <li key={r.actionId}>{r.kind === 'profile' ? '背景提取' : '连接测试'} · {r.model} · {r.status} · 请求 {r.attempts} 次 · 输入 {r.inputTokens ?? '未知'} / 输出 {r.outputTokens ?? '未知'} Token · <a href={`/api/byok/profile-calls/${encodeURIComponent(r.actionId)}`}>查看原请求</a></li>)}</ul></section>}
    </>}
    {busy && <PendingIndicator label="正在处理本次操作，请不要重复提交。" slowLabel="仍在等待结果。关闭页面不会撤销已发出的请求。" />}
    {message && <p role="status">{message}</p>}
    <Link href="/sample">返回免配置样本体验</Link>
  </div>;
}
