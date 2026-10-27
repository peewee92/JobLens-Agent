import {NextResponse} from "next/server";

import {backendProxyResponse as backendResponse} from "@/lib/backend";

export async function POST(
  request: Request,
  {params}: {params: Promise<{threadId: string}>},
) {
  const {threadId} = await params;
  const response = await backendResponse(
    `/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/continue`,
    {method: "POST", headers: {"Content-Type": "application/json"}, body: (await request.text()) || undefined},
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}
