"use client";
import Link from "next/link";
import {AuthorizedModelCall} from "@/components/authorized-model-call";
import type {RequirementCallPlan, SemanticCallPlan} from "@/lib/contracts";
import {useRouter} from "next/navigation";
import {useState, type FormEvent} from "react";

type Job = {id: string; title: string; company: string};
type Plan = RequirementCallPlan | SemanticCallPlan;
function JobCall({job, task}: {job: Job; task: 'requirement' | 'semantic'}) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const base = `/api/jobs/${encodeURIComponent(job.id)}/${task}`;
  async function preview() {
    setBusy(true); setMessage('');
    try {const r = await fetch(base + '-call-plan', {cache:'no-store'}); const d = await r.json();
      if (!r.ok) {setMessage(d.error?.message ?? '请先确认背景、求职偏好和岗位要求。'); return;}
      setPlan(d);
      if (!d.available) setMessage(`当前无需或不能调用：${d.blockerCode}。如已满足规则或明确存在硬冲突，无需额外语义调用。`);
    } catch {setMessage('计划读取失败，尚未调用模型。');} finally {setBusy(false);}
  }
  return <section className="stack-sm"><button disabled={busy} onClick={preview}>查看{task === 'requirement' ? '岗位提取' : '语义匹配'}计划</button>
    {plan?.available && <AuthorizedModelCall key={plan.planDigest} jobId={job.id} plan={plan} disabled={busy} kind={task}/>}
    {message && <p role="status">{message}</p>}</section>;
}
export function ByokJobs({jobs}: {jobs: Job[]}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    const form = e.currentTarget; const values = new FormData(form); setBusy(true); setMessage('');
    try {const r = await fetch('/api/job-imports/manual', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:values.get('title'), company:values.get('company'), description:values.get('description')})});
      const d = await r.json(); if (!r.ok) setMessage(d.error?.message ?? '添加失败。');
      else {form.reset(); setMessage('已保存岗位原文，尚未调用模型。'); router.refresh();}
    } catch {setMessage('网络中断，请先刷新岗位列表检查，不要重复添加。');} finally {setBusy(false);}
  }
  return <section className="stack"><h2>第二步：添加并分析岗位</h2>
    <p>先保存并确认背景和求职偏好，再逐个提取岗位要求、核对原文依据并匹配。最多保存 5 个岗位，每次明确授权仅允许一次模型请求。</p>
    <form className="panel stack-sm" onSubmit={add}>
      <label>岗位名称<input required name="title" maxLength={255}/></label><label>公司<input required name="company" maxLength={255}/></label>
      <label>岗位正文<textarea required name="description" minLength={40} maxLength={12000} rows={8}/></label>
      <button disabled={busy || jobs.length >= 5}>保存岗位（不调用模型）</button>
    </form>{message && <p role="status">{message}</p>}
    {jobs.map(job => <article className="card stack-sm" key={job.id}><h3>{job.title} · {job.company}</h3>
      <JobCall job={job} task="requirement"/><Link href={`/jobs/${encodeURIComponent(job.id)}`}>查看岗位原文、提取依据与匹配报告</Link>
      <JobCall job={job} task="semantic"/>
    </article>)}
    <h2>第三步：比较岗位并开始准备</h2><p>先完成各岗位的匹配报告，再比较并确认目标。这一步读取已有报告，不自动付费重算；自然语言 Agent 本版尚未开放。</p>
    <Link className="button" href="/agent">比较岗位、确认目标并开始行动</Link>
  </section>;
}
