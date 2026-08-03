import {NextRequest, NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: NextRequest,
  {params}: {params: Promise<{id: string}>},
) {
  const {id} = await params;
  const body = await request.text();
  const response = await backendResponse(
    `/api/v1/profile-evals/${encodeURIComponent(id)}/review`,
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
