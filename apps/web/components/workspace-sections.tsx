"use client";

import {useEffect, useRef, useSyncExternalStore, type KeyboardEvent, type ReactNode} from "react";

export const workspaceTabs = [
  ["resume", "简历"], ["interview", "面试"], ["actions", "行动"], ["evidence", "经历"],
] as const;
const sectionIcons = {
  resume: "M5 2h5l3 3v9H5z M10 2v4h3 M7 9h4m-4 2h4",
  interview: "M3 3h10v7H7l-3 3v-3H3z M5.5 6h5m-5 2h4",
  actions: "M6 4h7M6 8h7m-7 4h7 M3 4h.5M3 8h.5m-.5 4h.5",
  evidence: "M4 3h8v10H4z M6 6h4M6 8h4m-4 2h2",
};
type SectionId = (typeof workspaceTabs)[number][0];
const changeEvent = "joblens:workspace-section";
function subscribe(listener: () => void) {
  window.addEventListener("hashchange", listener);
  window.addEventListener("popstate", listener);
  window.addEventListener(changeEvent, listener);
  return () => {
    window.removeEventListener("hashchange", listener);
    window.removeEventListener("popstate", listener);
    window.removeEventListener(changeEvent, listener);
  };
}

export function WorkspaceSections({panels, recommended}: {panels: Record<SectionId, ReactNode>; recommended?: string}) {
  const fallback = workspaceTabs.find(([id]) => id === recommended)?.[0] ?? "resume";
  const active = useSyncExternalStore(subscribe, () => workspaceTabs.find(([id]) => `#${id}` === location.hash)?.[0] ?? fallback, () => fallback);
  const root = useRef<HTMLDivElement>(null);

  function select(id: SectionId) {
    if (location.hash !== `#${id}`) {
      history.pushState(null, "", `#${id}`);
      window.dispatchEvent(new Event(changeEvent));
    }
  }

  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const length = workspaceTabs.length;
    let target: number;
    switch (event.key) {
      case "ArrowLeft": target = (index - 1 + length) % length; break;
      case "ArrowRight": target = (index + 1) % length; break;
      case "Home": target = 0; break;
      case "End": target = length - 1; break;
      default: return;
    }
    event.preventDefault();
    const [id] = workspaceTabs[target];
    select(id);
    root.current?.querySelector<HTMLButtonElement>(`#workspace-tab-${id}`)?.focus();
  }

  // Direct anchors (including Next's links from other pages) should reach the open section.
  useEffect(() => {
    const reveal = () => {
      const id = location.hash.slice(1);
      if (!workspaceTabs.some(([key]) => key === id)) return;
      requestAnimationFrame(() => {
        const target = document.getElementById(id);
        if (target?.offsetParent !== null) {
          target?.scrollIntoView({behavior: "instant", block: "start"});
          root.current?.querySelector<HTMLElement>(`#workspace-panel-${id}`)?.focus({preventScroll: true});
        }
      });
    };
    window.addEventListener("hashchange", reveal);
    if (location.hash) reveal();
    return () => window.removeEventListener("hashchange", reveal);
  }, []);

  return <div className="jl-workspace-sections" ref={root}>
    <div role="tablist" aria-label="岗位准备类别" className="jl-workspace-tabs">
      {workspaceTabs.map(([id, title], index) => <button key={id} id={`workspace-tab-${id}`} role="tab"
        aria-controls={`workspace-panel-${id}`} aria-selected={id === active} type="button" tabIndex={id === active ? 0 : -1}
        onClick={() => select(id)} onKeyDown={event => navigate(event, index)}>
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"><path d={sectionIcons[id]} /></svg>
        {title}</button>)}
    </div>
    {workspaceTabs.map(([id]) => <div key={id} id={`workspace-panel-${id}`} role="tabpanel" aria-labelledby={`workspace-tab-${id}`}
      tabIndex={0} hidden={id !== active}>{panels[id]}</div>)}
  </div>;
}
