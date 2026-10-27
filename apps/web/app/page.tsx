import {systemReadinessNotice} from "@/components/system-readiness-notice";
import {ServiceError} from "@/components/service-error";
import {WorkbenchView} from "@/components/workbench-view";
import {fetchWorkbench, BackendApiError} from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const notice = await systemReadinessNotice("/");
  if (notice) return notice;
  try {
    return <WorkbenchView data={await fetchWorkbench()} />;
  } catch (error) {
    return <ServiceError message={error instanceof BackendApiError ? error.message : "暂时无法连接工作台，请确认后端服务和数据库已就绪后刷新。"} />;
  }
}
