import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readUpdateBatch, sendUpdateBatch, clearUpdateBatch, type UpdateBatchCommand} from '../lib/update-batch-command';
import {UpdateMatchProgress} from '../components/update-match-progress';
import type {CareerAgentRunState} from '../lib/contracts';
function storage() {
  const map = new Map<string,string>();
  return {getItem: (k: string) => map.get(k) ?? null, setItem: (k: string,v: string) => {map.set(k,v);}, removeItem: (k: string) => {map.delete(k);}};
}
const command: UpdateBatchCommand = {threadId: 'updated /a', body: {actionId: 'continue', expectedRevision: 12, useCompletedOnly: false}};
test('bounded continue saves before sending and retains identical content after a lost response', async () => {
  const db = storage(), bodies: unknown[] = [];
  const fetcher = (async (url, options) => {
    assert.equal(url, '/api/career-agent/runs/updated%20%2Fa/continue');
    assert.deepEqual(readUpdateBatch(db, command.threadId), command);
    bodies.push(options?.body);
    throw new Error('lost response');
  }) as typeof fetch;
  await assert.rejects(sendUpdateBatch(db, command, fetcher), /lost response/);
  await assert.rejects(sendUpdateBatch(db, readUpdateBatch(db, command.threadId)!, fetcher), /lost response/);
  assert.equal(bodies[0], bodies[1]);
  await assert.rejects(sendUpdateBatch(db, {...command, body: {...command.body, useCompletedOnly: true}}, fetcher), /原分批请求/);
  assert.equal(bodies.length, 2);
});
test('storage failure sends zero requests; clearing old command preserves a newer one', async () => {
  const db = storage(); let sent = 0;
  const fetcher = (async () => {sent++; return new Response('{}');}) as typeof fetch;
  await assert.rejects(sendUpdateBatch({...db, setItem: () => {throw new Error('quota');}}, command, fetcher), /quota/);
  assert.equal(sent, 0);
  const newer = {...command, body: {...command.body, actionId: 'newer'}};
  await sendUpdateBatch(db, newer, fetcher);
  clearUpdateBatch(db, command);
  assert.deepEqual(readUpdateBatch(db, command.threadId), newer);
});
test('progress explains actual partial results and requires explicit continuation', () => {
  const run = {threadId: 'thread', status: 'running', currentStep: 'update_matching', revision: 4, updatePartial: true,
    updateSteps: [
      {jobId: 'job1', extractionId: 'e1', status: 'completed', reportId: 'm1', attempt: 1, errorCode: null},
      {jobId: 'job2', extractionId: 'e2', status: 'requires_model', reportId: null, attempt: 0, errorCode: 'model_authorization_required'},
    ]} as CareerAgentRunState;
  const html = renderToStaticMarkup(React.createElement(UpdateMatchProgress, {run, onState: () => {}, jobTitles: {job1: '目标工程师'}}));
  for (const label of ['1 / 2', '目标工程师', '已重算保存', '需要单独模型授权', '未完成项不计入本次结果', '最多 5 个', '仅使用已完成的 1 个岗位']) assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /全部岗位已完成/);
});
