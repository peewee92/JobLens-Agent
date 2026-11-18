import {Panel, Skeleton} from "@/components/ui/primitives";

export default function Loading() {
  return <Panel className="stack-md route-loading" role="status" aria-live="polite">
    <h1>正在打开页面…</h1>
    <p>正在读取已保存的内容，不会自动提交或重新分析。</p>
    <Skeleton className="h-3 w-3/4" />
    <Skeleton className="h-3 w-1/2" />
  </Panel>;
}
