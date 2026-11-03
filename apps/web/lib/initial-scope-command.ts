/** Delivery receipt only; durable execution and idempotency remain in the backend. */
import type {InitialScopePlan} from './contracts';
import type {CommandStorage} from './career-agent-commands';
import {parseAgentScope} from './agent-job-scope';
export type InitialScopeCommand = {version: 1; body: {
  threadId: string; runId: string; requestId: string; jobIds: string[]; inputDigest: string; topN: number;
}};
const scopeKey = (ids: readonly string[]) => `joblens.initialAnalysis.${encodeURIComponent(JSON.stringify([...ids].sort()))}`;
const sameScope = (a: readonly string[], b: readonly string[]) => scopeKey(a) === scopeKey(b);
export function loadInitialScopeCommand(storage: CommandStorage, ids: readonly string[]): InitialScopeCommand | null {
  const raw = storage.getItem(scopeKey(ids));
  if (raw === null) return null;
  try {
    const c = JSON.parse(raw), b = c?.body;
    if (c.version === 1 && Array.isArray(b?.jobIds) && b.jobIds.every((id: unknown) => typeof id === 'string') && parseAgentScope(b.jobIds)
      && sameScope(b.jobIds, ids) && [b.threadId, b.runId, b.requestId].every(v => typeof v === 'string' && v.trim() && v.length <= 100)
      && typeof b.inputDigest === 'string' && /^[a-f0-9]{64}$/.test(b.inputDigest)
      && Number.isInteger(b.topN) && b.topN >= 1 && b.topN <= 5) return c;
  } catch {}
  throw new Error('本地分析请求无法读取，请先核对最近运行，不能直接创建另一次分析。');
}
export function createInitialScopeCommand(plan: InitialScopePlan, uuid: () => string): InitialScopeCommand {
  const ids = plan.items.map(item => item.jobId);
  if (!parseAgentScope(ids)) throw new Error('岗位范围无效，请返回重新选择。');
  return {version: 1, body: {threadId: `analysis-${uuid()}`, runId: `run-${uuid()}`, requestId: `request-${uuid()}`,
    jobIds: ids, inputDigest: plan.inputDigest, topN: 3}};
}
export async function sendInitialScopeCommand(storage: CommandStorage, command: InitialScopeCommand, fetcher: typeof fetch = fetch) {
  const old = loadInitialScopeCommand(storage, command.body.jobIds);
  if (old && JSON.stringify(old) !== JSON.stringify(command)) throw new Error('已有请求待核对，请重试原请求。');
  storage.setItem(scopeKey(command.body.jobIds), JSON.stringify(command));
  if (JSON.stringify(loadInitialScopeCommand(storage, command.body.jobIds)) !== JSON.stringify(command)) throw new Error('请求已被其他页面更改，尚未发送。');
  return fetcher('/api/career-agent/initial-scope-runs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(command.body)});
}
export function forgetInitialScopeCommand(storage: CommandStorage, command: InitialScopeCommand) {
  if (JSON.stringify(loadInitialScopeCommand(storage, command.body.jobIds)) === JSON.stringify(command)) storage.removeItem(scopeKey(command.body.jobIds));
}
