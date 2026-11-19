import "server-only";
import {cache} from "react";
import {cookies} from "next/headers";
import {backendResponse} from "@/lib/backend";
import {DEMO_COOKIE, demoSessionStateFromResponse, publicDemoEnabled, type DemoSessionState} from "@/lib/public-demo";

export const publicSessionState = cache(async function publicSessionState(): Promise<DemoSessionState> {
  if (!publicDemoEnabled() || !(await cookies()).get(DEMO_COOKIE)?.value) return {status: "not-started"};
  try {
    const response = await backendResponse("/api/v1/demo/session");
    return demoSessionStateFromResponse(response.status, response.ok ? await response.json() : null);
  } catch {
    return {status: "unavailable"};
  }
});

export async function publicSession() {
  const state = await publicSessionState();
  return state.status === "active" ? state.session : null;
}
