"use client";

import {useRouter} from "next/navigation";
import {useTransition} from "react";
import {Button} from "./button";
import {PendingIndicator} from "./pending-indicator";

export function ReadRetry({reset}: {reset?: () => void}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return <div className="stack-sm">
    <div className="jl-inline">
      <Button onClick={() => startTransition(() => { router.refresh(); reset?.(); })} disabled={pending}>
        {pending ? "正在重新读取…" : "重新读取当前页面"}
      </Button>
    </div>
    {pending && <PendingIndicator label="正在读取本页，不会重复提交。" />}
  </div>;
}
