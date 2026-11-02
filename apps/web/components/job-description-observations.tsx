import {formatDateTime} from "@/lib/format";
import type {JobDescriptionObservations} from "@/lib/contracts";

export function JobDescriptionObservationsView({history}: {history: JobDescriptionObservations | null}) {
  if (!history) return <p className="notice">历史采集记录暂时无法读取，请稍后刷新；这不代表记录不存在。</p>;
  if (!history.items.length) return <p className="muted-copy">没有可查看的导入观察记录；旧记录可能未保存历史原文。</p>;
  return <details><summary>查看最近采集的历史描述（{history.items.length} 条）</summary>
    <p>下列时间是导入记录保存时间，不是岗位发布时间或有效性证明。当前岗位内容可能已再次更新；查看历史不会恢复或重新分析岗位。</p>
    {history.hasMore && <p>这里只显示最近 10 条；更早的记录未显示。</p>}
    {history.items.map(item => <article className="detail-section" key={`${item.importId}-${item.inputIndex}`}>
      <h3>导入记录：{formatDateTime(item.recordedAt)} · 第 {item.inputIndex + 1} 条</h3>
      {item.description === null ? <p>这条记录没有保存可查看的描述，无法还原原文。</p> :
        <p className="description">{item.description || "本次采集未提供描述。"}</p>}
      {item.truncated && <p>描述超过展示上限，仅显示前 50000 个字符。</p>}
    </article>)}
  </details>;
}
