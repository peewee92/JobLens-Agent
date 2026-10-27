import {fetchSystemReadiness} from "@/lib/backend";
import {readinessMessage} from "@/lib/system-readiness";

/** Returns null when ready. Call before querying business tables on entry pages. */
export async function systemReadinessNotice(returnHref: string) {
  try {
    const result = await fetchSystemReadiness();
    if (result.ready) return null;
    return <section className="error-panel" role="alert">
      <h1>运行环境尚未就绪</h1>
      <p>{readinessMessage(result.code)}</p>
      <p>你的资料不会在这里被修改，也不会发起模型调用。处理完成后可以重新检查。</p>
      <details>
        <summary>环境检查详情</summary>
        <p>当前数据库版本：{result.currentRevisions.join("、") || "未登记"}</p>
        <p>程序要求版本：{result.requiredRevisions.join("、") || "暂不可读"}</p>
        {result.missingTables.length > 0 ? <p>缺少 {result.missingTables.length} 张数据表。</p> : null}
        <p>由本地维护者按后端 README 的数据库迁移步骤处理，请勿清空真实记录。</p>
      </details>
      <div className="actions"><a className="button" href={returnHref}>重新检查</a></div>
    </section>;
  } catch {
    return <section className="error-panel" role="alert">
      <h1>暂时无法确认运行环境</h1>
      <p>请确认后端已启动且版本匹配、网页连接配置正确，再重新检查。暂不继续分析或修改求职记录。</p>
      <div className="actions"><a className="button" href={returnHref}>重新检查</a></div>
    </section>;
  }
}
