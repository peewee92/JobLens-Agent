import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: Request,
  {params}: {params: Promise<{id: string; variantId: string}>},
) {
  const {id, variantId} = await params;
  const response = await backendResponse(
    `/api/v1/application-workspaces/${encodeURIComponent(id)}/resume-variants/${encodeURIComponent(variantId)}/review`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: await request.text(),
    },
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}
