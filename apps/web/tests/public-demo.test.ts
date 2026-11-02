import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";
import test from "node:test";
import {demoBackendHeaders, demoOriginAllowed} from "../lib/public-demo";

const root = resolve(import.meta.dirname, "..");
test("public demo write origins are exact and fail closed", () => {
  assert.equal(demoOriginAllowed(null, "https://demo.example"), false);
  assert.equal(demoOriginAllowed("https://evil.example", "https://demo.example"), false);
  assert.equal(demoOriginAllowed("https://demo.example", "https://demo.example"), true);
});
test("public demo credentials are server configuration and missing settings fail closed", () => {
  const saved = {...process.env};
  try {
    delete process.env.JOBLENS_DEMO_PROXY_SECRET;
    assert.throws(() => demoBackendHeaders("token"));
    process.env.JOBLENS_DEMO_PROXY_SECRET = "a".repeat(32);
    process.env.JOBLENS_DEMO_FRONTEND_ORIGIN = "https://demo.example";
    assert.equal(demoBackendHeaders("token")["X-Demo-Session"], "token");
  } finally {process.env = saved;}
});
test("session is HttpOnly, reset is explicit and token is never returned to client JavaScript", async () => {
  const source = await readFile(resolve(root, "app/api/demo/session/route.ts"), "utf8");
  for (const text of ["httpOnly: true", 'sameSite: "lax"', 'process.env.NODE_ENV === "production"', 'token ? "DELETE" : "POST"']) assert.ok(source.includes(text));
  assert.doesNotMatch(source, /NextResponse\.json\(\{[^}]*sessionToken/);
  const start = await readFile(resolve(root, "components/demo-start.tsx"), "utf8");
  assert.doesNotMatch(start, /JOBLENS_DEMO_PROXY_SECRET|setInterval|sessionToken/);
});
