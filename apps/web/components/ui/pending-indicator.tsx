"use client";

import {useEffect, useState} from "react";

export function PendingIndicator({label = "正在读取内容…", slowLabel = "比平时慢一些，仍在读取。", skeleton = false}: {
  label?: string; slowLabel?: string; skeleton?: boolean;
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 3000);
    return () => clearTimeout(timer);
  }, []);

  return <div className="jl-pending" role="status">
    <p>{label}</p>
    {slow && <p>{slowLabel}</p>}
    {skeleton && <div className="jl-route-skeleton" aria-hidden="true">
      <i /><i /><i /><i />
    </div>}
  </div>;
}
