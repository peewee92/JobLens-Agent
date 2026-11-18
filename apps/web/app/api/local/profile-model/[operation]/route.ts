import {backendResponse} from "@/lib/backend";
import {NextResponse} from "next/server";

export async function POST(request: Request, {params}: {params: Promise<{operation: string}>}) {
  const {operation} = await params;
  if (process.env.JOBLENS_LOCAL_PRODUCT !== "1" || !["plan", "file-plan", "calls"].includes(operation)) {
    return new Response(null, {status: 404});
  }
  const origin = request.headers.get("origin");
  const port = process.env.JOBLENS_LOCAL_WEB_PORT;
  // Next may normalize 127.0.0.1 to localhost in request.url; only allow our bound loopback port.
  if (origin && origin !== `http://127.0.0.1:${port}` && origin !== `http://localhost:${port}`) {
    return NextResponse.json({error: {message: "请从当前本地 JobLens 页面提交文件。"}}, {status: 403});
  }
  try {
    const type = request.headers.get("content-type") ?? "";
    if (operation === "file-plan" && !type.startsWith("multipart/form-data;")) {
      return NextResponse.json({error: {message: "请选择 PDF 或 DOCX。"}}, {status: 422});
    }
    if (operation !== "file-plan" && !type.startsWith("application/json")) {
      return new Response(null, {status: 415});
    }
    const body = new Uint8Array(await request.arrayBuffer());
    if (body.byteLength > (operation === "file-plan" ? 5 * 1024 * 1024 + 65536 : 256 * 1024)) {
      return NextResponse.json({error: {message: "文件或文本超过大小限制。"}}, {status: 413});
    }
    const response = await backendResponse(`/api/v1/local/profile-model/${operation}`, {
      method: "POST", headers: {"Content-Type": type}, body,
    });
    return new Response(await response.text(), {status: response.status, headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    }});
  } catch {
    return NextResponse.json({error: {message: "暂时无法读取服务响应，请不要重新授权。"}}, {status: 503});
  }
}
