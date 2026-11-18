"use client";

import {useState} from "react";
import {ManualJobForm} from "./manual-job-form";
import {PastedJobsForm} from "./pasted-jobs-form";

export function ManualImportChoices() {
  const [batch, setBatch] = useState(false);
  return <>
    <div className="button-row" aria-label="手动添加方式">
      <button className="button-secondary" type="button" aria-pressed={!batch} onClick={() => setBatch(false)}>逐条填写</button>
      <button className="button-secondary" type="button" aria-pressed={batch} onClick={() => setBatch(true)}>批量粘贴文本</button>
    </div>
    <div hidden={batch}><ManualJobForm /></div>
    <div hidden={!batch}><PastedJobsForm /></div>
  </>;
}
