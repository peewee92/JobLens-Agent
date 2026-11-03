import {backendProxyResponse} from "@/lib/backend";
// This is not an arbitrary backend proxy; both layers deny unlisted operations.
const allowed = /^(?:model-connection(?:\/test(?:-plan)?)?|profile-call-plan|profile-calls(?:\/[A-Za-z0-9_-]{1,100})?|session-export|demo\/session)$/;
async function forward(request: Request, {params}: {params: Promise<{path: string[]}>}) {
  const path = (await params).path.join("/");
  if (!allowed.test(path)) return new Response(null, {status: 404});
  return backendProxyResponse(`/api/v1/${path}`, {
    method: request.method, headers: {"Content-Type": "application/json"},
    ...(["GET", "HEAD"].includes(request.method) ? {} : {body: await request.text()}),
    signal: AbortSignal.timeout(70000),
  });
}
export {forward as GET, forward as POST, forward as PUT, forward as DELETE};
