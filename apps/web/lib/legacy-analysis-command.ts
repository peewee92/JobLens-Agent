import type {CommandStorage} from './career-agent-commands';
import type {LegacyWorkspaceAnalysisPlan} from './contracts';
export type LegacyAnalysisCommand = {version: 1; workspaceId: string; body: {
  threadId: string; runId: string; requestId: string; inputDigest: string;
}};
const key = (id: string) => `joblens.legacyAnalysis.${encodeURIComponent(id)}`;
export function loadLegacyAnalysis(storage: CommandStorage, workspaceId: string): LegacyAnalysisCommand | null {
  const raw = storage.getItem(key(workspaceId));
  if (raw === null) return null;
  try {
    const c = JSON.parse(raw), b = c?.body;
    if (c.version === 1 && c.workspaceId === workspaceId &&
      [b?.threadId, b?.runId, b?.requestId].every(v => typeof v === 'string' && v.length > 0 && v.length <= 100) &&
      /^[a-f0-9]{64}$/.test(b?.inputDigest)) return c;
  } catch {}
  throw new Error('本地请求无法读取，请先核对最近运行，不能直接创建另一份。');
}
export function createLegacyAnalysis(plan: LegacyWorkspaceAnalysisPlan, uuid: () => string): LegacyAnalysisCommand {
  return {version: 1, workspaceId: plan.workspaceId, body: {threadId: `legacy-${uuid()}`, runId: `run-${uuid()}`,
    requestId: `request-${uuid()}`, inputDigest: plan.inputDigest}};
}
export async function sendLegacyAnalysis(storage: CommandStorage, command: LegacyAnalysisCommand, fetcher: typeof fetch = fetch) {
  const old = loadLegacyAnalysis(storage, command.workspaceId);
  if (old && JSON.stringify(old) !== JSON.stringify(command)) throw new Error('已有请求待核对，请重试原请求。');
  storage.setItem(key(command.workspaceId), JSON.stringify(command));
  if (JSON.stringify(loadLegacyAnalysis(storage, command.workspaceId)) !== JSON.stringify(command)) throw new Error('请求已被其他页面更改，尚未发送。');
  return fetcher(`/api/application-workspaces/${encodeURIComponent(command.workspaceId)}/analysis-runs`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(command.body),
  });
}
export function forgetLegacyAnalysis(storage: CommandStorage, command: LegacyAnalysisCommand) {
  if (JSON.stringify(loadLegacyAnalysis(storage, command.workspaceId)) === JSON.stringify(command)) storage.removeItem(key(command.workspaceId));
}
