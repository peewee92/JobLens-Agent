import {publicSession} from "@/lib/model-session";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import {publicDemoEnabled} from "@/lib/public-demo";
import {ThemeChoice} from "@/components/theme-choice";
import {NavLink} from "@/components/nav-link";
import "@/app/globals.css";
import "@/app/design.css";

export const metadata: Metadata = {
  title: "JobLens",
  description: "基于真实经历和真实岗位，帮助你判断哪些机会更值得优先投入。",
};

export default async function RootLayout({children}: {children: ReactNode}) {
  const session = await publicSession();
  const isPublicDemo = publicDemoEnabled();
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main">
          跳到主要内容
        </a>
        <header className="site-header">
          <div className="shell header-inner">
            <a className="brand" href="/" aria-label="JobLens 首页">
              <span className="brand-mark" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><path d="M4 7.5h5.5l3 4.5-3 4.5H4l3-4.5L4 7.5Z"/><path d="M14 7.5h5.5l-3 4.5 3 4.5H14"/></svg></span>
              <span>
                <strong>JobLens</strong>
                <small>看懂岗位 · 做更稳的求职选择</small>
              </span>
            </a>
            <nav className="site-nav" aria-label="主导航">
              <NavLink fresh={isPublicDemo} href="/">首页</NavLink>
              <NavLink fresh={isPublicDemo} href="/profile">我的背景</NavLink>
              <NavLink fresh={isPublicDemo} href="/jobs">我的岗位</NavLink>
              <NavLink fresh={isPublicDemo} href="/applications">我的准备</NavLink>
              {publicDemoEnabled() && <NavLink fresh={isPublicDemo} href="/connect">模型设置</NavLink>}
            </nav>
            <ThemeChoice />
          </div>
        </header>
        <main id="main" tabIndex={-1} className="shell page-shell">
          {session?.mode === "byok" && <aside className="jl-root-notice"><strong>自带模型真实分析</strong>：资料来源为{session.synthetic ? "合成样本" : "用户填写"}，模型费用由你的账户承担。进度临时保存，闲置 30 分钟、最长两小时或服务重启后失效。<Link href="/my-analysis">继续分析</Link> · <Link href="/connect">设置与导出</Link></aside>}
          {(process.env.JOBLENS_DEMO === "1" || publicDemoEnabled()) && session?.mode !== "byok" && <aside className="jl-root-notice" role="note" aria-label="隔离合成演示">
            <strong>离线合成演示</strong>：这里的资料、公司和岗位均为合成样本，不是真实求职结论。已禁用在线模型；数据保存在独立演示库，不会修改你的真实记录。{publicDemoEnabled() && <>临时进度可能随服务休眠或重启丢失。<Link href="/demo">样本体验说明</Link></>}
          </aside>}
          {process.env.JOBLENS_LOCAL_PRODUCT === "1" && !publicDemoEnabled() &&
            <aside className="jl-root-notice" role="note" aria-label="本地正式使用"><strong>本地正式使用</strong>：使用你录入的资料与岗位，进度保存在本机。只有授权的模型步骤才会把指定文本发送给模型服务。</aside>}
          {children}
        </main>
        <footer className="shell site-footer">
          <span>JobLens · 基于真实经历和真实岗位做判断</span>
          {!publicDemoEnabled() && <Link href="/quality">模型质量检查（维护用）</Link>}
          <span>版本：{process.env.JOBLENS_RELEASE_VERSION ?? process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "本地开发"}</span>
        </footer>
      </body>
    </html>
  );
}
