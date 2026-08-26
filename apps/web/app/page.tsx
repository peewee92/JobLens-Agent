import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <section className="hero product-hero">
        <p className="eyebrow">JobLens</p>
        <h1>先把自己和岗位看清楚，再决定把时间花在哪里</h1>
        <p className="lede">
          JobLens 会把你确认过的经历、求职偏好和真实岗位描述整理到一起，先帮助你看清自己的背景和岗位真正要求什么。不会替你编经历，也不会自动投递。
        </p>
        <div className="actions">
          <Link className="button" href="/recommendations">看优先投哪些岗位</Link>
          <Link className="button-secondary" href="/profile">完善我的背景</Link>
          <Link className="button-ghost" href="/jobs">查看岗位</Link>
        </div>
      </section>

      <section className="product-step-grid" aria-label="JobLens 使用步骤">
        <article className="product-step-card">
          <span className="step-number">1</span>
          <h2>完善我的背景</h2>
          <p>上传简历或手动补充经历、技能和求职偏好。只有你确认过的信息才会用于后续分析。</p>
          <Link href="/profile">去完善 →</Link>
        </article>
        <article className="product-step-card">
          <span className="step-number">2</span>
          <h2>添加感兴趣的岗位</h2>
          <p>导入浏览器插件收集的岗位，集中查看薪资、城市、远程信息和完整 JD。</p>
          <Link href="/import">添加岗位 →</Link>
        </article>
        <article className="product-step-card">
          <span className="step-number">3</span>
          <h2>先投最值得投入的岗位</h2>
          <p>基于硬条件、真实经历证据和求职偏好，把已有完整匹配结果排成优先级，并说明为什么。</p>
          <Link href="/recommendations">查看优先级 →</Link>
        </article>
      </section>

      <section className="notice product-trust-note">
        <strong>当前能做什么？</strong>
        <p>现在已经可以确认你的背景、收集真实岗位、分析岗位要求，并对已有完整匹配结果给出 Top 优先级。没有证据的岗位不会被硬塞进排名，也不会展示一个看似精确但没有依据的“匹配概率”。</p>
      </section>
    </>
  );
}
