import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

function forward(response: Response, body: string) {
  return new NextResponse(body, {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}

export async function POST(request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  const response = await backendResponse(`/api/v1/application-workspaces/${encodeURIComponent(id)}/actions`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: await request.text(),
  });
  return forward(response, await response.text());
}
