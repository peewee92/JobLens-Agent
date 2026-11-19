import type {ReactNode} from "react";

export default function EvaluationLayout({children}: {children: ReactNode}) {
  return <div className="jl-section-stack jl-maintenance">{children}</div>;
}
