import Link from "next/link";
import {PageHeading, EmptyState} from "@/components/ui/patterns";

export default function NotFoundPage() {
  return <>
    <PageHeading kicker="页面不可用" title="找不到这个页面" description="链接可能已失效，或这条记录已不在当前列表中。" />
    <EmptyState title="可以从工作台继续" description="此页面没有改动你的资料或岗位。"
      actions={<><Link className="button" href="/">返回首页</Link><Link className="button-ghost" href="/jobs">查看我的岗位</Link></>} />
  </>;
}
