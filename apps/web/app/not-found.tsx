import Link from "next/link";

export default function NotFoundPage() {
  return (
    <section className="empty-state">
      <p className="eyebrow">404</p>
      <h1>没有找到这条记录</h1>
      <p className="lede">它可能不存在、已经被删除，或者这个链接已经失效。</p>
      <div className="actions">
        <Link className="button" href="/jobs">返回我的岗位</Link>
        <Link className="button-ghost" href="/import">添加岗位</Link>
      </div>
    </section>
  );
}
