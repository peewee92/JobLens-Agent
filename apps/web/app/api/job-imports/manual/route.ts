import {backendProxyResponse} from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  let payload: unknown;
  try { payload = await request.json(); }
  catch {
    return Response.json({error: {code: "request_validation_error", message: "请提交有效的岗位内容。"}}, {status: 422});
  }
  const response = await backendProxyResponse("/api/v1/job-imports/manual", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
  });
  return new Response(await response.text(), {status: response.status, headers: {"Content-Type": "application/json"}});
}
