import test from 'node:test';
import assert from 'node:assert/strict';
import {createInitialScopeCommand, loadInitialScopeCommand, sendInitialScopeCommand, forgetInitialScopeCommand} from '../lib/initial-scope-command';
import {initialScopeAnalysisHref, parseAgentScope} from '../lib/agent-job-scope';
import type {InitialScopePlan} from '../lib/contracts';
const plan = {items: [{jobId:'job /a'}, {jobId:'job-b'}], inputDigest: 'a'.repeat(64)} as InitialScopePlan;
function storage() {
  const values = new Map<string,string>();
  return {getItem:(k:string)=>values.get(k)??null, setItem:(k:string,v:string)=>{values.set(k,v);}, removeItem:(k:string)=>{values.delete(k);}};
}
function command() {let n=0; return createInitialScopeCommand(plan,()=>String(++n));}
test('initial analysis preserves scope in local URL and stores the command before sending', async () => {
  const href = new URL(initialScopeAnalysisHref(['job /a','job-b']), 'http://local.test');
  assert.equal(href.pathname, '/agent/analyze');
  assert.deepEqual(parseAgentScope(href.searchParams.getAll('scopeJobId')), ['job /a','job-b']);
  const db=storage(), c=command(), bodies:string[]=[];
  const fetcher=(async (url, init)=>{
    assert.equal(url,'/api/career-agent/initial-scope-runs');
    assert.deepEqual(loadInitialScopeCommand(db,['job-b','job /a']),c);
    bodies.push(init?.body as string); throw new Error('lost response');
  }) as typeof fetch;
  await assert.rejects(sendInitialScopeCommand(db,c,fetcher),/lost response/);
  const loaded=loadInitialScopeCommand(db,['job-b','job /a'])!;
  await assert.rejects(sendInitialScopeCommand(db,loaded,fetcher),/lost response/);
  assert.equal(bodies[0],bodies[1]);
});
test('unwritable storage and another pending command cannot send a new request',async()=>{
  const db=storage(), c=command(); let calls=0;
  const fetcher=(async()=>{calls++; return new Response('{}');}) as typeof fetch;
  await assert.rejects(sendInitialScopeCommand({...db,setItem:()=>{throw new Error('quota');}},c,fetcher),/quota/);
  assert.equal(calls,0);
  await sendInitialScopeCommand(db,c,fetcher);
  await assert.rejects(sendInitialScopeCommand(db,{...c,body:{...c.body,topN:5}},fetcher),/待核对/);
  assert.equal(calls,1);
  const newer={...c,body:{...c.body,requestId:'newer'}};
  db.setItem(`joblens.initialAnalysis.${encodeURIComponent(JSON.stringify([...c.body.jobIds].sort()))}`,JSON.stringify(newer));
  forgetInitialScopeCommand(db,c);
  assert.deepEqual(loadInitialScopeCommand(db,c.body.jobIds),newer);
});
test('corrupt or substituted local scope is not silently replaced',()=>{
  const db=storage(), c=command();
  const key=`joblens.initialAnalysis.${encodeURIComponent(JSON.stringify([...c.body.jobIds].sort()))}`;
  db.setItem(key,'{bad'); assert.throws(()=>loadInitialScopeCommand(db,c.body.jobIds),/无法读取/);
  db.setItem(key,JSON.stringify({...c,body:{...c.body,jobIds:['different']}}));
  assert.throws(()=>loadInitialScopeCommand(db,c.body.jobIds),/无法读取/);
});
