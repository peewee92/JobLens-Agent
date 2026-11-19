"use client";

import {useState, type ReactNode} from "react";
import {lastPageOffset} from "@/lib/pagination";
import {Pagination} from "./ui/pagination";

export function PagedRecords({items, label, limit, ordered = false}: {items: ReactNode[]; label: string; limit: number; ordered?: boolean}) {
  const [requestedOffset, setOffset] = useState(0);
  const offset = Math.min(requestedOffset, lastPageOffset(items.length, limit));
  const visible = items.slice(offset, offset + limit);
  const Container = ordered ? "ol" : "ul";
  return <>
    {requestedOffset !== offset && <p role="status" className="jl-callout">记录有变化，已显示最后一个有效页面。</p>}
    <Container aria-label={label} className="jl-records">{visible.map((item, index) => <li key={offset + index}>{item}</li>)}</Container>
    <Pagination label={`${label}分页`} offset={offset} count={visible.length} limit={limit} total={items.length} onChange={setOffset} />
  </>;
}
