import Link from "next/link";
import {ModelConnection} from "@/components/model-connection";
import {PageHeading} from "@/components/ui/patterns";
import {Panel} from "@/components/ui/primitives";
import {publicDemoEnabled} from "@/lib/public-demo";

export const dynamic = "force-dynamic";

export default function ConnectPage() {
  return publicDemoEnabled() ? <ModelConnection /> : <>
    <PageHeading kicker="求职工作台" title="模型设置" description="本地使用后端的模型配置。此页不会发出调用。" />
    <Panel className="stack-sm">
      <h2>正在使用本地配置</h2>
      <p>如果没有可用的简历模型，你也可以手填职业定位和一段真实经历，之后再确认保存。</p>
      <Link className="button-secondary" href="/profile">返回我的背景</Link>
    </Panel>
  </>;
}
