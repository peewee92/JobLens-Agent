/** Transport recovery only; the run in SQLite is authoritative. */
import type {AnalysisUpdatePlan} from './contracts';
import type {CommandStorage} from './career-agent-commands';
export type UpdateCommand = {version: 1; sourceThreadId: string; body: {
  threadId: string; runId: string; requestId: string; sourceResultId: string;
  scope: 'targets' | 'batch'; inputDigest: string; topN: number;
}};
export function updateCommandKey(source: string, scope: string) {return `joblens.analysisUpdate.${encodeURIComponent(source)}.${scope}`;}
export function loadUpdateCommand(storage: CommandStorage, source: string, scope: string): UpdateCommand | null {
  const raw = storage.getItem(updateCommandKey(source, scope));
  if (raw === null) return null;
  try {
    const c = JSON.parse(raw);
    const b = c?.body;
    if (c.version === 1 && c.sourceThreadId === source && b?.scope === scope
      && [b.threadId, b.runId, b.requestId, b.sourceResultId].every(v => typeof v === 'string' && v.length > 0 && v.length <= 100)
      && /^[a-f0-9]{64}$/.test(b.inputDigest) && Number.isInteger(b.topN) && b.topN >= 1 && b.topN <= 5) return c;
  } catch {}
  throw new Error('本地更新请求无法读取，请先核对最近运行，不能直接创建另一个更新。');
}
export function createUpdateCommand(plan: AnalysisUpdatePlan, uuid: () => string): UpdateCommand {
  return {version: 1, sourceThreadId: plan.sourceThreadId, body: {
    threadId: `update-${uuid()}`, runId: `run-${uuid()}`, requestId: `request-${uuid()}`,
    sourceResultId: plan.sourceResultId, scope: plan.scope, inputDigest: plan.inputDigest, topN: 3,
  }};
}
export async function sendUpdateCommand(storage: CommandStorage, command: UpdateCommand, fetcher: typeof fetch = fetch) {
  const {sourceThreadId: source, body: {scope}} = command;
  const old = loadUpdateCommand(storage, source, scope);
  if (old && JSON.stringify(old) !== JSON.stringify(command)) throw new Error('已有更新请求待核对，请重试原请求。');
  storage.setItem(updateCommandKey(source, scope), JSON.stringify(command));
  if (JSON.stringify(loadUpdateCommand(storage, source, scope)) !== JSON.stringify(command)) throw new Error('更新请求已被其他页面更改，尚未发送。');
  return fetcher(`/api/career-agent/runs/${encodeURIComponent(source)}/updates`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(command.body),
  });
}
export function forgetUpdateCommand(storage: CommandStorage, command: UpdateCommand) {
  const current = loadUpdateCommand(storage, command.sourceThreadId, command.body.scope);
  if (JSON.stringify(current) === JSON.stringify(command)) storage.removeItem(updateCommandKey(command.sourceThreadId, command.body.scope));
}
