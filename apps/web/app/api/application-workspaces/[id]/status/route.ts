import {NextResponse} from "next/server";

import {backendProxyResponse} from "@/lib/backend";

export async function POST(
  request: Request,
  {params}: {params: Promise<{id: string}>},
) {
  const {id} = await params;
  const response = await backendProxyResponse(
    `/api/v1/application-workspaces/${encodeURIComponent(id)}/status`,
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
