import type {AnalysisExecutionCommand} from "./contracts";

type StoragePort = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type PendingAnalysisExecution = {version: 1; threadId: string; body: AnalysisExecutionCommand};
const key = (threadId: string) => `joblens.analysisExecution.${threadId}`;

function valid(value: unknown, threadId: string): value is PendingAnalysisExecution {
  if (!value || typeof value !== "object") return false;
  const journal = value as Partial<PendingAnalysisExecution>;
  const body = journal.body;
  return journal.version === 1 && journal.threadId === threadId && !!body
    && typeof body.commandId === "string" && body.commandId.length > 0 && body.commandId.length <= 120
    && typeof body.resultId === "string" && body.resultId.length > 0 && body.resultId.length <= 120
    && Array.isArray(body.jobIds) && body.jobIds.length > 0 && body.jobIds.length <= 5
    && body.jobIds.every(id => typeof id === "string" && id.length > 0 && id.length <= 120);
}

export function readPendingExecution(storage: StoragePort, threadId: string): PendingAnalysisExecution | null {
  const raw = storage.getItem(key(threadId));
  if (!raw) return null;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { throw new Error("本地原请求记录损坏，请先查看已保存工作区。"); }
  if (!valid(parsed, threadId)) throw new Error("本地原请求内容无法确认，请先查看已保存工作区。");
  return {version: 1, threadId, body: {commandId: parsed.body.commandId, resultId: parsed.body.resultId,
    jobIds: Array.from(new Set(parsed.body.jobIds))}};
}

export function clearPendingExecution(storage: StoragePort, command: PendingAnalysisExecution): void {
  const saved = readPendingExecution(storage, command.threadId);
  if (JSON.stringify(saved) === JSON.stringify(command)) storage.removeItem(key(command.threadId));
}

export async function sendAnalysisExecution(storage: StoragePort, command: PendingAnalysisExecution,
                                          fetcher: typeof fetch = fetch): Promise<Response> {
  const existing = readPendingExecution(storage, command.threadId);
  if (existing && JSON.stringify(existing) !== JSON.stringify(command)) {
    throw new Error("另一个标签页保存了不同的待确认请求，请先查看已有工作区。");
  }
  storage.setItem(key(command.threadId), JSON.stringify(command));
  if (JSON.stringify(readPendingExecution(storage, command.threadId)) !== JSON.stringify(command)) {
    throw new Error("发送前原请求已变化，请先查看已有工作区。");
  }
  return fetcher(`/api/career-agent/runs/${encodeURIComponent(command.threadId)}/execution`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(command.body),
  });
}
