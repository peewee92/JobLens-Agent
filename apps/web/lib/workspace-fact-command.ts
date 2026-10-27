/** Only non-model fact commands. A pending request is never sent during a GET/render. */
export type WorkspaceFactCommand = {
  version: 1; workspaceId: string; commandId: string; path: string;
  body: Record<string, unknown>; rejected?: boolean;
};
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const key = (id: string) => `joblens.workspaceFactCommand.${id}`;
const canonical = (command: WorkspaceFactCommand) => JSON.stringify({version: command.version,
  workspaceId: command.workspaceId, commandId: command.commandId, path: command.path, body: command.body});
export function readWorkspaceFactCommand(store: Store, id: string): WorkspaceFactCommand | null {
  const raw = store.getItem(key(id));
  if (!raw) return null;
  let command: WorkspaceFactCommand;
  try { command = JSON.parse(raw); } catch { throw new Error("待确认请求记录无法读取，请先核对服务端提案，不要重复提交。"); }
  const prefix = `/api/application-workspaces/${encodeURIComponent(id)}/`;
  const suffix = typeof command.path === "string" && command.path.startsWith(prefix) ? command.path.slice(prefix.length) : "";
  if (!command || raw.length > 16000 || command.version !== 1 || command.workspaceId !== id || typeof command.commandId !== "string"
    || !command.commandId || !/^(actions\/[^/]+\/evidence-proposals|evidence-proposals\/[^/]+\/(confirm|reconsider))$/.test(suffix)
    || !command.body || typeof command.body !== "object" || Array.isArray(command.body)) throw new Error("待确认请求不属于本工作区的事实操作，请先核对服务端记录。");
  return command;
}
export function clearWorkspaceFactCommand(store: Store, command: WorkspaceFactCommand) {
  const current = readWorkspaceFactCommand(store, command.workspaceId);
  if (current && canonical(current) === canonical(command)) store.removeItem(key(command.workspaceId));
}
export async function sendWorkspaceFactCommand(store: Store, command: WorkspaceFactCommand,
  send: typeof fetch = fetch): Promise<Response> {
  const previous = readWorkspaceFactCommand(store, command.workspaceId);
  if (previous && canonical(previous) !== canonical(command)) throw new Error("先核对或重试上一个原请求；本次输入不会覆盖待确认请求。");
  const raw = JSON.stringify(command);
  if (raw.length > 16000) throw new Error("提案请求过大，未发送，请缩短真实成果描述。");
  store.setItem(key(command.workspaceId), raw);
  const saved = readWorkspaceFactCommand(store, command.workspaceId);
  if (!saved || canonical(saved) !== canonical(command)) throw new Error("另一个标签页改变了待确认请求，未发送，请刷新核对。");
  const response = await send(command.path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(command.body)});
  if (response.ok) clearWorkspaceFactCommand(store, command);
  else if ([404, 409, 422].includes(response.status)) {
    const current = readWorkspaceFactCommand(store, command.workspaceId);
    if (current && canonical(current) === canonical(command)) store.setItem(key(command.workspaceId), JSON.stringify({...command, rejected: true}));
  }
  return response;
}
