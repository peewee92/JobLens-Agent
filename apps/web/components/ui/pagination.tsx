import {Fragment} from "react";
import Link from "next/link";
import {pageWindow} from "@/lib/pagination";

type Props = {
  label?: string; offset: number; limit: number; count: number; total?: number; hasMore?: boolean;
} & ({href: (offset: number) => string; onChange?: never} | {href?: never; onChange: (offset: number) => void});

export function Pagination({label = "分页", offset, limit, count, total, hasMore, href, onChange}: Props) {
  const {current, last, numbers} = pageWindow(offset, limit, total);
  const previous = offset > 0;
  const next = last === undefined ? Boolean(hasMore) : current < last;
  if (total === 0 || (!count && !previous && !next)) return null;
  const button = (to: number, text: string, name = text) => href
    ? <Link href={href(to)} aria-label={name} className="jl-page-button" prefetch={false}>{text}</Link>
    : <button type="button" aria-label={name} className="jl-page-button" onClick={() => onChange?.(to)}>{text}</button>;
  return <nav aria-label={label} className="jl-pager">
    <span className="jl-page-range" aria-live="polite">
      {total === undefined ? `第 ${current} 页 · 本页 ${count} 条` : `第 ${offset + 1}–${offset + count} 条，共 ${total} 条`}
    </span>
    {(previous || next) && <div className="jl-page-controls">
      {previous ? button(Math.max(0, offset - limit), "上一页") : <span className="jl-page-direction" aria-disabled="true">上一页</span>}
      {numbers.map((page, index) => <Fragment key={page}>
        {index > 0 && page - numbers[index - 1] > 1 && <span className="jl-page-number" aria-hidden="true">…</span>}
        <span className="jl-page-number">{page === current ? <span className="jl-page-current" aria-current="page" aria-label={`第 ${page} 页`}>{page}</span>
          : button((page - 1) * limit, String(page), `第 ${page} 页`)}</span>
      </Fragment>)}
      {next ? button(offset + limit, "下一页") : <span className="jl-page-direction" aria-disabled="true">下一页</span>}
    </div>}
  </nav>;
}
