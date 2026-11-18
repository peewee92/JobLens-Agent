import React, {type ComponentProps, type ReactNode} from "react";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export function Panel({className = "", ...props}: ComponentProps<"section">) {
  return <section className={`jl-panel ${className}`} {...props} />;
}

export function Badge({tone = "neutral", children}: {tone?: Tone; children: ReactNode}) {
  return <span data-tone={tone} className="jl-badge">{children}</span>;
}

export function Callout({tone = "neutral", className = "", ...props}: ComponentProps<"div"> & {tone?: Tone}) {
  return <div data-tone={tone} className={`jl-callout ${className}`} {...props} />;
}

export function Field({id, label, hint, error, children}: {id: string; label: string; hint?: string; error?: string; children: ReactNode}) {
  return <div className="jl-field">
    <label htmlFor={id}>{label}</label>
    {hint && <p id={`${id}-hint`}>{hint}</p>}
    {children}
    {error && <p id={`${id}-error`} className="jl-field-error">{error}</p>}
  </div>;
}

export function Skeleton({className = ""}: {className?: string}) {
  return <span aria-hidden="true" className={`jl-skeleton ${className}`} />;
}

export function Table({children, label}: {children: ReactNode; label: string}) {
  return <div className="jl-table-scroll" role="region" aria-label={label} tabIndex={0}>
    <table className="jl-table">{children}</table>
  </div>;
}
