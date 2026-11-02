import assert from 'node:assert/strict';
import test from 'node:test';
import {loadLegacyAnalysis, sendLegacyAnalysis, type LegacyAnalysisCommand} from '../lib/legacy-analysis-command';
const command: LegacyAnalysisCommand = {version: 1, workspaceId: 'space /1', body: {threadId: 'thread', runId: 'run', requestId: 'req', inputDigest: 'a'.repeat(64)}};
function storage() {const m = new Map<string, string>(); return {getItem: (k: string) => m.get(k) ?? null, setItem: (k: string,v: string) => {m.set(k,v);}, removeItem: (k: string) => {m.delete(k);}};}
test('lost response is retried with same persisted command; refresh never sends', async () => {
  const db = storage(), bodies: string[] = [];
  const fetcher = (async (url: string | URL | Request, init?: RequestInit) => {assert.equal(url, '/api/application-workspaces/space%20%2F1/analysis-runs'); bodies.push(init?.body as string); throw Error('lost');}) as typeof fetch;
  await assert.rejects(sendLegacyAnalysis(db, command, fetcher), /lost/);
  const original = loadLegacyAnalysis(db, command.workspaceId)!;
  assert.equal(bodies.length, 1);
  await assert.rejects(sendLegacyAnalysis(db, original, fetcher), /lost/);
  assert.equal(bodies[0], bodies[1]);
});
test('unwritable storage or conflicting request cannot send', async () => {
  const db = storage(); let calls = 0;
  const fetcher = (async () => {calls++; return new Response('{}');}) as typeof fetch;
  await assert.rejects(sendLegacyAnalysis({...db, setItem: () => {throw Error('quota');}}, command, fetcher), /quota/);
  assert.equal(calls, 0);
  await sendLegacyAnalysis(db, command, fetcher);
  await assert.rejects(sendLegacyAnalysis(db, {...command, body: {...command.body, inputDigest:'b'.repeat(64)}}, fetcher), /待核对/);
  assert.equal(calls, 1);
});
