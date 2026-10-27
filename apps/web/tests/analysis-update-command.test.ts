import test from 'node:test';
import assert from 'node:assert/strict';
import {createUpdateCommand, loadUpdateCommand, sendUpdateCommand, forgetUpdateCommand, updateCommandKey} from '../lib/analysis-update-command';
import type {AnalysisUpdatePlan} from '../lib/contracts';
function storage() {
  const values = new Map<string, string>();
  return {getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => {values.set(k,v);}, removeItem: (k: string) => {values.delete(k);}};
}
const plan = {sourceThreadId: 'old /a', sourceResultId: 'saved', scope: 'targets', inputDigest: 'a'.repeat(64)} as AnalysisUpdatePlan;
function command() {let n = 0; return createUpdateCommand(plan, () => `id-${++n}`);}
test('command is saved before POST and a lost response replays exactly the same body', async () => {
  const db = storage(), c = command();
  const bodies: string[] = [];
  const fetcher = (async (url, options) => {
    assert.equal(url, '/api/career-agent/runs/old%20%2Fa/updates');
    assert.deepEqual(loadUpdateCommand(db, 'old /a', 'targets'), c);
    bodies.push(options?.body as string);
    throw new Error('lost response');
  }) as typeof fetch;
  await assert.rejects(sendUpdateCommand(db, c, fetcher), /lost response/);
  const reloaded = loadUpdateCommand(db, 'old /a', 'targets')!;
  await assert.rejects(sendUpdateCommand(db, reloaded, fetcher), /lost response/);
  assert.equal(bodies[0], bodies[1]);
});
test('unwritable storage never sends, another command cannot replace unresolved request', async () => {
  let calls = 0;
  const fetcher = (async () => {calls++; return new Response('{}');}) as typeof fetch;
  const db = storage(), c = command();
  await assert.rejects(sendUpdateCommand({...db, setItem: () => {throw new Error('quota');}}, c, fetcher), /quota/);
  assert.equal(calls, 0);
  await sendUpdateCommand(db, c, fetcher);
  await assert.rejects(sendUpdateCommand(db, {...c, body: {...c.body, topN: 5}}, fetcher), /待核对/);
  assert.equal(calls, 1);
});
test('malformed journal cannot silently become a new command; clearing does not delete a newer tab request', () => {
  const db = storage(), c = command();
  db.setItem(updateCommandKey('old /a', 'targets'), '{bad');
  assert.throws(() => loadUpdateCommand(db, 'old /a', 'targets'), /无法读取/);
  const newer = {...c, body: {...c.body, requestId: 'different'}};
  db.setItem(updateCommandKey('old /a', 'targets'), JSON.stringify(newer));
  forgetUpdateCommand(db, c);
  assert.deepEqual(loadUpdateCommand(db, 'old /a', 'targets'), newer);
});
