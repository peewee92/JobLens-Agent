import {DemoStart} from "@/components/demo-start";
import {publicDemoEnabled} from "@/lib/public-demo";

export const dynamic = "force-dynamic";
export default function DemoPage() {
  return <section className="hero product-hero"><p className="eyebrow">JobLens · 公开合成演示</p>
    <h1>三个岗位，先准备哪个？</h1>
    <p className="lede">用一份合成背景，比较有证据支持、证据不足和明确冲突的三个岗位，再确认目标并开始一项准备行动。</p>
    <ol><li>比较岗位，看清依据与未知。</li><li>确认目标，查看准备材料。</li><li>开始行动，刷新检查进度。</li></ol>
    <p>不需要私人简历或模型密钥。所有资料和岗位均为合成样本，在线模型已禁用；这不是实时模型效果展示。</p>
    <p>每位访客独立体验；刷新保留当前进度。闲置 30 分钟、最长两小时或服务重启后重置，不用于长期保存求职资料。</p>
    {publicDemoEnabled() ? <DemoStart/> : <p>本地演示请运行仓库根目录的 <code>python3 scripts/demo.py</code>。</p>}
  </section>;
}
