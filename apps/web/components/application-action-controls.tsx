'use client';
import React from 'react';
import {useProgressRequest} from './workspace-progress-recovery';
import type {ApplicationExecutionAction} from '@/lib/contracts';
const nextStatus: Record<string,{status:string;label:string}|undefined> = {
  todo:{status:'in_progress',label:'开始行动'}, in_progress:{status:'done',label:'标记完成'},
};
function ActionStatus({workspaceId,actorId,action}: {workspaceId:string;actorId:string;action:ApplicationExecutionAction}) {
  const request = useProgressRequest(workspaceId,`action:${action.actionId}`);
  const transition = nextStatus[action.status];
  return <>{request.recovery}{transition && <div className="actions" style={{marginTop:8}}>
    <button className="button-secondary" disabled={request.disabled} onClick={() => void request.send({actorId,expectedStatus:action.status,newStatus:transition.status})}>
      {request.busy ? '正在更新…' : `${transition.label}：${action.sourceGapCapability ?? action.description}`}
    </button></div>}</>;
}
function CreateActions({workspaceId,actorId,showButton}: {workspaceId:string;actorId:string;showButton:boolean}) {
  const request = useProgressRequest(workspaceId,'create-actions');
  return <>{request.recovery}{showButton && <div className="actions"><button className="button" disabled={request.disabled}
    onClick={() => void request.send({actorId,idempotencyKey:`web-study-actions-${workspaceId}`})}>
    {request.busy ? '正在建立…' : '把学习清单建立为行动'}</button></div>}</>;
}
export function ApplicationActionControls({workspaceId,actorId,actions}: {workspaceId:string;actorId:string;actions:ApplicationExecutionAction[]}) {
  return <><CreateActions workspaceId={workspaceId} actorId={actorId} showButton={!actions.length} />{actions.map(action => <ActionStatus key={action.actionId} workspaceId={workspaceId} actorId={actorId} action={action} />)}</>;
}
