import {NextRequest, NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: NextRequest,
  {params}: {params: Promise<{runId: string}>},
) {
  const {runId} = await params;
  const body = await request.text();
  const response = await backendResponse(
    `/api/v1/requirement-acceptance-runs/${encodeURIComponent(runId)}/canary-review`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body,
    },
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
