import {NextRequest, NextResponse} from "next/server";
import {DEMO_COOKIE, demoOriginAllowed, isDemoDestination, publicDemoEnabled} from "@/lib/public-demo";
import {WORKSPACE_SESSION_COOKIE} from "@/lib/cloud-api-identity";
import {hostingOrigin, isPrivateWorkspaceBuild, PRIVATE_WORKSPACE_PATH, workspacePath} from "@/lib/workspace-path";
import {PRIVATE_SIGN_IN_HEADER, privateResponseHeaders, privateRouteKind} from "@/lib/private-routing";

function privateProxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const kind = privateRouteKind(path);
  const headers = privateResponseHeaders();
  const origin = hostingOrigin(process.env.JOBLENS_CLOUD_FRONTEND_ORIGIN);
  if (!origin || kind === "blocked") return new NextResponse(null, {status: 404, headers});
  if (!["GET", "HEAD"].includes(request.method) && request.headers.get("origin") !== origin) {
    return NextResponse.json({error: {code: "workspace_origin_rejected", message: "请在 JobLens 个人工作台中重新操作。"}}, {status: 403, headers});
  }
  // This is just an early navigation check. Only a server-verified account can read or modify the database.
  if (kind !== "sign-in" && kind !== "session" && !request.cookies.has(WORKSPACE_SESSION_COOKIE)) {
    if (kind === "api") return NextResponse.json({error: {code: "workspace_sign_in_required", message: "请先登录个人工作台。"}}, {status: 401, headers});
    return NextResponse.redirect(new URL(workspacePath("/sign-in"), origin), {headers});
  }
  const forwarded = new Headers(request.headers);
  forwarded.delete(PRIVATE_SIGN_IN_HEADER);
  if (kind === "sign-in") forwarded.set(PRIVATE_SIGN_IN_HEADER, "1");
  return NextResponse.next({request: {headers: forwarded}, headers});
}

export function proxy(request: NextRequest) {
  if (isPrivateWorkspaceBuild()) return privateProxy(request);
  const path = request.nextUrl.pathname;
  if ((path === PRIVATE_WORKSPACE_PATH || path.startsWith(`${PRIVATE_WORKSPACE_PATH}/`)) &&
      hostingOrigin(process.env.JOBLENS_PRIVATE_UPSTREAM_URL)) return NextResponse.next();
  if (!publicDemoEnabled()) return NextResponse.next();
  if (!["GET", "HEAD"].includes(request.method) &&
      !demoOriginAllowed(request.headers.get("origin"), process.env.JOBLENS_DEMO_FRONTEND_ORIGIN)) {
    return NextResponse.json({error: {code: "demo_origin_rejected", message: "请求来源无效。"}}, {status: 403});
  }
  if (path === "/connect" || path === "/demo" || path === "/api/demo/session" || isDemoDestination(path)) return NextResponse.next();
  if (!request.cookies.get(DEMO_COOKIE)?.value) {
    if (path.startsWith("/api/")) return NextResponse.json({error: {code: "demo_session_expired", message: "演示已结束，请重新开始样本体验。"}}, {status: 410});
    return NextResponse.redirect(new URL("/demo", request.url));
  }
  // Public visitors cannot upload private files or access administration screens.
  if (/^\/(?:evals|quality|import)(?:\/|$)/.test(path)) return NextResponse.redirect(new URL("/demo", request.url));
  return NextResponse.next();
}

// The explicit root also matches the bare /private base path (with no trailing slash).
export const config = {matcher: ["/", "/((?!_next/static|_next/image|favicon.ico).*)"]};
