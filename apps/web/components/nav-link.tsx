"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

export function NavLink({href, children}: {href: string; children: React.ReactNode}) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  // Mutations can complete through route handlers while a previous workbench is cached in the router.
  if (href === "/") return <a href={href} aria-current={active ? "page" : undefined}>{children}</a>;
  return (
    <Link href={href} aria-current={active ? "page" : undefined}>
      {children}
    </Link>
  );
}
