"use client";

import {useLinkStatus} from "next/link";

/** Render inside a Next Link; keeps the label in place while the route responds. */
export function LinkFeedback() {
  const {pending} = useLinkStatus();
  return pending ? <span className="link-feedback" role="status"> · 正在打开…</span> : null;
}
