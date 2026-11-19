import React from "react";
import type {Workbench} from "@/lib/workbench";

export function FirstUseSteps({snapshot}: {snapshot: Workbench["snapshot"]}) {
  const profileReady = snapshot.inputIssueCodes.length === 0;
  const jobsAdded = snapshot.jobCount > 0;
  const prepared = snapshot.currentRun?.status === "completed" && snapshot.currentRun.resultIsCurrent === true;
  const current = !profileReady ? 0 : !jobsAdded ? 1 : !prepared ? 2 : -1;
  const steps = [
    {title: "确认资料", hint: "上传简历或手填经历，确认你想找的岗位。", done: profileReady},
    {title: "添加岗位", hint: "先粘贴招聘描述；比较前，在对应岗位核对要求。", done: jobsAdded},
    {title: "比较并准备", hint: "查看有依据的诊断，确认目标并开始准备。", done: prepared},
  ];
  return <nav aria-label="首次使用三步" className="jl-first-use">
    <ol className="jl-phase">{steps.map((step, index) =>
      <li key={step.title} aria-current={index === current ? "step" : undefined}>
        <span className="jl-phase-number" aria-hidden="true">{index + 1}</span>
        <div><strong>{step.title}</strong>
        <small>{index === current ? "当前步骤" : step.done ? "已完成" : "待开始"}</small></div>
        <p>{step.hint}</p>
      </li>
    )}</ol>
  </nav>;
}
