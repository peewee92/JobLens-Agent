"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

export function NavLink({href, children}: {href: string; children: React.ReactNode}) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link href={href} aria-current={active ? "page" : undefined}>
      {children}
    </Link>
  );
}
