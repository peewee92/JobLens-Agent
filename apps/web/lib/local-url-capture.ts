function loopback(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) &&
      !url.username && !url.password && !url.search && !url.hash && url.pathname === "/" ? url : null;
  } catch { return null; }
}

/** Server-side feature gate and the one permitted browser origin. */
export function localUrlCaptureOrigin(env: Record<string, string | undefined> = process.env): URL | null {
  if (env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD === "1" || env.JOBLENS_PUBLIC_DEMO === "1" || env.JOBLENS_DEMO === "1" ||
      (env.APP_ENV && !["local", "development"].includes(env.APP_ENV)) ||
      (env.JOBLENS_LOCAL_PRODUCT !== "1" && env.JOBLENS_URL_CAPTURE !== "1") ||
      !loopback(env.JOBLENS_BACKEND_URL ?? "http://127.0.0.1:8000")) return null;
  return loopback(env.WEB_BASE_URL ?? "http://localhost:3000");
}

export function permitsLocalCaptureRequest(request: Request, local: URL | null): boolean {
  return !!local && request.headers.get("origin") === local.origin &&
    request.headers.get("host") === local.host;
}
