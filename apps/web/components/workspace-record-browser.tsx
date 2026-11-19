"use client";

import {useId, useRef, useState, type ReactNode} from "react";
import {lastPageOffset} from "@/lib/pagination";
import {Button} from "./ui/button";
import {Pagination} from "./ui/pagination";

export type WorkspaceRecord = {id: string; title: string; summary?: string; content: ReactNode};
const limit = 6;

/** Show just one record while retaining in-progress forms when moving between records. */
export function WorkspaceRecordBrowser({label, records}: {label: string; records: WorkspaceRecord[]}) {
  const detailId = useId();
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelected] = useState("");
  const [showDetail, setShowDetail] = useState(false);
  const actualOffset = Math.min(offset, lastPageOffset(records.length, limit));
  const visibleRecords = records.slice(actualOffset, actualOffset + limit);
  const activeRecord = visibleRecords.find(record => record.id === selectedId) ?? visibleRecords[0];
  const detail = useRef<HTMLDivElement>(null);
  const returnTo = useRef<{element: HTMLButtonElement; scrollTop: number} | null>(null);
  if (!activeRecord) return null;

  return <div className="jl-task-layout" data-show-detail={showDetail}>
    <div className="jl-task-browser">
      {actualOffset !== offset && <p className="jl-callout" role="status">记录已变化，已显示最后一个有效页面。</p>}
      <ul aria-label={label} className="jl-task-rows">{visibleRecords.map(record => <li key={record.id}>
        <button type="button" className="jl-task-row" aria-current={record.id === activeRecord.id ? "true" : undefined}
          aria-controls={detailId} onClick={event => {
            returnTo.current = {element: event.currentTarget, scrollTop: window.scrollY};
            setSelected(record.id); setShowDetail(true);
            requestAnimationFrame(() => {
              if (window.matchMedia("(max-width: 1023px)").matches) detail.current?.focus();
            });
          }}>
          <span><strong>{record.title}</strong>{record.summary && <small>{record.summary}</small>}</span>
        </button>
      </li>)}</ul>
      <Pagination label={`${label}分页`} count={visibleRecords.length} offset={actualOffset} limit={limit}
        total={records.length} onChange={page => {setOffset(page); setShowDetail(false);}} />
    </div>
    <div id={detailId} className="jl-task-detail" ref={detail} tabIndex={-1}>
      <div className="jl-task-back"><Button variant="secondary" onClick={() => {
        setShowDetail(false);
        requestAnimationFrame(() => {
          if (!returnTo.current) return;
          window.scrollTo({top: returnTo.current.scrollTop, behavior: "instant"});
          returnTo.current.element.focus({preventScroll: true});
        });
      }}>返回{label}</Button></div>
      {records.map(record => <div hidden={record.id !== activeRecord.id} key={record.id}>{record.content}</div>)}
    </div>
  </div>;
}
