import assert from "node:assert/strict";
import test from "node:test";
import {cloudIdentityHeaders} from "../lib/cloud-api-identity";
import {privateRouteKind} from "../lib/private-routing";
import {parseWorkspaceSignIn, workspaceCodeRecipients} from "../lib/private-sign-in";
import {hostingOrigin, privateWorkspaceRewrites, publicDemoHref, workspacePath} from "../lib/workspace-path";

test("the independent build preserves route, query and anchor without absorbing public or external links", () => {
  const previous = process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD;
  try {
    delete process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD;
    assert.equal(workspacePath("/profile"), "/profile");
    process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD = "1";
    assert.equal(workspacePath("/"), "/private");
    assert.equal(workspacePath("/jobs?sort=latest#job-list"), "/private/jobs?sort=latest#job-list");
    assert.equal(workspacePath("/api/profile"), "/private/api/profile");
    assert.equal(workspacePath("/private/jobs"), "/private/jobs");
    assert.equal(workspacePath("#job-list"), "#job-list");
    assert.equal(workspacePath("https://example.com/job"), "https://example.com/job");
    assert.equal(workspacePath("//example.com/job"), "//example.com/job");
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD;
    else process.env.NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD = previous;
  }
});

test("the gateway forwards the bare private root without a trailing slash and handles child paths separately", () => {
  assert.deepEqual(privateWorkspaceRewrites("https://private.example.com"), [
    {source: "/private", destination: "https://private.example.com/private"},
    {source: "/private/:path+", destination: "https://private.example.com/private/:path+"},
  ]);
});

test("individual work surfaces do not expose demo endpoints, model secrets or maintenance", () => {
  for (const path of ["/", "/jobs/one", "/applications/one", "/profile", "/agent/results/run", "/import"]) assert.equal(privateRouteKind(path), "page");
  for (const path of ["/demo", "/connect", "/quality", "/evals/profile", "/api/demo/session", "/api/byok/model-connection", "/api/local/profile-model/status"]) assert.equal(privateRouteKind(path), "blocked");
  assert.equal(privateRouteKind("/api/profile"), "api");
  assert.equal(privateRouteKind("/api/workspace-session"), "session");
  assert.equal(privateRouteKind("/sign-in"), "sign-in");
  assert.equal(hostingOrigin("https://user:secret@cloud.example.com"), null);
  assert.equal(hostingOrigin("http://cloud.example.com"), null);
  assert.equal(hostingOrigin("https://cloud.example.com/private"), null);
  assert.equal(hostingOrigin("http://localhost:3230"), "http://localhost:3230");
  assert.equal(publicDemoHref("https://joblens.example.com"), "https://joblens.example.com/demo");
  assert.equal(publicDemoHref("https://joblens.example.com/not-a-site-root"), "/demo");
});

test("tenant forwarding matches the FastAPI HMAC and binds method and query", () => {
  const secret = "local-signature-contract-fixed-test-only";
  const path = "/api/v1/jobs?offset=0&limit=20";
  const now = 1795076000000;
  const expected = "d8e55e6a4b7f95031007a99b53327c4cbec36787afe44a886997312ff387c6d8";
  const make = (method: string, target: string) => cloudIdentityHeaders(secret, "test-account-1", method, target, now);
  assert.equal(make("GET", path)["X-Joblens-Workspace-Signature"], expected);
  assert.notEqual(make("POST", path)["X-Joblens-Workspace-Signature"], expected);
  assert.notEqual(make("GET", path + "&owner=another")["X-Joblens-Workspace-Signature"], expected);
  assert.throws(() => make("GET", "/api/v1/jobs\ntest"));
});

test("the invited email-code path accepts fixed length text with leading zeros and does not parse registration", () => {
  const email = "pilot@example.com";
  const recipients = workspaceCodeRecipients(" , PILOT@example.com ,invalid,pilot@example.com, next@example.com");
  assert.deepEqual([...recipients], [email, "next@example.com"]);
  assert.deepEqual([...workspaceCodeRecipients(undefined)], []);
  assert.deepEqual(parseWorkspaceSignIn({mode: "send-code", email: "  PILOT@example.com", ownerId: "not-trusted"}), {mode: "send-code", email});
  assert.deepEqual(parseWorkspaceSignIn({mode: "verify-code", email, code: "009912"}), {mode: "verify-code", email, code: "009912"});
  assert.deepEqual(parseWorkspaceSignIn({email, password: "unchanged secret"}), {mode: "password", email, password: "unchanged secret"});
  for (const input of [{mode: "sign-up", email}, {mode: "verify-code", email, code: 123456},
    {mode: "verify-code", email, code: "A23456"}, {mode: "send-code", email: "a@@example.com"}, null]) {
    assert.equal(parseWorkspaceSignIn(input), null);
  }
});
