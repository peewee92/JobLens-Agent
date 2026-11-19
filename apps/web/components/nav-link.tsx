"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

export function NavLink({href, children, fresh = false}: {href: string; children: React.ReactNode; fresh?: boolean}) {
  const pathname = usePathname();
  const matches = (path: string) => pathname === path || pathname.startsWith(path + "/");
  const active = pathname === href || (href !== "/" && matches(href)) ||
    (href === "/jobs" && ["/import", "/imports", "/agent", "/recommendations"].some(matches));
  // Mutations can complete through route handlers while a previous workbench is cached in the router.
  if (href === "/" || fresh) return <a href={href} aria-current={active ? "page" : undefined}>{children}</a>;
  return (
    <Link href={href} aria-current={active ? "page" : undefined}>
      {children}
    </Link>
  );
}
