export const PRIVATE_SIGN_IN_HEADER = "x-joblens-private-sign-in-page";
const pageRoots = new Set(["", "profile", "jobs", "import", "imports", "agent", "recommendations", "applications", "gaps"]);
const apiRoots = new Set([
  "workspace-session", "profile", "profile-proposals", "search-intent", "jobs", "job-imports", "career-agent",
  "match-batch", "match-ranking", "application-workspaces", "user-feedback", "target-cohort", "requirement-batch",
]);

/** Exclude demo, model credentials, and maintenance from the private web surface. */
export function privateRouteKind(path: string): "api" | "page" | "session" | "sign-in" | "blocked" {
  if (path === "/api/workspace-session") return "session";
  if (path === "/sign-in") return "sign-in";
  const [, root, endpoint] = path.split("/");
  if (root === "api") return endpoint && endpoint !== "workspace-session" && apiRoots.has(endpoint) ? "api" : "blocked";
  return pageRoots.has(root) ? "page" : "blocked";
}

export function privateResponseHeaders() {
  return {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "same-origin"};
}
