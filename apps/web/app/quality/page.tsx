import Link from "next/link";
import {Button} from "@/components/ui/button";
import {PageHeading} from "@/components/ui/patterns";

const tools = [
  {title: "简历解析评测", description: "检查模型是否漏掉、误解或编造了简历中的技能和经历。", href: "/evals/profile", action: "查看简历解析评测"},
  {title: "岗位要求评测", description: "检查模型是否读对了岗位的学历、经验、技能和加分项。", href: "/evals/requirements", action: "查看岗位要求评测"},
  {title: "在线模型小批验证", description: "先核对少量真实调用的结果，再决定是否继续整批测试。", href: "/evals/requirements/canary", action: "查看在线验证记录"},
];

export default function QualityPage() {
  return <div className="jl-section-stack jl-maintenance">
    <div className="jl-maintenance-heading stack-sm">
      <PageHeading kicker="仅供维护与测试 · 求职流程无需操作" title="模型质量检查"
        description="这里检查模型能不能准确读懂简历和岗位，不是用来核对你的个人资料，也不影响你继续使用求职工作台。" />
      <div className="jl-inline">
        <Button variant="secondary" asChild><Link href="/">返回求职工作台</Link></Button>
      </div>
    </div>
    <section className="product-step-grid jl-quality-cards" aria-label="维护工具">
      {tools.map(tool => <article className="product-step-card" key={tool.href}>
        <h2>{tool.title}</h2>
        <p>{tool.description}</p>
        <Button variant="subtle" asChild><Link href={tool.href}>{tool.action}</Link></Button>
      </article>)}
    </section>
  </div>;
}
