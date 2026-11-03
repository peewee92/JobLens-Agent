"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";

export function JobAvailabilityControl({jobId, inactive, revision}: {
  jobId: string; inactive?: boolean; revision?: number;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const known = typeof inactive === "boolean" && Number.isSafeInteger(revision) && revision! >= 0;
  async function change() {
    if (!known || pending) return;
    setPending(true); setMessage("");
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/user-availability`, {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({userMarkedInactive: !inactive, expectedRevision: revision}),
      });
      const result = await response.json();
      if (!response.ok || result.jobId !== jobId || result.userMarkedInactive !== !inactive ||
          !Number.isSafeInteger(result.availabilityRevision)) throw new Error();
      setMessage("标记已保存，正在更新页面。");
      router.refresh();
    } catch {
      setMessage("保存结果尚未确认或标记已变化，请刷新页面核对后再操作。");
    } finally { setPending(false); }
  }
  return <div className="notice">
    <p>{!known ? "暂时无法确认岗位标记，请刷新或检查服务版本。" : inactive
      ? "你已标记此岗位失效；它不会进入当前推荐。历史分析和投递记录仍保留。"
      : "如果你确认不再考虑这个岗位，可以自行标记失效。"}</p>
    <p>这是你的标记，不代表招聘网站的实时状态；重新导入不会自动恢复。</p>
    <button type="button" className="button-secondary" disabled={!known || pending} onClick={change}>
      {pending ? "保存中…" : inactive ? "恢复为待核实" : "标记岗位失效"}
    </button>
    {message && <p role="status">{message}</p>}
  </div>;
}
