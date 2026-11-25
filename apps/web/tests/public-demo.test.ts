import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";
import test from "node:test";
import {NextRequest} from "next/server";
import {canStartAfterExpiredReset, demoBackendHeaders, demoOriginAllowed, demoSessionStateFromResponse, isDemoDestination} from "../lib/public-demo";
import {releaseVersionLabel} from "../lib/release-version";
import {proxy} from "../proxy";

const root = resolve(import.meta.dirname, "..");
test("public demo write origins are exact and fail closed", () => {
  assert.equal(demoOriginAllowed(null, "https://demo.example"), false);
  assert.equal(demoOriginAllowed("https://evil.example", "https://demo.example"), false);
  assert.equal(demoOriginAllowed("https://demo.example", "https://demo.example"), true);
});
test("a visitor without a cookie can reach only the exact BYOK status GET before creating a session", () => {
  const saved = {...process.env};
  try {
    const origin = "https://demo.example";
    process.env.JOBLENS_PUBLIC_DEMO = "1";
    process.env.JOBLENS_DEMO_FRONTEND_ORIGIN = origin;
    delete process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD;
    const status = "/api/byok/model-connection";
    const request = (path: string, method = "GET") => proxy(new NextRequest(origin + path, {method, headers: {origin}}));
    assert.equal(request(status).headers.get("x-middleware-next"), "1");
    for (const [path, method] of [[status, "PUT"], [status, "DELETE"], [status + "/test-plan", "GET"],
      [status + "/test", "POST"], ["/api/byok/session-export", "GET"]]) {
      assert.equal(request(path, method).status, 410);
    }
  } finally {process.env = saved;}
});
test("legacy page only redirects reads and only the new public session route can start without a cookie", () => {
  const saved = {...process.env};
  const origin = "https://joblens.example";
  try {
    process.env.JOBLENS_PUBLIC_DEMO = "1";
    process.env.JOBLENS_DEMO_FRONTEND_ORIGIN = origin;
    delete process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD;
    const request = (path: string, method = "GET", from = origin, cookie = "") =>
      proxy(new NextRequest(origin + path, {method, headers: {origin: from, cookie}}));
    for (const method of ["GET", "HEAD"]) {
      const result = request("/demo?source=resume&lang=zh", method);
      assert.equal(result.status, 308);
      assert.equal(result.headers.get("location"), origin + "/?source=resume&lang=zh");
      assert.equal(result.headers.get("set-cookie"), null);
    }
    for (const path of ["/", "/sample", "/connect"]) {
      assert.equal(request(path).headers.get("x-middleware-next"), "1", path);
    }
    assert.equal(request("/demo", "POST").status, 404);
    assert.equal(request("/api/public-session", "POST").headers.get("x-middleware-next"), "1");
    assert.equal(request("/api/public-session", "POST", "https://other.example").status, 403);
    for (const old of ["/api/demo/session", "/api/byok/demo/session"]) assert.equal(request(old, "POST").status, 410);
    assert.equal(request("/jobs/private-id").headers.get("location"), origin + "/");
    assert.equal(request("/quality", "GET", origin, "joblens_demo_session=opaque").headers.get("location"), origin + "/");
    delete process.env.JOBLENS_PUBLIC_DEMO;
    assert.equal(request("/demo").status, 308);
    process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD = "1";
    process.env.JOBLENS_CLOUD_FRONTEND_ORIGIN = origin;
    assert.equal(request("/demo").status, 404);
  } finally {process.env = saved;}
});
test("footer shows only the release number, or the local development label", () => {
  assert.equal(releaseVersionLabel("0.2.1-preview+b510bc3", false), "v0.2.1");
  assert.equal(releaseVersionLabel(" v1.2.3-rc.2+build.10 ", false), "v1.2.3");
  assert.equal(releaseVersionLabel("2.0.0", false), "v2.0.0");
  for (const missing of [undefined, "", "b510bc3", "v1.2", "1.2.0+"]) {
    assert.equal(releaseVersionLabel(missing, false), null);
    assert.equal(releaseVersionLabel(missing, true), "本地开发");
  }
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
  const source = await readFile(resolve(root, "app/api/public-session/route.ts"), "utf8");
  for (const text of ["httpOnly: true", 'sameSite: "lax"', 'process.env.NODE_ENV === "production"', 'current ? "DELETE" : "POST"']) assert.ok(source.includes(text));
  assert.doesNotMatch(source, /NextResponse\.json\(\{[^}]*sessionToken/);
  const start = await readFile(resolve(root, "components/demo-start.tsx"), "utf8");
  assert.doesNotMatch(start, /JOBLENS_DEMO_PROXY_SECRET|setInterval|sessionToken/);
  const proxyRoute = await readFile(resolve(root, "app/api/byok/[...path]/route.ts"), "utf8");
  assert.doesNotMatch(proxyRoute, /demo\\\/session|public-session/);
});

test("only top-level previews are available without a demo session", () => {
  for (const path of ["/", "/profile", "/jobs", "/applications"]) assert.equal(isDemoDestination(path), true, path);
  for (const path of ["/api/jobs", "/jobs/private-id", "/applications/private-id", "/evals/profile", "/profile/"]) {
    assert.equal(isDemoDestination(path), false, path);
  }
});

test("expired sessions are distinct from temporary read errors and invalid replies", () => {
  assert.deepEqual(demoSessionStateFromResponse(410), {status: "expired"});
  for (const status of [429, 500, 503, 504]) assert.deepEqual(demoSessionStateFromResponse(status), {status: "unavailable"});
  assert.deepEqual(demoSessionStateFromResponse(200, {active: true, mode: "unknown"}), {status: "unavailable"});
  assert.deepEqual(demoSessionStateFromResponse(200, {active: true, mode: "sample", synthetic: true}),
    {status: "active", session: {mode: "sample", synthetic: true}});
});

test("start can replace an expired cookie only after definitive no-write evidence", () => {
  const expired = {error: {code: "demo_session_expired"}};
  assert.equal(canStartAfterExpiredReset(true, 410, expired), true);
  assert.equal(canStartAfterExpiredReset(false, 410, expired), false);
  assert.equal(canStartAfterExpiredReset(true, 410, {error: {code: "different"}}), false);
  for (const status of [408, 429, 500, 502, 503, 504]) assert.equal(canStartAfterExpiredReset(true, status, expired), false);
});
