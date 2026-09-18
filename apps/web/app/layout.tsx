import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

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
              <NavLink href="/recommendations">优先投递</NavLink>
              <NavLink href="/gaps">能力差距</NavLink>
              <NavLink href="/agent">Career Agent</NavLink>
              <NavLink href="/import">添加岗位</NavLink>
            </nav>
          </div>
        </header>
        <main id="main" className="shell page-shell">
          {children}
        </main>
        <footer className="shell site-footer">
          <span>JobLens · 基于真实经历和真实岗位做判断</span>
          <Link href="/quality">质量检查（高级）</Link>
        </footer>
      </body>
    </html>
  );
}
