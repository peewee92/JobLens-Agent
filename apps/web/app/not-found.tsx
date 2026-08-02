import Link from "next/link";

export default function NotFoundPage() {
  return (
    <section className="empty-state">
      <p className="eyebrow">404</p>
      <h1>没有找到这条记录</h1>
      <p className="lede">它可能不存在、已经被删除，或链接中的 ID 不正确。</p>
      <div className="actions">
        <Link className="button" href="/jobs">返回岗位池</Link>
        <Link className="button-ghost" href="/import">导入新岗位</Link>
      </div>
    </section>
  );
}
