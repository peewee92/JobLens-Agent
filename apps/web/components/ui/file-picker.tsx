"use client";

import {useId, useRef, type ReactNode} from "react";
import {Button} from "./button";

export function FilePicker({name, title, hint, accept, disabled, invalid, file, onSelect}: {
  name?: string; title: string; hint: string; accept: string; disabled?: boolean; invalid?: boolean;
  file: File | null; onSelect: (file: File | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const mark: ReactNode = <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10z" /><path d="M13 3v7h7M8 15h8m-8 3h5" />
  </svg>;
  return <div className="jl-file-picker" data-invalid={invalid || undefined}>
    <div className="jl-file-mark">{mark}</div>
    <div className="jl-file-copy">
      <strong>{title}</strong>
      <p id={hintId}>{hint}</p>
      <p role="status" className="jl-file-name">{file ? `已选择：${file.name} · ${Math.ceil(file.size / 1024)} KiB` : "还没选择文件"}</p>
    </div>
    <input hidden ref={input} type="file" name={name} accept={accept} disabled={disabled} onChange={event => {
      const value = event.target.files?.[0] ?? null;
      onSelect(value);
      if (!name) event.target.value = "";
    }} />
    <Button variant="secondary" aria-describedby={hintId} aria-label={file ? `更换：${title}` : `选择：${title}`}
      aria-invalid={invalid} disabled={disabled} onClick={() => input.current?.click()}>{file ? "更换文件" : "选择文件"}</Button>
  </div>;
}
