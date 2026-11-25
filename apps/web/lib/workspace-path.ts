export const PRIVATE_WORKSPACE_PATH = "/private";

// A separate Next build owns the whole path. The public demo build never handles its API calls.
export const isPrivateWorkspaceBuild = () => process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD === "1";

export function workspacePath(path: string): string {
  if (!isPrivateWorkspaceBuild() || !path.startsWith("/") || path.startsWith("//") ||
    path === PRIVATE_WORKSPACE_PATH || path.startsWith(`${PRIVATE_WORKSPACE_PATH}/`)) return path;
  return path === "/" ? PRIVATE_WORKSPACE_PATH : PRIVATE_WORKSPACE_PATH + path;
}

/** Browser API calls are scoped by the build, not the URL/cookie in another tab. */
export function workspaceFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(workspacePath(path), init);
}

export function hostingOrigin(value: string | undefined): string | null {
  try {
    const url = new URL(value ?? "");
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/") return null;
    return url.protocol === "https:" || (url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname))
      ? url.origin : null;
  } catch { return null; }
}

export function publicEntryHref(origin = process.env.JOBLENS_PUBLIC_ENTRY_ORIGIN): string {
  const publicOrigin = hostingOrigin(origin);
  return publicOrigin ? `${publicOrigin}/` : "/";
}

export function privateWorkspaceRewrites(upstream: string) {
  const root = PRIVATE_WORKSPACE_PATH;
  return [
    // An optional catch-all sometimes forwards the bare path as /private/ on Vercel.
    // That upstream canonical redirect would point back to the original gateway URL.
    {source: root, destination: `${upstream}${root}`},
    {source: `${root}/:path+`, destination: `${upstream}${root}/:path+`},
  ];
}
