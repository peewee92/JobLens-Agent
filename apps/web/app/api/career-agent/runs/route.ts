import {NextResponse} from "next/server";

import {backendProxyResponse as backendResponse} from "@/lib/backend";

export async function POST(request: Request) {
  const body = await request.text();
  const response = await backendResponse("/api/v1/career-agent/runs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body,
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}


export async function GET(request: Request) {
  const limit = new URL(request.url).searchParams.get("limit") ?? "10";
  const response = await backendResponse(`/api/v1/career-agent/runs?${new URLSearchParams({limit})}`, {
    method: "GET", cache: "no-store",
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"},
  });
}
