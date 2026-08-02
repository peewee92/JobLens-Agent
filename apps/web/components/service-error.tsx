import Link from "next/link";

export function ServiceError({message}: {message: string}) {
  return (
    <section className="error-panel">
      <p className="eyebrow">Service error</p>
      <h2>暂时无法读取 JobLens 数据</h2>
      <p>{message}</p>
      <div className="actions">
        <Link className="button-ghost" href="/jobs">重新加载岗位池</Link>
        <Link className="button-secondary" href="/import">检查导入入口</Link>
      </div>
    </section>
  );
}
