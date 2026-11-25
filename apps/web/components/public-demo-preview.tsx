import Link from "next/link";

import {DemoStart} from "@/components/demo-start";
import {PageHeading} from "@/components/ui/patterns";
import {Panel} from "@/components/ui/primitives";
import {publicSessionState} from "@/lib/model-session";
import {publicDemoEnabled, type DemoDestination, type DemoInactiveState} from "@/lib/public-demo";

const previews = {
  "/": {
    title: "求职工作台",
    description: "先了解样本背景，再看看三条岗位的要求，最后决定从哪一条开始准备。",
    action: "开始样本体验",
    content: <ul><li><Link href="/profile">看样本背景</Link>：看看已有经历能支持哪些要求。</li>
      <li><Link href="/jobs">浏览样本岗位</Link>：区分有依据、证据不足和明确冲突。</li>
      <li><Link href="/applications">了解准备工作区</Link>：把选定岗位拆成下一步行动。</li></ul>,
  },
  "/profile": {
    title: "我的背景",
    description: "用一份合成背景看看 JobLens 如何把经历和岗位要求对应起来。",
    action: "打开样本背景",
    content: <><h2>样本资料概览</h2><p>这位求职者有两年工作经验，做过 Python 服务开发与维护。岗位建议只引用已有经历，不把缺少记录说成不会。</p>
      <p>公开样本不接收私人简历，也不会修改真实职业资料。</p></>,
  },
  "/jobs": {
    title: "我的岗位",
    description: "先看看会比较哪三类岗位，再打开完整列表、要求和比较依据。",
    action: "打开三个样本岗位",
    content: <><h2>样本岗位概览</h2><ul><li>Python 后端岗位：有经历可以对照。</li>
      <li>TypeScript 岗位：需要进一步核实。</li><li>要求至少五年经验的岗位：和样本年限有明确冲突。</li></ul></>,
  },
  "/applications": {
    title: "我的准备",
    description: "确认想继续尝试的岗位后，可建一个独立工作区跟踪准备行动。",
    action: "打开准备工作区",
    content: <><h2>工作区会保存什么</h2><p>你可以查看已确认的目标、分析依据和下一步行动。公开样本不会投递，也不会永久保存进度。</p></>,
  },
} satisfies Record<DemoDestination, {title: string; description: string; action: string; content: React.ReactNode}>;

export function PublicDemoPreview({destination, status}: {destination: DemoDestination; status: DemoInactiveState}) {
  const view = previews[destination];
  return <>
    <PageHeading kicker="公开合成演示" title={view.title} description={view.description} />
    <Panel className="stack-md">
      {view.content}
      {status === "expired" && <p className="jl-callout" role="status">上一次演示已结束，旧进度不会恢复。可在此开启新样本。</p>}
      {status === "unavailable"
        ? <><p className="jl-callout" role="status">暂时无法确认演示进度。免费服务可能正在唤醒，现有进度未被主动重置。</p>
          <p><a className="button" href={destination}>重新读取此页</a></p></>
        : <div><DemoStart destination={destination} label={view.action} /></div>}
    </Panel>
  </>;
}

export async function demoEntryPreview(destination: DemoDestination) {
  if (!publicDemoEnabled()) return null;
  const session = await publicSessionState();
  return session.status === "active" ? null : <PublicDemoPreview destination={destination} status={session.status} />;
}
