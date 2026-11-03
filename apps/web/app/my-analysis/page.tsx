import Link from "next/link";
import {ProfileEditor} from "@/components/profile-editor";
import {ByokJobs} from "@/components/byok-jobs";
import {fetchCurrentProfile, fetchCurrentSearchIntent, fetchJobPage} from "@/lib/backend";
import {publicSession} from "@/lib/model-session";
export const dynamic = "force-dynamic";
export default async function MyAnalysis() {
  const session = await publicSession();
  if (session?.mode !== 'byok') return <section><h1>使用自己的模型分析</h1><Link href="/connect">先创建真实使用会话</Link></section>;
  try {
    const [profile,intent,jobs] = await Promise.all([fetchCurrentProfile(), fetchCurrentSearchIntent(), fetchJobPage(new URLSearchParams({limit:'5'}))]);
    return <div className="stack"><h1>我的求职分析</h1><p>资料来源：{session.synthetic ? '合成样本' : '用户填写'}；使用自己的真实模型，不使用模拟模型结果。</p>
      <p><Link href="/connect">模型设置与导出</Link> · <Link href="/applications">查看准备行动</Link></p>
      <h2>第一步：填写并确认背景与偏好</h2><ProfileEditor initialProfile={profile} initialIntent={intent} byok/>
      <ByokJobs jobs={jobs.items}/>
    </div>;
  } catch {return <section><h1>当前会话暂时不可用</h1><p>请检查后端是否唤醒；过期或服务重启后需要重新开始。</p><Link href="/connect">检查连接或重新开始</Link></section>;}
}
