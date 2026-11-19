import Link from "next/link";
import {ReadRetry} from "./ui/read-retry";

export function ServiceError({message, heading = "暂时无法读取内容", recovery = "retry"}: {
  message: string; heading?: string; recovery?: "retry" | "home";
}) {
  return (
    <section className="jl-callout jl-status-panel" data-tone="warning" aria-labelledby="service-error-heading">
      <div role="alert">
        <h2 id="service-error-heading">{heading}</h2>
        <p>{message}</p>
        <p>已保存的数据不会因读取失败而改变。</p>
      </div>
      <div className="jl-inline">
        {recovery === "retry" && <ReadRetry />}
        <Link className={recovery === "home" ? "button" : "button-ghost"} href="/">返回首页</Link>
      </div>
    </section>
  );
}
