import {backendProxyResponse} from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(request: Request, {params}: {params: Promise<{id: string}>}): Promise<Response> {
  let body: unknown;
  try { body = await request.json(); }
  catch { return Response.json({error: {code: "request_validation_error", message: "请提交有效的确认请求。"}}, {status: 422}); }
  const {id} = await params;
  const response = await backendProxyResponse(`/api/v1/jobs/${encodeURIComponent(id)}/requirement-confirmations`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  return new Response(await response.text(), {status: response.status, headers: {"Content-Type": "application/json"}});
}
