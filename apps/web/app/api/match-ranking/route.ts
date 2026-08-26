import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const params = new URLSearchParams();

  for (const jobId of incoming.searchParams.getAll("jobId")) {
    params.append("jobId", jobId);
  }
  const includeBlocked = incoming.searchParams.get("includeBlocked");
  if (includeBlocked !== null) {
    params.set("includeBlocked", includeBlocked);
  }
  const topN = incoming.searchParams.get("topN");
  if (topN !== null) {
    params.set("topN", topN);
  }

  const query = params.toString();
  const response = await backendResponse(
    `/api/v1/match-ranking${query ? `?${query}` : ""}`,
    {method: "GET"},
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
