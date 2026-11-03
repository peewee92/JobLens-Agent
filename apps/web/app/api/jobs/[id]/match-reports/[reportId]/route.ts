import {fetchMatchReportHistory} from "@/lib/backend";
import {rankedReportSnapshot} from "@/lib/ranked-report";

export async function GET(_request: Request, {params}: {params: Promise<{id: string; reportId: string}>}) {
  const {id, reportId} = await params;
  try {
    const saved = rankedReportSnapshot(await fetchMatchReportHistory(id), id, reportId);
    return saved ? Response.json(saved, {headers: {"Cache-Control": "no-store"}})
      : Response.json({error: {code: "ranked_report_missing", message: "本次排序引用的报告暂不可读取，不会替换为最新报告。"}}, {status: 404});
  } catch {
    return Response.json({error: {code: "ranked_report_unavailable", message: "暂时无法读取本次排序依据，请稍后重试或查看岗位详情。"}}, {status: 503});
  }
}
