import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import {publicDemoEnabled} from "@/lib/public-demo";
import {NavLink} from "@/components/nav-link";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "JobLens",
  description: "基于真实经历和真实岗位，帮助你判断哪些机会更值得优先投入。",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main">
          跳到主要内容
        </a>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/" aria-label="JobLens 首页">
              <span className="brand-mark">JL</span>
              <span>
                <strong>JobLens</strong>
                <small>看懂岗位 · 做更稳的求职选择</small>
              </span>
            </Link>
            <nav className="site-nav" aria-label="主导航">
              <NavLink href="/">首页</NavLink>
              <NavLink href="/profile">我的背景</NavLink>
              <NavLink href="/jobs">我的岗位</NavLink>
              <NavLink href="/applications">我的准备</NavLink>
            </nav>
          </div>
        </header>
        <main id="main" className="shell page-shell">
          {(process.env.JOBLENS_DEMO === "1" || publicDemoEnabled()) && <aside className="notice" role="note" aria-label="隔离合成演示">
            <strong>离线合成演示</strong>：这里的资料、公司和岗位均为合成样本，不是真实求职结论。已禁用在线模型；数据保存在独立演示库，不会修改你的真实记录。{publicDemoEnabled() && <>临时进度可能随服务休眠或重启丢失。<Link href="/demo">重新开始样本体验</Link></>}
          </aside>}
          {children}
        </main>
        <footer className="shell site-footer">
          <span>JobLens · 基于真实经历和真实岗位做判断</span>
          {!publicDemoEnabled() && <Link href="/quality">质量检查（高级）</Link>}
          <span>版本：{process.env.JOBLENS_RELEASE_VERSION ?? process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "本地开发"}</span>
        </footer>
      </body>
    </html>
  );
}
