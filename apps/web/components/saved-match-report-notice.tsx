import React from "react";
import type {MatchReportHistoryItem} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";
import {reportStaleReasonLabel} from "@/lib/match-report";

export function SavedMatchReportNotice({result}: {result: MatchReportHistoryItem}) {
  return (
    <section className="notice" aria-label="保存的分析版本">
      <strong>{result.isCurrent ? "已保存的当前结果" : "历史结果：不再用于当前排序"}</strong>
      <p>{formatDateTime(result.createdAt)} · 资料第 {result.report.profileVersion} 版
        · 求职意向 {result.report.searchIntentVersion ?? "未记录"}
        · 规则 {result.report.policyVersion ?? "未记录"}</p>
      <p>岗位要求版本：{result.report.extractionId}</p>
      {!result.isCurrent ? <>
        <ul>{result.staleReasons.map((code) => <li key={code}>{reportStaleReasonLabel(code)}</li>)}</ul>
        <p>下面是当时保存的原始结论，不代表当前判断。补齐或确认输入后可重新生成；旧结果不会被覆盖。</p>
      </> : null}
    </section>
  );
}
