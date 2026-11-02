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
