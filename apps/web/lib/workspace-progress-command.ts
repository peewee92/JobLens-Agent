/** Only pending user progress requests; never business progress or career facts. */
import type {CommandStorage} from './career-agent-commands';
import {workspaceCommandError} from './workspace-command-errors';
export const workspaceStatuses = ['considering','preparing','ready_to_apply','applied','interviewing','offer','rejected','withdrawn'];
export type ProgressCommand = {version: 1; workspaceId: string; slot: string; commandId: string;
  body: {actorId: string; idempotencyKey?: string; expectedStatus?: string; newStatus?: string}; rejected?: boolean};
const key = (workspace: string, slot: string) => `joblens.workspaceProgress.${encodeURIComponent(workspace)}.${encodeURIComponent(slot)}`;
const canonical = (c: ProgressCommand) => JSON.stringify([c.version,c.workspaceId,c.slot,c.commandId,c.body.actorId,c.body.idempotencyKey,c.body.expectedStatus,c.body.newStatus]);
export function progressPath(c: ProgressCommand) {
  const base = `/api/application-workspaces/${encodeURIComponent(c.workspaceId)}`;
  return c.slot === 'status' ? `${base}/status` : c.slot === 'create-actions' ? `${base}/actions` : `${base}/actions/${encodeURIComponent(c.slot.slice(7))}/status`;
}
function valid(c: ProgressCommand, workspace: string, slot: string) {
  if (!c || c.version !== 1 || c.workspaceId !== workspace || c.slot !== slot || typeof c.commandId !== 'string' || !c.commandId || c.commandId.length > 100
    || !c.body || typeof c.body.actorId !== 'string' || !c.body.actorId || c.body.actorId.length > 200
    || Object.keys(c.body).some(k => !['actorId','idempotencyKey','expectedStatus','newStatus'].includes(k))) return false;
  if (slot === 'create-actions') return typeof c.body.idempotencyKey === 'string' && !!c.body.idempotencyKey && !c.body.expectedStatus && !c.body.newStatus;
  if (slot === 'status') return typeof c.body.idempotencyKey === 'string' && !!c.body.idempotencyKey && workspaceStatuses.includes(c.body.expectedStatus!) && workspaceStatuses.includes(c.body.newStatus!) && c.body.expectedStatus !== c.body.newStatus;
  return slot.startsWith('action:') && slot.length > 7 && !c.body.idempotencyKey && ['todo','in_progress'].includes(c.body.expectedStatus!)
    && (c.body.expectedStatus === 'todo' ? ['in_progress','done','skipped'] : ['done','skipped']).includes(c.body.newStatus!);
}
export function readProgressCommand(store: CommandStorage, workspace: string, slot: string): ProgressCommand | null {
  const raw = store.getItem(key(workspace,slot));
  if (!raw) return null;
  try { const c = JSON.parse(raw); if (raw.length <= 4000 && valid(c,workspace,slot)) return c; } catch {}
  throw new Error('本地原请求无法读取；请刷新核对服务端记录后，再清除本地请求。');
}
export function progressRaw(store: CommandStorage, workspace: string, slot: string) { return store.getItem(key(workspace,slot)); }
export function discardProgressRaw(store: CommandStorage, workspace: string, slot: string, expected: string | null) {
  if (store.getItem(key(workspace,slot)) !== expected) throw new Error('另一个标签页改变了原请求，请重新核对。');
  store.removeItem(key(workspace,slot));
}
export function clearProgressCommand(store: CommandStorage, c: ProgressCommand) {
  const current = readProgressCommand(store,c.workspaceId,c.slot);
  if (current && canonical(current) === canonical(c)) store.removeItem(key(c.workspaceId,c.slot));
}
export async function sendProgressCommand(store: CommandStorage, c: ProgressCommand, fetcher: typeof fetch = fetch) {
  if (!valid(c,c.workspaceId,c.slot)) throw new Error('人工进度请求内容不完整，尚未发送。');
  const previous = readProgressCommand(store,c.workspaceId,c.slot);
  if (previous && canonical(previous) !== canonical(c)) throw new Error('请先核对或重试原请求；不能覆盖保存结果未知的操作。');
  store.setItem(key(c.workspaceId,c.slot),JSON.stringify(c));
  const saved = readProgressCommand(store,c.workspaceId,c.slot);
  if (!saved || canonical(saved) !== canonical(c)) throw new Error('另一个标签页改变了原请求，尚未发送。');
  const response = await fetcher(progressPath(c),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c.body)});
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if ([400,401,403,404,409,422].includes(response.status)) {
      const current = readProgressCommand(store,c.workspaceId,c.slot);
      if (current && canonical(current) === canonical(c)) store.setItem(key(c.workspaceId,c.slot),JSON.stringify({...c,rejected:true}));
    }
    throw new Error(workspaceCommandError(payload,'保存结果未确认，请先刷新核对，再重试原请求。'));
  }
  const matches = (value: unknown): value is {workspaceId: string; actorId?: string; actionId?: string} =>
    typeof value === 'object' && value !== null && 'workspaceId' in value && value.workspaceId === c.workspaceId;
  if (c.slot === 'create-actions' ? !Array.isArray(payload) || !payload.every(matches)
    : !matches(payload) || (c.slot === 'status' && payload.actorId !== c.body.actorId) || (c.slot.startsWith('action:') && payload.actionId !== c.slot.slice(7))) {
    throw new Error('返回结果的身份无法核对；原请求保留，请先刷新查询服务端。');
  }
  clearProgressCommand(store,c);
  return payload;
}
