import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "JobLens",
  description: "把真实岗位数据变成可追溯的求职决策基础。",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/jobs" aria-label="JobLens 首页">
              <span className="brand-mark">JL</span>
              <span>
                <strong>JobLens</strong>
                <small>真实岗位 · 可追溯分析</small>
              </span>
            </Link>
            <nav className="site-nav" aria-label="主导航">
              <Link href="/profile">职业画像</Link>
              <Link href="/evals/profile">画像评测</Link>
              <Link href="/evals/requirements">要求评测</Link>
              <Link href="/jobs">岗位池</Link>
              <Link href="/import">导入岗位</Link>
            </nav>
          </div>
        </header>
        <main className="shell page-shell">{children}</main>
        <footer className="shell site-footer">
          <span>JobLens MVP · Evidence before recommendation</span>
        </footer>
      </body>
    </html>
  );
}
