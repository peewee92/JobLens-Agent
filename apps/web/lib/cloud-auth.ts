import "server-only";
import {createAuthServer, extractNeonAuthCookies, resolveNeonAuthLogging} from "@neon/auth/server";
import {cookies, headers} from "next/headers";
import {cache} from "react";
import {validCloudOwner, WORKSPACE_SESSION_COOKIE} from "@/lib/cloud-api-identity";
import {hostingOrigin, isPrivateWorkspaceBuild, PRIVATE_WORKSPACE_PATH} from "@/lib/workspace-path";

export function workspaceAuth() {
  const baseUrl = process.env.NEON_AUTH_BASE_URL;
  const secret = process.env.NEON_AUTH_COOKIE_SECRET;
  const browserOrigin = hostingOrigin(process.env.JOBLENS_CLOUD_FRONTEND_ORIGIN);
  if (!isPrivateWorkspaceBuild() || !baseUrl || !browserOrigin || !secret || secret.length < 32) throw new Error("Private sign-in is not configured");
  const origin = new URL(baseUrl);
  if (origin.protocol !== "https:" || !origin.hostname.endsWith(".aws.neon.tech") ||
    !origin.hostname.includes(".neonauth.") || origin.username || origin.password || origin.search || origin.hash) {
    throw new Error("Invalid managed sign-in configuration");
  }
  return createAuthServer({baseUrl, cookieSecret: secret, sessionDataTtl: 15, sameSite: "strict",
    log: resolveNeonAuthLogging({logLevel: "silent"}),
    async context() {
      const incoming = await headers();
      const store = await cookies();
      return {
        getCookies: () => extractNeonAuthCookies(incoming),
        // The demo and other routes do not receive these cookies, even on the same hostname.
        setCookie: (name, value, options) => { store.set(name, value, {...options, domain: undefined, path: PRIVATE_WORKSPACE_PATH}); },
        getHeader: name => incoming.get(name),
        getOrigin: () => browserOrigin,
        getFramework: () => "nextjs",
      };
    },
  });
}

export const readWorkspaceOwner = cache(async (): Promise<string | null> => {
  if (!(await cookies()).has(WORKSPACE_SESSION_COOKIE)) return null;
  // Ask the managed server on this request; a cached cookie is not authority after session revocation.
  const auth = workspaceAuth();
  type SessionOptions = NonNullable<Parameters<typeof auth.getSession>[0]>;
  const {data, error} = await auth.getSession({query: {disableCookieCache: "true"}} as unknown as SessionOptions);
  if (error && ![401, 403].includes(error.status ?? 0)) throw new Error("Private sign-in is unavailable");
  return data?.session && validCloudOwner(data.user?.id) ? data.user.id : null;
});
