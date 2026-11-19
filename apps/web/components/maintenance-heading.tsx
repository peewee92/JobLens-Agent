import Link from "next/link";
import type {ReactNode} from "react";
import {Button} from "./ui/button";
import {PageHeading} from "./ui/patterns";

export function MaintenanceHeading({title, description, returnTo, children}: {
  title: string;
  description: string;
  returnTo: "profile" | "jobs";
  children?: ReactNode;
}) {
  return <div className="jl-maintenance-heading stack-sm">
    <PageHeading kicker="仅供维护与测试 · 求职流程无需操作" title={title} description={description} />
    <div className="jl-inline">
      <Button variant="secondary" asChild>
        {returnTo === "profile" ? <Link href="/profile">去核对我的简历资料</Link> : <Link href="/jobs">返回我的岗位</Link>}
      </Button>
      <Button variant="subtle" asChild><Link href="/quality">查看维护工具</Link></Button>
      {children}
    </div>
  </div>;
}
