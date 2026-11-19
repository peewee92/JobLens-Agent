import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {backendBaseUrl} from "@/lib/backend";
import {canStartAfterExpiredReset, DEMO_COOKIE, demoBackendHeaders, demoOriginAllowed, publicDemoEnabled} from "@/lib/public-demo";

export async function POST(request: Request) {
  if (!publicDemoEnabled()) return new Response(null, {status: 404});
  if (!demoOriginAllowed(request.headers.get("origin"), process.env.JOBLENS_DEMO_FRONTEND_ORIGIN)) return new Response(null, {status: 403});
  const jar = await cookies();
  const token = jar.get(DEMO_COOKIE)?.value;
  try {
    // Vercel overwrites x-forwarded-for. Only the first trusted edge address is used;
    // the backend never accepts this identity without the service credential.
    const client = (request.headers.get("x-forwarded-for") ?? "local").split(",")[0].trim();
    const body = await request.text();
    const deadline = AbortSignal.timeout(57000);
    const requestSession = (current: string | undefined) => fetch(`${backendBaseUrl()}/api/v1/demo/session`, {
      method: current ? "DELETE" : "POST", cache: "no-store", signal: deadline,
      headers: {...demoBackendHeaders(current), "X-Demo-Client": client, "Content-Type": "application/json"}, body,
    });
    let response = await requestSession(token);
    let data = await response.json();
    // 410 + this exact backend code proves that reset never created or replaced a session.
    // The user explicitly clicked start. Never retry a timed-out or ambiguous write.
    if (canStartAfterExpiredReset(Boolean(token), response.status, data)) {
      jar.delete(DEMO_COOKIE);
      response = await requestSession(undefined);
      data = await response.json();
    }
    if (!response.ok) {
      if (response.status === 410) jar.delete(DEMO_COOKIE);
      return NextResponse.json(data, {status: response.status, headers: {"Cache-Control": "no-store"}});
    }
    if (typeof data.sessionToken !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(data.sessionToken)) {
      return NextResponse.json({error: {code: "demo_session_response_invalid", message: "未能确认演示是否已准备好，请稍后再试。"}}, {status: 502, headers: {"Cache-Control": "no-store"}});
    }
    jar.set(DEMO_COOKIE, data.sessionToken, {httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 7200});
    return NextResponse.json({active: true}, {headers: {"Cache-Control": "no-store"}});
  } catch {
    return NextResponse.json({error: {code: "demo_backend_waking", message: "演示服务可能正在唤醒，请稍后重试。不会自动重复创建会话。"}}, {status: 503});
  }
}
