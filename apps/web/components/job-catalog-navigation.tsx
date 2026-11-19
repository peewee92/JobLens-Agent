"use client";

import Link from "next/link";
import {useEffect, type ReactNode} from "react";

const scrollKey = (id: string) => `joblens.catalog-return:${id}`;

export function OpenCatalogJob({href, rowId, fromOriginal = false, children, ...props}: {
  href: string; rowId: string; fromOriginal?: boolean; children: ReactNode; id?: string;
}) {
  return <Link {...props} href={href} onClick={event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    try {
      sessionStorage.setItem(scrollKey(rowId), JSON.stringify({
        path: window.location.pathname + window.location.search,
        top: window.scrollY,
        fromOriginal,
      }));
    } catch { /* Returning to the row does not require storage. */ }
  }}>{children}</Link>;
}

export function RestoreCatalogPosition() {
  useEffect(() => {
    const rowId = window.location.hash.slice(1);
    if (!rowId.startsWith("saved-job-")) return;
    const frame = requestAnimationFrame(() => {
      const title = document.getElementById(rowId);
      const fallback = document.getElementById("job-list-heading");
      if (!title) {
        fallback?.focus();
        return;
      }
      let record: {path?: string; top?: number; fromOriginal?: boolean} | null = null;
      try {
        record = JSON.parse(sessionStorage.getItem(scrollKey(rowId)) ?? "null");
        sessionStorage.removeItem(scrollKey(rowId));
      } catch { /* Use the located row when storage is unavailable. */ }
      if (record?.path === window.location.pathname + window.location.search
        && typeof record.top === "number" && Number.isFinite(record.top)) {
        window.scrollTo({top: record.top, behavior: "instant"});
        (record.fromOriginal ? document.getElementById(`${rowId}-original`) ?? title : title).focus({preventScroll: true});
      } else {
        title.focus({preventScroll: true});
        title.scrollIntoView({block: "center", behavior: "instant"});
      }
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  return null;
}
