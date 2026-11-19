"use client";

import Link from "next/link";
import {ReadRetry} from "@/components/ui/read-retry";

export default function ErrorBoundary({reset}: {error: Error & {digest?: string}; reset: () => void}) {
  return <section className="jl-panel stack-md" aria-labelledby="route-error-heading">
    <div className="jl-callout jl-status-panel" data-tone="danger" role="alert">
      <h1 id="route-error-heading">暂时打不开这个页面</h1>
      <p>可以重新读取当前页面，不会自动提交或重新执行分析。也可以先返回工作台。</p>
    </div>
    <div className="jl-inline"><ReadRetry reset={reset} /><Link href="/" className="button-ghost">返回首页</Link></div>
  </section>;
}
