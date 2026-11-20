import {backendProxyResponse} from "@/lib/backend";
import {localUrlCaptureOrigin, permitsLocalCaptureRequest} from "@/lib/local-url-capture";

export const dynamic = "force-dynamic";

function error(status: number, code: string, message: string) {
  return Response.json({error: {code, message}}, {status, headers: {"Cache-Control": "no-store"}});
}

export async function POST(request: Request): Promise<Response> {
  if (!permitsLocalCaptureRequest(request, localUrlCaptureOrigin())) {
    return error(403, "url_capture_forbidden", "岗位链接抓取仅在本机开放。");
  }
  if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return error(422, "request_validation_error", "请提交有效的公开岗位链接。");
  }
  let payload: unknown;
  try { payload = await request.json(); }
  catch { return error(422, "request_validation_error", "请提交有效的公开岗位链接。"); }
  const response = await backendProxyResponse("/api/v1/job-imports/url-capture", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
    signal: AbortSignal.any([request.signal, AbortSignal.timeout(27_000)]),
    redirect: "error",
  });
  return new Response(response.body, {
    status: response.status,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}
