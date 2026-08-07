import Link from "next/link";

export default function QualityPage() {
  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">高级工具</p>
        <h1>AI 分析质量检查</h1>
        <p className="lede">
          这里用于检查 JobLens 的 AI 分析是否可靠，主要面向产品验收、模型调试和开发排查。普通求职使用不需要理解下面的运行记录、模型版本或技术证据。
        </p>
      </section>

      <section className="product-step-grid">
        <article className="product-step-card">
          <h2>简历分析质量</h2>
          <p>检查 AI 从简历中整理经历和技能时，有没有遗漏、误解或编造。</p>
          <Link href="/evals/profile">进入高级检查 →</Link>
        </article>
        <article className="product-step-card">
          <h2>岗位要求分析质量</h2>
          <p>检查 AI 是否正确理解了 JD 里的学历、经验、技能、职责和加分项。</p>
          <Link href="/evals/requirements">进入高级检查 →</Link>
        </article>
        <article className="product-step-card">
          <h2>真实模型调用验证</h2>
          <p>小批量检查真实模型调用结果，再决定是否继续扩大到完整验收集。</p>
          <Link href="/evals/requirements/canary">进入高级检查 →</Link>
        </article>
      </section>

      <p className="notice">
        高级页面会保留 Run、Trace、Provider、Baseline 等工程术语，因为这些信息对排查模型质量问题有用；它们不会重新出现在普通求职主流程中。
      </p>
    </>
  );
}
