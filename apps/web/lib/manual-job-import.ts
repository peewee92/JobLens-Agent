import type {ApiErrorBody, ManualJobImportResult, ManualJobInput} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

type Result =
  | {kind: "saved"; result: ManualJobImportResult}
  | {kind: "error"; message: string}
  | {kind: "unknown"; message: string};

export const maxPastedJobs = 20;
export const maxPastedCharacters = 1_020_000;

export function parsePastedJobs(text: string): ManualJobInput[] {
  if (text.length > maxPastedCharacters) throw new Error("文本太长，请拆成几批，每批最多 20 条。");
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  const jobs: Array<{title: string; company: string; lines: string[]}> = [];
  for (const [index, line] of lines.entries()) {
    if (!jobs.length && /^【[^】]+】$/u.test(line.trim())) continue;
    const match = /^(?:(\d{1,2})\s*[.、）)]\s*)?([^｜|]{1,255})[｜|]([^｜|]{1,255})$/u.exec(line.trim());
    if (match && (!jobs.length || match[1] || !lines[index - 1].trim()) && match[2].trim() && match[3].trim()) {
      jobs.push({title: match[2].trim(), company: match[3].trim(), lines: []});
      if (jobs.length > maxPastedJobs) throw new Error("每批最多添加 20 条岗位，请分批粘贴。");
    } else if (jobs.length) {
      jobs[jobs.length - 1].lines.push(line);
    } else if (line.trim()) {
      throw new Error("没找到第一条岗位的标题。请用「岗位名称｜公司名称」作为每条的第一行。");
    }
  }
  if (!jobs.length) throw new Error("没有找到岗位。每条请先写「岗位名称｜公司名称」，换行再贴描述。");
  return jobs.map(({title, company, lines}) => ({title, company, description: lines.join("\n").trim()}));
}

export function manualJobValidation(job: ManualJobInput): string | null {
  if (!job.title.trim() || !job.company.trim()) return "请填写岗位名称和公司名称。";
  if (Array.from(job.title.trim()).length > 255 || Array.from(job.company.trim()).length > 255) return "岗位名称或公司名称超过 255 字。";
  if (!job.description.trim()) return "请至少粘贴一段岗位描述。很短的描述可以先存为待补充。";
  if (Array.from(job.description).length > 50_000) return "单条岗位描述不能超过 50,000 字，请先拆分或缩短。";
  return null;
}

export async function submitManualJob(job: ManualJobInput): Promise<Result> {
  const issue = manualJobValidation(job);
  if (issue) return {kind: "error", message: issue};
  const unknown: Result = {kind: "unknown", message: "暂时不能确认是否已保存。请先到我的岗位核对，不要连续提交。"};
  try {
    const response = await fetch("/api/job-imports/manual", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(job),
    });
    if (response.status >= 500 || response.status === 408) return unknown;
    const body = await response.json();
    if (!response.ok) return {kind: "error", message: userFacingApiError(body as Partial<ApiErrorBody>, "没有保存成功，请核对必填内容和岗位链接。")};
    if (typeof body?.jobId !== "string" || !body.jobId || !Number.isInteger(body.created)) return unknown;
    return {kind: "saved", result: body as ManualJobImportResult};
  } catch {
    return unknown;
  }
}
