"use client";

import {useEffect, useState} from "react";

type Theme = "pine" | "berry";

export function ThemeChoice() {
  const [theme, setTheme] = useState<Theme>("pine");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("joblens-color");
      if (saved === "berry") {
        document.documentElement.dataset.theme = saved;
        setTheme(saved);
      }
    } catch { /* The default theme is usable without browser storage. */ }
  }, []);

  function choose(next: Theme) {
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("joblens-color", next); } catch { /* theme applies to this page */ }
  }

  return <details className="jl-theme-choice" onKeyDown={event => {
    if (event.key !== "Escape" || !event.currentTarget.open) return;
    event.preventDefault();
    event.currentTarget.open = false;
    event.currentTarget.querySelector("summary")?.focus();
  }}>
    <summary aria-label="切换配色"><span aria-hidden="true" />配色</summary>
    <fieldset>
      <legend>页面配色</legend>
      <label><input type="radio" name="jl-theme" checked={theme === "pine"} onChange={() => choose("pine")} />暖纸白＋墨绿</label>
      <label><input type="radio" name="jl-theme" checked={theme === "berry"} onChange={() => choose("berry")} />燕麦白＋深莓红</label>
    </fieldset>
  </details>;
}
