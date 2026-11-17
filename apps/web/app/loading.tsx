export default function Loading() {
  return <section className="card stack-md route-loading" role="status" aria-live="polite">
    <h1>正在打开页面…</h1>
    <p>正在读取已保存的内容，不会自动提交或重新分析。</p>
    <div className="route-loading-bar" aria-hidden="true" />
    <div className="route-loading-bar" aria-hidden="true" />
  </section>;
}
