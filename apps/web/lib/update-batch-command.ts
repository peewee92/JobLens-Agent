/** A pending transport command, never a second business progress store. */
import type {CommandStorage} from './career-agent-commands';
export type UpdateBatchCommand = {threadId: string; body: {actionId: string; expectedRevision: number; useCompletedOnly: boolean}};
const key = (id: string) => `joblens.updateBatch.${encodeURIComponent(id)}`;
export function readUpdateBatch(storage: CommandStorage, threadId: string): UpdateBatchCommand | null {
  const raw = storage.getItem(key(threadId));
  if (!raw) return null;
  try {
    const c = JSON.parse(raw);
    if (c.threadId === threadId && typeof c.body?.actionId === 'string' && c.body.actionId.length > 0 && c.body.actionId.length <= 100
      && Number.isInteger(c.body.expectedRevision) && c.body.expectedRevision >= 0 && typeof c.body.useCompletedOnly === 'boolean') return c;
  } catch {}
  throw new Error('原分批请求无法读取，请先查看服务端运行，不要直接创建新请求。');
}
export function clearUpdateBatch(storage: CommandStorage, command: UpdateBatchCommand) {
  if (JSON.stringify(readUpdateBatch(storage, command.threadId)) === JSON.stringify(command)) storage.removeItem(key(command.threadId));
}
export async function sendUpdateBatch(storage: CommandStorage, command: UpdateBatchCommand, fetcher: typeof fetch = fetch) {
  const prior = readUpdateBatch(storage, command.threadId);
  if (prior && JSON.stringify(prior) !== JSON.stringify(command)) throw new Error('请先核对或重试原分批请求。');
  storage.setItem(key(command.threadId), JSON.stringify(command));
  if (JSON.stringify(readUpdateBatch(storage, command.threadId)) !== JSON.stringify(command)) throw new Error('分批请求已变化，尚未发送。');
  return fetcher(`/api/career-agent/runs/${encodeURIComponent(command.threadId)}/continue`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(command.body),
  });
}
