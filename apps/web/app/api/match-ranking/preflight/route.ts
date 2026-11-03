import {NextResponse} from "next/server";
import {backendResponse} from "@/lib/backend";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const params = new URLSearchParams();
  for (const id of incoming.searchParams.getAll("jobId")) params.append("jobId", id);
  const response = await backendResponse(`/api/v1/match-ranking/preflight?${params}`, {method: "GET"});
  return new NextResponse(await response.text(), {status: response.status, headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"}});
}
