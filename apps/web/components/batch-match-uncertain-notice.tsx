"use client";

export function BatchMatchUncertainNotice({kind = "match"}: {kind?: "match" | "requirements"}) {
  return <div className="inline-error" role="alert">
    <strong>本轮结果暂时无法确认</strong>
    <p>服务可能已保存{kind === "match" ? "部分匹配结果" : "岗位要求分析结果"}。请先刷新本页，核对已完成和待处理岗位；不要直接重复提交本轮请求。</p>
    <button type="button" className="button-ghost" onClick={() => window.location.reload()}>刷新并核对结果</button>
  </div>;
}
