"use client";

import {useId, useRef, useState} from "react";
import {actionStatusLabels} from "@/lib/application-actions";
import type {ApplicationExecutionAction} from "@/lib/contracts";
import {lastPageOffset} from "@/lib/pagination";
import {ApplicationActionControls} from "./application-action-controls";
import {Button} from "./ui/button";
import {Pagination} from "./ui/pagination";
import {Badge} from "./ui/primitives";
import type {ReactNode} from "react";

type Item = {action: ApplicationExecutionAction; detail: ReactNode};
const filters = [["all", "全部"], ["open", "待处理"], ["done", "已完成"], ["skipped", "已跳过"]] as const;
type Filter = (typeof filters)[number][0];
function matches(action: ApplicationExecutionAction, filter: Filter) {
  return filter === "all" || (filter === "open" && ["todo", "in_progress"].includes(action.status)) || action.status === filter;
}
const limit = 6;
export function WorkspaceTaskList({items, workspaceId, actorId}: {items: Item[]; workspaceId: string; actorId: string}) {
  const radioGroup = useId();
  const [filter, setFilter] = useState<Filter>("all");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string>();
  const [showDetail, setShowDetail] = useState(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const savedScroll = useRef(0);
  const detailTitle = useRef<HTMLHeadingElement | null>(null);
  const matched = items.filter(({action}) => matches(action, filter));
  const actualOffset = Math.min(offset, lastPageOffset(matched.length, limit));
  const visible = matched.slice(actualOffset, actualOffset + limit);
  const item = visible.find(({action}) => action.actionId === selected) ?? visible[0];
  const selectedId = item?.action.actionId;
  function setCategory(value: Filter) {
    setFilter(value);
    setOffset(0);
    setShowDetail(false);
    setSelected(undefined);
  }

  function display(id: string, button: HTMLButtonElement) {
    trigger.current = button;
    savedScroll.current = window.scrollY;
    setSelected(id);
    setShowDetail(true);
    requestAnimationFrame(() => {
      // On wide screens the list remains present; keep focus on the selected row.
      if (window.matchMedia("(max-width: 1023px)").matches) detailTitle.current?.focus();
    });
  }

  return <div className="jl-task-layout" data-show-detail={showDetail && Boolean(item)}>
    <div className="jl-task-browser">
      <fieldset className="jl-filter-options">
        <legend className="sr-only">按行动状态筛选</legend>
        <div className="jl-choice-group">
          {filters.map(([value, label]) => <label key={value}>
            <input name={radioGroup} type="radio" checked={filter === value} onChange={() => setCategory(value)} />
            <span>{label} {items.filter(({action}) => matches(action, value)).length}</span>
          </label>)}
        </div>
      </fieldset>
      {visible.length === 0 ? <div className="jl-callout stack-sm" role="status">
        <h3>没有符合条件的行动</h3><p>现有行动没有改变，可以清除筛选后继续查看。</p>
        <div><Button variant="secondary" onClick={() => setCategory("all")}>清除筛选</Button></div>
      </div> : <>
        {actualOffset !== offset && <p role="status" className="jl-callout">记录有变化，已显示最后一个有效页面。</p>}
        <ul className="jl-task-rows">
          {visible.map(({action}) => <li key={action.actionId}>
            <button type="button" className="jl-task-row" aria-current={selectedId === action.actionId ? "true" : undefined}
              onClick={event => display(action.actionId, event.currentTarget)}>
              <span><strong>{action.sourceGapCapability ?? action.description}</strong>
                {action.sourceGapCapability && <small>{action.description}</small>}</span>
              <Badge tone={action.status === "done" ? "success" : "neutral"}>{actionStatusLabels[action.status] ?? "待核对"}</Badge>
            </button>
          </li>)}
        </ul>
        <Pagination label="行动分页" offset={actualOffset} count={visible.length} limit={limit} total={matched.length}
          onChange={value => {setOffset(value); setShowDetail(false); setSelected(undefined);}} />
      </>}
    </div>
    {item && <article key={item.action.actionId} className="jl-task-detail stack-md">
      <div className="jl-task-back"><Button variant="secondary" onClick={() => {
        setShowDetail(false);
        requestAnimationFrame(() => {
          window.scrollTo({top: savedScroll.current, behavior: "instant"});
          trigger.current?.focus({preventScroll: true});
        });
      }}>返回行动列表</Button></div>
      <header><Badge tone="info">{actionStatusLabels[item.action.status] ?? "待核对"}</Badge>
        <h3 tabIndex={-1} ref={detailTitle}>{item.action.sourceGapCapability ?? item.action.description}</h3>
        {item.action.sourceGapCapability && <p>{item.action.description}</p>}</header>
      <ApplicationActionControls workspaceId={workspaceId} actorId={actorId} actions={[item.action]} />
      {item.detail}
    </article>}
  </div>;
}
