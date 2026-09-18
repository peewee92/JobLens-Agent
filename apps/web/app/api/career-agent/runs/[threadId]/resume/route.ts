import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: Request,
  {params}: {params: Promise<{threadId: string}>},
) {
  const {threadId} = await params;
  const body = await request.text();
  const response = await backendResponse(
    `/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/resume`,
    {method: "POST", headers: {"Content-Type": "application/json"}, body},
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}
