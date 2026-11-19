import {Panel} from "@/components/ui/primitives";
import {PendingIndicator} from "@/components/ui/pending-indicator";

export default function Loading() {
  return <Panel className="stack-md route-loading">
    <h1>正在打开页面</h1>
    <PendingIndicator label="正在读取已保存的内容，不会自动提交或重新分析。" skeleton />
  </Panel>;
}
