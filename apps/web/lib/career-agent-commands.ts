/** Transport-only recovery journal. Server runtime state remains authoritative. */
import type {CareerAgentRunState} from "./contracts";

export type StartRunBody = {
  threadId: string; runId: string; requestId: string; jobIds: string[]; topN: number;
};
export type DecisionRunBody = {
  interruptId: string; actionId: string; decision: "approve" | "edit" | "reject"; selectedJobIds: string[];
};
export type SavedRunCommand =
  | {version: 1; kind: "start"; threadId: string; body: StartRunBody}
  | {version: 1; kind: "decision"; threadId: string; body: DecisionRunBody};
export type CommandStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const PREFIX = "joblens.careerAgent.command.";

export function validThreadReference(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 120 && !/[\u0000-\u001f\u007f]/.test(value);
}
function ids(value: unknown, max: number, allowEmpty = false): value is string[] {
  return Array.isArray(value) && value.length <= max && (allowEmpty || value.length > 0)
    && value.every(validThreadReference);
}

export function parseSavedRunCommand(raw: string | null, threadId: string): SavedRunCommand | null {
  if (!raw || raw.length > 32000) return null;
  try {
    const data = JSON.parse(raw);
    if (data?.version !== 1 || data.threadId !== threadId || !validThreadReference(threadId) || !data.body) return null;
    const body = data.body;
    if (data.kind === "start" && body.threadId === threadId && validThreadReference(body.runId)
      && validThreadReference(body.requestId) && ids(body.jobIds, 50)
      && Number.isInteger(body.topN) && body.topN >= 1 && body.topN <= 5) {
      return {version: 1, kind: "start", threadId, body: {
        threadId, runId: body.runId, requestId: body.requestId, jobIds: [...new Set(body.jobIds)] as string[], topN: body.topN,
      }};
    }
    if (data.kind === "decision" && validThreadReference(body.interruptId) && validThreadReference(body.actionId)
      && ["approve", "edit", "reject"].includes(body.decision) && ids(body.selectedJobIds, 5, true)
      && (body.decision !== "edit" || body.selectedJobIds.length > 0)) {
      return {version: 1, kind: "decision", threadId, body: {
        interruptId: body.interruptId, actionId: body.actionId, decision: body.decision,
        selectedJobIds: [...new Set(body.selectedJobIds)] as string[],
      }};
    }
  } catch {}
  return null;
}

export function loadRunCommand(storage: CommandStorage, threadId: string): SavedRunCommand | null {
  return parseSavedRunCommand(storage.getItem(PREFIX + threadId), threadId);
}

export function saveRunCommand(storage: CommandStorage, command: SavedRunCommand): void {
  const normalized = parseSavedRunCommand(JSON.stringify(command), command.threadId);
  if (!normalized) throw new Error("请求内容无法安全保存，尚未发送。请检查所选岗位。");
  const key = PREFIX + command.threadId;
  const old = loadRunCommand(storage, command.threadId);
  if (old && JSON.stringify(old) !== JSON.stringify(normalized)) {
    throw new Error("还有一个结果未确认的请求，请先查看状态或重试原请求，不能覆盖原决定。");
  }
  storage.setItem(key, JSON.stringify(normalized));
}

export function clearRunCommand(storage: CommandStorage, command: SavedRunCommand): void {
  // Do not delete a newer command from another tab.
  const current = loadRunCommand(storage, command.threadId);
  if (current && JSON.stringify(current) === JSON.stringify(command)) storage.removeItem(PREFIX + command.threadId);
}

export function commandResolution(command: SavedRunCommand, state: CareerAgentRunState): "accepted" | "superseded" | "pending" {
  if (command.threadId !== state.threadId) return "pending";
  if (command.kind === "start") return "accepted";
  if (!state.decisionActionId) return "pending";
  return state.decisionActionId === command.body.actionId ? "accepted" : "superseded";
}

export async function sendRunCommand(
  storage: CommandStorage, command: SavedRunCommand, fetcher: typeof fetch = fetch,
): Promise<Response> {
  saveRunCommand(storage, command); // Failure must happen before any request is sent.
  const path = command.kind === "start" ? "/api/career-agent/runs"
    : `/api/career-agent/runs/${encodeURIComponent(command.threadId)}/resume`;
  const saved = loadRunCommand(storage, command.threadId);
  const expected = parseSavedRunCommand(JSON.stringify(command), command.threadId);
  if (!saved || JSON.stringify(saved) !== JSON.stringify(expected)) {
    throw new Error("已保存请求发生变化，尚未发送。请先重新查看状态。");
  }
  return fetcher(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(saved.body)});
}

export function runHref(threadId: string): string {
  return `/agent?${new URLSearchParams({threadId})}`;
}
