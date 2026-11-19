import {createHmac} from "node:crypto";

export const WORKSPACE_SESSION_COOKIE = "__Secure-neon-auth.session_token";
export const validCloudOwner = (id: unknown): id is string => typeof id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(id);

export function cloudIdentityHeaders(secret: string, owner: string, method: string, target: string, now = Date.now()) {
  if (secret.length < 32 || !validCloudOwner(owner) || !/^[A-Z]+$/.test(method) ||
    !target.startsWith("/api/v1/") || !/^[!-~]+$/.test(target)) throw new Error("Invalid private workspace forwarding configuration");
  const issued = String(Math.floor(now / 1000));
  const message = ["joblens-private-workspace/v1", owner, issued, method, target].join("\n");
  return {
    "X-Joblens-Owner": owner,
    "X-Joblens-Issued": issued,
    "X-Joblens-Workspace-Signature": createHmac("sha256", secret).update(message, "ascii").digest("hex"),
  };
}
