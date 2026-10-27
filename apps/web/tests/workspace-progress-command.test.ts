import test from 'node:test';
import assert from 'node:assert/strict';
import {readProgressCommand,sendProgressCommand,clearProgressCommand,progressRaw,discardProgressRaw,progressPath,type ProgressCommand} from '../lib/workspace-progress-command';
function storage() { const values=new Map<string,string>(); return {getItem:(k:string)=>values.get(k)??null,setItem:(k:string,v:string)=>{values.set(k,v);},removeItem:(k:string)=>{values.delete(k);}}; }
const status:ProgressCommand={version:1,workspaceId:'workspace',slot:'status',commandId:'first',body:{actorId:'local-user',idempotencyKey:'original',expectedStatus:'preparing',newStatus:'applied'}};
const action:ProgressCommand={...status,slot:'action:action a',body:{actorId:'local-user',expectedStatus:'in_progress',newStatus:'done'}};
for(const c of [status,action]) test(`${c.slot} preserves original before send and reads after lost response with zero automatic sends`,async()=>{
  const store=storage(); let calls=0; const bodies:string[]=[];
  const send:typeof fetch=async(path,init)=>{calls++;assert.equal(path,progressPath(c));assert.deepEqual(readProgressCommand(store,c.workspaceId,c.slot),c); bodies.push(init!.body as string);
    if(calls===1) throw new Error('response lost after commit');
    return Response.json({workspaceId:c.workspaceId,...(c.slot === 'status' ? {actorId:c.body.actorId} : {}),actionId:'action a',status:c.body.newStatus});};
  await assert.rejects(sendProgressCommand(store,c,send),/response lost/);
  const restored=readProgressCommand(store,c.workspaceId,c.slot)!;assert.equal(calls,1);
  await assert.rejects(sendProgressCommand(store,{...c,commandId:'other'},send),/不能覆盖/);assert.equal(calls,1);
  await sendProgressCommand(store,restored,send); assert.equal(calls,2);assert.equal(bodies[0],bodies[1]);assert.equal(readProgressCommand(store,c.workspaceId,c.slot),null);
});
test('failed storage sends zero requests, malformed content and foreign identities never clear a request',async()=>{
  const store=storage();let calls=0; const send:typeof fetch=async()=>{calls++;return Response.json({workspaceId:'foreign',actorId:'local-user'});};
  await assert.rejects(sendProgressCommand({...store,setItem:()=>{throw new Error('quota');}},status,send),/quota/);assert.equal(calls,0);
  await assert.rejects(sendProgressCommand(store,{...status,body:{...status.body,newStatus:'invented'}},send),/尚未发送/);assert.equal(calls,0);
  await assert.rejects(sendProgressCommand(store,status,send),/身份无法核对/);assert.ok(readProgressCommand(store,'workspace','status'));
  await assert.rejects(sendProgressCommand(store,status,async()=>new Response('not json')),/身份无法核对/);assert.ok(readProgressCommand(store,'workspace','status'));
});
test('503 remains unknown; 409 explicitly rejected but still blocks replacement until reviewed',async()=>{
  const store=storage();
  await assert.rejects(sendProgressCommand(store,status,async()=>Response.json({}, {status:503})),/保存结果未确认/);
  assert.equal(readProgressCommand(store,'workspace','status')!.rejected,undefined);
  await assert.rejects(sendProgressCommand(store,status,async()=>Response.json({detail:'application_status_conflict'},{status:409})),/投递状态已被其他操作更新/);
  assert.equal(readProgressCommand(store,'workspace','status')!.rejected,true);
  const raw=progressRaw(store,'workspace','status');discardProgressRaw(store,'workspace','status',raw);assert.equal(readProgressCommand(store,'workspace','status'),null);
});
test('different resource journals do not collide; clearing old request never removes newer command',async()=>{
  const store=storage();
  for(const c of [status,action]) await assert.rejects(sendProgressCommand(store,c,async()=>{throw new Error('lost');}),/lost/);
  assert.ok(readProgressCommand(store,'workspace','status'));assert.ok(readProgressCommand(store,'workspace','action:action a'));
  const raw=progressRaw(store,'workspace','status');clearProgressCommand(store,status);
  const newer={...status,commandId:'newer',body:{...status.body,idempotencyKey:'newer'}};
  await assert.rejects(sendProgressCommand(store,newer,async()=>{throw new Error('lost');}),/lost/);
  clearProgressCommand(store,status); assert.equal(readProgressCommand(store,'workspace','status')!.commandId,'newer');
  assert.throws(()=>discardProgressRaw(store,'workspace','status',raw),/另一个标签页/);
});
test('creation is identity-checked and path-safe, unknown command data is not executed',async()=>{
  const store=storage(); const c:ProgressCommand={...status,workspaceId:'w /',slot:'create-actions',body:{actorId:'local-user',idempotencyKey:'create'}};
  assert.equal(progressPath(c),'/api/application-workspaces/w%20%2F/actions');
  await sendProgressCommand(store,c,async()=>Response.json([]));assert.equal(readProgressCommand(store,c.workspaceId,c.slot),null);
  await assert.rejects(sendProgressCommand(store,{...c,slot:'unexpected'},async()=>{throw new Error('must not send');}),/尚未发送/);
});
