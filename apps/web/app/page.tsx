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
          <Link className="button" href="/profile">完善我的背景</Link>
          <Link className="button-secondary" href="/jobs">查看岗位</Link>
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
          <h2>看懂岗位，再做选择</h2>
          <p>先把 JD 整理成学历、经验、技能和职责；质量确认后，再用于后续匹配和排序。</p>
          <Link href="/jobs">查看岗位 →</Link>
        </article>
      </section>

      <section className="notice product-trust-note">
        <strong>当前能做什么？</strong>
        <p>现在已经可以确认你的背景、收集真实岗位并分析岗位要求。岗位匹配和优先级排序仍在建设中，JobLens 不会提前展示一个没有可靠依据的“匹配度”。</p>
      </section>
    </>
  );
}
