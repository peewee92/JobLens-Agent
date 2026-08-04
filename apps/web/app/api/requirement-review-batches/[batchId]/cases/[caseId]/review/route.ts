import {NextRequest, NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: NextRequest,
  {params}: {params: Promise<{batchId: string; caseId: string}>},
) {
  const {batchId, caseId} = await params;
  const body = await request.text();
  const response = await backendResponse(
    `/api/v1/requirement-review-batches/${encodeURIComponent(batchId)}/cases/${encodeURIComponent(caseId)}/review`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body,
    },
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}
