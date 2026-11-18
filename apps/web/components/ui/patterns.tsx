import React, {type ReactNode} from "react";
import {Callout, Panel, type Tone} from "./primitives";

export function PageHeading({kicker, title, description}: {kicker?: string; title: string; description?: string}) {
  return <header className="jl-page-heading">
    {kicker && <p className="jl-kicker">{kicker}</p>}
    <h1>{title}</h1>
    {description && <p className="jl-description">{description}</p>}
  </header>;
}

export function EmptyState({title, description, actions}: {title: string; description: string; actions?: ReactNode}) {
  return <Panel>
    <h2>{title}</h2>
    <p>{description}</p>
    {actions && <div className="jl-inline">{actions}</div>}
  </Panel>;
}

export function ActionFeedback({tone = "info", children}: {tone?: Tone; children: ReactNode}) {
  return <Callout role={tone === "danger" ? "alert" : "status"} tone={tone}>{children}</Callout>;
}
