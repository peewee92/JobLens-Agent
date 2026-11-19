/** Public deployment configuration is server-only; never serialize its secret. */
export const DEMO_COOKIE = "joblens_demo_session";
export const publicDemoEnabled = () => process.env.JOBLENS_PUBLIC_DEMO === "1";

export function demoOriginAllowed(origin: string | null, expected: string | undefined): boolean {
  return Boolean(origin && expected && origin === expected);
}

export function demoBackendHeaders(token: string | undefined): Record<string, string> {
  const secret = process.env.JOBLENS_DEMO_PROXY_SECRET;
  const origin = process.env.JOBLENS_DEMO_FRONTEND_ORIGIN;
  if (!secret || secret.length < 32 || !origin) throw new Error("公开演示代理配置不完整。");
  return {"X-Joblens-Proxy": secret, "X-Demo-Session": token ?? "", Origin: origin};
}

export const DEMO_DESTINATIONS = ["/", "/profile", "/jobs", "/applications"] as const;
export type DemoDestination = typeof DEMO_DESTINATIONS[number];
export const isDemoDestination = (path: string): path is DemoDestination =>
  DEMO_DESTINATIONS.some(destination => destination === path);

export type DemoInactiveState = "not-started" | "expired" | "unavailable";
export type DemoSession = {mode: "sample" | "byok"; synthetic: boolean};
export type DemoSessionState = {status: DemoInactiveState} | {status: "active"; session: DemoSession};
export function demoSessionStateFromResponse(status: number, payload?: unknown): DemoSessionState {
  if (status === 410) return {status: "expired"};
  if (status === 200 && typeof payload === "object" && payload !== null && "active" in payload &&
    payload.active === true && "mode" in payload && (payload.mode === "sample" || payload.mode === "byok") &&
    "synthetic" in payload && typeof payload.synthetic === "boolean") {
    return {status: "active", session: {mode: payload.mode, synthetic: payload.synthetic}};
  }
  return {status: "unavailable"};
}

export function canStartAfterExpiredReset(hadCookie: boolean, status: number, payload: unknown) {
  return hadCookie && status === 410 && typeof payload === "object" && payload !== null &&
    "error" in payload && typeof payload.error === "object" && payload.error !== null &&
    "code" in payload.error && payload.error.code === "demo_session_expired";
}
