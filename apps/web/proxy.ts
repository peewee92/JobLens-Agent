import {NextRequest, NextResponse} from "next/server";
import {DEMO_COOKIE, demoOriginAllowed, publicDemoEnabled} from "@/lib/public-demo";

export function proxy(request: NextRequest) {
  if (!publicDemoEnabled()) return NextResponse.next();
  const path = request.nextUrl.pathname;
  if (!["GET", "HEAD"].includes(request.method) &&
      !demoOriginAllowed(request.headers.get("origin"), process.env.JOBLENS_DEMO_FRONTEND_ORIGIN)) {
    return NextResponse.json({error: {code: "demo_origin_rejected", message: "请求来源无效。"}}, {status: 403});
  }
  if (path === "/connect" || path === "/demo" || path === "/api/demo/session") return NextResponse.next();
  if (!request.cookies.get(DEMO_COOKIE)?.value) {
    if (path.startsWith("/api/")) return NextResponse.json({error: {code: "demo_session_expired", message: "演示已结束，请重新开始样本体验。"}}, {status: 410});
    return NextResponse.redirect(new URL("/demo", request.url));
  }
  // Public visitors cannot upload private files or access administration screens.
  if (/^\/(?:evals|quality|import)(?:\/|$)/.test(path)) return NextResponse.redirect(new URL("/demo", request.url));
  return NextResponse.next();
}

export const config = {matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]};
