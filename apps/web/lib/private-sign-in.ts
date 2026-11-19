const VALID_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalizeSignInEmail(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 254) return null;
  const normalized = value.trim().toLowerCase();
  return VALID_EMAIL.test(normalized) ? normalized : null;
}

export function workspaceCodeRecipients(config: string | undefined): ReadonlySet<string> {
  return new Set((config ?? "").split(",").flatMap(value => {
    const email = normalizeSignInEmail(value);
    return email ? [email] : [];
  }));
}

export type WorkspaceSignIn =
  | {mode: "password"; email: string; password: string}
  | {mode: "send-code"; email: string}
  | {mode: "verify-code"; email: string; code: string};

export function parseWorkspaceSignIn(data: unknown): WorkspaceSignIn | null {
  if (!data || typeof data !== "object" || !("email" in data)) return null;
  const email = normalizeSignInEmail(data.email);
  if (!email) return null;
  const mode = "mode" in data ? data.mode : "password";
  if (mode === "send-code") return {mode, email};
  if (mode === "verify-code" && "code" in data && typeof data.code === "string" && /^[0-9]{6}$/.test(data.code)) {
    return {mode, email, code: data.code};
  }
  if (mode === "password" && "password" in data && typeof data.password === "string" && data.password.length > 0 && data.password.length <= 128) {
    return {mode, email, password: data.password};
  }
  return null;
}
